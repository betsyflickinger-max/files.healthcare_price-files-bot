"""Private price as a multiple of Medicare, by kind of care: one command per state (or all states).

  python analysis/medicare_multiple/run.py bench     --state TX                     CMS files -> benchmark tables (no keys needed)
  python analysis/medicare_multiple/run.py plan      --state TX                     list the tables to read (storage keys needed)
  python analysis/medicare_multiple/run.py estimate  --state TX                     cost before anything heavy runs
  python analysis/medicare_multiple/run.py reduce    --state TX --shard 0 --shards 8   read tables -> small "parts" in storage
  python analysis/medicare_multiple/run.py summarize --state TX                     parts -> reports/medicare-multiple/tx/
  python analysis/medicare_multiple/run.py all       --state TX                     every step above on this machine
  python analysis/medicare_multiple/run.py local     --state TX --bench B --prov P --insurer 'dir/*.parquet' --out O
                                                     (tests and small samples: no storage)
--state ALL runs every state: each area's insurer tables are read ONCE for all the states in that area (insurers/bot.py
SCOPES), then each state is summarized on its own.

Storage layout (R2/B2, under analysis/medicare-multiple/<run id>/): bench/ (benchmark CSVs), plan.json, parts/<table>.*.parquet,
logs/. Nothing outside that folder is written, and nothing is deleted. The site is never touched.

The cost rule (Betsy, Nov 10, 2026): `estimate` must come in at or under the approved amount (MM_LIMIT_USD = $40 for a state
pilot, or build_approvals.json "mm-<state>") before `reduce` starts rented machines; GitHub's machines are free for this
public repo and are always used first.
"""
import argparse
import csv
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "insurers" / "pipeline"), str(ROOT / "bot")]
import cms  # noqa: E402
import hospital_match  # noqa: E402
import rates  # noqa: E402
import segments  # noqa: E402
import summarize as summ  # noqa: E402

PFX = "analysis/medicare-multiple/"
# area (insurers/bot.py SCOPES) -> states; Texas also reads the DFW tables for networks the Texas tables don't have
AREAS = {"tx": ["TX"], "s7": ["TN", "CO", "OK", "AL", "MS", "MO", "GA"], "nc": ["NC"], "ct": ["CT"], "il": ["IL"],
         "n5": ["NY", "CA", "VA", "DC", "FL", "WI"], "ar": ["AR"], "b1": ["MD", "NM", "MT"], "la": ["LA"],
         "b4": ["IN", "KY", "OH"], "az": ["AZ"], "c1": ["MI", "ND", "SD", "IA", "MN", "NE", "KS"],
         "c2": ["PA", "DE", "WV", "NJ", "MA", "RI", "VT", "NH", "ME", "SC"], "c3": ["WA", "OR", "ID", "UT", "AK", "NV", "HI", "WY"],
         "nyhf": ["NY"]}
EXTRA = {"tx": ["dfw"]}                 # dfw tables: only networks whose label isn't in the Texas tables (no double count)
TABLES = {"dfw": "data/full/", **{a: f"data/{a}/" for a in AREAS}}
NPIS = {"dfw": "data/2026-09-29/dfw_npis_all.parquet", **{a: f"data/scope/{a}_npis_all.parquet" for a in AREAS}}
NPIS["nyhf"] = "data/scope/nyhf_npis_all.parquet"
MED_LOCAL = "site/med_local/2026.json"
ENROLL = "data/names/hospital_enrollments.csv"          # CMS Hospital Enrollments (CCN, NPI), already in storage
FILE_MANIFEST = "bot/manifest/files/{state}.csv"         # the bot's per-file facts, incl. license number read from each file
# Machines. Speed measured Nov 10, 2026 on 20 million made-up rows shaped like an insurer table (fee-schedule-like
# amounts, 40,000 providers, 6,000 codes): 112 s on 2 cores for labels + Medicare join + counts = about 89,000 rows per
# core-second. Assumed 85% of that per core on more cores. See docs/medicare-multiple.md "Cost".
GH_MAX_ROWS = 800_000_000        # a table up to this many rows is read on a free GitHub machine (4 cores, 16 GB, 14 GB disk)
ROWS_PER_SEC = {"gh": 300_000, "do": 600_000}       # GitHub 4-core machine; DigitalOcean 8-core machine
PASS_ROWS = {"gh": 60_000_000, "do": 250_000_000}   # rows per pass (a big table is read in passes split by provider)
BYTES_PER_ROW = 4.4              # stored size of insurer tables (biggest Texas table: ~38 GB for 8.6 billion rows)
DO_SIZE = "m-8vcpu-64gb-intel"   # 64 GB memory, 400 GB disk (price read live from DigitalOcean when a token is set)
DO_USD_HOUR = 0.60               # used only when the live price can't be read (list price is about $0.50-0.60/hour)
DO_BOOT_H = 0.25                 # boot, install and download per machine
DO_MACHINES = 4                  # most rented machines this analysis may hold at once (machine_shares.py: never all of them)
MM_LIMIT_USD = 40


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def areas_for(states):
    if "ALL" in states:
        return list(AREAS)
    return [a for a, ss in AREAS.items() if set(ss) & set(states)]


