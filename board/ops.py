"""Bot health and cost data for the "Bot health" tab of the Price Transparency Metrics dashboard (Oct 15, 2026).

Runs right after board/status.py in .github/workflows/board-status.yml (every 15 min) and writes out/board/ops_*.json,
which that workflow publishes with status.json to the private repo price-dashboard-data, branch board-status. The
dashboard's upload task uploads them (also when Betsy presses "Refresh data now"). Real counts only; the one
projection (days of credit left) is labelled as one.

  ops_meta.json      one row: when built, spend this month, credit left, $/hour now, machines now / limit, credit runway
  ops_bots.json      one row per bot: what it does, schedule, last run, its files (done / total, running, failed,
                     waiting), machines now, $/hour now, cost this month (DigitalOcean's own per-machine billing)
  ops_holds.json     one row per insurer area: moving or held, and why; files waiting, being read, free slots
  ops_failures.json  one row per insurer file that failed: area, insurer, network, tries, the reason in plain words
  ops_machines.json  one row per machine running now: bot, $/hour, hours so far, cost so far, the file it is on, idle?
  ops_costs.json     one row per day x bot x detail (e.g. a state): billed $ and machine-hours this month
  ops_jobs.json      one row per insurer file read this month: area, file, ok, full read or new fields only,
                     minutes, machine, estimated $ (minutes x that machine's hourly price)
"""
import csv, io, json, os, re, sys, time, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import boto3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "insurers"))
import fleet  # noqa: E402  (the insurer queue's own rules for claims and holds)

E = {k: v.strip() for k, v in os.environ.items()}
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B = E["R2_BUCKET"]
OUT = Path("out/board"); OUT.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(timezone.utc); MONTH = NOW.strftime("%Y-%m")
ST = json.load(open(OUT / "status.json")) if (OUT / "status.json").exists() else {}

def get(key): return s3.get_object(Bucket=B, Key=key)["Body"].read()
def getj(key, default=None):
    try: return json.loads(get(key))
    except Exception: return default
def ls(prefix):
    return [o for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=prefix) for o in pg.get("Contents", [])]
