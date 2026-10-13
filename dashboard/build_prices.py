"""Price-side data for the Price Transparency Metrics dashboard: DFW plus every live Price Finder area whose build is finished
(the Texas cities and metro areas, small-town Texas, and the first national batch of states; the list is site/city_page.py CITIES).
Moved from Healthcare/14b_build_dashboard_prices.py into the bot on Oct 13, 2026; run daily by .github/workflows/dashboard.yml.

Same counting rules as Healthcare/14_build_dashboard_summary.py (which it replaces): counts and actual rates at ranks
(lowest, p10, middle, p90, highest), never averages; $99,999+ placeholders left out; only the 89 featured procedures.

Reads (R2):
  site/deploy/price-finder.html                 DFW Price Finder page (embedded tables: providers, networks, Medicare,
                                                posted cash prices, DFW hospital files, CMS shoppable list)
  site/every/CURRENT -> site/every/<build>/t/    DFW per-code insurer rate files
  site/every/<build>/h/<code>.txt               DFW hospital price file lines per code
  site/every-tx|every-st/<area>/<YYYY-MM>/embed.json  an area's finished build (written only when all 256 parts are in);
          .../t/<code>.txt                      areas without embed.json are skipped, so nothing half-built shows
          .../hosp/hosp_index.json, hosp/h/<code>.txt   the area's own hospital price files (site/hosp_area.py), when built
  reference/2026-09-29/cms/rvu26d-*.zip         CMS 2026 physician fee schedule (RVUs + GPCIs) for each metro's locality
  bot/dashboard/price-history/                  rate snapshots, one per market per insurer-file date (for rate_changes)
Writes out/dashboard/{markets,insurers,procedures,procedure_rates..procedure_rates_N,site_of_care,hospital_files,rate_changes}.json
(rate rows are packed whole-market into files under 7 MB each, because a dashboard file must stay under 8 MB; always
RATE_FILES files, empty ones as []).

Medicare: hospital outpatient (OPPS), surgery center (ASC) and lab rates are national, taken from the DFW page;
doctor fees use each area's own Medicare locality (the same state and locality as its Price Finder page, city_page.CITIES),
same formula as site/build_med_all.py. Providers' posted cash prices are only in the DFW Price Finder, so other areas show
none (blank, not 0); an area without its own hospital price files yet also shows blank.

  python dashboard/build_prices.py [--only DFW,AUS] [--dry]   (--dry: don't write snapshots to R2)
Env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
"""
import argparse, base64, csv, datetime, gzip, io, json, os, re, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import boto3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import city_page as CP   # the live area list, states and Medicare localities

ap = argparse.ArgumentParser(); ap.add_argument("--only", default=""); ap.add_argument("--dry", action="store_true")
ap.add_argument("--out", default="out/dashboard"); ap.add_argument("--dfw-page", default="", help="local copy of the DFW Price Finder page (testing)")
ARGS = ap.parse_args()
E = {k: "".join(v.split()) if k.startswith("R2_") else v for k, v in os.environ.items()}; BUCKET = E["R2_BUCKET"]   # secrets may carry a newline
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
def get_bytes(key): return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
def get_text(key): return get_bytes(key).decode().strip()
def exists(key):
    try: s3.head_object(Bucket=BUCKET, Key=key); return True
    except Exception: return False
def ls_dirs(prefix): return [c["Prefix"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix, Delimiter="/") for c in pg.get("CommonPrefixes", [])]
def page_data(html):
    a = html.find('<script type="application/json" id="data">'); a = html.find(">", a) + 1
    return json.loads(html[a:html.find("</script>", a)])

FEATURED = {"00811", "00812", "19120", "216", "22551", "27130", "27447", "29826", "29827", "29881", "29888", "42820", "43235", "43239", "43644", "43775", "45378", "45380", "45385", "45391", "460", "470", "473", "47562", "49505", "55250", "55700", "55866", "59400", "59510", "59610", "62322", "62323", "63030", "64483", "64721", "66821", "66984", "70450", "70551", "70553", "72110", "72148", "72193", "73721", "74177", "743", "75571", "76700", "76805", "76830", "77065", "77066", "77067", "80048", "80053", "80055", "80061", "80069", "80076", "81000", "81001", "81002", "81003", "84153", "84154", "84443", "85025", "85027", "85610", "85730", "88305", "90832", "90834", "90837", "90846", "90847", "90853", "93000", "93452", "95810", "97110", "99203", "99204", "99205", "99243", "99244", "99385", "99386"}
FEATURED_EXTRA = "description as written in the insurer file"
TODAY = datetime.date.today()
PLACES = {"H": "Hospital", "A": "Surgery center", "G": "Office or clinic", "P": "Office or clinic"}