def states_of(area, states):
    ss = AREAS[area]
    return ss if "ALL" in states else [s for s in ss if s in states]


# ------------------------------------------------------------------ storage

def s3():
    import store
    return store.r2()


def duck(work, threads=None, mem=None):
    import duckdb
    con = duckdb.connect()
    os.makedirs(f"{work}/spill", exist_ok=True)
    con.execute(f"set temp_directory='{work}/spill'")
    con.execute("set preserve_insertion_order=false")
    if threads:
        con.execute(f"set threads={int(threads)}")
    if mem:
        con.execute(f"set memory_limit='{mem}'")
    if os.environ.get("R2_ACCESS_KEY_ID"):
        g = lambda k: "".join(os.environ.get(k, "").split())
        ep = (os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com").replace("https://", "").rstrip("/")
        con.execute("install httpfs; load httpfs")
        con.execute(f"""create or replace secret store (type s3, key_id '{g("R2_ACCESS_KEY_ID")}', secret '{g("R2_SECRET_ACCESS_KEY")}',
                        endpoint '{ep}', region '{os.environ.get("STORAGE_REGION") or "auto"}', url_style 'path')""")
    return con


def ls(s3c, b, pfx):
    return [(o["Key"], o["Size"]) for pg in s3c.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=pfx)
            for o in pg.get("Contents", [])]


# ------------------------------------------------------------------ plan

def plan(states, run_id, work, gh_max=GH_MAX_ROWS):
    """Every table to read for these states, with its size and row count (from the Parquet footer only)."""
    s3c, b = s3()
    con = duck(work)
    items = []
    # market segment of each network, from the insurers' own tables of contents (segments.py); rebuilt every run
    segs, seg_note = segments.from_storage(con, s3c, b)
    log("market segments:", seg_note)
    for area in areas_for(states):
        labels = set()
        for scope in [area] + EXTRA.get(area, []):
            rates_ = [(k, n) for k, n in ls(s3c, b, TABLES[scope] + "rates/") if k.endswith(".parquet")]
            for k, n in rates_:
                meta = con.execute(f"select sum(num_rows), count(*) from (select distinct row_group_id, row_group_num_rows num_rows "
                                   f"from parquet_metadata('s3://{b}/{k}'))").fetchone()
                lab = ""
                try:
                    lab = con.execute(f"select any_value(file_label) from read_parquet('s3://{b}/{k}') limit 1").fetchone()[0] or ""
                except Exception:
                    pass
                stem = k.rsplit("/", 1)[1]
                if scope != area and (lab in labels or stem in labels):
                    continue          # the same network or the same file is already read from the area's own tables
                if scope == area:
                    labels.update({lab, stem})
                rows = int(meta[0] or 0)
                sg = segments.table_segment(stem, segs) or {}
                items.append(dict(source="insurer", area=area, scope=scope, key=k, bytes=n, rows=rows, row_groups=int(meta[1] or 0),
                                  network=lab, membership=k.replace("/rates/", "/membership/"),
                                  segment=sg.get("segment", ""), segment_method=sg.get("method", ""),
                                  lane="gh" if rows <= gh_max else "do"))
    # hospital files: the newest parsed copy of each hospital's file in these states (site/hosp_every.py cache), matched to its
    # CMS number from what the file says about itself (hospital_match.py), rebuilt every run
    items += hospital_items(con, s3c, b, states)
    # out-of-network allowed amounts: the newest month of every insurer's files
    newest = {}
    for k, n in ls(s3c, b, "raw/allowed/"):
        m = re.match(r"raw/allowed/(\d{4}-\d{2})/(.+)\.tar$", k)
        if m and (m.group(2) not in newest or m.group(1) > newest[m.group(2)][0]):
            newest[m.group(2)] = (m.group(1), k, n)
    for ins, (month, k, n) in sorted(newest.items()):
        items.append(dict(source="allowed", area="", scope="allowed", key=k, bytes=n, rows=0, insurer=ins, month=month, lane="gh"))
    doc = dict(run_id=run_id, states=states, made=time.strftime("%Y-%m-%d %H:%M"), items=items, segment_note=seg_note)
    s3c.put_object(Bucket=b, Key=f"{PFX}{run_id}/plan.json", Body=json.dumps(doc).encode())
    return doc


