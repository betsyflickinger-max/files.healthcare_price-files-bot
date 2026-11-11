"""Hospital rows v2: re-parse hospital price files so every row also keeps the 2026 allowed-amount fields (Nov 11, 2026).

Plain-language guide: docs/hospital-rows-v2.md. Workflow: .github/workflows/hosp-rows-v2.yml (by hand only).

  python site/hosp_rebuild.py estimate --scope tx      files, GB, machine-hours and dollars; rents nothing, writes nothing
  python site/hosp_rebuild.py start --scope tx --confirm yes
                                                       rents machines that run site/hosp_every.py with ROWS_VERSION=v2
  python site/hosp_rebuild.py status --scope tx        how many files are done, failures, machines still on, and a sample
                                                       check of finished files against their v1 rows
  python site/hosp_rebuild.py estimate --scope all --offline
                                                       estimate from data/hospitals.csv alone (no storage, no keys)

Scopes: dfw (the hospitals the DFW page uses), tx (every Texas hospital in the bot's hospital list), all (every state).
Rows go to the v2 folder named in site/hosp_rows.json (data/2026-11-11/hosp_every_v2/rows/<sha16>.parquet), with done markers
(done/<sha16>.done) so a stopped run picks up where it left off. The v1 rows (data/hosp_every/) are never touched, and
nothing reads the v2 rows until Betsy sets "use": "v2" in site/hosp_rows.json. Nothing here deletes anything.

Every step refuses to run while the bot is paused for maintenance (board/maintenance.py: its open "Bot paused for
maintenance" issue, or the hospital queue's hold file). start also needs: the estimate at or under the approved amount
(HV2_LIMIT_USD, or build_approvals.json "hosp-v2-<scope>"), the month's card spend plus the estimate under Betsy's card cap
(build_approvals.json _card_cap), and free machine slots under the machine-share rules (machine_shares.py; RESERVE_SLOTS are
always left for other work).
"""
import argparse
import csv
import io
import json
import math
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "bot"), str(ROOT / "insurers"), str(ROOT)]
import hosp_rows  # noqa: E402

# ---- maintenance pause (must match board/maintenance.py; tests/test_hosp_rows_v2.py checks it does)
MAINT_TITLE = "Bot paused for maintenance"
HOSPITAL_HOLD = "bot/fleet/hold_hospitals.txt"

# ---- cost (docs/hospital-rows-v2.md "Cost"). Speed measured Nov 11, 2026 with site/hosp_every.py on made-up files on one
# core: CSV (tall) 9.3 MB/s and JSON 6.0 MB/s of original file, including the Parquet step; v2 columns cost nothing extra
# measurable. Planned at half that, to cover wide CSVs (one row per payer column) and slower shared machine cores.
MB_PER_SEC = {"csv": 4.5, "json": 3.0}
FILE_OVERHEAD_S = 30          # download, decompress, upload, done marker
BOOT_H = 0.25                 # machine boot + install, per machine
SIZE = "s-4vcpu-8gb-intel"    # the same size the monthly DFW refresh uses for hosp_every.py (site/orchestrate.py SIZE_HOSP)
USD_HOUR = 0.083              # list price; read live from DigitalOcean when a token is set
STORED_SHARE = 0.25           # compressed (.zst) originals are about this share of the raw size or less: what is downloaded
HV2_LIMIT_USD = 25            # Betsy's OK is needed above this (build_approvals.json "hosp-v2-<scope>")
RESERVE_SLOTS = 2             # machine slots always left free for other work (same as analysis/medicare_multiple)
MACHINES = 4                  # most machines at once by default
FILES_PER_MACHINE = 10        # don't rent a machine for fewer files than this
DFW_ZIP3 = [("750", "753"), ("760", "762")]   # site/hosp_area.py BIG: the DFW area by 3-digit ZIP


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ maintenance pause