def save(name, rows): (OUT / f"{name}.json").write_text(json.dumps(rows, separators=(",", ":"), default=str))
def hours_since(iso):
    try: return round((NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 3600, 2)
    except Exception: return None

def do(path):
    r = urllib.request.Request("https://api.digitalocean.com/v2/" + path, headers={"Authorization": "Bearer " + E["DIGITALOCEAN_TOKEN"]})
    return json.load(urllib.request.urlopen(r, timeout=60))

# ---------- which bot a machine belongs to (by its name) ----------
def bot_of(name):
    n = name.split(" (")[0]
    if n.startswith(("upfront-fleet-", "upfront-bot-")): return "insurers", ""
    if n.startswith("upfront-site-st-"): return "state_pages", re.sub(r"^upfront-site-st-\d{4}-\d{2}-", "", n).rsplit("-c", 1)[0]
    if n.startswith("upfront-site-stnc-"): return "nc_pages", re.sub(r"^upfront-site-stnc-\d{4}-\d{2}-", "", n).rsplit("-c", 1)[0]
    if n.startswith("upfront-site-stct-"): return "ct_pages", re.sub(r"^upfront-site-stct-\d{4}-\d{2}-", "", n).rsplit("-c", 1)[0]
    if n.startswith("upfront-site-hosp-"): return "hospital_pages", ("North Carolina" if "-hosp-stnc-" in n else "Connecticut" if "-hosp-stct-" in n else "states" if "-hosp-st-" in n else "Texas")
    if n.startswith("upfront-site-tx-"): return "texas_pages", re.sub(r"^upfront-site-tx-\d{4}-\d{2}-(metros-)?", "", n)
    if n.startswith("upfront-site-"): return "refresh", "Dallas-Fort Worth"
    if n.startswith("upfront-test-"): return "tests", n[len("upfront-test-"):]
    if n.startswith(("upfront-every", "upfront-hosp-", "upfront-p2", "upfront-tx-", "upfront-national")): return "one_off_builds", ""
    if n.startswith(("upfront-find", "upfront-archive", "upfront-retry", "upfront-fill")): return "one_off_downloads", ""
    return "other", n

# ---------- DigitalOcean: machines now + this month's billing per machine ----------
machines, items, limit = [], [], 0
if E.get("DIGITALOCEAN_TOKEN"):
    try:
        machines = do("droplets?per_page=200")["droplets"]
        limit = int(do("account")["account"].get("droplet_limit") or 0)
        page = 1
        while True:   # billing so far this month, one line per machine per day (DigitalOcean updates it during the day)
            d = do(f"customers/my/invoices/preview?per_page=200&page={page}")
            items += d.get("invoice_items", [])
            if not d.get("links", {}).get("pages", {}).get("next"): break
            page += 1
    except Exception as e:
        print("DigitalOcean:", repr(e)[:200])
costs = defaultdict(lambda: [0.0, 0.0])   # (day, bot, detail) -> [usd, hours]
bot_month = defaultdict(float)
for it in items:
    if it.get("product") != "Droplets": continue
    bot, det = bot_of(it.get("description", ""))
    day = (it.get("start_time") or "")[:10]
    usd = float(it.get("amount") or 0); hrs = float(it.get("duration") or 0)
    costs[(day, bot, det)][0] += usd; costs[(day, bot, det)][1] += hrs; bot_month[bot] += usd
save("ops_costs", [{"id": f"{d}|{b}|{x}", "day": d, "bot": b, "detail": x, "usd": round(v[0], 2), "machine_hours": round(v[1], 1)}
                   for (d, b, x), v in sorted(costs.items())])

# ---------- insurer queue: jobs, claims, holds ----------
qjobs, qclaims = fleet.jobs(s3, B), fleet.claims(s3, B)
names = [m["name"] for m in machines]
held = fleet.held_scopes(s3, B, qjobs, names)
claim_by_machine = {c.get("name"): jid for jid, c in qclaims.items()}

mrows = []
for m in machines:
    bot, det = bot_of(m["name"]); h = hours_since(m["created_at"]); price = m["size"]["price_hourly"]
    job = claim_by_machine.get(m["name"], "")
    idle = bot == "insurers" and m["name"].startswith(fleet.NAME) and not job and (h or 0) > 0.5
    mrows.append({"id": m["name"], "bot": bot, "detail": det, "size": m["size_slug"], "usd_hour": price, "started": m["created_at"],
                  "hours": h, "usd_so_far": round(price * (h or 0), 2), "working_on": job.split("__", 1)[-1] if job else "",
                  "idle": idle})
save("ops_machines", mrows)
now_by_bot = defaultdict(lambda: [0, 0.0])
for r in mrows: now_by_bot[r["bot"]][0] += 1; now_by_bot[r["bot"]][1] += r["usd_hour"]
free = max(0, limit - len(machines) - 1)

# ---------- insurer manifests: counts + failures ----------
AREAS = {"dfw": ("Dallas-Fort Worth", "bot/insurers/manifest.csv"), "tx": ("Texas", "bot/insurers/tx/manifest.csv"),
         "s7": ("Seven states", "bot/insurers/s7/manifest.csv"), "nc": ("North Carolina", "bot/insurers/nc/manifest.csv"),
         "ct": ("Connecticut", "bot/insurers/ct/manifest.csv"), "il": ("Illinois", "bot/insurers/il/manifest.csv"), "n5": ("NY, CA, VA, DC, FL, WI", "bot/insurers/n5/manifest.csv"), "ar": ("Arkansas", "bot/insurers/ar/manifest.csv"), "b1": ("MD, NM, MT", "bot/insurers/b1/manifest.csv"), "la": ("Louisiana", "bot/insurers/la/manifest.csv"), "b4": ("IN, KY, OH", "bot/insurers/b4/manifest.csv")}
def reason(detail):
    d = (detail or "").lower()
    for pat, why in (("premature eof|incompletejson|unexpected end", "Download was cut off before the end of the file"),
                     ("403|forbidden|expired|accessdenied", "The insurer's link was refused or has expired"),
                     ("404|not found", "The file is no longer at its link"),
                     ("s3uploadfailed|completemultipartupload|invalidpart|read timeout on endpoint", "Saving to storage failed (network hiccup); a retry usually works"),
                     ("gzipfile|not a gzipped|bad gzip|crc check", "The download isn't a readable compressed file"),
                     ("out of memory|killed process|oom", "The machine ran out of memory"),
                     ("stopped \\d+ times|gave no result", "The machine reading it stopped or got stuck"),
                     ("could not check the file", "Couldn't check the file for changes")):
        if re.search(pat, d): return why
    return "Other (see detail)"
counts, fails = {}, []
for sc, (label, key) in AREAS.items():
    try: rows = list(csv.DictReader(io.StringIO(get(key).decode())))
    except Exception: continue
    act = [r for r in rows if r["insurer"] != "Molina"]
    c = Counter(r["status"] for r in act)
    counts[sc] = {"total": len(act), "done": c.get("processed", 0), "running": c.get("running", 0), "failed": c.get("failed", 0),
                  "waiting": c.get("queued", 0) + c.get("new", 0), "molina": len(rows) - len(act)}
    for r in act:
        if r["status"] == "failed":
            fails.append({"id": f"{sc}|{r['slot']}", "area": label, "insurer": r["insurer"], "network": r["network_label"],
                          "tries": int(r.get("fails") or 0), "last_checked": r.get("last_checked", ""),
                          "reason": reason(r.get("detail", "")), "detail": (r.get("detail") or "")[:300]})
save("ops_failures", sorted(fails, key=lambda x: (-x["tries"], x["area"], x["insurer"])))

hold_rows = []
for sc, (label, _) in AREAS.items():
    js = {k: v for k, v in qjobs.items() if v.get("scope") == sc}
    waiting = sum(1 for k in js if k not in qclaims); reading = sum(1 for k in js if k in qclaims)
    why = held.get(sc, "")
    if not why and waiting and free == 0: why = "every machine slot is in use; files start as slots free up"
    hold_rows.append({"id": sc, "area": label, "state": "held" if sc in held else ("waiting for a slot" if why else "moving"),
                      "reason": why or ("nothing waiting" if not waiting else "files are being started"),
                      "waiting": waiting, "being_read": reading, "free_slots": free})
save("ops_holds", hold_rows)

# ---------- finished insurer reads this month (cached so each run reads only new results) ----------
CACHE = "bot/ops/jobs_cache.json"
cache = getj(CACHE, {}) or {}
keys = [o["Key"] for p in ("bot/insurers/runs/", "bot/insurers/tx/runs/", "bot/insurers/s7/runs/", "bot/insurers/nc/runs/", "bot/insurers/ct/runs/") for o in ls(p)
        if "/done/" in o["Key"] and o["LastModified"].strftime("%Y-%m") == MONTH]
new = [k for k in keys if k not in cache]
def one(k):
    try: d = json.loads(get(k))
    except Exception: return k, None
    sc = "s7" if "/s7/" in k else "nc" if "/nc/" in k else "ct" if "/ct/" in k else "il" if "/il/" in k else "n5" if "/n5/" in k else "ar" if "/ar/" in k else "b1" if "/b1/" in k else "la" if "/la/" in k else "b4" if "/b4/" in k else "tx" if "/tx/" in k else "dfw"
    mem = re.search(r"-(\d+)g-", d.get("machine", "") or ""); mem = int(mem.group(1)) if mem else 16
    return k, {"area": AREAS[sc][0], "file": d.get("slot", ""), "ok": bool(d.get("ok")), "fields_only": bool(d.get("fields_only")),
               "secs": d.get("secs"), "machine": d.get("machine", ""), "mem_gb": mem, "finished": d.get("finished_at", ""),
               "error": (d.get("error") or "")[:160]}
with ThreadPoolExecutor(16) as ex:
    for k, v in ex.map(one, new):
        if v: cache[k] = v
cache = {k: v for k, v in cache.items() if k in set(keys)}
try: s3.put_object(Bucket=B, Key=CACHE, Body=json.dumps(cache).encode())
except Exception as e: print("cache save failed:", e)
PRICE = {8: 0.07143, 16: 0.16667, 32: 0.25}   # DigitalOcean $/hour for the fleet's sizes (s-4vcpu-8gb, s-8vcpu-16/32gb-amd)
jobs = []
for k, v in cache.items():
    mins = round((v["secs"] or 0) / 60, 1)
    jobs.append({"id": k.split("/runs/", 1)[-1], **{x: v[x] for x in ("area", "file", "ok", "fields_only", "machine", "finished", "error")},
                 "how": "new fields only" if v["fields_only"] else "full read", "minutes": mins,
                 "usd_est": round(mins / 60 * PRICE.get(v["mem_gb"], 0.16667), 2) if v["secs"] else None})
save("ops_jobs", sorted(jobs, key=lambda j: j["finished"], reverse=True))

# ---------- GitHub: last run of each workflow ----------
last = {}
try:
    req = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "Bearer " + E["GH_TOKEN"],
                                                     "Accept": "application/vnd.github+json"}), timeout=30))
    for w in req(f"https://api.github.com/repos/{E['GITHUB_REPOSITORY']}/actions/workflows?per_page=100")["workflows"]:
        r = req(f"https://api.github.com/repos/{E['GITHUB_REPOSITORY']}/actions/workflows/{w['id']}/runs?per_page=1")["workflow_runs"]
        if r: last[w["path"].rsplit("/", 1)[-1]] = (r[0]["created_at"], r[0]["conclusion"] or r[0]["status"])
