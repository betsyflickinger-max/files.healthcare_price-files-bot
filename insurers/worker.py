"""Runs on a rented machine: read insurer files and replace their tables in R2, then delete itself.

Queue mode (Oct 14, 2026; the default): claim the next job from the shared queue (insurers/fleet.py) that this
machine is big enough for, read it, save its result, and claim another, until nothing is left that it can take.
Old mode (a fixed list, RUN_ID + GROUP set): R2 bot/insurers/runs/<RUN_ID>/<GROUP>.csv (slot, url, network_label, prev_table).
For each file:
  1. 06f_full_extract.py (unchanged pipeline code): download, read the roster, stream every price for
     every in-scope provider into data/rates/<name>.parquet and data/membership/<name>.parquet.
  2. Upload both to R2 data/full/rates/ and data/full/membership/.
  3. Double-count fix: if this network's previous table had a different name (insurers date their file
     names), move the old tables to history/insurers/<yyyy-mm>/ (kept permanently) so a build over data/full/rates/*.parquet
     counts each network once. The old table is only moved after the new one is safely uploaded.
  4. Upload the file's inventory (06f census) to bot/insurers/census/<yyyy-mm>/<scope>/<table>.json.
  5. Write a result marker: bot/insurers/runs/<RUN_ID>/done/<slot>.json
"""
import csv
import io
import json
import shutil
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import boto3
import duckdb
import requests

HERE = Path(__file__).resolve().parent
PIPE, DATA = HERE / "pipeline", HERE / "data"
E = {k: "".join(os.environ.get(k, "").split()) for k in
     ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "DIGITALOCEAN_TOKEN", "RUN_ID", "GROUP",
      "BOT_GITHUB_TOKEN")}
# Oct 15, 2026: BCBSTX tables are several GB. With boto3's defaults (60 s read timeout, 8 MB parts, 10 at a time) their
# uploads failed (InvalidPart / upload failed), and moving an old table hit "EntityTooLarge" (a one-step copy is capped
# at 5 GB) or timed out. Now: long timeouts with retries, bigger parts a few at a time, a multipart copy, and a whole
# upload is retried before the file is called failed.
from boto3.s3.transfer import TransferConfig  # noqa: E402
from botocore.config import Config  # noqa: E402

s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                  region_name="auto",
                  config=Config(connect_timeout=60, read_timeout=900, retries={"max_attempts": 10, "mode": "adaptive"}))
BIG = TransferConfig(multipart_threshold=64 << 20, multipart_chunksize=256 << 20, max_concurrency=4)
B = E["R2_BUCKET"]


def put(path, key, tries=3):
    """Upload a local file; on failure wait and start the whole upload again (a failed multipart upload can't resume)."""
    for i in range(tries):
        try:
            s3.upload_file(str(path), B, key, Config=BIG)
            return
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"upload of {key} failed ({type(e).__name__}); retrying in {60 * (i + 1)} s", flush=True)
            time.sleep(60 * (i + 1))
RUN = os.environ.get("RUN_PREFIX", "bot/insurers/") + f"runs/{E['RUN_ID']}/"
OUT = os.environ.get("OUT_PREFIX", "data/full/")  # data/full/ = DFW tables, data/tx/ = all of Texas (set per job in queue mode)
SCOPE_KEY = os.environ.get("SCOPE_KEY", "data/2026-09-29/dfw_npis_all.parquet")
SCOPE_FILE = DATA / "scope.parquet"
LOG = []
LOG_KEY = RUN + f"log_{E['GROUP']}.txt"


def log(*a):
    m = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(m, flush=True)
    LOG.append(m)
    try:
        s3.put_object(Bucket=B, Key=LOG_KEY, Body="\n".join(LOG[-3000:]).encode())
    except Exception:
        pass