def paused_issue(repo=None, token=None, get=None):
    """The open maintenance-pause issue's number, None if there is none. Raises if GitHub can't be asked: a failed check
    must never read as "not paused"."""
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if not repo or not token:
        raise RuntimeError("can't check the maintenance pause: GITHUB_REPOSITORY / GITHUB_TOKEN not set")
    if get is None:
        import requests
        get = lambda url, params: requests.get(url, params=params, timeout=60,
                                               headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    page = 1
    while True:
        r = get(f"https://api.github.com/repos/{repo}/issues", {"state": "open", "per_page": 100, "page": page})
        if r.status_code != 200:
            raise RuntimeError(f"can't check the maintenance pause: GitHub HTTP {r.status_code}")
        items = r.json()
        for i in items:
            if i.get("title", "").startswith(MAINT_TITLE) and "pull_request" not in i:
                return i["number"]
        if len(items) < 100:
            return None
        page += 1


def refuse_if_paused(offline=False):
    if offline:
        log("offline estimate: the maintenance pause was not checked (nothing is read or rented)")
        return
    n = paused_issue()
    if n:
        sys.exit(f"REFUSED: the bot is paused for maintenance (issue #{n}). After the storage move, run Actions -> "
                 "Maintenance -> resume first, then this again.")


def held(s3, b):
    """Text of the hospital queue's hold file, "" when there is none."""
    try:
        return s3.get_object(Bucket=b, Key=HOSPITAL_HOLD)["Body"].read().decode("utf-8", "replace").strip() or "(empty hold file)"
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            return ""
        raise


# ------------------------------------------------------------------ which files

def fmt_of(key):
    k = (key or "").lower()
    return "json" if ".json" in k else "csv"


def zips():
    """CCN -> 5-digit ZIP from Medicare's hospital list (reference/geo) plus the hand-found ones (data/hospital_zip_extra.csv)."""
    out = {}
    for f, col in ((ROOT / "reference" / "geo" / "medicare_hospitals.csv", "zip"), (ROOT / "data" / "hospital_zip_extra.csv", "zip")):
        try:
            for r in csv.DictReader(open(f)):
                if r.get("ccn") and r.get(col):
                    out.setdefault(r["ccn"], r[col].strip()[:5])
        except FileNotFoundError:
            pass
    return out


def is_dfw(z):
    return bool(z) and any(lo <= z[:3] <= hi for lo, hi in DFW_ZIP3)


def _read_csv(s3, b, key):
    try:
        return list(csv.DictReader(io.StringIO(s3.get_object(Bucket=b, Key=key)["Body"].read().decode("utf-8", "replace"))))
    except Exception:
        return []


def jobs_for(scope, s3=None, b=None, listed=None):
    """One job per distinct hospital file in the scope: {id, key, url, name, ccn, state, bytes, fmt}.
    The file per hospital is data/hospitals.csv's, replaced by the one the daily run has now (bot/manifest) when storage
    is given, the same rule as site/hosp_area.py. Files ruled another hospital's (bot/identity.py) are left out."""
    import identity
    listed = listed if listed is not None else list(csv.DictReader(open(ROOT / "data" / "hospitals.csv")))
    states = sorted({r["state"] for r in listed}) if scope == "all" else ["TX"]
    z = zips() if scope == "dfw" else {}
    cur = {}
    if s3 is not None:
        for st in states:
            files = {f["url"]: f for f in _read_csv(s3, b, f"bot/manifest/files/{st}.csv")}
            for m in _read_csv(s3, b, f"bot/manifest/hospitals/{st}.csv"):
                f = files.get(m.get("mrf_url", ""))
                if f and f.get("sha256") and f.get("r2_key") and m.get("status") != identity.WRONG_STATUS:
                    cur[m["ccn"]] = (m["mrf_url"], f["r2_key"], f["sha256"], f.get("bytes") or f.get("size") or "")
    wrong = identity.load(s3, b)
    out, seen = [], set()
    for r in listed:
        if r["state"] not in states:
            continue
        if scope == "dfw" and not is_dfw(z.get(r["ccn"], "")):
            continue
        url, key, sha, nb = r.get("mrf_url", ""), r.get("last_key", ""), r.get("last_sha256", ""), r.get("last_bytes", "")
        if r["ccn"] in cur:
            url, key, sha, nb = cur[r["ccn"]]
        if not key or not sha or identity.is_wrong(wrong, r["ccn"], url):
            continue
        sid = sha[:16]
        if sid in seen:
            continue
        seen.add(sid)
        out.append(dict(id=sid, key=key, url=url, name=r["name"].title(), ccn=r["ccn"], state=r["state"],
                        bytes=int(nb) if str(nb).isdigit() else 0, fmt=fmt_of(key)))
    if scope == "dfw" and s3 is not None:   # anything else the live DFW page's monthly refresh parses (site/orchestrate.py)
        try:
            for j in json.loads(s3.get_object(Bucket=b, Key="site/builds/hosp_jobs_base.json")["Body"].read()):
                if j.get("id") and j.get("key") and j["id"] not in seen:
                    seen.add(j["id"])
                    out.append(dict(id=j["id"], key=j["key"], url=j.get("url", ""), name=j.get("name", ""), ccn=j.get("ccn", ""),
                                    state="TX", bytes=int(j.get("size") or 0), fmt=fmt_of(j["key"])))
        except Exception as e:
            log("DFW monthly job list not read (ZIP rule only):", repr(e)[:120])
    return out


# ------------------------------------------------------------------ cost

def do_price():
    try:
        import requests
        r = requests.get("https://api.digitalocean.com/v2/sizes?per_page=200", timeout=30,
                         headers={"Authorization": f"Bearer {''.join(os.environ['DIGITALOCEAN_TOKEN'].split())}"})
        return float(next(z["price_hourly"] for z in r.json()["sizes"] if z["slug"] == SIZE))
    except Exception:
        return USD_HOUR


def estimate(jobs, machines=MACHINES, price=USD_HOUR, per_gb=None, done=()):
    """Files, GB, machine-hours and dollars for the jobs not done yet. A file with no known size counts at the average."""
    todo = [j for j in jobs if j["id"] not in set(done)]
    known = [j["bytes"] for j in jobs if j["bytes"]]
    avg = sum(known) / len(known) if known else 0
    size = lambda j: j["bytes"] or avg
    ep = os.environ.get("STORAGE_ENDPOINT", "")
    per_gb = per_gb if per_gb is not None else (0.01 if "backblaze" in ep else 0.0)
    n = machines_for(len(todo), machines)
    secs = sum(size(j) / 1e6 / MB_PER_SEC[j["fmt"]] + FILE_OVERHEAD_S for j in todo)
    mh = secs / 3600 + BOOT_H * n
    raw_gb = sum(size(j) for j in todo) / 1e9
    out = dict(files=len(jobs), files_done=len(jobs) - len(todo), files_to_parse=len(todo),
               csv_files=sum(1 for j in todo if j["fmt"] == "csv"), json_files=sum(1 for j in todo if j["fmt"] == "json"),
               files_without_size=sum(1 for j in todo if not j["bytes"]),
               raw_gb=round(raw_gb, 1), biggest_file_gb=round(max([size(j) for j in todo] or [0]) / 1e9, 2),
               download_gb=round(raw_gb * STORED_SHARE, 1), machines=n, machine_size=SIZE,
               machine_hours=round(mh, 1), wall_hours=round(mh / max(n, 1), 1), usd_per_machine_hour=price,
               machine_usd=round(mh * price, 2), storage_download_usd=round(raw_gb * STORED_SHARE * per_gb, 2))
    out["total_usd"] = round(out["machine_usd"] + out["storage_download_usd"], 2)
    return out


def machines_for(files, machines):
    return max(0, min(machines, math.ceil(files / FILES_PER_MACHINE)))


def approved(scope):
    key = f"hosp-v2-{scope}"
    try:
        a = json.load(open(ROOT / "build_approvals.json")).get(key) or {}
        return key, float(a.get("usd") or 0) or HV2_LIMIT_USD
    except Exception:
        return key, HV2_LIMIT_USD


def bid(scope, month=None):
    """Build id for the machine-share rules: ends in a letter, so it counts as a rebuild (machine_shares.REBUILD_SHARE)."""
    return f"hosp-v2-{scope}-{month or time.strftime('%Y-%m')}a"


# ------------------------------------------------------------------ machines

def free_machines(asked, files, s3, b, scope, droplets=None, shares=None, log=log):
    """How many machines start may rent now: never more than asked or useful for the files, than the build may hold under
    the machine-share rules (minus its own machines already on), or than the free slots minus RESERVE_SLOTS. 0 when the
    month's card spend has reached the cap (droplets.room() is 0 then)."""
    if droplets is None:
        import droplets
    if shares is None:
        import machine_shares as shares
    names = droplets.names()
    me = bid(scope)
    own = sum(1 for n in names if n.startswith(f"upfront-site-{me}-"))
    cap = shares.build_cap(me, droplets.limit(), RESERVE_SLOTS, names, s3, b, log=log)
    return max(0, min(machines_for(files, asked), cap - own, droplets.room() - RESERVE_SLOTS))


def userdata(scope, run_key, shard, shards, ref, v2):
    keys = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "STORAGE_ENDPOINT", "STORAGE_REGION",
            "DIGITALOCEAN_TOKEN"]
    env = "\n".join(f"export {k}='{''.join(os.environ.get(k, '').split())}'" for k in keys)
    return f"""#!/bin/bash
exec > /root/boot.log 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y python3-venv git
python3 -m venv /root/v && /root/v/bin/pip install -q duckdb==1.1.3 boto3==1.35.36 ijson==3.3.0 zstandard==0.23.0
cat > /root/env.sh <<'ENV'
{env}
export ROWS_VERSION=v2 HPFX='{v2}' JOBS_KEY='{run_key}todo.json' SHARD='{shard}' SHARDS='{shards}'
ENV
. /root/env.sh
git clone --depth 1 -b {ref} https://github.com/betsyflickinger-max/files.healthcare_price-files-bot.git /root/r
cd /root/r
for t in 1 2 3; do /root/v/bin/python site/hosp_every.py >> /root/run.log 2>&1 && break; sleep 5; done
/root/v/bin/python -c "
import sys; sys.path.insert(0, 'bot'); import store; s3, b = store.r2()
s3.upload_file('/root/run.log', b, '{run_key}logs/m{shard}.log'); s3.upload_file('/root/boot.log', b, '{run_key}logs/m{shard}-boot.log')"
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DIGITALOCEAN_TOKEN" https://api.digitalocean.com/v2/droplets/$ID
"""


