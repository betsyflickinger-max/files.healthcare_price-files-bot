"""Insurer side (version 2), run daily on GitHub:  python insurers/bot.py [--dry-run] [--only SLOT,...]

  1. Collect: read results from rented machines; mark each network processed or failed;
     delete any bot machine older than 2 days (cost safety net).
  2. Check: for every network in networks.csv, find this month's file (find_links.py) and decide,
     without downloading it, whether it changed (same ETag, or same size + same internal
     last_updated_on = unchanged; the same rules as 06g_check_changed.py).
  3. Launch: rent one machine per insurer group that has changed files (worker.py reads them and
     deletes itself). Nothing is launched for a network that is already being read.

State lives in R2: bot/insurers/manifest.csv (one row per network), runs/<run_id>/ (job lists,
results, logs). Unchanged networks get last_checked = today, which the site uses as "checked on".
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from botocore.exceptions import ClientError

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bot")]
import check  # noqa: E402
import droplets  # noqa: E402
import find_links  # noqa: E402
import fleet  # noqa: E402
import store  # noqa: E402

P = "bot/insurers/"
SCOPES = {  # name: (state prefix in R2, provider list, where tables go)
    "dfw": ("bot/insurers/", "data/2026-09-29/dfw_npis_all.parquet", "data/full/"),
    "tx": ("bot/insurers/tx/", "data/scope/tx_npis_all.parquet", "data/tx/"),
    # first national batch: TN, CO, OK, AL, MS, MO, GA in one provider list ("Build provider list" with TN,CO,OK,AL,MS,MO,GA and s7)
    "s7": ("bot/insurers/s7/", "data/scope/s7_npis_all.parquet", "data/s7/"),
    # North Carolina (Oct 16, 2026): its own provider list ("Build provider list" with NC and nc) and network list
    "nc": ("bot/insurers/nc/", "data/scope/nc_npis_all.parquet", "data/nc/"),
    # Connecticut (Oct 16, 2026): same pattern as North Carolina (provider list "Build provider list" with CT and ct)
    "ct": ("bot/insurers/ct/", "data/scope/ct_npis_all.parquet", "data/ct/"),
    # Illinois (Oct 18, 2026): same pattern (provider list "Build provider list" with IL and il); pick list claude/illinois-pick-list.md
    "il": ("bot/insurers/il/", "data/scope/il_npis_all.parquet", "data/il/"),
    # Next five states (Oct 19, 2026; Betsy approved claude/next-five-pick-lists.md): New York, California, Virginia + DC,
    # Florida, Wisconsin as ONE scope, so the national UnitedHealthcare/Cigna/Aetna files are read once for all of them
    # (provider list "Build provider list" with NY,CA,VA,DC,FL,WI and n5); tx_split.py splits rows by practice state
    "n5": ("bot/insurers/n5/", "data/scope/n5_npis_all.parquet", "data/n5/"),
    # Healthfirst (NY marketplace), Oct 20, 2026 (Betsy: yes, in as many pieces as needed): 6,137 plain-JSON files, about
    # 2 TB, read in its own scope so the five states' pages don't wait on it; its New York tables join New York's build later
    "nyhf": ("bot/insurers/nyhf/", "data/scope/nyhf_npis_all.parquet", "data/nyhf/"),
    # Arkansas (Oct 20, 2026; Betsy: ahead of CT, IL and n5): own provider list ("Build provider list" with AR and ar);
    # pick list claude/arkansas-pick-list.md. Arkansas Blue Cross is left out while every part 1 of its files is missing (404).
    "ar": ("bot/insurers/ar/", "data/scope/ar_npis_all.parquet", "data/ar/"),
    # Maryland, New Mexico and Montana (Oct 22, 2026; Betsy OK'd batches 1-2 of claude/pick-lists-oct21.md): one area so the
    # national files are read once for all three. Provider list "Build provider list" with MD,NM,MT and b1.
    "b1": ("bot/insurers/b1/", "data/scope/b1_npis_all.parquet", "data/b1/"),
    # Louisiana (Oct 22, 2026; Betsy OK'd batch 3). Provider list "Build provider list" with LA and la.
    "la": ("bot/insurers/la/", "data/scope/la_npis_all.parquet", "data/la/"),
    # Skipped-network check (Oct 21, 2026; Betsy OK'd the full 102 GB sample): 20 UnitedHealthcare/Aetna networks the pick
    # lists leave out, read with Illinois's provider list into their own folder (no state build reads data/skipil/);
    # insurers/skip_check.py compare checks their prices against Illinois's kept networks.
    "skipil": ("bot/insurers/skipil/", "data/scope/il_npis_all.parquet", "data/skipil/"),
}
NETWORKS = {"s7": "networks_s7.csv", "nc": "networks_nc.csv", "ct": "networks_ct.csv", "il": "networks_il.csv", "n5": "networks_n5.csv", "nyhf": "networks_nyhf.csv", "ar": "networks_ar.csv", "b1": "networks_b1.csv", "la": "networks_la.csv", "skipil": "networks_skipil.csv"}  # an area's own network list; dfw and tx use networks.csv
REPO = "https://github.com/betsyflickinger-max/price-files-bot"
FIELDS = ["slot", "insurer", "network_label", "machine_group", "url", "url_date", "table", "etag", "size",
          "file_last_updated_on", "rows", "status", "detail", "last_checked", "last_changed", "processed_on",
          "run_id", "droplet_id", "launched_at", "fails", "problem", "next_url", "reader", "backfill"]
# Reader version (Oct 13, 2026): tables read by an older reader lack the newly kept fields (insurer notes, bundled codes,
# covered services, code version). When a machine slot is free, the bot re-reads those files, new files always first.
READER = "2"
REREAD_OLD_TABLES = True
# Oct 15, 2026: such a re-read (an unchanged file, tables from an older reader) only collects the fields kept since Oct 13,
# so it streams the file once and writes just those to <scope>/fields/ (worker.py fields_only) instead of re-writing
# every price row. Aetna national files took 3+ hours per scope the full way. False = re-read in full as before.
REREAD_FIELDS_ONLY = True
SIZES = {"uhc": "s-8vcpu-16gb-amd", "aetna": "s-8vcpu-16gb-amd", "bcbs": "s-8vcpu-16gb-amd", "bcbstx": "s-8vcpu-32gb-amd", "cigna": "s-8vcpu-32gb-amd"}  # 320 GB disk for the biggest files; BCBSTX reader needs >8 GB (OOM Oct 11)
# Oct 12, 2026: DigitalOcean answered "Size is not available in this region" for s-4vcpu-8gb in nyc3, nyc1 and sfo3, so the
# last Texas Cigna file (Pathwell OAP) could not start; s-8vcpu-32gb-amd was renting fine in nyc3 (and Cigna ran out of memory before).
# Oct 14, 2026: no more fixed files-per-machine batches. Every waiting file is one job in the shared queue
# (insurers/fleet.py); each machine keeps taking the next job it is big enough for until none are left.
RESERVE = 0  # slots to leave free for other jobs; 0 = use every free machine
ST_ROOM = fleet.ST_ROOM  # while the seven-state website build runs, leave this many machines free for it
SCOPE = "dfw"  # biggest files; anything else: 4 vCPU / 8 GB
# Machine cap (Oct 14, 2026): no fixed number. droplets.room() reads the account's live limit from DigitalOcean on
# every pass, so a raised limit is used on the very next 10-minute pass (was a hard-coded 14, then 9 before Oct 13).
STUCK_HOURS = 48
STALE_DAYS = 45      # flag a network whose file hasn't changed in this long
PEEK = 256 * 1024


def url_date(u):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", u) or re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", u)
    if not m:
        return ""
    return m.group(1) if len(m.groups()) == 1 else f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def peek(url):
    """Headers plus last_updated_on from the first 256 KB. Never downloads the whole file."""
    h = {"User-Agent": check.UA, "Range": f"bytes=0-{PEEK - 1}"}
    with requests.get(url, headers=h, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        head = r.raw.read(PEEK, decode_content=False)
        size = ""
        cr = r.headers.get("Content-Range", "")
        if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
            size = cr.rsplit("/", 1)[1]
        elif r.status_code == 200:
            size = r.headers.get("Content-Length", "")
        etag = r.headers.get("ETag", "").replace("W/", "").strip('"')
    if head.lstrip()[:1] == b"<":
        raise ValueError("link opens a web page, not a price file")
    if head[:2] == b"\x1f\x8b":
        try:
            head = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(head)
        except zlib.error:
            head = b""
    m = re.search(rb'"last_updated_on"\s*:\s*"([^"]*)"', head)
    return dict(etag=etag, size=size, file_last_updated_on=m.group(1).decode() if m else "")


def stem_of(url):
    """Table name a link produces (same naming as worker.stem / 06f)."""
    name = url.split("?")[0].rsplit("/", 1)[-1]
    for ext in (".gz", ".json", ".zip", ".7z"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name[:180]


def gone_back(n, m, url, err, today):
    """Oct 15, 2026: the bot took a 403 on a guessed 2026-10-15 Curative link as "file exists" (fixed in find_links),
    queued it, and the network sat at "failed" on a link that leads to no file. When the current link is refused or missing (403/404/410) and it is newer
    than the file our table came from, look again from the table's date and return the newest link that answers."""
    code = getattr(getattr(err, "response", None), "status_code", None)
    t = re.search(r"\d{4}-\d{2}-\d{2}", m.get("table", ""))
    if code not in (403, 404, 410) or url != m.get("url") or not t or stem_of(url) == m.get("table"):
        return ""
    since = date.fromisoformat(t.group(0)) - timedelta(days=1)
    f = find_links.find(dict(n, current_url=""), today, since)
    return f["url"] if f.get("found") and f["url"] != url else ""


