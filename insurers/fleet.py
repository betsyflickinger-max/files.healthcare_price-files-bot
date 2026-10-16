"""One shared work queue for every rented machine (Oct 14, 2026).

Before: each machine was handed a fixed list of files when it was rented. A machine with 12 files worked through them
one by one while machines that had finished deleted themselves, and their slots sat empty until the next pass.

Now: every file waiting to be read is one job in R2 (bot/fleet/queue/). A machine claims the next job it is big
enough for, reads it, marks it done, and claims another. When nothing is left that it can take, it deletes itself.
The launcher (insurers/bot.py, every 10 minutes and whenever a machine finishes) rents one machine per unclaimed
job, up to the account's live machine limit, so every slot stays busy and nothing sits idle.

  bot/fleet/queue/<id>.json    a job: scope, slot, url, which machine size it needs, where its result goes
  bot/fleet/claims/<id>.json   who is reading it: machine id and name, when it started, last heartbeat
  bot/fleet/logs/<machine>.txt each machine's log

A claim is made with a "create only if it doesn't exist yet" write, so two machines can never take the same job.
Machines refresh their claim every few minutes; a claim whose machine is gone is cleared and the job goes back in
line (twice at most, then it is reported as failed so a file that crashes machines can't loop forever).
"""
import json
import re
import time
from datetime import datetime, timezone

from botocore.exceptions import ClientError

Q, C, L = "bot/fleet/queue/", "bot/fleet/claims/", "bot/fleet/logs/"
NAME = "upfront-fleet-"        # every queue machine's name starts with this (and carries the droplets.TAG tag)
HEARTBEAT_SECS = 300           # machines refresh their claim this often
GONE_MINS = 20                 # a claim with no heartbeat for this long, whose machine no longer exists, is cleared
BOOT_MINS = 20                 # a new machine gets this long to install and claim its first job
MAX_ATTEMPTS = 2               # machines that died mid-file before the file is reported as failed
ST_ROOM = 4                    # while the seven-state website build runs, leave this many slots free for it


def now():
    return datetime.now(timezone.utc)