# ------------------------------------------------------------------ storage helpers

def ls(s3, b, pfx):
    return [(o["Key"], o["Size"]) for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=pfx)
            for o in pg.get("Contents", [])]


def done_ids(s3, b, v2):
    return {k.rsplit("/", 1)[1][:-5] for k, _ in ls(s3, b, v2 + "done/") if k.endswith(".done")}


def put_json(s3, b, key, doc):
    s3.put_object(Bucket=b, Key=key, Body=json.dumps(doc, indent=1).encode())


# ------------------------------------------------------------------ steps

def cmd_estimate(a, s3=None, b=None):
    v2 = hosp_rows.v2_prefix()
    jobs = jobs_for(a.scope, s3, b)
    done = done_ids(s3, b, v2) if s3 is not None else set()
    price = do_price() if os.environ.get("DIGITALOCEAN_TOKEN") else USD_HOUR
    est = estimate(jobs, a.machines, price, a.per_gb, done)
    key, limit = approved(a.scope)
    est.update(scope=a.scope, v2_folder=v2, approval_key=key, limit_usd=limit,
               verdict="ok" if est["total_usd"] <= limit else "over the limit: needs Betsy's OK",
               source="data/hospitals.csv only (offline)" if s3 is None else "data/hospitals.csv + the bot's current files (bot/manifest)")
    if os.environ.get("DIGITALOCEAN_TOKEN") and s3 is not None:
        try:
            import droplets
            spent, mtd, credit = droplets.card_spend()
            est.update(card_spent_this_month=round(spent, 2), card_cap=droplets.card_cap(),
                       card_room_left=round(droplets.card_cap() - spent, 2))
        except Exception as e:
            est["card_check"] = f"couldn't read DigitalOcean balance: {e!r}"[:160]
    return jobs, done, est