# market keys: the first four cities keep their old short keys (rate-change history is saved under them); others use the page's slug
OLDKEY = {"austin": "AUS", "san-antonio": "SAT", "houston": "HOU", "el-paso": "ELP"}
RATE_FILES, RATE_MAX = 10, 7_000_000

# ---------- DFW page (also the source of national Medicare rates and the shoppable list) ----------
DFW = page_data(open(ARGS.dfw_page, encoding="utf-8").read() if ARGS.dfw_page else get_bytes("site/deploy/price-finder.html").decode("utf-8"))
SHOP = set(DFW.get("shop", []))
NATIONAL = DFW["med"]["codes"]

# ---------- Medicare physician fee schedule for each locality (same formula as site/build_med_all.py) ----------
Z = zipfile.ZipFile(io.BytesIO(get_bytes("reference/2026-09-29/cms/rvu26d-updated-08-26-2026.zip")))
GPCI = {(r[1], r[2]): [float(r[4]), float(r[5]), float(r[6])] for r in csv.reader(io.TextIOWrapper(Z.open("GPCI2026.csv"), encoding="latin-1"))
        if len(r) > 6 and re.fullmatch(r"[A-Z]{2}", r[1]) and re.fullmatch(r"\d\d", r[2])}
def num(x):
    try: return float(str(x).replace("$", "").replace(",", "").strip())
    except ValueError: return None
L = list(csv.reader(io.TextIOWrapper(Z.open("PPRRVU2026_Oct_nonQPP.csv"), encoding="latin-1")))
k0 = next(j for j, r in enumerate(L) if r and r[0].strip() == "HCPCS")
PFS = {}
for r in L[k0 + 1:]:
    if len(r) < 26 or r[0] not in FEATURED or r[1] != "" or r[3] not in ("A", "R", "T"): continue
    w, pen, nfna, pef, fna, mp, cf = num(r[5]), num(r[6]), r[7].strip(), num(r[8]), r[9].strip(), num(r[10]), num(r[25])
    v = {}
    for loc, (gw, gp, gm) in GPCI.items():
        nf = None if nfna == "NA" else round((w * gw + pen * gp + mp * gm) * cf, 2)
        fa = None if fna == "NA" else round((w * gw + pef * gp + mp * gm) * cf, 2)
        v[loc] = [nf, fa if fa is not None else nf]
    if all(x is None or x == 0 for x in v[("TX", "11")]): continue
    PFS[r[0]] = v
# check: Dallas figures must match the DFW page's own Medicare table
bad = [c for c in FEATURED if (NATIONAL.get(c, {}).get("pfs", {}).get("dal")) != (PFS.get(c, {}).get(("TX", "11")))]
assert not bad, f"Dallas doctor fees don't match the DFW page for {bad[:5]}"

def medicare(code, m):
    n = NATIONAL.get(code, {}); p = PFS.get(code, {}).get((m["state"], m["loc"])) or [None, None]
    return {"opps": (n.get("opps") or [None])[0], "asc": (n.get("asc") or [None])[0], "doc_fac": p[1], "doc_off": p[0],
            "lab": n.get("lab"), "loc": m["locname"]}

# ---------- markets ----------
_cur = f"site/every/{get_text('site/every/CURRENT')}/"
MARKETS = {"DFW": {"state": "TX", "name": "Dallas–Fort Worth", "loc": "11", "locname": "Dallas", "D": DFW, "codes": _cur + "t/",
                   "hosp": (DFW["hosp"]["src"], _cur + "h/")}}