def hospital_items(con, s3c, b, states):
    have = {k.rsplit("/", 1)[1][:-8]: n for k, n in ls(s3c, b, "data/hosp_every/rows/") if k.endswith(".parquet")}
    listed = list(csv.DictReader(open(ROOT / "data" / "hospitals.csv")))
    known = {r["ccn"]: r["state"] for r in listed}                      # every CMS hospital record (CCN -> state)
    files, fallback, meta = [], {}, {}
    sts = {r["state"] for r in listed} if "ALL" in states else set(states)
    lic = {}
    for st in sorted(sts):
        try:
            body = s3c.get_object(Bucket=b, Key=FILE_MANIFEST.format(state=st))["Body"].read().decode("utf-8", "replace")
            for m in csv.DictReader(io.StringIO(body)):
                if m.get("sha256"):
                    lic[m["sha256"][:16]] = m
        except Exception:
            pass
    for r in listed:
        if r["state"] in sts and r.get("last_sha256") and r["last_sha256"][:16] in have:
            sid = r["last_sha256"][:16]
            key = f"data/hosp_every/rows/{sid}.parquet"
            try:
                cols = {x[0] for x in con.execute(f"describe select * from read_parquet('s3://{b}/{key}')").fetchall()}
                pick = [c for c in ("type_2_npi", "hospital_name", "location_name", "ein") if c in cols]
                one = con.execute(f"select {', '.join(pick)} from read_parquet('s3://{b}/{key}') limit 1").fetchone() if pick else None
                own = dict(zip(pick, one or []))
            except Exception:
                own = {}
            m = lic.get(sid, {})
            files.append(dict(key=key, state=r["state"], url=r.get("mrf_url", ""), license_number=m.get("license_number", ""),
                              license_state=m.get("license_state", ""), **{k: str(v or "") for k, v in own.items()}))
            fallback[key] = r["ccn"]
            meta[key] = (have[sid], r["name"])
    npi_ccn = {}
    try:
        body = s3c.get_object(Bucket=b, Key=ENROLL)["Body"].read().decode("latin-1")
        for e in csv.DictReader(io.StringIO(body)):
            if e.get("NPI") and e.get("CCN"):
                npi_ccn.setdefault(e["NPI"].strip(), set()).add(e["CCN"].strip())
    except Exception as e:
        log("hospital enrollments not read:", repr(e)[:120])
    try:
        for npi, v in json.loads(s3c.get_object(Bucket=b, Key=MED_LOCAL)["Body"].read())["npi"].items():
            if v[0] == "H" and v[2]:
                npi_ccn.setdefault(npi, set()).add(v[2])
    except Exception as e:
        log("med_local not read:", repr(e)[:120])
    matches = hospital_match.match_files(files, npi_ccn, known, fallback)
    log("hospital files matched:", json.dumps(hospital_match.counts(matches)))
    out = []
    for f in files:
        m = matches[f["key"]]
        st = known.get(m["ccn"] or "", f["state"])
        if not m["ccn"] or ("ALL" not in states and st not in states):
            continue
        out.append(dict(source="hospital", area="", scope="hospital", key=f["key"], bytes=meta[f["key"]][0], rows=0, ccn=m["ccn"],
                        state=st, name=meta[f["key"]][1], lane="gh", match_method=m["method"], file_npis=m["npis"],
                        fallback_ccn=m["fallback_ccn"], agrees_with_list=m["agrees_with_list"]))
    # files not matched (or matched to another state) stay listed in the plan, never read silently away
    for f in files:
        m = matches[f["key"]]
        if not m["ccn"]:
            out.append(dict(source="hospital-unmatched", area="", scope="hospital", key=f["key"], bytes=0, rows=0, ccn="",
                            state=f["state"], name=meta[f["key"]][1], lane="none", match_method=m["method"], file_npis=m["npis"],
                            fallback_ccn="", agrees_with_list=""))
    return out


def hospital_match_rows(doc, state=None):
    """One row per hospital file in the plan: name, CCN, how it was matched, the bot's list's CCN, agree?"""
    return [dict(file=i["key"], hospital=i.get("name", ""), state=i.get("state", ""), ccn=i.get("ccn", ""), method=i.get("match_method", ""),
                 bots_list_ccn=i.get("fallback_ccn", ""), agrees_with_list=i.get("agrees_with_list", ""), npis_in_file=" ".join(i.get("file_npis") or []))
            for i in doc["items"] if i["source"].startswith("hospital") and (not state or i.get("state") == state)]