def stem(name):  # same naming as 06f
    for ext in (".gz", ".json", ".zip", ".7z"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name[:180]


def exists(key):
    try:
        s3.head_object(Bucket=B, Key=key)
        return True
    except Exception:
        return False


HISTORY = "history/insurers/"   # every replaced insurer table, by month replaced; kept permanently


def move(src, dst):
    """Copy then delete. s3.copy does a multipart copy for big tables (copy_object stops at 5 GB); the old table is
    deleted only once the copy exists at the full size."""
    s3.copy({"Bucket": B, "Key": src}, B, dst, Config=BIG)
    if s3.head_object(Bucket=B, Key=dst)["ContentLength"] != s3.head_object(Bucket=B, Key=src)["ContentLength"]:
        raise RuntimeError(f"copy of {src} came out a different size; old table left in place")
    s3.delete_object(Bucket=B, Key=src)


def one(job):
    t0 = time.time()
    url, label = job["url"], job["network_label"]
    src, extra = url, []
    if url.split("?")[0].endswith(".7z"):  # BSW posts 7-Zip archives: unpack the rate file first
        src, extra = unpack_7z(url), ["--source-url", url.split("?")[0]]
    new = stem(Path(src.split("?")[0]).name)
    res = dict(slot=job["slot"], url=url, table=new, prev_table=job.get("prev_table", ""), ok=False)
    if job.get("fields_only") == "1":
        return fields_only(job, src, label, extra, new, res, t0)
    for sub in ("rates", "membership", "codes", "ends"):
        (DATA / sub / f"{new}.parquet").unlink(missing_ok=True)
    p = subprocess.run([sys.executable, str(PIPE / "06f_full_extract.py"), src, "--network", label,
                        "--scope", str(SCOPE_FILE)] + extra, cwd=PIPE, capture_output=True, text=True)
    if src != url:
        Path(src).unlink(missing_ok=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-6:]
    if p.returncode != 0:  # record why: the program's own error, plus any out-of-memory kill
        err = p.stderr.strip().splitlines()[-12:]
        oom = subprocess.run("dmesg 2>/dev/null | grep -iE 'out of memory|killed process' | tail -2; df -h / | tail -1",
                             shell=True, capture_output=True, text=True).stdout.strip().splitlines()
        tail = tail + [f"exit code {p.returncode}"] + err + oom
    log(f"[{job['slot']}]", *tail)
    rates, memb = DATA / "rates" / f"{new}.parquet", DATA / "membership" / f"{new}.parquet"
    if p.returncode != 0 or not rates.exists() or not memb.exists():
        res["error"] = " | ".join(tail)[-1500:] or f"06f exit {p.returncode}"
        if "premature EOF" in res["error"]:  # Oct 15, 2026: Community Health Choice's server stops every file at 128,000 bytes
            res["error"] = ("insurer's file is cut off: it ends partway through the price list (a problem with the "
                            "insurer's file, not the reader) | " + res["error"])[:1500]
        return res
    con = duckdb.connect()
    res["rows"] = con.execute(f"select count(*) from '{rates}'").fetchone()[0]
    res["roster_rows"] = con.execute(f"select count(*) from '{memb}'").fetchone()[0]
    meta = con.execute(f"select any_value(reporting_entity_name), any_value(last_updated_on) from '{memb}'").fetchone()
    res["reporting_entity_name"], res["file_last_updated_on"] = meta[0] or "", meta[1] or ""
    put(rates, f"{OUT}rates/{new}.parquet")
    put(memb, f"{OUT}membership/{new}.parquet")
    rates.unlink(); memb.unlink()
    for sub in ("codes", "ends"):   # code descriptions once per code; per-provider contract end dates
        f = DATA / sub / f"{new}.parquet"
        if f.exists():
            put(f, f"{OUT}{sub}/{new}.parquet")
            f.unlink()
    cen = DATA / "census" / f"{new}.json"   # "what's in the file" inventory; kept per month so history builds up
    if cen.exists():
        try:
            put(cen, f"bot/insurers/census/{date.today().strftime('%Y-%m')}/{OUT.strip('/').replace('/', '_')}/{new}.json")
        except Exception as e:
            log(f"[{job['slot']}] census upload failed: {e}")
        cen.unlink()
    old = job.get("prev_table", "")
    if old and old != new:
        month = date.today().strftime("%Y-%m")
        for sub in ("rates", "membership", "codes", "ends"):
            k = f"{OUT}{sub}/{old}.parquet"
            if exists(k):
                # Oct 15, 2026 (Betsy): never delete a table; old months are kept for price history in history/insurers/
                # (outside work/, which has a 60-day cleanup rule). If archiving keeps failing, the file is reported as
                # failed and the old table stays where it is until the next try; nothing is removed.
                dst = f"{HISTORY}{month}/{OUT.strip('/').replace('/', '_')}/{sub}/{old}.parquet"
                for i in range(3):
                    try:
                        move(k, dst)
                        break
                    except Exception as e:
                        if i == 2:
                            raise RuntimeError(f"could not archive old table {k} after 3 tries ({type(e).__name__}); "
                                               "it was left in place, nothing deleted")
                        time.sleep(60 * (i + 1))
        res["retired"] = old
    res.update(ok=True, secs=round(time.time() - t0))
    return res


def fields_only(job, src, label, extra, new, res, t0):
    """Oct 15, 2026: an unchanged file whose tables came from an older reader. Instead of re-writing every price row
    (billions for Aetna, 3+ hours), stream the file once and keep only the fields the reader has kept since Oct 13
    (06f --fields-only -> data/fields/). Saved next to the existing tables under the existing table's name; the rates
    and membership tables are not touched."""
    name = job.get("prev_table") or new
    f = DATA / "fields" / f"{new}.parquet"
    f.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, str(PIPE / "06f_full_extract.py"), src, "--network", label, "--scope", str(SCOPE_FILE),
                        "--fields-only"] + extra, cwd=PIPE, capture_output=True, text=True)
    if src != job["url"]:
        Path(src).unlink(missing_ok=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-6:]
    if p.returncode != 0:
        tail += [f"exit code {p.returncode}"] + p.stderr.strip().splitlines()[-12:]
    log(f"[{job['slot']}] (new fields only)", *tail)
    if p.returncode != 0 or not f.exists():
        res["error"] = " | ".join(tail)[-1500:] or f"06f exit {p.returncode}"
        return res
    put(f, f"{OUT}fields/{name}.parquet")
    f.unlink()
    res.update(ok=True, fields_only=True, table=name, secs=round(time.time() - t0))
    return res