missing = [st for st in {CP.STATE_OF.get(s, "TX") for s in CP.CITIES} if not any(k[0] == st for k in GPCI)]
assert not missing, f"no Medicare localities for {missing} in GPCI2026.csv"
for slug, (name, _, loc, locname) in CP.CITIES.items():
    key, st = OLDKEY.get(slug, slug), CP.STATE_OF.get(slug, "TX")
    assert (st, loc) in GPCI, f"Medicare locality {st} {loc} for {name} is not in GPCI2026.csv"
    months = sorted(d for d in ls_dirs(f"{CP.root(slug)}{slug}/") if exists(d + "embed.json"))
    if not months: print(f"{name}: not finished yet, skipped"); continue
    d = months[-1]
    hosp = None
    for d_ in reversed(months):   # newest finished build that has the area's own hospital files (as city_page.py picks them)
        if exists(d_ + "hosp/hosp_index.json"): hosp = (json.loads(get_bytes(d_ + "hosp/hosp_index.json"))["src"], d_ + "hosp/h/"); break
    D_ = json.loads(get_bytes(d + "embed.json"))
    lines = sum(c.get("n", 0) for c in D_["codes"].values()); have = sum(c in D_["codes"] for c in FEATURED)
    if lines == 0 or have < 45:   # a finished build with no rates (or few featured codes) is a broken build, not a real market
        print(f"WARNING {name}: {d}embed.json has {len(D_['codes'])} codes, {lines} rate lines, {have} of 89 featured codes; skipped as a broken build"); continue
    MARKETS[key] = {"state": st, "name": name, "loc": loc, "locname": locname, "D": D_, "codes": d + "t/", "hosp": hosp}
    print(f"{name}: using {d} ({len(D_['codes']):,} codes, {have} of 89 featured; {len(hosp[0]) if hosp else 'no'} hospital files)")
if ARGS.only: MARKETS = {k: v for k, v in MARKETS.items() if k in ARGS.only.split(",")}

def pdate(x):
    """A file's own date as written (ISO or M/D/YYYY) -> date, else None."""
    x = str(x or "").strip()[:10]
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try: return datetime.datetime.strptime(x, f).date()
        except ValueError: pass
    return None

def at(vals, q): return vals[int(q * (len(vals) - 1))]

def stats(vals_by_prov, nrates):
    v = sorted(vals_by_prov.values())
    if not v: return None
    return {"prov": len(v), "rates": nrates, "lo": v[0], "p10": at(v, .1), "mid": at(v, .5), "p90": at(v, .9), "hi": v[-1],
            "spread": round(at(v, .9) / at(v, .1), 2) if len(v) >= 10 and at(v, .1) > 0 else None}

def bench(md, fee, place):
    """Medicare rate for the same setting, and what it is."""
    if md.get("lab") and not (md.get("opps") or md.get("doc_fac") or md.get("doc_off")):
        return md["lab"], "Medicare lab fee schedule"
    if fee == "fac":
        if place == "Surgery center" and md.get("asc"): return md["asc"], "Medicare surgery center rate (national)"
        if place in ("Hospital", "All places") and md.get("opps"): return md["opps"], "Medicare hospital outpatient rate (national)"
        return None, ""
    if place == "Office or clinic" and md.get("doc_off"): return md["doc_off"], f"Medicare doctor fee, office ({md['loc']})"
    if md.get("doc_fac"): return md["doc_fac"], f"Medicare doctor fee, facility ({md['loc']})"
    if md.get("doc_off"): return md["doc_off"], f"Medicare doctor fee, office ({md['loc']})"
    return None, ""


def hfile(prefix, code):
    """One code's hospital price-file lines: {"c": [[s,st,cash,gross,row,fee,d]], "r": [[s,ins,prod,p,fee,pct,val,row,st,flat]]}."""
    try: t = get_bytes(prefix + f"{code}.txt")
    except Exception: return None   # no hospital file lists this code
    try: return json.loads(t)
    except ValueError: return json.loads(gzip.decompress(base64.b64decode(t)))