# ------------------------------------------------------------------ estimate

def do_price():
    try:
        import requests
        r = requests.get("https://api.digitalocean.com/v2/sizes?per_page=200", timeout=30,
                         headers={"Authorization": f"Bearer {os.environ['DIGITALOCEAN_TOKEN']}"})
        return float(next(z["price_hourly"] for z in r.json()["sizes"] if z["slug"] == DO_SIZE))
    except Exception:
        return DO_USD_HOUR


def estimate(doc, storage_usd_per_gb=None, machines=DO_MACHINES):
    """Hours and dollars before anything heavy runs. GitHub machines are free here (public repo). Rented machines: hours x
    hourly price (+ boot). Storage: R2 charges nothing to read data out and $0.36 per million read requests; Backblaze
    B2 charges $0.01/GB downloaded beyond its free allowance (3x what is stored), counted here as if none were free."""
    items = doc["items"]
    ep = os.environ.get("STORAGE_ENDPOINT", "")
    per_gb = storage_usd_per_gb if storage_usd_per_gb is not None else (0.01 if "backblaze" in ep else 0.0)
    gh = [i for i in items if i["lane"] == "gh"]
    do = [i for i in items if i["lane"] == "do"]
    gh_h = sum(i["rows"] for i in gh) / ROWS_PER_SEC["gh"] / 3600 + 0.05 * len(gh)
    do_h = sum(i["rows"] for i in do) / ROWS_PER_SEC["do"] / 3600 + DO_BOOT_H * min(len(do), machines)
    # each extra pass over a big table re-reads its columns from the machine's own disk: about 20 ns per row per core
    do_h += sum(i["rows"] * (math.ceil(i["rows"] / PASS_ROWS["do"]) - 1) for i in do) * 20e-9 / 8 / 3600
    price = do_price() if do else DO_USD_HOUR
    gbytes = sum(i["bytes"] or i["rows"] * BYTES_PER_ROW for i in items) / 1e9
    read_gb = gbytes                # each table is downloaded whole once (then read in passes from the machine's disk)
    requests_m = sum(i.get("row_groups", 1) + 10 for i in items) / 1e6   # multipart download parts + listings, generously
    out = dict(tables=len(gh) + len(do), insurer_tables=sum(1 for i in items if i["source"] == "insurer"),
               hospital_files_not_matched=sum(1 for i in items if i["source"] == "hospital-unmatched"),
               rows=sum(i["rows"] for i in items), stored_gb=round(gbytes, 1), read_gb=round(read_gb, 1),
               github_tables=len(gh), github_machine_hours=round(gh_h, 1), github_usd=0.0,
               rented_tables=len(do), rented_machine_hours=round(do_h, 1), rented_usd_per_hour=price,
               rented_usd=round(do_h * price, 2), storage_requests_usd=round(requests_m * 0.36, 2),
               storage_download_usd=round(read_gb * per_gb, 2))
    out["total_usd"] = round(out["rented_usd"] + out["storage_requests_usd"] + out["storage_download_usd"], 2)
    out["rented_wall_hours"] = round(do_h / max(1, min(len(do), machines)), 1)
    out["github_wall_hours_per_shard_of_8"] = round(gh_h / 8, 1)
    return out


def approved(states):
    key = "mm-" + ("all" if "ALL" in states else "-".join(sorted(s.lower() for s in states)))
    try:
        a = json.load(open(ROOT / "build_approvals.json")).get(key) or {}
        return key, float(a.get("usd") or 0)
    except Exception:
        return key, 0.0


# ------------------------------------------------------------------ reduce

def provider_table(con, s3c, b, area, work, hosp_npis=()):
    """prov table for an area: NPI, practice ZIP (the area's NPI list), and for hospitals and surgery centers their CMS
    number and wage index (site/med_local.py). hosp_npis: (npi, ccn) the hospital files list for themselves (type 2 NPIs,
    hospital_match.py), added as hospitals where med_local doesn't already place the NPI; wage index from the FY2026 file."""
    npis = f"{work}/{area}_npis.parquet"
    if not os.path.exists(npis):
        s3c.download_file(b, NPIS[area], npis)
    ml = json.loads(s3c.get_object(Bucket=b, Key=MED_LOCAL)["Body"].read())["npi"]
    for npi, ccn in hosp_npis:
        ml.setdefault(npi, ["H", None, ccn])
    con.execute("create or replace temp table ml (npi varchar, kind varchar, wage_index double, ccn varchar)")
    con.executemany("insert into ml values (?, ?, ?, ?)", [(k, v[0], v[1], v[2]) for k, v in ml.items()])
    return (f"(select cast(n.npi as varchar) npi, n.zip5, ml.kind, coalesce(ml.wage_index, (select max(w.wage_index) from b_wi2026 w "
            f"where w.ccn = ml.ccn)) wage_index, ml.ccn from read_parquet('{npis}') n left join ml using (npi))")