def cmd_start(a, s3, b):
    if (a.confirm or "").strip().lower() != "yes":
        sys.exit("REFUSED: start needs confirm = yes (run the estimate first and read it)")
    h = held(s3, b)
    if h:
        sys.exit(f"REFUSED: the hospital queue is on hold ({HOSPITAL_HOLD}: {h[:160]}). Lift it first (Maintenance -> resume).")
    jobs, done, est = cmd_estimate(a, s3, b)
    print(json.dumps(est, indent=1), flush=True)
    if est["verdict"] != "ok":
        sys.exit(f"REFUSED: estimate ${est['total_usd']} is over ${est['limit_usd']}. Betsy: add \"{est['approval_key']}\": "
                 "{\"usd\": N, \"why\": \"...\"} to build_approvals.json to allow more.")
    if "card_room_left" in est and est["total_usd"] > est["card_room_left"]:
        sys.exit(f"REFUSED: estimate ${est['total_usd']} is more than what is left under this month's card cap "
                 f"(${est['card_room_left']}; build_approvals.json _card_cap).")
    todo = [j for j in jobs if j["id"] not in done]
    if not todo:
        log("every file in this scope is already done; nothing to rent")
        return
    import droplets
    if droplets.over_cap():
        sys.exit("REFUSED: this month's card spending cap is reached (build_approvals.json _card_cap); no machines rented")
    n, waited = 0, 0
    while True:
        n = free_machines(a.machines, len(todo), s3, b, a.scope)
        if n > 0 or waited + 10 > a.wait_minutes:
            break
        log(f"no free machine slots (keeping {RESERVE_SLOTS} for other work); checking again in 10 minutes")
        time.sleep(600)
        waited += 10
    if n <= 0:
        sys.exit(f"no free machine slot now (machine shares, {RESERVE_SLOTS} reserve slots, card cap). Nothing rented; "
                 "run start again later. Finished files stay done.")
    v2 = hosp_rows.v2_prefix()
    run_key = f"{v2}runs/{a.scope}/{time.strftime('%Y%m%d-%H%M%S')}/"
    todo.sort(key=lambda j: -j["bytes"])          # biggest first; SHARD i takes every n-th, so sizes spread evenly
    put_json(s3, b, run_key + "todo.json", todo)
    put_json(s3, b, run_key + "estimate.json", est)
    made = []
    for i in range(n):
        name = f"upfront-site-{bid(a.scope)}-{i}"
        d = droplets.create(name, userdata(a.scope, run_key, i, n, a.ref, v2), size=SIZE)
        made.append(dict(id=d["id"], name=name))
        log("rented", name, d["id"])
    put_json(s3, b, run_key + "launched.json", dict(at=time.strftime("%Y-%m-%d %H:%M"), ref=a.ref, machines=made,
                                                   files=len(todo)))
    log(f"started {n} machines for {len(todo)} files; rows go to {v2}rows/. Check with step 'status'.")