except Exception as e:
    print("GitHub:", repr(e)[:200])

# ---------- the bots ----------
SEVEN = ["tennessee", "colorado", "oklahoma", "alabama", "mississippi", "missouri", "georgia"]
bm = MONTH if any(o for o in ls(f"site/builds/st-{MONTH}/state.json")) else "2026-10"   # the latest seven-state build
st7 = getj(f"site/builds/st-{bm}/state.json", {}) or {}
built7 = sum(1 for s in SEVEN if ls(f"site/every-st/{s}/{bm}/embed.json"))
hst = getj(f"site/builds/hosp-st-{bm}/state.json", {}) or {}
stnc = getj(f"site/builds/stnc-{bm}/state.json", {}) or {}        # North Carolina (Oct 16, 2026)
hnc = getj(f"site/builds/hosp-stnc-{bm}/state.json", {}) or {}
nc_note = f"{bm} build, stage: {stnc.get('stage', 'not started')}"
if stnc.get("split_failed"): nc_note += f"; {len(stnc['split_failed'])} tables not split"
if stnc.get("problems"): nc_note += f"; problems: {'; '.join(stnc['problems'][-3:])}"
if (hnc.get("published") or {}): nc_note += "; page published"
stct = getj(f"site/builds/stct-{bm}/state.json", {}) or {}        # Connecticut (Oct 16, 2026)
hct = getj(f"site/builds/hosp-stct-{bm}/state.json", {}) or {}
ct_note = f"{bm} build, stage: {stct.get('stage', 'not started')}"
if stct.get("split_failed"): ct_note += f"; {len(stct['split_failed'])} tables not split"
if stct.get("problems"): ct_note += f"; problems: {'; '.join(stct['problems'][-3:])}"
if (hct.get("published") or {}): ct_note += "; page published"
s7_note = f"{bm} build, stage: {st7.get('stage', '?')}"
try: rb = json.load(open(HERE.parent / "site" / "state_rebuild.json")).get("st") or {}
except Exception: rb = {}   # Oct 16, 2026: a rebuild of some states (new Anthem tables for CO, GA, MO)
if rb.get("base") == bm and rb.get("build"):
    rst = getj(f"site/builds/st-{rb['build']}/state.json", {}) or {}
    rnames = {"TN": "Tennessee", "CO": "Colorado", "OK": "Oklahoma", "AL": "Alabama", "MS": "Mississippi", "MO": "Missouri", "GA": "Georgia"}
    rdone = [rnames[c] for c in rb["states"] if c in rnames and ls(f"site/every-st/{rnames[c].lower()}/{rb['build']}/embed.json")]
    s7_note += (f"; rebuild of {', '.join(rnames.get(c, c) for c in rb['states'])} with new insurer tables: "
                f"stage {rst.get('stage', 'waiting for insurer files')}" + (f", built: {', '.join(rdone)}" if rdone else "")
                + (" (PAUSED Oct 18: too big; Anthem to be slimmed and added as an update)" if rb.get("paused") else ""))