def reduce_items(items, states, bench, work, upload_pfx=None, spec=True, lane="gh", hosp_npis=()):
    """Read each item and write its part files to <work>/parts/ (and to storage when upload_pfx is given). An insurer table
    is downloaded once to this machine's disk and read in passes of PASS_ROWS rows, split by provider (rates.insurer_units).
    A finished item leaves done/<name> in storage, so a restarted machine skips it."""
    s3c, b = s3()
    parts = Path(work) / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    by_area = {}
    for it in items:
        by_area.setdefault(it.get("area") or "", []).append(it)
    import rate_labels
    for area, its in by_area.items():
        con = duck(work)
        sts = states_of(area, states) if area else [s for s in (cms.STATE_NAMES if "ALL" in states else states)]
        if area:
            rates.register_bench(con, bench, provider_table(con, s3c, b, area, work, hosp_npis), sts)
        else:   # hospital files and allowed amounts: every NPI list of these states' areas
            provs = [provider_table(con, s3c, b, a, work, hosp_npis) for a in areas_for(states)]
            rates.register_bench(con, bench, "(" + " union all ".join(provs) + ")", sts)
        sp = rate_labels.spec_from_storage(con, f"{work}/spec") if spec else None
        for it in its:
            name = f"{it['source']}__{it.get('scope', '')}__" + rates.safe_name(it["key"].rsplit("/", 1)[1].rsplit(".", 1)[0])
            if upload_pfx and _exists(s3c, b, f"{upload_pfx}done/{name}"):
                log("already done:", it["key"])
                continue
            t0 = time.time()
            const = dict(source=it["source"], scope=it.get("scope", ""), table_name=name)
            local = f"{work}/table.parquet"
            outs = []
            if it["source"] in ("insurer", "hospital"):
                s3c.download_file(b, it["key"], local)
                t = f"read_parquet('{local}')"
                have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
            if it["source"] == "insurer":
                mem = None
                if _exists(s3c, b, it["membership"]):
                    s3c.download_file(b, it["membership"], f"{work}/membership.parquet")
                    mem = f"read_parquet('{work}/membership.parquet')"
                k = max(1, math.ceil((it.get("rows") or 0) / PASS_ROWS[lane]))
                for j in range(k):
                    out = parts / (name + (f"__p{j}" if k > 1 else ""))
                    seg = (it.get("segment"), it.get("segment_method")) if it.get("segment") else None
                    n = rates.reduce_table(con, rates.insurer_units(t, have, mem, sp, j, k, seg=seg), const, str(out))
                    outs.append(out)
                    log(f"  pass {j + 1}/{k}: {n:,} part rows, {time.time() - t0:,.0f}s")
            elif it["source"] == "hospital":
                con.execute("create or replace temp table hosp as select ? ccn, ? state", [it["ccn"], it["state"]])
                out = parts / name
                rates.reduce_table(con, rates.hospital_units(t, have), const, str(out))
                outs.append(out)
            else:
                t = _allowed_table(con, s3c, b, it, work)
                if t is not None:
                    out = parts / name
                    rates.reduce_table(con, rates.allowed_units(t, set(ALLOWED_COLS)), const, str(out))
                    outs.append(out)
            for p in (local, f"{work}/membership.parquet"):
                if os.path.exists(p):
                    os.remove(p)
            log(f"{it['source']} {it['key']}: {len(outs)} part(s), {time.time() - t0:,.0f}s")
            if upload_pfx:
                for out in outs:
                    for suf in rates.OUT_SUFFIXES:
                        if os.path.exists(str(out) + suf):
                            s3c.upload_file(str(out) + suf, b, f"{upload_pfx}parts/{out.name}{suf}")
                s3c.put_object(Bucket=b, Key=f"{upload_pfx}done/{name}", Body=b"1")
        con.close()


