"""Status snapshot (every 15 min) for the "Price Project Status" board.

Writes out/board/status.json with: rented machines + DigitalOcean spend, Texas and DFW insurer-file progress,
hospital-file coverage, R2 storage size, and recent GitHub workflow runs. A scheduled Claude task reads it
from the private repo (branch board-status) and updates the board, so no keys are needed on that side.
"""
import csv, io, json, os, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
import boto3

E = {k: v.strip() for k, v in os.environ.items()}  # secrets may carry a trailing newline
out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
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

# every other insurer batch (bot/insurers/<scope>/manifest.csv), e.g. the national batches once they start reading files
try:
    out["insurer_scopes"] = {}
    for p in s3.list_objects_v2(Bucket=B, Prefix="bot/insurers/", Delimiter="/").get("CommonPrefixes", []):
        sc = p["Prefix"].split("/")[2]
        if sc in ("runs", "tx"):
            continue
        try:
            m = manifest(p["Prefix"] + "manifest.csv")
            out["insurer_scopes"][sc] = {"active": m["active"], "processed": m["status"].get("processed", 0), "status": m["status"]}
        except Exception:
            pass
except Exception as e:
    out["insurer_scopes"] = {"error": str(e)[:200]}

# hospital coverage from the bot's latest status
try:
    rows = list(csv.DictReader(io.StringIO(get("bot/status/latest.csv"))))
    st = Counter(r.get("status", "") for r in rows)
    out["hospitals"] = {"listed": len(rows), "status": dict(st.most_common(12))}
except Exception as e:
    out["hospitals"] = {"error": str(e)[:200]}
# hospitals with a price file on record, out of all hospitals (the dashboard's latest daily count)
try:
    hk = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=B, Prefix="bot/dashboard/history/").get("Contents", []) if o["Key"].endswith(".json"))
    allrow = next(r for r in json.loads(get(hk[-1])) if r["state"] == "ALL")
    out.setdefault("hospitals", {}).update(total=allrow["hospitals"], have_file=allrow["have"], as_of=allrow["date"])
except Exception as e:
    out.setdefault("hospitals", {})["total_error"] = str(e)[:200]

# plain-English names: CPT codes on the live Price Finder that still show the insurer's wording
# (same rule as names/auto_names.py: hand-written and auto names both count as named)
try:
    s = get("site/deploy/price-finder.html")
    i = s.find('id="data"'); a = s.find(">", i) + 1; b = s.find("</script>", i)
    codes = json.loads(s[a:b])["codes"]
    def tsv(p):
        return {l.split("\t", 1)[0] for l in open(p) if "\t" in l} if os.path.exists(p) else set()
    named = tsv("site/plain_names_cpt.tsv") | tsv("site/plain_names_auto.tsv")
    cpt = {c: v for c, v in codes.items() if v.get("type") == "CPT"}
    left = sum(1 for c, v in cpt.items() if "name as written" in v.get("cat", "") and c not in named)
    out["code_names"] = {"cpt_codes": len(cpt), "named": len(cpt) - left, "left": left}
except Exception as e:
    out["code_names"] = {"error": str(e)[:200]}

# R2 size by top-level folder; the same pass counts finished Texas city-build batches
# (work/every-tx/<city>/<run>/B/<n>.json; each city build has TX_BATCHES batches, newest run counts)
TX_BATCHES = 256
# Oct 29, 2026: the whole-bucket size pass (millions of objects, listing is R2's pricier request class) ran every 15
# minutes and pushed each run past its 50-minute limit after the storage outage, so the board stopped updating. Now the
# size is re-counted at most every 6 hours and saved; runs in between reuse it. Texas batches list only their own folder.
SIZE_KEY, SIZE_HOURS = "bot/dashboard/r2_size.json", 6
txb = Counter()
for p in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="work/every-tx/"):
    for o in p.get("Contents", []):
        k = o["Key"].split("/")
        if len(k) == 6 and k[:2] == ["work", "every-tx"] and k[4] == "B" and k[5].endswith(".json") and k[3][:1] == "v":
            txb[(k[2], k[3])] += 1
cities = {}
for (city, run), cnt in txb.items():
    if city not in cities or int(run[1:] or 0) > int(cities[city]["run"][1:] or 0):
        cities[city] = {"run": run, "done": min(cnt, TX_BATCHES), "total": TX_BATCHES}
out["tx_cities"] = cities
try:
    size = json.loads(get(SIZE_KEY))
except Exception:
    size = {}
if time.time() - size.get("at", 0) > SIZE_HOURS * 3600:
    tot, n, top = 0, 0, Counter()
    for p in s3.get_paginator("list_objects_v2").paginate(Bucket=B):
        for o in p.get("Contents", []):
            tot += o["Size"]; n += 1; top["/".join(o["Key"].split("/")[:2])] += o["Size"]
    size = {"at": time.time(), "objects": n, "gb": round(tot / 1e9, 1),
            "est_usd_month": round(max(tot / 1e9 - 10, 0) * 0.015, 2),
            "largest": [[k, round(v / 1e9, 1)] for k, v in top.most_common(6)]}
    s3.put_object(Bucket=B, Key=SIZE_KEY, Body=json.dumps(size).encode())
out["r2"] = {k: v for k, v in size.items() if k != "at"}
out["r2"]["counted_at"] = datetime.fromtimestamp(size["at"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
                               "usd_hour_now": round(sum(x["size"]["price_hourly"] for x in d), 3),
                               # Oct 14, 2026: the account's live machine limit, so the board shows "N of <limit>" (was 10, now 25)
                               "machine_limit": int(do("account")["account"].get("droplet_limit") or 0)}
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