def load(s3, b, scope):
    man = {r["slot"]: r for r in store.read_csv(s3, b, P + "manifest.csv")}
    for n in csv.DictReader(open(HERE / NETWORKS.get(scope, "networks.csv"))):
        if n["slot"] in man:
            pass
        elif scope == "dfw" and n.get("current_table"):  # first run: start from the tables already in R2
            man[n["slot"]] = dict(slot=n["slot"], insurer=n["insurer"], network_label=n["network_label"],
                                  machine_group=n["machine_group"], url=n["current_url"],
                                  url_date=url_date(n["current_url"]), table=n["current_table"],
                                  file_last_updated_on=n["last_updated_on"], status="processed",
                                  processed_on="(before the bot)", fails="0")
        else:  # a new area, or a network added later (no table yet): read it once
            man[n["slot"]] = dict(slot=n["slot"], insurer=n["insurer"], network_label=n["network_label"],
                                  machine_group=n["machine_group"], url=n["current_url"],
                                  url_date=(date.today() - timedelta(days=40)).isoformat(), table="",
                                  status="new", fails="0")
        man[n["slot"]]["_net"] = n
    return man


def collect(s3, b, man, now, dry):
    notes = []
    try:  # the shared machine queue: clear claims of machines that are gone, so their files go back in line
        alive = {str(d[0]) for d in droplets.mine()}
    except Exception as e:
        alive = None
        print("could not list machines:", e)
    qjobs, qclaims = fleet.jobs(s3, b), fleet.claims(s3, b)
    if alive is not None and not dry:
        def save(j, res):
            res.update(kind=j.get("kind", "insurer"), state=j.get("state", ""), ccns=j.get("ccns", []))
            s3.put_object(Bucket=b, Key=j["done_key"], Body=json.dumps(res).encode())
        for n in fleet.reap(s3, b, qjobs, qclaims, alive, save):
            print("queue:", n)
    for m in man.values():
        if m.get("status") != "running":
            continue
        key = f"{P}runs/{m['run_id']}/done/{m['slot']}.json"
        try:
            res = json.loads(s3.get_object(Bucket=b, Key=key)["Body"].read())
        except Exception:
            jid = fleet.job_id(SCOPE, m["slot"])
            if jid in qjobs:  # in the shared queue: only the time on a machine counts toward "stuck"
                c = qclaims.get(jid)
                if not c:
                    m["detail"] = "in the machine queue, waiting for a free machine"
                    continue
                if fleet.age_mins(c.get("claimed_at", "")) / 60 <= STUCK_HOURS:
                    m["detail"] = f"being read on {c.get('name')} since {c.get('claimed_at', '')[:16].replace('T', ' ')} UTC"
                    continue
                if not dry:  # a machine stuck on one file: return it and take the file out of line
                    droplets.delete(c.get("droplet_id"))
                    fleet.finish(s3, b, jid)
                m.update(status="failed", detail=f"machine gave no result in {STUCK_HOURS} hours", fails=str(int(m.get("fails") or 0) + 1))
                notes.append(("failed", m))
                continue
            age = (now - datetime.fromisoformat(m["launched_at"].replace("Z", "+00:00"))).total_seconds() / 3600
            if age > STUCK_HOURS:
                m.update(status="failed", detail=f"machine gave no result in {STUCK_HOURS} hours", fails=str(int(m.get("fails") or 0) + 1))
                notes.append(("failed", m))
            continue
        if res.get("ok") and res.get("fields_only"):   # prices unchanged: keep the table, its rows and dates
            m.update(status="processed", reader=READER, backfill="", fails="0", processed_on=res.get("finished_at", "")[:10],
                     detail=f"new fields collected in {res.get('secs', '?')}s (prices unchanged, price tables kept)")
            continue
        if res.get("ok"):
            old_rows = m.get("rows", "")
            reread = m.get("backfill") == "1"   # an unchanged file re-read for the new fields: its prices didn't change
            m.update(status="processed", table=res["table"], rows=str(res.get("rows", "")), reader=READER, backfill="",
                     file_last_updated_on=res.get("file_last_updated_on", m.get("file_last_updated_on", "")),
                     processed_on=res.get("finished_at", "")[:10],
                     last_changed=m.get("last_changed", "") if reread else res.get("finished_at", "")[:10],
                     fails="0", detail=f"read in {res.get('secs', '?')}s" + (f"; retired {res['retired']}" if res.get("retired") else ""))
            if old_rows.isdigit() and int(old_rows) > 0 and int(m["rows"] or 0) < int(old_rows) / 2:
                m["detail"] += f"; rows fell from {int(old_rows):,} to {int(m['rows']):,}"
                notes.append(("rows dropped", m))
        else:
            m.update(status="failed", detail=res.get("error", "unknown error")[:300], fails=str(int(m.get("fails") or 0) + 1))
            notes.append(("failed", m))
    # cost safety net. Old fixed-list machines: any older than STUCK_HOURS is deleted. Queue machines may run as long
    # as there is work, so one is deleted only if it has held no job for an hour (stuck starting up or failed to exit).
    try:
        # Oct 16, 2026: one look at the claims caught a busy machine between two files and deleted it mid-read
        # (Anthem Georgia 102_11D0 part 7). Now a machine must be seen idle on two passes at least 20 minutes apart
        # (first sighting saved in R2) and still hold no claim on a fresh read just before deleting.
        busy = {str(c.get("droplet_id")) for c in qclaims.values()}
        idle_key = "bot/fleet/idle_seen/"
        for did, name, created in droplets.mine():
            age = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 3600
            if name.startswith(fleet.NAME):
                if dry or age <= 1:
                    continue
                k = f"{idle_key}{did}.json"
                if str(did) in busy:
                    try:
                        s3.delete_object(Bucket=b, Key=k)
                    except Exception:
                        pass
                    continue
                seen = fleet._get(s3, b, k)
                if not seen:
                    s3.put_object(Bucket=b, Key=k, Body=json.dumps(dict(name=name, first_idle=fleet.iso())).encode())
                    continue
                if fleet.age_mins(seen.get("first_idle", "")) < 20:
                    continue
                if str(did) in {str(c.get("droplet_id")) for c in fleet.claims(s3, b).values()}:
                    s3.delete_object(Bucket=b, Key=k)
                    continue
                droplets.delete(did)
                s3.delete_object(Bucket=b, Key=k)
                print(f"deleted idle queue machine {name} ({age:.1f} h old, no job for 20+ minutes)")
            elif age > STUCK_HOURS and not dry:
                droplets.delete(did)
                print(f"deleted leftover machine {name} ({age:.0f} h old)")
    except Exception as e:
        print("could not list machines:", e)
    return notes