def status(doc):
    """How many planned items are finished (done markers in storage)."""
    s3c, b = s3()
    done = {k.rsplit("/", 1)[1] for k, _ in ls(s3c, b, f"{PFX}{doc['run_id']}/done/")}
    left = [i for i in doc["items"] if i["lane"] != "none"
            if f"{i['source']}__{i.get('scope', '')}__" + rates.safe_name(i["key"].rsplit("/", 1)[1].rsplit(".", 1)[0]) not in done]
    planned = sum(1 for i in doc["items"] if i["lane"] != "none")
    return dict(planned=planned, done=planned - len(left), left=len(left),
                left_rows=sum(i["rows"] for i in left), left_sample=[i["key"] for i in left[:10]])


def launch(doc, ref, machines=DO_MACHINES):
    """Rent up to DO_MACHINES DigitalOcean machines for the big tables. Each one clones this repo at `ref` (public, no
    key), reads its share of the tables, uploads the parts and deletes itself. Respects Betsy's monthly card cap and the
    machine-share rules (never more than the free slots, never all of them)."""
    sys.path.insert(0, str(ROOT / "insurers"))
    import droplets
    big = [i for i in doc["items"] if i["lane"] == "do"]
    if not big:
        return []
    if droplets.over_cap():
        sys.exit("card spending cap reached for this month: no machines rented (build_approvals.json _card_cap)")
    n = min(machines, len(big), max(0, droplets.room() - 2))
    if n <= 0:
        sys.exit("no free machine slots right now (the November builds have them): run 'start' again later")
    keys = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "STORAGE_ENDPOINT", "STORAGE_REGION", "DIGITALOCEAN_TOKEN"]
    env = "\n".join(f"export {k}='{''.join(os.environ.get(k, '').split())}'" for k in keys)
    made = []
    for i in range(n):
        ud = f"""#!/bin/bash
exec > /root/boot.log 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y python3-venv git
python3 -m venv /root/v && /root/v/bin/pip install -q duckdb==1.5.6 boto3 requests
cat > /root/env.sh <<'ENV'
{env}
ENV
. /root/env.sh
git clone --depth 1 -b {ref} https://github.com/betsyflickinger-max/files.healthcare_price-files-bot.git /root/r
cd /root/r
/root/v/bin/python analysis/medicare_multiple/run.py reduce --state {",".join(doc["states"])} --run {doc["run_id"]} \\
  --lane do --shard {i} --shards {n} --work /root/w --bench /root/w/bench --from-storage > /root/run.log 2>&1
/root/v/bin/python -c "
import sys; sys.path.insert(0, 'bot'); import store; s3, b = store.r2()
s3.upload_file('/root/run.log', b, '{PFX}{doc["run_id"]}/logs/do-{i}.log'); s3.upload_file('/root/boot.log', b, '{PFX}{doc["run_id"]}/logs/do-{i}-boot.log')"
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DIGITALOCEAN_TOKEN" https://api.digitalocean.com/v2/droplets/$ID
"""
        d = droplets.create(f"upfront-mm-{doc['run_id']}-{i}", ud, size=DO_SIZE)
        made.append(d["id"])
        log("rented machine", d["id"], f"upfront-mm-{doc['run_id']}-{i}")
    return made


def _exists(s3c, b, key):
    try:
        s3c.head_object(Bucket=b, Key=key)
        return True
    except Exception:
        return False


def _allowed_table(con, s3c, b, it, work):
    """Flatten one insurer's allowed-amount tar into a temp table (only NPIs in prov)."""
    import tarfile
    import gzip
    p = f"{work}/allowed.tar"
    s3c.download_file(b, it["key"], p)
    keep = {r[0] for r in con.execute("select npi from prov").fetchall()}
    rows = []
    with tarfile.open(p) as tar:
        for m in tar:
            if not m.isfile():
                continue
            raw = tar.extractfile(m).read()
            try:
                raw = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
                doc = json.loads(raw)
            except Exception:
                continue
            rows += [r for r in rates.allowed_rows(doc, it["insurer"]) if r["npi"] in keep]
    os.remove(p)
    if not rows:
        return None
    cols = ALLOWED_COLS
    con.execute("create or replace temp table allowed (" + ", ".join(f"{c} {'double' if c == 'allowed_amount' else 'varchar'}" for c in cols) + ")")
    con.executemany(f"insert into allowed values ({', '.join('?' * len(cols))})", [[r[c] for c in cols] for r in rows])
    return "allowed"


ALLOWED_COLS = ["insurer", "plan", "code_type", "code", "tin", "npi", "billing_class", "modifier", "service_code", "allowed_amount",
                "plan_market_type", "plan_id_type", "plan_id"]


# ------------------------------------------------------------------ commands

def cmd_bench(a):
    cms.fetch(a.cache, a.states)
    cms.build(a.cache, a.bench, a.states)