def compare_sample(s3, b, sid, v1, v2, work):
    """One finished file: its v2 rows against its v1 rows (same original file). Old columns must match row for row."""
    p1, p2 = f"{work}/{sid}.v1.parquet", f"{work}/{sid}.v2.parquet"
    s3.download_file(b, f"{v2}rows/{sid}.parquet", p2)
    have_v1 = True
    try:
        s3.download_file(b, f"{v1}rows/{sid}.parquet", p1)
    except Exception:
        have_v1 = False
    out = compare_files(p1 if have_v1 else None, p2)
    for p in (p1, p2):
        if os.path.exists(p):
            os.remove(p)
    return dict(file=sid, **out)


def compare_files(p1, p2):
    import duckdb
    con = duckdb.connect()
    cols2 = [r[0] for r in con.execute(f"describe select * from read_parquet('{p2}')").fetchall()]
    q = lambda c: f"count(*) filter (where coalesce(cast({c} as varchar), '') <> '')" if c in cols2 else "0"
    ver_sql = "string_agg(distinct file_version, ', ')" if "file_version" in cols2 else "null"
    n2, p10, p90, cnt, ver = con.execute(f"select count(*), {q('p10_amount')}, {q('p90_amount')}, {q('allowed_count')}, {ver_sql} "
                                         f"from read_parquet('{p2}')").fetchone()
    out = dict(v2_rows=n2, rows_with_p10=p10, rows_with_p90=p90, rows_with_count=cnt, file_version=ver or "")
    if p1:
        cols1 = [r[0] for r in con.execute(f"describe select * from read_parquet('{p1}')").fetchall()]
        sel = ", ".join(f'"{c}"' for c in cols1)
        n1 = con.execute(f"select count(*) from read_parquet('{p1}')").fetchone()[0]
        d1 = con.execute(f"select count(*) from (select {sel} from read_parquet('{p1}') except all select {sel} from read_parquet('{p2}'))").fetchone()[0]
        d2 = con.execute(f"select count(*) from (select {sel} from read_parquet('{p2}') except all select {sel} from read_parquet('{p1}'))").fetchone()[0]
        out.update(v1_rows=n1, old_columns_same=(d1 == 0 and d2 == 0 and n1 == n2), v1_rows_not_in_v2=d1, v2_rows_not_in_v1=d2)
    else:
        out.update(v1_rows=None, old_columns_same=None)
    con.close()
    return out