def check_all(man, today, only, force=False):
    notes = []
    for m in man.values():
        n = m["_net"]
        if n.get("enabled", "yes") != "yes" or (only and m["slot"] not in only) or m.get("status") == "running":
            continue
        since = date.fromisoformat(m["url_date"]) if m.get("url_date") else today - timedelta(days=40)
        f = find_links.find(dict(n, current_url=m["url"]), today, since)
        url = f["url"] or m["url"]
        if f.get("error") and url == m["url"]:  # the file we have is gone and no newer one was found
            m.update(last_checked=today.isoformat(), detail=f"{f['how']}; keeping the last good tables")
            notes.append(("link broken", m))
            continue
        try:
            info = peek(url)
        except Exception as e:
            m["last_checked"] = today.isoformat()
            back = gone_back(n, m, url, e, today)
            if back:  # the newer link leads nowhere: go back to the newest file that still answers
                url = back
                try:
                    info = peek(url)
                except Exception:
                    info = None
                if info is not None and stem_of(url) == m.get("table"):
                    m.update(status="processed", url=url, url_date=url_date(url) or m.get("url_date", ""), fails="0",
                             etag=info["etag"] or m.get("etag", ""), size=info["size"] or m.get("size", ""),
                             detail="newer link led to no file; back on the newest file that is up (tables unchanged)")
                    notes.append(("dead link replaced", m))
                    continue
                if info is None:
                    info = dict(etag="", size="", file_last_updated_on="")
            elif url == m["url"]:
                m["detail"] = f"could not check the file: {type(e).__name__}: {str(e)[:150]}"
                notes.append(("check failed", m))
                continue
            info = dict(etag="", size="", file_last_updated_on="")
        same = False
        if m.get("status") == "processed":
            if info["etag"] and info["etag"] == m.get("etag"):
                same, why = True, "same ETag"
            elif info["file_last_updated_on"] and info["file_last_updated_on"] == m.get("file_last_updated_on") \
                    and (not m.get("size") or info["size"] == m.get("size")):
                same, why = True, "same internal date" + (" and size" if m.get("size") else "")
        m["last_checked"] = today.isoformat()
        if same and force and only:  # --force with --only: re-read it anyway (e.g. to fill in newly kept fields)
            same = False
        if same and REREAD_OLD_TABLES and m.get("reader") != READER and m.get("table"):
            m.update(status="queued", next_url=url, backfill="1", etag=info["etag"] or m.get("etag", ""), size=info["size"] or m.get("size", ""),
                     detail=f"unchanged ({why}); re-reading when a machine is free to collect the newly kept fields")
            continue
        if same:
            m.update(etag=info["etag"] or m.get("etag", ""), size=info["size"] or m.get("size", ""),
                     url=url, url_date=url_date(url) or m.get("url_date", ""), detail=f"unchanged ({why})")
            if m.get("last_changed") and (today - date.fromisoformat(m["last_changed"])).days > STALE_DAYS:
                notes.append(("stale", m))
            continue
        if m.get("status") == "failed" and int(m.get("fails") or 0) >= 3 and url == m["url"] and not (force and only):
            continue  # gave up on this file; it's in the issue already
        if m.get("status") == "failed" and url == m["url"]:
            m.update(status="queued", next_url=url, detail=f"retry {m.get('fails')} of 3: {(m.get('detail') or '')[:150]}")
            continue
        m.update(status="queued", next_url=url, etag=info["etag"], size=info["size"],
                 detail=f"{f['how']}; internal date {info['file_last_updated_on'] or '?'}")
    return notes


