"""Watchdog for Betsy's control center (files.healthcare/control).

Checks how old each part's files are in R2 control/data/ and writes a plain-English list of anything stale to
stale.txt (empty file = all fresh). The workflow then opens a GitHub issue (which emails Betsy) or closes it.
Limits are about twice each part's normal schedule.
"""
import json
import os
from datetime import datetime, timezone

import boto3

LIMITS = [  # (label, test on the file name, max age in hours, how often it normally updates)
    ("Visitors", lambda n: n.startswith("visitors_"), 2, "every 15 minutes"),
    ("Bot health and progress", lambda n: n.startswith("ops_") or n == "status.json", 3, "about every 30 minutes"),
    ("Prices, hospitals and networks", lambda n: n not in ("medicare_inpatient.json",) and not n.startswith(("visitors_", "ops_")) and n != "status.json", 36, "once a day"),
]


def env(name):
    return "".join(os.environ.get(name, "").split())


def main():
    s3 = boto3.client("s3", endpoint_url=f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                      aws_access_key_id=env("R2_ACCESS_KEY_ID"), aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"), region_name="auto")
    objs = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=env("R2_BUCKET"), Prefix="control/data/"):
        objs += page.get("Contents", [])
    now = datetime.now(timezone.utc)
    stale = []
    for label, test, hours, how in LIMITS:
        times = [o["LastModified"] for o in objs if test(o["Key"].rsplit("/", 1)[-1])]
        if not times:
            stale.append(f"- **{label}**: no files found at all (normally updates {how}).")
            continue
        age = (now - max(times)).total_seconds() / 3600
        print(f"{label}: last updated {age:.1f} hours ago (limit {hours})")
        if age > hours:
            stale.append(f"- **{label}**: last updated {age:.0f} hours ago; it normally updates {how}.")
    # Oct 22, 2026: bots that found the Anthropic API credit used up (bot/api_credit.py); they stay switched off until it's topped up
    names = {"hospital_web_search": "Hospital web search", "insurer_search": "Insurer file search", "plain_names": "Plain-English code names"}
    for o in s3.list_objects_v2(Bucket=env("R2_BUCKET"), Prefix="bot/alerts/anthropic_credit_").get("Contents", []):
        try:
            f = json.loads(s3.get_object(Bucket=env("R2_BUCKET"), Key=o["Key"])["Body"].read())
        except Exception:
            f = {}
        bot = o["Key"].rsplit("_credit_", 1)[-1][:-5]
        stale.append(f"- **{names.get(bot, bot)}**: the Anthropic API credit ran out ({f.get('at', '')}), so it runs without Claude "
                     f"until credit is added at console.anthropic.com (Billing, same organization as the bot's key). {f.get('run', '')}")
    open("stale.txt", "w").write("\n".join(stale))
    print("stale:" if stale else "all fresh", *stale, sep="\n")


if __name__ == "__main__":
    main()