def cmd_local(a):
    """Small runs and tests: local insurer tables / hospital rows, local provider list, no storage."""
    con = duck(a.work)
    rates.register_bench(con, a.bench, f"read_csv('{a.prov}', all_varchar=true)" if a.prov.endswith(".csv") else f"read_parquet('{a.prov}')", a.states)
    parts = Path(a.work) / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    import glob
    segs = {}
    if a.xwalk:    # local plan-network crosswalk parquet(s) (tests, small samples)
        segs = segments.network_segments(con, f"read_parquet('{a.xwalk}', union_by_name=true)",
                                         f"read_parquet('{a.f5500}')" if a.f5500 else None)
    for p in sorted(glob.glob(a.insurer)) if a.insurer else []:
        t = f"read_parquet('{p}')"
        have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
        m = p.replace("/rates/", "/membership/")
        sg = segments.table_segment(Path(p).stem, segs)
        units = rates.insurer_units(t, have, f"read_parquet('{m}')" if m != p and os.path.exists(m) else None,
                                    seg=(sg["segment"], sg["method"]) if sg else None)
        n = Path(p).stem
        rates.reduce_table(con, units, dict(source="insurer", scope="local", table_name=n), str(parts / f"insurer__{n}"))
    for spec_ in a.hospital or []:
        p, ccn, st = spec_.split(":")
        con.execute("create or replace temp table hosp as select ? ccn, ? state", [ccn, st])
        t = f"read_parquet('{p}')" if p.endswith(".parquet") else f"read_csv('{p}', all_varchar=true)"
        have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
        rates.reduce_table(con, rates.hospital_units(t, have), dict(source="hospital", scope="local", table_name=ccn),
                           str(parts / f"hospital__{ccn}"))
    if a.allowed:
        t = f"(select * replace (try_cast(allowed_amount as double) as allowed_amount) from read_csv('{a.allowed}', header=true, all_varchar=true))"
        have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
        rates.reduce_table(con, rates.allowed_units(t, have), dict(source="allowed", scope="local", table_name="allowed"),
                           str(parts / "allowed__local"))
    for st in a.states:
        print(summ.summarize(con, parts, a.bench, Path(a.out) / st.lower(), st))


def _bench_to_storage(s3c, b, bench, run_id):
    for f in Path(bench).glob("*"):
        s3c.upload_file(str(f), b, f"{PFX}{run_id}/bench/{f.name}")


