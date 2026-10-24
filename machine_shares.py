"""Machine shares (Oct 18, 2026, Betsy OK'd): no single kind of job may take every rented machine.

Why: on Oct 17-18 a website rebuild (Colorado, Georgia and Missouri with new Anthem tables, build st-2026-10b) held all 24
machines for 27 hours while 623 Connecticut insurer files waited with 0 machines. Builds hold machines for days; insurer
files finish and hand theirs back in minutes, so builds must leave room.

Rules (fractions of the account's live machine limit, read from DigitalOcean every time):
  INSURER_SHARE  while insurer files are waiting in the shared queue (bot/fleet/queue/), website builds together leave
                 this share of the slots for the insurer reader (or fewer, if fewer files are waiting).
  REBUILD_SHARE  a rebuild (a build id ending in a letter, e.g. st-2026-10b) holds at most this share. Rebuilds go last.
A build over its share has its newest machines stopped by the build's own make_room(); for website builds that loses at
most the batch each stopped machine was on (finished batches stay in R2).

Used by site/orchestrate_states.py (state builds) and site/orchestrate.py (DFW / Texas builds).
"""
import math, re

INSURER_SHARE = 0.4
REBUILD_SHARE = 0.25
QUEUE = "bot/fleet/queue/"


def is_rebuild(bid):
    """st-2026-10b, stnc-2026-11c ... (a month's build id plus a letter)"""
    return bool(re.search(r"\d{4}-\d{2}[a-z]$", bid or ""))


def insurer_waiting(s3, bucket):
    """insurer files in the shared queue (waiting or being read) that need a rented machine.
    Oct 24, 2026 (Betsy OK'd): small files that GitHub's free machines read (fleet.GHA_LANE, up to GHA_MAX_MEM GB) no
    longer count. 13,700 queued files kept 10 rented slots from the six-state build though most never need one."""
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "insurers"))
    import fleet
    n = 0
    for j in fleet.jobs(s3, bucket).values():
        small = (fleet.GHA_LANE and j.get("kind", "insurer") == "insurer" and j.get("mem", 8) <= fleet.GHA_MAX_MEM
                 and not j.get("nogha"))
        n += 0 if small else 1
    return n


def floor(bid):
    """Oct 24, 2026: the fewest machines this build is promised (site/build_floors.json), 0 if none."""
    import json, os
    try:
        f = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "build_floors.json")))
        return int((f.get(bid) or {}).get("machines", 0))
    except Exception:
        return 0


def build_cap(bid, limit, reserve, names, s3, bucket, log=print):
    """Most machines build `bid` may hold right now, given every machine on the account (`names`).
    Counts only website-build machines (upfront-site-*) of OTHER builds against the shared build share."""
    own_pre = f"upfront-site-{bid}-"
    others = sum(1 for n in names if n.startswith("upfront-site-") and not n.startswith(own_pre))
    try:
        waiting = insurer_waiting(s3, bucket)
    except Exception as e:
        log("machine shares: could not count the insurer queue:", repr(e)[:120]); waiting = 0
    guard = min(waiting, math.ceil(INSURER_SHARE * limit))
    cap = limit - reserve - guard - others
    why = f"{guard} kept for {waiting} waiting insurer files" if guard else "no insurer files waiting"
    if is_rebuild(bid):
        rcap = math.floor(REBUILD_SHARE * limit)
        if rcap < cap: cap, why = rcap, why + f"; rebuild share {rcap}"
    cap = max(cap, 1, floor(bid))   # a build always keeps at least one machine (or its floor), so it still moves
    log(f"machine shares: {bid} may hold {cap} of {limit} ({why}; {others} on other builds)")
    return cap