hosp = ST.get("hospitals", {}); names_ = ST.get("code_names", {})
def tot(*scs, f): return sum(counts.get(s, {}).get(f, 0) for s in scs)
BOTS = [
    ("insurers", "Insurer file reader", "Downloads every insurer's price file and keeps the prices for the area's providers",
     "insurers.yml", "Checks every 6 hours; starts waiting files every 10 min", "insurer files",
     tot("dfw", "tx", "s7", "nc", "ct", "il", "n5", "ar", "b1", "la", "b4", f="total"), tot("dfw", "tx", "s7", "nc", "ct", "il", "n5", "ar", "b1", "la", "b4", f="done"), tot("dfw", "tx", "s7", "nc", "ct", "il", "n5", "ar", "b1", "la", "b4", f="running"),
     tot("dfw", "tx", "s7", "nc", "ct", "il", "n5", "ar", "b1", "la", "b4", f="failed"), tot("dfw", "tx", "s7", "nc", "ct", "il", "n5", "ar", "b1", "la", "b4", f="waiting"),
     "Dallas, Texas and seven-state files together (Molina left out: it posts no Texas files). Machines also take oversized hospital files."),
    ("hospitals", "Hospital price file bot", "Checks each hospital's own price file and saves it", "hospitals.yml",
     "Daily, 4:17am CT (each hospital about once a week)", "hospitals", hosp.get("total"), hosp.get("have_file"), (hosp.get("status") or {}).get("queued for a rented machine"),
     sum((hosp.get("status") or {}).get(k, 0) for k in ("link broken", "not a price file")),
     None, "Done = hospitals with a price file on record, nationwide. Failed = link broken or not a price file at its last check; "
     f"{(hosp.get('status') or {}).get('no price file found', 0):,} more have no price file found yet."),
    ("find_sites", "Hospital website finders", "Looks for the websites and price files of hospitals with none on record",
     "find-sites.yml", "Sundays (map listings, chains) and monthly on the 6th (web search)", "", None, None, None, None, None, ""),
    ("refresh", "Monthly website refresh", "Rebuilds the Dallas Price Finder from the month's files and publishes it", "site-build.yml",
     "Every 6 hours; starts on the 8th", "", None, None, None, None, None, "First automatic build: November 8."),
    ("texas_pages", "Texas city pages", "Builds the 23 Texas city and metro Price Finder pages", "site-build.yml",
     "Monthly, after the Dallas refresh", "", None, None, None, None, None, ""),
    ("state_pages", "Seven-state page builder", "Builds the Price Finder pages for TN, CO, OK, AL, MS, MO, GA", "state-pages.yml",
     "Hourly while a build runs", "states", 7, built7, None, None, None, s7_note),
    ("nc_pages", "North Carolina page builder", "Builds the North Carolina Price Finder page", "nc-pages.yml",
     "Hourly at :11 while a build runs", "states", 1, 1 if ls(f"site/every-st/north-carolina/{bm}/embed.json") else 0, None,
     None, None, nc_note),
    ("ct_pages", "Connecticut page builder", "Builds the Connecticut Price Finder page", "ct-pages.yml",
     "Hourly at :26 while a build runs", "states", 1, 1 if ls(f"site/every-st/connecticut/{bm}/embed.json") else 0, None,
     None, None, ct_note),
    ("hospital_pages", "Hospital prices for the state and city pages", "Adds each area's hospital prices to its Price Finder page",
     "hosp-areas.yml", "Runs with the page builders", "states", len(hst.get("areas") or []) or None, len(hst.get("published") or {}) or None,
     None, None, None, ""),
    ("dashboard", "Dashboard data", "Builds this dashboard's files, including the Network access tab", "dashboard.yml",
     "Daily, after the hospital bot", "", None, None, None, None, None, "Uploaded to the dashboard daily at 12:52pm CT and by Refresh data now."),
    ("names", "Plain-English code names", "Writes plain names for codes still showing the insurer's wording", "names.yml",
     "Daily, 4:37am CT", "CPT codes", names_.get("cpt_codes"), names_.get("named"), None, None, None, ""),
    ("inventory", "Contract end dates and file inventory", "Counts what's in each insurer table and its contract end dates",
     "inventory-backfill.yml", "Every 6 hours until every table is done", "", None, None, None, None, None, ""),
    ("calculator", "Plan Calculator data", "Builds next year's marketplace plans the day CMS posts them", "calculator.yml",
     "Daily, 8:23am CT", "", None, None, None, None, None, "Waiting on CMS's 2027 files."),
    ("status", "Status snapshot", "Collects these numbers for this tab and the status board", "board-status.yml",
     "Every 15 minutes", "", None, None, None, None, None, ""),
    ("tests", "Tests (Claude)", "One-off test machines Claude starts to check a change before it goes live", "", "As needed", "",
     None, None, None, None, None, ""),
    ("one_off_builds", "Earlier hand-run builds", "Machines from builds run by hand before the bots took over", "", "Not scheduled", "",
     None, None, None, None, None, ""),
    ("one_off_downloads", "Earlier hand-run downloads", "Hospital file downloads run by hand", "", "Not scheduled", "", None, None, None,
     None, None, ""),
]
bots = []
for i, (bid, name, does, wf, sched, unit, total, done, running, failed, waiting, note) in enumerate(BOTS):
    lr = last.get(wf, ("", ""))
    lr = (lr[0], {"pending": "running", "in_progress": "running", "queued": "starting"}.get(lr[1], lr[1]))
    bots.append({"id": bid, "order": i + 1, "bot": name, "does": does, "schedule": sched, "last_run": lr[0], "last_result": lr[1],
                 "unit": unit, "total": total, "done": done, "running": running, "failed": failed, "waiting": waiting,
                 "machines_now": now_by_bot[bid][0], "usd_hour_now": round(now_by_bot[bid][1], 3),
                 "usd_month": round(bot_month.get(bid, 0.0), 2), "note": note})