def _bench_from_storage(s3c, b, bench, run_id):
    Path(bench).mkdir(parents=True, exist_ok=True)
    for k, _ in ls(s3c, b, f"{PFX}{run_id}/bench/"):
        s3c.download_file(b, k, str(Path(bench) / k.rsplit("/", 1)[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["bench", "plan", "estimate", "start", "reduce", "status", "summarize", "local"])
    ap.add_argument("--state", default="TX", help="two-letter code(s), comma-separated, or ALL")
    ap.add_argument("--run", default="", help="run id (default: <state>-<yyyy-mm>)")
    ap.add_argument("--cache", default="/tmp/mm/cms")
    ap.add_argument("--bench", default="/tmp/mm/bench")
    ap.add_argument("--work", default="/tmp/mm/work")
    ap.add_argument("--out", default=str(ROOT / "reports" / "medicare-multiple"))
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--lane", default="gh", choices=["gh", "do"])
    ap.add_argument("--ref", default="main", help="start: the branch the rented machines clone")
    ap.add_argument("--machines", type=int, default=DO_MACHINES, help="start: most rented machines at once")
    ap.add_argument("--gh-max-rows", type=int, default=GH_MAX_ROWS,
                    help="plan: tables up to this many rows go to GitHub's free machines (0 = every insurer table on rented machines)")
    ap.add_argument("--from-storage", action="store_true", help="reduce: read the run's plan and benchmark from storage")
    ap.add_argument("--force", action="store_true", help="summarize even if some planned tables aren't done (they are listed)")
    ap.add_argument("--prov", default="")
    ap.add_argument("--insurer", default="")
    ap.add_argument("--hospital", action="append")
    ap.add_argument("--allowed", default="")
    ap.add_argument("--xwalk", default="", help="local: plan-network crosswalk parquet(s) for market segments")
    ap.add_argument("--f5500", default="", help="local: Form 5500 health plans parquet (column ein)")
    ap.add_argument("--no-spec", action="store_true", help="skip the specialty-mismatch label (needs reference/specialty in storage)")
    a = ap.parse_args()
    a.states = [x.strip().upper() for x in a.state.split(",")]
    run_id = a.run or f"{'all' if 'ALL' in a.states else '-'.join(x.lower() for x in a.states)}-{time.strftime('%Y-%m')}"
    os.makedirs(a.work, exist_ok=True)
    if a.cmd == "local":
        return cmd_local(a)
    if a.cmd == "bench":
        return cmd_bench(a)
    s3c, b = s3()
    pk = f"{PFX}{run_id}/plan.json"
    if a.cmd in ("plan", "estimate", "start"):
        if a.cmd == "plan" or not _exists(s3c, b, pk):
            doc = plan(a.states, run_id, a.work, a.gh_max_rows)
        else:
            doc = json.loads(s3c.get_object(Bucket=b, Key=pk)["Body"].read())
        est = estimate(doc, machines=a.machines)
        key, ok_usd = approved(a.states)
        limit = ok_usd or MM_LIMIT_USD
        est.update(run_id=run_id, limit_usd=limit, approval_key=key,
                   verdict="ok" if est["total_usd"] <= limit else "over the limit: needs Betsy's OK")
        s3c.put_object(Bucket=b, Key=f"{PFX}{run_id}/estimate.json", Body=json.dumps(est, indent=1).encode())
        json.dump(est, open(f"{a.work}/estimate.json", "w"), indent=1)
        print(json.dumps(est, indent=1), flush=True)
        if a.cmd == "start":
            if est["verdict"] != "ok":
                sys.exit(f"stopped before reading anything: estimate ${est['total_usd']} > ${limit} "
                         f"(Betsy: add \"{key}\": {{\"usd\": N}} to build_approvals.json to allow more)")
            cmd_bench(a)
            _bench_to_storage(s3c, b, a.bench, run_id)
            launch(doc, a.ref, a.machines)
        return
    doc = json.loads(s3c.get_object(Bucket=b, Key=pk)["Body"].read())
    if a.cmd == "status":
        print(json.dumps(status(doc), indent=1))
        return
    if a.cmd == "reduce":
        est = json.loads(s3c.get_object(Bucket=b, Key=f"{PFX}{run_id}/estimate.json")["Body"].read())
        if est["verdict"] != "ok":
            sys.exit(f"not reading: estimate ${est['total_usd']} is over ${est['limit_usd']}")
        if a.from_storage or not Path(a.bench, "pfs.csv").exists():
            _bench_from_storage(s3c, b, a.bench, run_id)
        its = sorted([i for i in doc["items"] if i["lane"] == a.lane], key=lambda i: -i["rows"])
        shares = [[] for _ in range(a.shards)]          # biggest first, each to the least-loaded shard
        for i in its:
            min(shares, key=lambda sh: sum(x["rows"] + 1 for x in sh)).append(i)
        hosp_npis = [(n, i["ccn"]) for i in doc["items"] if i["source"] == "hospital" for n in i.get("file_npis") or []]
        reduce_items(shares[a.shard], doc["states"], a.bench, a.work, f"{PFX}{run_id}/", spec=not a.no_spec, lane=a.lane,
                     hosp_npis=hosp_npis)
        return
    if a.cmd == "summarize":
        st = status(doc)
        if st["left"] and not a.force:
            sys.exit(f"{st['left']} of {st['planned']} planned tables aren't done yet ({st['left_sample'][:3]} ...); "
                     "run again later, or with --force to summarize what is there")
        if not Path(a.bench, "pfs.csv").exists():
            _bench_from_storage(s3c, b, a.bench, run_id)
        parts = Path(a.work) / "parts"
        parts.mkdir(parents=True, exist_ok=True)
        for k, _ in ls(s3c, b, f"{PFX}{run_id}/parts/"):
            p = parts / k.rsplit("/", 1)[1]
            if not p.exists():
                s3c.download_file(b, k, str(p))
        con = duck(a.work)
        for x in (sorted(cms.STATE_NAMES) if "ALL" in a.states else a.states):
            hm = hospital_match_rows(doc, x)
            log(x, summ.summarize(con, parts, a.bench, Path(a.out) / x.lower(), x, hospital_matches=hm,
                                  notes=[f"Market segments: {doc.get('segment_note', 'not recorded')}"]))
        if st["left"]:
            for x in (sorted(cms.STATE_NAMES) if "ALL" in a.states else a.states):
                f = Path(a.out) / x.lower() / "summary.md"
                if f.exists():
                    f.write_text(f"> **Not complete:** {st['left']} of {st['planned']} planned tables were not read yet "
                                 f"({st['left_rows']:,} rows). Figures below cover only what was read.\n\n" + f.read_text())


if __name__ == "__main__":
    main()
