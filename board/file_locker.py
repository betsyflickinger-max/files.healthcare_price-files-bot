"""File locker (Nov 9, 2026, Betsy): lock the files that must never be lost, so no script, key or mistake can delete them.

What it locks: every file under history/ (replaced insurer tables), raw/ (original price files) and research/packages/
(frozen article data). Lock = Backblaze Object Lock, GOVERNANCE mode, for RETAIN_YEARS (default 10). Governance mode
can be lifted only with Betsy's master key (it has bypassGovernance); no bot key can.

Why a separate job: the bot's own key can't set locks (Backblaze keys can't gain permissions after they're made), so
this job has its own key (secrets LOCKER_KEY_ID / LOCKER_APP_KEY) and does nothing but list and lock.
It never deletes, moves or rewrites a file. Locking adds no storage cost.

How it runs:
  - First pass: walks each folder in name order and locks everything, resuming where it stopped (a run stops itself at
    TIME_BUDGET_MIN and saves its place in research/locker/state.json).
  - After the first pass: each run locks only files uploaded since the last finished pass (with a 2-day overlap;
    re-locking a locked file to the same or a later date is allowed and harmless).
  - DRY_RUN=1 counts what it would lock and changes nothing.
"""
import datetime as dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

PREFIXES = ["history/", "raw/", "research/packages/"]
STATE_KEY = "research/locker/state.json"
LOG_PREFIX = "research/locker/log/"


def env(k, default=""):
    return "".join(os.environ.get(k, default).split())


B = env("R2_BUCKET")
RETAIN_YEARS = int(env("RETAIN_YEARS", "10"))
DRY = env("DRY_RUN", "0") == "1"
BUDGET = float(env("TIME_BUDGET_MIN", "320")) * 60
THREADS = int(env("THREADS", "32"))
START = time.time()
NOW = dt.datetime.now(dt.timezone.utc)
UNTIL = NOW.replace(year=NOW.year + RETAIN_YEARS)


def client():
    if not (env("LOCKER_KEY_ID") and env("LOCKER_APP_KEY")):
        print("LOCKER_KEY_ID / LOCKER_APP_KEY secrets are missing, so nothing was locked. Create the 'file-locker' key "
              "in Backblaze (Read and Write, bucket files.healthcare-DATA) and add both values as GitHub secrets.")
        sys.exit(0)
    ep = env("STORAGE_ENDPOINT")
    if ep and "://" not in ep:
        ep = "https://" + ep
    if not ep or not B:
        sys.exit("Backblaze endpoint or bucket is missing (secrets B2_ENDPOINT / B2_BUCKET).")
    return boto3.client("s3", endpoint_url=ep, aws_access_key_id=env("LOCKER_KEY_ID"),
                        aws_secret_access_key=env("LOCKER_APP_KEY"), region_name=env("STORAGE_REGION") or "auto",
                        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}, max_pool_connections=THREADS + 4,
                                      connect_timeout=20, read_timeout=60))


def load_state(s3):
    try:
        return json.loads(s3.get_object(Bucket=B, Key=STATE_KEY)["Body"].read())
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return {}
        raise


def save_state(s3, state):
    if not DRY:
        s3.put_object(Bucket=B, Key=STATE_KEY, Body=json.dumps(state, indent=1).encode(), ContentType="application/json")


def lock(s3, key):
    s3.put_object_retention(Bucket=B, Key=key,
                            Retention={"Mode": "GOVERNANCE", "RetainUntilDate": UNTIL})


def out_of_time():
    return time.time() - START > BUDGET


def run_prefix(s3, pool, prefix, st):
    """Returns (seen, locked, failed, finished)."""
    full_done = st.get("full_pass_done", False)
    since = dt.datetime.fromisoformat(st["since"]) - dt.timedelta(days=2) if full_done and st.get("since") else None
    after = st.get("after", "")
    pass_started = st.get("pass_started") or NOW.isoformat()
    seen = locked = failed = 0
    kw = {"Bucket": B, "Prefix": prefix, "MaxKeys": 1000}
    if after:
        kw["StartAfter"] = after
    while True:
        page = s3.list_objects_v2(**kw)
        todo = [o["Key"] for o in page.get("Contents", [])
                if since is None or o["LastModified"] >= since]
        seen += len(page.get("Contents", []))
        if todo and not DRY:
            futs = {pool.submit(lock, s3, k): k for k in todo}
            for f in as_completed(futs):
                try:
                    f.result()
                    locked += 1
                except ClientError as e:
                    code = e.response.get("Error", {}).get("Code", "")
                    if code in ("AccessDenied", "Forbidden"):
                        sys.exit(f"The locker key isn't allowed to set locks ({code}) on {futs[f]}. Check that the "
                                 "'file-locker' key is Read and Write on files.healthcare-DATA and that Object Lock "
                                 "is enabled on the bucket.")
                    failed += 1
                    print(f"  could not lock {futs[f]}: {code}")
        elif DRY:
            locked += len(todo)
        if page.get("Contents"):
            st["after"] = page["Contents"][-1]["Key"]
        if not page.get("IsTruncated"):
            # Finished this folder: next pass only needs files uploaded after this pass began.
            st.update(full_pass_done=True, since=pass_started, after="", pass_started=None)
            return seen, locked, failed, True
        kw["ContinuationToken"] = page["NextContinuationToken"]
        kw.pop("StartAfter", None)
        st["pass_started"] = pass_started
        if out_of_time():
            return seen, locked, failed, False


def main():
    s3 = client()
    state = load_state(s3)
    report = {"run_at": NOW.isoformat(), "dry_run": DRY, "retain_until": UNTIL.isoformat(), "folders": {}}
    all_done = True
    with ThreadPoolExecutor(THREADS) as pool:
        for p in PREFIXES:
            if out_of_time():
                all_done = False
                break
            st = state.setdefault(p, {})
            seen, locked, failed, finished = run_prefix(s3, pool, p, st)
            report["folders"][p] = dict(files_listed=seen, locked=locked, failed=failed, finished=finished)
            print(f"{p}: listed {seen:,}, {'would lock' if DRY else 'locked'} {locked:,}, failed {failed:,}, "
                  f"{'finished' if finished else 'will resume next run'}")
            all_done &= finished
            save_state(s3, state)
    report["all_caught_up"] = all_done
    if not DRY:
        s3.put_object(Bucket=B, Key=f"{LOG_PREFIX}{NOW:%Y-%m-%dT%H%M}.json",
                      Body=json.dumps(report, indent=1).encode(), ContentType="application/json")
    summ = env("GITHUB_STEP_SUMMARY")
    if summ:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(f"## File locker {'(dry run, nothing changed)' if DRY else ''}\n\n"
                     f"Locks last until {UNTIL:%B %d, %Y} (governance mode).\n\n| Folder | Listed | "
                     f"{'Would lock' if DRY else 'Locked'} | Failed | Done |\n|---|---:|---:|---:|---|\n")
            for p, r in report["folders"].items():
                fh.write(f"| {p} | {r['files_listed']:,} | {r['locked']:,} | {r['failed']:,} | "
                         f"{'yes' if r['finished'] else 'resumes next run'} |\n")
    if any(r["failed"] for r in report["folders"].values()):
        sys.exit("Some files could not be locked; they'll be retried on the next pass.")


if __name__ == "__main__":
    main()
