"""How long each full insurer check takes (Nov 2, 2026; Betsy: "can we measure it each time it runs").

Runs as the last step of every full check (insurers.yml, not the 10-minute fills). Reads this run's own step times from
GitHub and adds one row to R2 control/data/full_check_times.json (newest first, last 400 runs), plus a line in the
run's summary. Parts of a full check:
  wait     waiting for the lock and for machines (a full check waits for a running fill)
  dfw      checking DFW's networks (the first area)
  states   checking Texas and every other state group and queueing their new files (the long part: 2 h 42 min on
           Nov 2, 2026; the whole run is capped at 4 hours). The machines read the queued files on their own time.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

import boto3


def t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if s else None


def mins(a, b):
    return round((b - a).total_seconds() / 60, 1) if a and b else None


def main():
    E = os.environ
    run = E["GITHUB_RUN_ID"]
    req = urllib.request.Request(f"{E['GITHUB_API_URL']}/repos/{E['GITHUB_REPOSITORY']}/actions/runs/{run}/jobs",
                                 headers={"Authorization": f"Bearer {E['GH_TOKEN']}", "Accept": "application/vnd.github+json"})
    job = json.load(urllib.request.urlopen(req, timeout=30))["jobs"][0]
    now = datetime.now(timezone.utc)
    start = t(job["started_at"])
    part = {"wait": None, "dfw": None, "states": None}
    for s in job["steps"]:
        a, b = t(s.get("started_at")), t(s.get("completed_at")) or now
        n = s["name"].lower()
        if s.get("conclusion") == "skipped":
            continue
        if n.startswith("full check lock") or n.startswith("machines only"):
            part["wait"] = round((part["wait"] or 0) + (mins(a, b) or 0), 1)
        elif n == "check insurer files":
            part["dfw"] = mins(a, b)
        elif n.startswith("all of texas"):
            part["states"] = mins(a, b)
    row = dict(run=int(run), started=job["started_at"], minutes=mins(start, now), **part,
               how=E.get("GITHUB_EVENT_NAME", ""), result=E.get("JOB_STATUS", ""),
               hit_time_limit=(mins(start, now) or 0) >= 235)
    s3 = boto3.client("s3", endpoint_url=(E.get("STORAGE_ENDPOINT") or f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com"),
                      aws_access_key_id="".join(E["R2_ACCESS_KEY_ID"].split()), aws_secret_access_key="".join(E["R2_SECRET_ACCESS_KEY"].split()),
                      region_name=(E.get("STORAGE_REGION") or "auto"))
    b, key = "".join(E["R2_BUCKET"].split()), "control/data/full_check_times.json"
    try:
        rows = json.loads(s3.get_object(Bucket=b, Key=key)["Body"].read())
    except Exception:
        rows = []
    rows = [row] + [r for r in rows if r.get("run") != row["run"]][:399]
    s3.put_object(Bucket=b, Key=key, Body=json.dumps(rows).encode(), ContentType="application/json", CacheControl="no-cache")
    line = (f"Full check took {row['minutes']} min (waiting {part['wait']}, DFW {part['dfw']}, "
            f"Texas and the other states {part['states']})" + (" and hit the 4-hour limit" if row["hit_time_limit"] else ""))
    print(line)
    if E.get("GITHUB_STEP_SUMMARY"):
        open(E["GITHUB_STEP_SUMMARY"], "a").write(f"\n**{line}.**\n")


if __name__ == "__main__":
    main()