def cmd_status(a, s3, b):
    v1, v2 = hosp_rows.setting()["v1"], hosp_rows.v2_prefix()
    jobs = jobs_for(a.scope, s3, b)
    done = done_ids(s3, b, v2)
    left = [j for j in jobs if j["id"] not in done]
    fails, secs, mb = {}, 0.0, 0.0
    size = {j["id"]: j["bytes"] for j in jobs}
    for k, _ in ls(s3, b, v2):
        if re.search(r"/log_\d+\.jsonl$", k):
            for line in s3.get_object(Bucket=b, Key=k)["Body"].read().decode("utf-8", "replace").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("ok") is False and r.get("id") not in done:
                    fails[r["id"]] = f"{r.get('name', '')}: {r.get('err', '')}"[:200]
                elif r.get("ok") and size.get(r.get("id")):
                    secs += float(r.get("secs") or 0); mb += size[r["id"]] / 1e6
    try:
        import droplets
        on = [n for n in droplets.names() if n.startswith(f"upfront-site-{bid(a.scope)}-")]
    except Exception as e:
        on = [f"(couldn't list machines: {e!r})"[:120]]
    print(f"## Hospital rows v2, scope {a.scope}\n\n- Files in scope: {len(jobs)}\n- Done: {len(jobs) - len(left)}\n"
          f"- Left: {len(left)}\n- Failed (latest try): {len(fails)}\n- Machines on: {len(on)} {' '.join(on)}\n"
          f"- Setting in use: {hosp_rows.use()} (site/hosp_rows.json)\n")
    if secs > 600:   # cost_check.py's rule: project from the real speed, not the guess
        left_mb = sum(j["bytes"] for j in left) / 1e6
        h = left_mb / (mb / secs) / 3600
        print(f"- Real speed so far: {mb / secs:.1f} MB/s per machine; about {h:.1f} machine-hours (${h * do_price():.2f}) "
              f"left for the files of known size (the estimate planned {MB_PER_SEC['csv']} MB/s CSV, {MB_PER_SEC['json']} JSON)\n")
    for sid, why in list(fails.items())[:30]:
        print(f"  - failed {sid}: {why}")
    fin = [j for j in jobs if j["id"] in done]
    small = [j for j in fin if 0 < j["bytes"] < 300e6] or fin
    random.Random(time.strftime("%Y-%m-%d")).shuffle(small)
    if small[:a.sample]:
        print("\n### Sample check (v2 rows against the same file's v1 rows)\n")
        with tempfile.TemporaryDirectory() as w:
            for j in small[:a.sample]:
                try:
                    r = compare_sample(s3, b, j["id"], v1, v2, w)
                    print(f"- {j['name']} ({j['id']}): {json.dumps(r)}")
                except Exception as e:
                    print(f"- {j['name']} ({j['id']}): couldn't compare: {e!r}"[:300])
        print("\n`old_columns_same: false` can be right for files parsed before a reader fix (e.g. the Nov 9 line-number fix): "
              "look at those by hand before switching.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["estimate", "start", "status"])
    ap.add_argument("--scope", default="tx", choices=["dfw", "tx", "all"])
    ap.add_argument("--confirm", default="")
    ap.add_argument("--machines", type=int, default=MACHINES)
    ap.add_argument("--wait-minutes", type=int, default=0)
    ap.add_argument("--ref", default="main", help="start: the branch the machines clone")
    ap.add_argument("--sample", type=int, default=3, help="status: how many finished files to compare with their v1 rows")
    ap.add_argument("--per-gb", type=float, default=None, help="estimate: storage download price per GB (default: B2 $0.01 if on Backblaze)")
    ap.add_argument("--offline", action="store_true", help="estimate only: data/hospitals.csv alone, no storage or keys")
    a = ap.parse_args(argv)
    if a.offline and a.step != "estimate":
        sys.exit("--offline is for estimate only")
    refuse_if_paused(a.offline)
    if a.offline:
        _, _, est = cmd_estimate(a)
        print(json.dumps(est, indent=1))
        return est
    import store
    s3, b = store.r2()
    if a.step == "estimate":
        _, _, est = cmd_estimate(a, s3, b)
        h = held(s3, b)
        if h:
            est["hospital_queue_on_hold"] = h[:160]
        print(json.dumps(est, indent=1))
        return est
    if a.step == "start":
        return cmd_start(a, s3, b)
    return cmd_status(a, s3, b)


if __name__ == "__main__":
    main()