def user_data(env):
    """Start-up script for a queue machine: install, then take jobs from the shared queue until none are left."""
    exports = "\n".join(f"export {k}='{v}'" for k, v in env.items())
    return f"""#!/bin/bash
exec > /var/log/job.log 2>&1
set -x
export DEBIAN_FRONTEND=noninteractive HOME=/root
{exports}
apt-get update -y && apt-get install -y python3-venv git curl
curl -sL https://go.dev/dl/go1.26.9.linux-amd64.tar.gz | tar -C /usr/local -xz
export PATH=$PATH:/usr/local/go/bin
git clone --depth 1 {REPO} /opt/bot
cd /opt/bot/insurers/pipeline/mrfrows && go build -o mrfrows . && cd /opt/bot
python3 -m venv /opt/venv && /opt/venv/bin/pip install -q -r insurers/requirements-worker.txt -r requirements.txt
/opt/venv/bin/python insurers/worker.py
# if the worker died before deleting the machine, delete it now
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DIGITALOCEAN_TOKEN" https://api.digitalocean.com/v2/droplets/$ID
"""


def launch(s3, b, man, now, dry):
    """Put this area's waiting files in the shared queue, then rent one machine per unclaimed job (biggest first)
    until the account's live machine limit is reached. Machines keep taking jobs until none are left, so files that
    don't get a machine now are picked up by the first machine that frees up."""
    queued = [m for m in man.values() if m.get("status") == "queued" and m.get("next_url")]
    # Oct 20, 2026: a new area's files wait until its provider list exists (workflow "Build provider list"), instead of
    # renting machines that would fail on the missing list. They go in line on the first pass after it appears.
    if queued and not dry:
        try:
            s3.head_object(Bucket=b, Key=SCOPES[SCOPE][1])
        except ClientError:
            print(f"queue: {len(queued)} {SCOPE} files wait for the provider list {SCOPES[SCOPE][1]}")
            return fill(s3, b, now)
    run_id = now.strftime("%Y%m%d-%H%M")
    for m in queued:
        size = SIZES.get(m["machine_group"], droplets.DEFAULT_SIZE)
        job = dict(id=fleet.job_id(SCOPE, m["slot"]), kind="insurer", scope=SCOPE, slot=m["slot"], url=m["next_url"],
                   network_label=m["network_label"], prev_table=m.get("table", ""), group=m["machine_group"],
                   size=size, mem=fleet.mem_gb(size), backfill="1" if m.get("backfill") == "1" else "",
                   fields_only="1" if m.get("backfill") == "1" and REREAD_FIELDS_ONLY else "",
                   run_id=run_id, done_key=f"{P}runs/{run_id}/done/{m['slot']}.json", out_prefix=SCOPES[SCOPE][2],
                   scope_key=SCOPES[SCOPE][1], hold_key=P + "hold.txt")
        if dry:
            print(f"[dry run] would queue {job['id']} ({size})")
            continue
        fleet.put_job(s3, b, job)
        u = m.pop("next_url")
        m.update(status="running", run_id=run_id, launched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), droplet_id="",
                 url=u, url_date=url_date(u) or m.get("url_date", ""),
                 detail="in the machine queue, waiting for a free machine")
    if dry:
        return []
    return fill(s3, b, now)