def unpack_7z(url):
    """Download a .7z and extract its rate file (the largest .json inside). Returns the local path."""
    import py7zr
    arc = DATA / "dl.7z"
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(arc, "wb") as f:
            for ch in r.iter_content(8 << 20):
                f.write(ch)
    out = DATA / "unpacked"
    out.mkdir(exist_ok=True)
    with py7zr.SevenZipFile(arc) as z:
        member = max((i for i in z.list() if i.filename.endswith(".json")), key=lambda i: i.uncompressed).filename
        z.extract(path=out, targets=[member])
    arc.unlink()
    return str(out / member)


def wake_github():
    """Tell GitHub this machine is done, so a waiting file starts right away instead of at the next 10-minute pass."""
    if not E["BOT_GITHUB_TOKEN"]:
        return
    try:
        r = requests.post("https://api.github.com/repos/betsyflickinger-max/price-files-bot/actions/workflows/insurers.yml/dispatches",
                          headers={"Authorization": f"Bearer {E['BOT_GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
                          json={"ref": "main", "inputs": {"dry_run": "false", "fill": "true"}}, timeout=30)
        log(f"asked GitHub to fill this slot: HTTP {r.status_code}")
    except Exception as e:
        log("could not reach GitHub (the 10-minute pass will fill the slot):", e)


def self_delete():
    try:
        did = requests.get("http://169.254.169.254/metadata/v1/id", timeout=5).text.strip()
        requests.delete(f"https://api.digitalocean.com/v2/droplets/{did}",
                        headers={"Authorization": f"Bearer {E['DIGITALOCEAN_TOKEN']}"}, timeout=30)
    except Exception as e:
        log("self-delete failed (the GitHub side deletes leftover machines after 2 days):", e)


def me():
    """This machine: its DigitalOcean id, name and memory (read from DigitalOcean, since the launcher may have had to
    take a different size than it asked for)."""
    if os.environ.get("GHA_WORKER"):   # Oct 18, 2026: a free GitHub Actions machine (gha-fleet.yml) takes only small files
        tag = f"gha-{os.environ.get('GITHUB_RUN_ID', '0')}-{os.environ.get('GHA_INDEX', '1')}"
        return dict(droplet_id=tag, name="upfront-fleet-" + tag, mem=int(os.environ.get("WORKER_MEM", "8")))
    meta = "http://169.254.169.254/metadata/v1/"
    did = requests.get(meta + "id", timeout=5).text.strip()
    name = requests.get(meta + "hostname", timeout=5).text.strip()
    mem = 0
    try:
        d = requests.get(f"https://api.digitalocean.com/v2/droplets/{did}", timeout=30,
                         headers={"Authorization": f"Bearer {E['DIGITALOCEAN_TOKEN']}"}).json()["droplet"]
        mem = int(d["memory"]) // 1024
    except Exception:
        kb = int(open("/proc/meminfo").read().split()[1])
        mem = round(kb / 1024 / 1024 * 1.05)
    return dict(droplet_id=did, name=name, mem=mem)


def machine_names():
    try:
        r = requests.get("https://api.digitalocean.com/v2/droplets", params={"per_page": 200}, timeout=60,
                         headers={"Authorization": f"Bearer {E['DIGITALOCEAN_TOKEN']}"})
        return [d["name"] for d in r.json()["droplets"]]
    except Exception:
        return []


def queue_main():
    """Keep claiming the next job this machine can take until none are left."""
    global OUT, SCOPE_FILE, LOG_KEY
    sys.path.insert(0, str(HERE))
    import fleet
    who = me()
    LOG_KEY = fleet.L + f"{who['name']}.txt"
    log(f"machine {who['name']} ({who['mem']} GB) taking jobs from the queue")
    (DATA / "rates").mkdir(parents=True, exist_ok=True)
    (DATA / "membership").mkdir(parents=True, exist_ok=True)
    have_scope, done_n, t_start = {}, 0, time.time()
    stop_after = float(os.environ.get("MAX_CLAIM_MINUTES", "0") or 0) * 60   # GitHub jobs end at 6 hours: stop claiming before
    while True:
        if stop_after and time.time() - t_start > stop_after:
            log(f"time limit for new files reached ({done_n} files read); leaving the rest for the next run")
            return
        js = fleet.jobs(s3, B)
        cl = fleet.claims(s3, B)
        held = fleet.held_scopes(s3, B, js, machine_names())
        cand = fleet.order([j for jid, j in js.items()
                            if jid not in cl and j["scope"] not in held and j.get("mem", 8) <= who["mem"]
                            and not (os.environ.get("GHA_WORKER") and (j.get("kind", "insurer") != "insurer" or j.get("nogha")))])
        job = next((j for j in cand if fleet.claim(s3, B, j["id"], who)), None)
        if job is None:
            left = len([j for jid, j in js.items() if jid not in cl])
            log(f"nothing left this machine can take ({done_n} files read; {left} unclaimed need a bigger machine "
                f"or are held: {held or 'none held'})")
            return
        claimed_at = fleet.iso()
        stop = threading.Event()

        def beat(jid=job["id"], st=stop, at=claimed_at):
            while not st.wait(fleet.HEARTBEAT_SECS):
                try:
                    fleet.heartbeat(s3, B, jid, who, at)
                except Exception as e:
                    print("heartbeat failed:", e, flush=True)
        threading.Thread(target=beat, daemon=True).start()
        log(f"[{job['id']}] claimed ({job['size']} job, attempt {int(job.get('attempts', 0)) + 1})")
        try:
            if job.get("kind") == "hospital":  # an oversized hospital file: the hospital bot's own steps (bot/run.py)
                sys.path.insert(0, str(HERE.parent / "bot"))
                import run as hospital_run
                res = hospital_run.run_on_machine(job, s3, B, log)
            else:
                OUT = job["out_prefix"]
                SCOPE_FILE = DATA / f"scope_{job['scope']}.parquet"
                if job["scope"] not in have_scope:
                    s3.download_file(B, job["scope_key"], str(SCOPE_FILE))
                    have_scope[job["scope"]] = True
                res = one(job)
        except Exception as e:
            res = dict(slot=job["slot"], url=job["url"], ok=False, error=f"{type(e).__name__}: {str(e)[:400]}",
                       kind=job.get("kind", "insurer"), state=job.get("state", ""), ccns=job.get("ccns", []))
        stop.set()
        err = str(res.get("error", ""))
        if os.environ.get("GHA_WORKER") and not res.get("ok") and any(x in err for x in (
                "No space left", "MemoryError", "Killed", "exit code -9", "exit code 137", "Out of Memory", "OutOfMemory")):
            # too big for a GitHub machine: hand it back to the queue for a rented machine instead of reporting a failure
            job["nogha"] = True
            job["enqueued_at"] = "2000-01-01T00:00:00Z"   # past the GitHub grace period, so the launcher rents for it now
            fleet.put_job(s3, B, job)
            fleet.release(s3, B, job["id"])
            log(f"[{job['id']}] too big for this GitHub machine ({err[:120]}); back in line for a rented machine")
            shutil.rmtree(DATA / "rates", ignore_errors=True); (DATA / "rates").mkdir(parents=True, exist_ok=True)
            continue
        res.update(finished_at=fleet.iso(), machine=who["name"])
        s3.put_object(Bucket=B, Key=job["done_key"], Body=json.dumps(res).encode())
        fleet.finish(s3, B, job["id"])
        done_n += 1
        log(f"[{job['id']}] {'ok' if res['ok'] else 'FAILED'} {res.get('rows', '')} rows {res.get('error', '')[:200]}")


def main():
    if not (E["RUN_ID"] and E["GROUP"]):
        queue_main()
        log("ALL DONE")
        return
    body = s3.get_object(Bucket=B, Key=RUN + f"{E['GROUP']}.csv")["Body"].read().decode()
    jobs = list(csv.DictReader(io.StringIO(body)))
    (DATA / "rates").mkdir(parents=True, exist_ok=True)
    (DATA / "membership").mkdir(parents=True, exist_ok=True)
    s3.download_file(B, SCOPE_KEY, str(SCOPE_FILE))
    log(f"group {E['GROUP']}: {len(jobs)} files")
    for job in jobs:
        key = RUN + f"done/{job['slot']}.json"
        if exists(key):  # finished before a restart
            continue
        try:
            res = one(job)
        except Exception as e:
            res = dict(slot=job["slot"], url=job["url"], ok=False, error=f"{type(e).__name__}: {str(e)[:400]}")
        res["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        s3.put_object(Bucket=B, Key=key, Body=json.dumps(res).encode())
        log(f"[{job['slot']}] {'ok' if res['ok'] else 'FAILED'} {res.get('rows', '')} rows {res.get('error', '')[:200]}")
    log("ALL DONE")


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.environ.get("NO_SELF_DELETE") != "1":
            self_delete()
            time.sleep(20)  # let the machine's deletion register before GitHub counts free slots
            wake_github()