def build_market(key, m):
    D = m["D"]; IS_DFW = key == "DFW"   # providers' posted cash prices exist only in the DFW Price Finder
    HAS_HOSP = m["hosp"] is not None    # hospital price files: DFW, and each area once site/hosp_area.py has built them
    HC = {}
    nets = [n.split("|", 1) for n in D["nets"]]
    insurers = sorted({i for i, _ in nets})
    kinds = [f[2] for f in D["fac"]]
    shop = SHOP   # CMS shoppable-services list (national; carried in the DFW Price Finder)
    ins_prov = {i: set() for i in insurers}; ins_rates = dict.fromkeys(insurers, 0); ins_lines = dict.fromkeys(insurers, 0)
    ins_codes = {i: set() for i in insurers}; ins_nets = {i: sorted(n for j, n in nets if j == i) for i in insurers}
    placeholders = 0; procs = []; seen = set(); dseen = set()   # networks with at least one rate line for a featured procedure here
    for code, c in D["codes"].items():
        if code not in FEATURED or c.get("cat") == FEATURED_EXTRA: continue
        try: f = json.loads(gzip.decompress(base64.b64decode(get_text(m["codes"] + f"{code}.txt"))))["f"]
        except Exception as e: print("could not read", code, e); f = {}
        acc = {}
        for fi, rows in f.items():
            fi = int(fi); place = PLACES.get(kinds[fi], "Office or clinic")
            for r in rows:
                ins = nets[r[0]][0]; n = 1 + (r[7] or 0)
                ins_prov[ins].add(fi); ins_rates[ins] += n; ins_lines[ins] += 1; ins_codes[ins].add(code); seen.add(r[0]); dseen.add(r[5])
                if r[2] == 0 and r[3] and r[3] >= 99999: placeholders += 1; continue
                if r[2] != 0 or not r[3] or r[3] <= 0: continue
                fee = "doc" if r[1] == 1 else "fac"
                for k in ((ins, fee, place), (ins, fee, "All places"), ("All insurers", fee, place), ("All insurers", fee, "All places")):
                    a = acc.setdefault(k, [{}, 0]); a[1] += n
                    if fi not in a[0] or r[3] < a[0][fi]: a[0][fi] = r[3]
        md = medicare(code, m)
        cash = [x for x in D["cash"] if x["code"] == code] if IS_DFW else None
        hc = HC[code] = hfile(m["hosp"][1], code) if HAS_HOSP else None
        procs.append({"code": code, "name": c["name"], "cat": c["cat"], "shop": code in shop, "medicare": md,
                      "stats": {k: stats(v, n) for k, (v, n) in acc.items()},
                      "cash": {"n": len(cash), "lo": min((x["v"] for x in cash), default=None), "hi": max((x["hi"] or x["v"] for x in cash), default=None)} if IS_DFW else {"n": None, "lo": None, "hi": None},
                      "hosp_cash_files": (len({r[0] for r in hc["c"]}) if hc else 0) if HAS_HOSP else None,
                      "hosp_rate_files": (len({r[0] for r in hc["r"]}) if hc else 0) if HAS_HOSP else None})
    print(key, len(procs), "procedures read")
    kind_ct = lambda S: {k: sum(1 for i in S if kinds[i] == k) for k in "HAGP"}
    allp = set().union(*ins_prov.values())
    # hospital files: age and how often a negotiated rate is given only as a percentage (featured codes)
    H = {"codes": {c: v for c, v in HC.items() if v}, "src": m["hosp"][0] if HAS_HOSP else []}; files = []
    per = {}
    for cc in H["codes"].values():
        for r in cc["r"]:
            if r[4] != 0: continue
            p = per.setdefault(r[0], [0, 0, 0]); p[1 if r[5] else 0] += 1
        for r in cc["c"]:
            if r[5] == 0: per.setdefault(r[0], [0, 0, 0])[2] += 1
    for s, src in enumerate(H["src"]):
        dd = pdate(src[3]); d = dd.isoformat() if dd else None; dollar, pct, cashn = per.get(s, [0, 0, 0])
        age = (TODAY - dd).days if dd else None
        files.append({"id": f"{key}|{s}", "market": key, "hospital": src[0], "city": src[1], "file_date": d, "days_old": age,
                      "age_flag": "No date in file" if age is None else ("Over 6 months old" if age > 183 else "Current"),
                      "negotiated_rates": dollar + pct, "percent_only": pct,
                      "percent_only_share": round(pct / (dollar + pct), 4) if dollar + pct else None,
                      "cash_prices": cashn, "file_url": src[4]})
    # Texas builds share one network list across all metros: count only insurers and networks with rates in this market
    live = [i for i in insurers if ins_lines[i] > 0]
    ins_nets = {i: sorted(n for x, (j, n) in enumerate(nets) if j == i and x in seen) for i in live}
    # DFW keeps the page's own file-date list; a Texas metro uses the dates of the insurer files that have rates there
    dates = sorted(set(D["dates"])) if IS_DFW else sorted({D["dates"][x] for x in dseen if D["dates"][x]})
    return {"state": m["state"], "name": m["name"], "dates": dates, "procs": procs, "files": files,
            "ins": [{"name": i, "networks": ins_nets[i], "prov": len(ins_prov[i]), "by_kind": kind_ct(ins_prov[i]),
                     "rates": ins_rates[i], "lines": ins_lines[i], "codes": len(ins_codes[i])} for i in live],
            "totals": {"providers": len(allp), "by_kind": kind_ct(allp), "rates": sum(ins_rates.values()), "lines": sum(ins_lines.values()),
                       "placeholders_excluded": placeholders, "insurers": len(live), "networks": len(seen), "procedures": len(procs),
                       "all_codes": len(D["codes"]), "all_providers": len(D["fac"]), "all_rate_lines": sum(c.get("n", 0) for c in D["codes"].values()),
                       "hospital_files": len(H["src"]) if HAS_HOSP else None, "cash_listings": len(D["cash"]) if IS_DFW else None}}


