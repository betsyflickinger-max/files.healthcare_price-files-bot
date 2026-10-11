"""Hourly status snapshot for the "Price Project Status" board.

Writes out/board/status.json with: rented machines + DigitalOcean spend, Texas and DFW insurer-file progress,
hospital-file coverage, R2 storage size, and recent GitHub workflow runs. A scheduled Claude task reads it
from the private repo (branch board-status) and updates the board, so no keys are needed on that side.
"""
import csv, io, json, os, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
import boto3

E = os.environ
out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B = E["R2_BUCKET"]

def get(key):
    return s3.get_object(Bucket=B, Key=key)["Body"].read().decode()

def manifest(key):
    rows = list(csv.DictReader(io.StringIO(get(key))))
    act = [r for r in rows if r["insurer"] != "Molina"]
    return {"networks": len(rows), "active": len(act), "status": dict(Counter(r["status"] for r in act)),
            "not_done": [{"network": r["network_label"], "status": r["status"], "fails": r["fails"],
                          "launched_at": r["launched_at"], "detail": (r["detail"] or "")[:120]}
                         for r in act if r["status"] != "processed"]}

for name, key in (("insurers_tx", "bot/insurers/tx/manifest.csv"), ("insurers_dfw", "bot/insurers/manifest.csv")):
    try: out[name] = manifest(key)
    except Exception as e: out[name] = {"error": str(e)[:200]}
try:
    out["insurer_hold"] = bool(s3.list_objects_v2(Bucket=B, Prefix="bot/insurers/hold.txt").get("KeyCount"))
except Exception: pass

# hospital coverage from the bot's latest status
try:
    rows = list(csv.DictReader(io.StringIO(get("bot/status/latest.csv"))))
    st = Counter(r.get("status", "") for r in rows)
    out["hospitals"] = {"listed": len(rows), "status": dict(st.most_common(12))}
except Exception as e:
    out["hospitals"] = {"error": str(e)[:200]}

# R2 size by top-level folder
tot, n, top = 0, 0, Counter()
for p in s3.get_paginator("list_objects_v2").paginate(Bucket=B):
    for o in p.get("Contents", []):
        tot += o["Size"]; n += 1; top["/".join(o["Key"].split("/")[:2])] += o["Size"]
out["r2"] = {"objects": n, "gb": round(tot / 1e9, 1),
             "est_usd_month": round(max(tot / 1e9 - 10, 0) * 0.015, 2),
             "largest": [[k, round(v / 1e9, 1)] for k, v in top.most_common(6)]}

# DigitalOcean: month-to-date spend, credit, machines running now
def do(path):
    r = urllib.request.Request("https://api.digitalocean.com/v2/" + path, headers={"Authorization": "Bearer " + E["DIGITALOCEAN_TOKEN"]})
    return json.load(urllib.request.urlopen(r, timeout=30))
if E.get("DIGITALOCEAN_TOKEN"):
    try:
        bal = do("customers/my/balance")
        d = do("droplets?per_page=100")["droplets"]
        out["digitalocean"] = {"month_to_date_usd": float(bal["month_to_date_usage"]),
                               "credit_left_usd": -float(bal["account_balance"]) if float(bal["account_balance"]) < 0 else 0.0,
                               "machines": [{"name": x["name"], "usd_hour": x["size"]["price_hourly"], "created": x["created_at"]} for x in d],
                               "usd_hour_now": round(sum(x["size"]["price_hourly"] for x in d), 3)}
    except Exception as e:
        out["digitalocean"] = {"error": str(e)[:200]}

# recent workflow runs
try:
    r = urllib.request.Request(f"https://api.github.com/repos/{E['GITHUB_REPOSITORY']}/actions/runs?per_page=30",
                               headers={"Authorization": "Bearer " + E["GH_TOKEN"], "Accept": "application/vnd.github+json"})
    runs = json.load(urllib.request.urlopen(r, timeout=30))["workflow_runs"]
    out["recent_runs"] = [{"name": x["name"], "status": x["status"], "conclusion": x["conclusion"], "at": x["created_at"]} for x in runs]
except Exception as e:
    out["recent_runs"] = {"error": str(e)[:200]}

os.makedirs("out/board", exist_ok=True)
json.dump(out, open("out/board/status.json", "w"), indent=1)
print(json.dumps({k: (v if k in ("generated_at", "r2", "insurer_hold") else "...") for k, v in out.items()}))