save("ops_bots", bots)

# ---------- one summary row ----------
dom = ST.get("digitalocean", {}) or {}
days = defaultdict(float)
for (d, _, _), v in costs.items(): days[d] += v[0]
# the last 7 days DigitalOcean has billed (its preview runs about a day behind), days without spend counted as $0
from datetime import timedelta
billed = sorted(d for d in days if d < NOW.strftime("%Y-%m-%d"))
if billed:
    end = datetime.fromisoformat(billed[-1]); week = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    per_day = sum(days.get(d, 0.0) for d in week) / 7
else:
    per_day, week = None, []
credit = dom.get("credit_left_usd")
save("ops_meta", [{"id": "now", "generated_at": NOW.isoformat(timespec="seconds"), "spend_month_usd": dom.get("month_to_date_usd"),
                   "credit_left_usd": credit, "usd_hour_now": round(sum(r["usd_hour"] for r in mrows), 3),
                   "machines_now": len(machines), "machine_limit": limit, "idle_machines": sum(1 for r in mrows if r["idle"]),
                   "failed_files": len(fails), "held_areas": sum(1 for r in hold_rows if r["state"] == "held"),
                   "usd_per_day_7d": round(per_day, 2) if per_day else None,
                   "billed_through": billed[-1] if billed else None, "billed_month_usd": round(sum(days.values()), 2),
                   "credit_days_left_projection": round(credit / per_day, 1) if credit and per_day else None}])
print("ops:", {p.name: p.stat().st_size for p in sorted(OUT.glob("ops_*.json"))})