def fill(s3, b, now):
    """Rent machines for unclaimed queue jobs, up to the account's live limit. Returns [(machine name, job id)]."""
    try:
        everyone = droplets.names()
        ours = droplets.fleet()
        free = droplets.room() - RESERVE
    except Exception as e:
        print("could not read machines or the account limit:", e)
        return []
    if any(n.startswith("upfront-site-") for n in everyone):   # Oct 22: any page build (was the seven-state build only)
        free -= ST_ROOM
    else:   # Oct 18, 2026: a state build is waiting to start (orchestrate_states.py asks within the last 2 hours)
        try:
            w = json.loads(s3.get_object(Bucket=b, Key="bot/fleet/build_wants_room.json")["Body"].read())
            if time.time() - float(w.get("at", 0)) < 2 * 3600:
                free -= ST_ROOM
                print(f"queue: leaving {ST_ROOM} slots for waiting website build {w.get('build')}")
        except Exception:
            pass
    qjobs, qclaims = fleet.jobs(s3, b), fleet.claims(s3, b)
    held = fleet.held_scopes(s3, b, qjobs, everyone)
    for sc, why in held.items():
        print(f"queue: {sc} files not started: {why}")
    want = fleet.plan(qjobs, qclaims, held, ours, free, fleet.idle_dedicated(s3, b, qclaims))
    env = {k: store.env(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
                                     "DIGITALOCEAN_TOKEN", "BOT_GITHUB_TOKEN", "IA_ACCESS_KEY", "IA_SECRET_KEY")}
    launched, stamp = [], now.strftime("%Y%m%d-%H%M")
    for i, (size, job) in enumerate(want, 1):
        name = f"{fleet.NAME}{fleet.mem_gb(size)}g-{stamp}-{i:02d}"
        try:
            droplets.create(name, user_data(env), size)
        except Exception as e:
            print(f"could not rent a machine for {job['id']}: {str(e)[:200]}")
            break  # the account or region is full; the next pass tries again
        launched.append((name, job["id"]))
    waiting = len([j for jid, j in qjobs.items() if jid not in qclaims])
    print(f"queue: {len(qjobs)} jobs, {len(qclaims)} being read, {waiting} waiting; "
          f"{len(ours)} queue machines running, {max(free, 0)} free slots, rented {len(launched)}")
    return launched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="check only; rent nothing, change nothing in R2")
    ap.add_argument("--only", default="", help="comma-separated slots")
    ap.add_argument("--force", action="store_true", help="with --only: re-read those files even if unchanged")
    ap.add_argument("--fill", action="store_true", help="quick pass: collect results and fill free machines, no file check")
    ap.add_argument("--scope", default="dfw", choices=sorted(SCOPES), help="dfw (default), tx (all of Texas), s7 (first national batch) or nc (North Carolina)")
    a = ap.parse_args()
    global P, SCOPE
    SCOPE, P = a.scope, SCOPES[a.scope][0]
    s3, b = store.r2()
    now = datetime.now(timezone.utc)
    today = now.date()
    man = load(s3, b, a.scope)
    notes = collect(s3, b, man, now, a.dry_run)
    if not a.fill:
        notes += check_all(man, today, {s.strip() for s in a.only.split(",") if s.strip()}, a.force)
    hold = ""
    try:
        hold = s3.get_object(Bucket=b, Key=P + "hold.txt")["Body"].read().decode().strip()
    except Exception:
        pass
    if not hold:  # a new area's machines would fail without its provider list
        try:
            s3.head_object(Bucket=b, Key=SCOPES[a.scope][1])
        except Exception:
            hold = "the provider list for this area isn't built yet (run 'Build provider list' first)"
    if hold:  # e.g. while a site build is reading data/full/rates; delete bot/insurers/hold.txt to resume
        print(f"ON HOLD (bot/insurers/hold.txt): {hold[:200]} -- checking only, no machines rented")
        launched = []
    else:
        launched = launch(s3, b, man, now, a.dry_run)
    # Only raise an issue the first time a problem appears (Molina's 47 dead links shouldn't open one every day)
    flagged = {}
    for k, m in notes:
        flagged.setdefault(m["slot"], (k, m))
    new_problems = []
    for m in man.values():
        k = flagged.get(m["slot"], ("", m))[0]
        if k == "stale" and today.day != 20:
            k = m.get("problem", "") if m.get("problem") == "stale" else ""
        if k and k != m.get("problem", ""):
            new_problems.append((k, m))
        if m.get("status") != "running" or k:
            m["problem"] = k
    rows = sorted(man.values(), key=lambda m: (m["insurer"], m["slot"]))
    if not a.dry_run:
        store.write_csv(s3, b, P + "manifest.csv", rows, FIELDS)

    out = HERE.parent / "out"
    out.mkdir(exist_ok=True)
    from collections import Counter
    c = Counter(m.get("status") for m in rows)
    lines = [f"## Insurer files, {today}", "", f"{len(rows)} networks: " + ", ".join(f"{v} {k}" for k, v in c.most_common())]
    if hold:
        lines.append(f"On hold, no machines rented: {hold[:200]}")
    if launched:
        lines.append(f"Rented {len(launched)} queue machines (each keeps taking files until none are left)")
    lines += ["", "| Insurer | Network | Status | Detail |", "|---|---|---|---|"]
    lines += [f"| {m['insurer']} | {m['network_label']} | {m.get('status', '')} | {(m.get('detail') or '').replace('|', '/')[:120]} |" for m in rows]
    (out / "insurer_summary.md").write_text("\n".join(lines) + "\n")
    bad = new_problems
    if bad and not a.dry_run:
        al = [f"{len(bad)} insurer file problem(s) on {today}:", "", "| Problem | Insurer | Network | Detail |", "|---|---|---|---|"]
        al += [f"| {k} | {m['insurer']} | {m['network_label']} | {(m.get('detail') or '').replace('|', '/')[:150]} |" for k, m in bad]
        (out / "insurer_alerts.md").write_text("\n".join(al) + "\n")
    print("\n".join(lines if a.dry_run else lines[:4]))
    why = Counter((m.get("detail") or "no detail")[:160] for m in rows if m.get("status") == "queued")
    for d, n in why.most_common(5):  # why queued files didn't start (machine limit, rent error, site build...)
        print(f"  {n} queued: {d}")
    for k, m in bad:
        print(f"NEW PROBLEM: {k}: {m['insurer']} {m['network_label']}")


if __name__ == "__main__":
    main()