def iso(t=None):
    return (t or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_mins(stamp):
    try:
        return (now() - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 60
    except Exception:
        return 1e9


def mem_gb(size):
    """Memory of a DigitalOcean size slug, e.g. s-8vcpu-32gb-amd -> 32."""
    m = re.search(r"(\d+)gb", size or "")
    return int(m.group(1)) if m else 8


def job_id(scope, slot):
    return f"{scope}__{slot}"


# ---- reading and writing the queue ----

def _keys(s3, b, prefix):
    out = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        out += [o["Key"] for o in page.get("Contents", [])]
    return out


def _get(s3, b, key):
    try:
        return json.loads(s3.get_object(Bucket=b, Key=key)["Body"].read())
    except ClientError:
        return None


def jobs(s3, b):
    """Every job in the queue: {id: job}."""
    out = {}
    for k in _keys(s3, b, Q):
        j = _get(s3, b, k)
        if j:
            out[j["id"]] = j
    return out


def claims(s3, b):
    """Every current claim: {id: claim}."""
    out = {}
    for k in _keys(s3, b, C):
        c = _get(s3, b, k)
        if c:
            out[k[len(C):-len(".json")]] = c
    return out


def put_job(s3, b, job):
    job.setdefault("enqueued_at", iso())
    job.setdefault("attempts", 0)
    s3.put_object(Bucket=b, Key=Q + job["id"] + ".json", Body=json.dumps(job).encode())


def claim(s3, b, jid, me):
    """Take a job. True only for the one machine whose write created the claim."""
    body = json.dumps(dict(me, claimed_at=iso(), heartbeat=iso())).encode()
    try:
        s3.put_object(Bucket=b, Key=C + jid + ".json", Body=body, IfNoneMatch="*")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("PreconditionFailed", "ConditionalRequestConflict") or status in (409, 412):
            return False
        if code not in ("NotImplemented",) and status != 501:
            raise
        # storage without "create only if new": write, wait, and check we are still the owner
        if _get(s3, b, C + jid + ".json"):
            return False
        s3.put_object(Bucket=b, Key=C + jid + ".json", Body=body)
        time.sleep(3)
    c = _get(s3, b, C + jid + ".json")
    return bool(c) and str(c.get("droplet_id")) == str(me.get("droplet_id")) and c.get("name") == me.get("name")


def heartbeat(s3, b, jid, me, claimed_at):
    s3.put_object(Bucket=b, Key=C + jid + ".json",
                  Body=json.dumps(dict(me, claimed_at=claimed_at, heartbeat=iso())).encode())


def finish(s3, b, jid):
    """The job's result is saved: take it out of the queue."""
    for k in (Q + jid + ".json", C + jid + ".json"):
        try:
            s3.delete_object(Bucket=b, Key=k)
        except ClientError:
            pass


def release(s3, b, jid):
    """Give a job back without finishing it (e.g. a website build started)."""
    try:
        s3.delete_object(Bucket=b, Key=C + jid + ".json")
    except ClientError:
        pass


# ---- what may run right now ----

def held_scopes(s3, b, all_jobs, names):
    """Scopes whose files must not be read right now, with the reason.
    - an area's hold.txt is set (e.g. while a website build reads its tables)
    - a website build is running that reads that area's tables: the seven-state build (upfront-site-st-*) reads only
      s7; any other build reads DFW and Texas tables (same rule the launcher has used since Oct 14)."""
    held = {}
    for j in all_jobs.values():
        sc = j["scope"]
        if sc in held:
            continue
        try:
            txt = s3.get_object(Bucket=b, Key=j["hold_key"])["Body"].read().decode().strip()
        except ClientError:
            txt = ""
        if txt:
            held[sc] = f"on hold: {txt[:120]}"
            continue
        if j.get("kind", "insurer") != "insurer":  # website builds read insurer tables only
            continue
        # Oct 15, 2026: hospital-page machines (upfront-site-hosp-*) read hospital files and finished page data, never
        # insurer tables, so they don't hold the queue (four of them held 55 seven-state re-reads for no reason).
        # Oct 16, 2026: each state build reads only its own area's tables: st-* = seven states (s7), stnc-* = North
        # Carolina (nc). The North Carolina build was holding 78 seven-state Anthem files for no reason.
        site = [n for n in names if n.startswith("upfront-site-") and not n.startswith("upfront-site-hosp-")]
        if sc in ("s7", "nc"):
            pre = "upfront-site-st-" if sc == "s7" else f"upfront-site-st{sc}-"
            builds = [n for n in site if n.startswith(pre)]
        else:
            builds = [n for n in site if not n.startswith("upfront-site-st")]
        if builds:
            held[sc] = f"waiting: a website build is running ({len(builds)} machines)"
    return held


def order(js):
    """Claim and rent in this order: new files before re-reads of unchanged files, then the biggest first (they take
    longest), then the oldest in line."""
    return sorted(js, key=lambda j: (bool(j.get("backfill")), -j.get("mem", 8), j.get("enqueued_at", "")))


# ---- the launcher's side ----

def reap(s3, b, all_jobs, all_claims, alive, results):
    """Clear claims whose machine is gone. The job goes back in line, or after MAX_ATTEMPTS is reported failed.
    `alive` = ids of machines that exist now. `results(job, res)` saves a result marker for a failed job."""
    notes = []
    for jid, c in list(all_claims.items()):
        j = all_jobs.get(jid)
        if j is None:  # its job is already finished or removed
            if age_mins(c.get("heartbeat", "")) > GONE_MINS:
                release(s3, b, jid)
                all_claims.pop(jid)
            continue
        if str(c.get("droplet_id")) in alive or age_mins(c.get("heartbeat", "")) < GONE_MINS:
            continue
        release(s3, b, jid)
        all_claims.pop(jid)
        j["attempts"] = int(j.get("attempts", 0)) + 1
        if j["attempts"] >= MAX_ATTEMPTS:
            results(j, dict(slot=j["slot"], url=j["url"], ok=False, finished_at=iso(),
                            error=f"the machine reading this file stopped {j['attempts']} times (last: {c.get('name')})"))
            finish(s3, b, jid)
            all_jobs.pop(jid)
            notes.append(f"{jid}: failed after {j['attempts']} machines stopped")
        else:
            put_job(s3, b, j)
            notes.append(f"{jid}: machine {c.get('name')} is gone; back in line")
    return notes


def plan(all_jobs, all_claims, held, machines, free):
    """Which machines to rent. `machines` = this queue's machines that exist now: [(id, name, created_at, size)].
    Machines still starting up (no claim yet, younger than BOOT_MINS) count as already covering a job, so the same
    job never gets two new machines. Returns a list of (size, job) - one machine per unclaimed job, biggest first,
    at most `free` of them."""
    waiting = order([j for jid, j in all_jobs.items() if jid not in all_claims and j["scope"] not in held])
    busy = {str(c.get("droplet_id")) for c in all_claims.values()}
    booting = sorted((m for m in machines if str(m[0]) not in busy and age_mins(m[2]) < BOOT_MINS),
                     key=lambda m: -mem_gb(m[3]))
    for m in booting:  # each starting machine will take the biggest waiting job it can
        for j in waiting:
            if j.get("mem", 8) <= mem_gb(m[3]):
                waiting.remove(j)
                break
    return [(j["size"], j) for j in waiting[:max(free, 0)]]