OUT = Path(ARGS.out); OUT.mkdir(parents=True, exist_ok=True)
HIST = OUT.parent / "price-history"; HIST.mkdir(parents=True, exist_ok=True); HIST_KEY = "bot/dashboard/price-history/"
for o in [o for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=HIST_KEY) for o in pg.get("Contents", [])]:
    dst = HIST / o["Key"].rsplit("/", 1)[1]
    if not dst.exists(): s3.download_file(BUCKET, o["Key"], str(dst))
save = lambda name, rows: (OUT / f"{name}.json").write_text(json.dumps(rows, separators=(",", ":")))

with ThreadPoolExecutor(8) as ex:
    built = dict(zip(MARKETS, ex.map(lambda kv: build_market(*kv), MARKETS.items())))
markets = built

mrows, irows, prows, rrows, srows, frows, allchg = [], [], [], [], [], [], []
for k, m in markets.items():
    t = m["totals"]
    mrows.append({"market": k, "name": m["name"], "state": m["state"], "providers": t["providers"], "hospitals": t["by_kind"]["H"],
                  "surgery_centers": t["by_kind"]["A"], "practices": t["by_kind"]["G"], "clinicians": t["by_kind"]["P"],
                  "rate_lines": t["lines"], "published_rates": t["rates"], "placeholders_excluded": t["placeholders_excluded"],
                  "insurers": t["insurers"], "networks": t["networks"], "procedures": t["procedures"], "all_codes": t["all_codes"],
                  "all_providers": t["all_providers"], "all_rate_lines": t["all_rate_lines"], "hospital_files": t["hospital_files"],
                  "cash_listings": t["cash_listings"], "oldest_file": m["dates"][0], "newest_file": m["dates"][-1]})
    frows += m["files"]
    pct_by_ins = {}
    for p in m["procs"]:
        md, c = p["medicare"], p["cash"]
        prows.append({"id": f"{k}|{p['code']}", "market": k, "code": p["code"], "procedure": p["name"], "category": p["cat"],
                      "shoppable": "Yes" if p["shop"] else "No", "medicare_hospital_outpatient": md["opps"], "medicare_surgery_center": md["asc"],
                      "medicare_doctor_facility": md["doc_fac"], "medicare_doctor_office": md["doc_off"], "medicare_lab": md["lab"],
                      "cash_listings": c["n"], "cash_lowest": c["lo"], "cash_highest": c["hi"],
                      "hospital_files_cash": p["hosp_cash_files"], "hospital_files_rates": p["hosp_rate_files"]})
        for (ins, fee, place), st in sorted(p["stats"].items(), key=lambda x: (x[0][0] != "All insurers",) + x[0]):
            if not st: continue
            b, basis = bench(md, fee, place)
            pm = lambda v: round(v / b, 3) if b else None
            lab = "Facility fee" if fee == "fac" else "Doctor fee"
            rrows.append({"id": f"{k}|{p['code']}|{ins}|{lab}|{place}", "market": k, "code": p["code"], "procedure": p["name"],
                          "category": p["cat"], "insurer": ins, "fee": lab, "place": place, "providers": st["prov"], "rates": st["rates"],
                          "lowest": st["lo"], "p10": st["p10"], "middle": st["mid"], "p90": st["p90"], "highest": st["hi"], "spread": st["spread"],
                          "medicare": b, "medicare_basis": basis, "pct_medicare_middle": pm(st["mid"]),
                          "pct_medicare_p10": pm(st["p10"]), "pct_medicare_p90": pm(st["p90"])})
            if place == "All places" and b: pct_by_ins.setdefault((ins, fee), []).append(st["mid"] / b)
        for ins in ["All insurers"] + [i["name"] for i in m["ins"]]:
            h, a = p["stats"].get((ins, "fac", "Hospital")), p["stats"].get((ins, "fac", "Surgery center"))
            if h and a:
                srows.append({"id": f"{k}|{p['code']}|{ins}", "market": k, "code": p["code"], "procedure": p["name"], "category": p["cat"],
                              "insurer": ins, "hospital_middle": h["mid"], "hospital_providers": h["prov"],
                              "surgery_center_middle": a["mid"], "surgery_center_providers": a["prov"],
                              "difference": round(h["mid"] - a["mid"], 2), "ratio": round(h["mid"] / a["mid"], 2) if a["mid"] else None})
    med = lambda v: sorted(v)[(len(v) - 1) // 2] if v else None
    for i in m["ins"]:
        f_, d_ = med(pct_by_ins.get((i["name"], "fac"), [])), med(pct_by_ins.get((i["name"], "doc"), []))
        irows.append({"id": f"{k}|{i['name']}", "market": k, "insurer": i["name"], "networks": len(i["networks"]),
                      "network_names": "; ".join(i["networks"]), "providers": i["prov"], "hospitals": i["by_kind"]["H"],
                      "surgery_centers": i["by_kind"]["A"], "practices": i["by_kind"]["G"], "clinicians": i["by_kind"]["P"],
                      "rate_lines": i["lines"], "published_rates": i["rates"], "procedures_priced": i["codes"],
                      "pct_medicare_facility": round(f_, 3) if f_ else None, "pct_medicare_doctor": round(d_, 3) if d_ else None,
                      "procedures_vs_medicare_facility": len(pct_by_ins.get((i["name"], "fac"), [])),
                      "procedures_vs_medicare_doctor": len(pct_by_ins.get((i["name"], "doc"), []))})

    # rate changes: snapshot per insurer-file month; compare with the latest earlier month
    snap = HIST / f"procedure_rates_{k}_{m['dates'][-1]}.json"
    if (not snap.exists() or snap.stat().st_size <= 2) and any(r["market"] == k for r in rrows):   # never save an empty snapshot; replace one
        snap.write_text(json.dumps([r for r in rrows if r["market"] == k], separators=(",", ":")))
        if not ARGS.dry: s3.upload_file(str(snap), BUCKET, HIST_KEY + snap.name); print("saved rate snapshot", snap.name)
    prev = sorted(p for p in HIST.glob(f"procedure_rates_{k}_*.json") if p.name < snap.name and p.stat().st_size > 2)   # ignore empty snapshots
    chg = []
    if prev:
        old = {r["id"]: r for r in json.loads(prev[-1].read_text())}
        prev_date = re.search(r"_(\d{4}-\d{2}-\d{2})\.json$", prev[-1].name).group(1)
        for r in rrows:
            o = old.get(r["id"])
            if r["market"] == k and o and o["middle"] and r["middle"] != o["middle"]:
                chg.append({"id": r["id"], "market": k, "code": r["code"], "procedure": r["procedure"], "insurer": r["insurer"],
                            "fee": r["fee"], "place": r["place"], "previous_middle": o["middle"], "current_middle": r["middle"],
                            "change": round(r["middle"] / o["middle"] - 1, 4), "previous_files": prev_date, "current_files": m["dates"][-1]})
    # one summary row per market says what was compared, so the section always has something true to show
    allchg.append({"id": f"{k}|summary", "kind": "summary", "market": k, "previous_files": prev_date if prev else None,
                   "current_files": m["dates"][-1], "changed": len(chg)})
    allchg += chg

save("markets", mrows); save("insurers", irows); save("procedures", prows)
# rate rows: whole markets packed into RATE_FILES files under RATE_MAX bytes each (a dashboard file must stay under 8 MB)
by_m = {}
for r in rrows: by_m.setdefault(r["market"], []).append(r)
packs = [[] for _ in range(RATE_FILES)]; size = [2] * RATE_FILES
for k in sorted(by_m, key=lambda k: -len(json.dumps(by_m[k], separators=(",", ":")))):
    n = len(json.dumps(by_m[k], separators=(",", ":"))) + 1
    i = min(range(RATE_FILES), key=lambda j: size[j])
    if size[i] + n > RATE_MAX: raise SystemExit(f"STOP: rate rows don't fit in {RATE_FILES} files of {RATE_MAX:,} bytes; raise RATE_FILES (and the dashboard's inputs)")
    packs[i] += by_m[k]; size[i] += n
for i, rows in enumerate(packs): save("procedure_rates" + (f"_{i + 1}" if i else ""), rows)
save("site_of_care", srows); save("hospital_files", frows); save("rate_changes", allchg)
print("flat files:", {p.name: p.stat().st_size for p in sorted(OUT.glob("*.json"))})
for r in mrows: print(f"  {r['name']}: {r['providers']:,} providers, {r['rate_lines']:,} rate lines, {r['insurers']} insurers, {r['networks']} networks, files {r['oldest_file']} to {r['newest_file']}")
