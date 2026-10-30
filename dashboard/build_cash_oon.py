"""Control center: "Cash prices" and "Out of network" tabs (Oct 30, 2026, Betsy). Run daily by .github/workflows/dashboard.yml.

Same counting rules as build_prices.py: only the 89 featured procedures, actual amounts at ranks (lowest, middle, highest),
never averages, every row keeps its file, line and link. Nothing here is estimated.

Cash prices (hospital price files, every live Price Finder area that has its own hospital files, plus DFW's posted prices):
  cash_hosp, cash_hosp_2 .. _N   one row per area x procedure x hospital file x fee type x setting: the lowest cash price
                                 the file lists, its list price, and that same file's in-network dollar rates for the same
                                 procedure (count, lowest, middle, highest, how many are below the cash price). In-network
                                 means commercial, marketplace or unlabelled plans: Medicare Advantage, Medicaid and
                                 out-of-network rows are left out, and so are "flat" amounts (the same dollar amount on 5+
                                 procedures in one file), which are not a price for the service.
  cash_proc                      one row per area x procedure: how many hospital files list a cash price, the lowest /
                                 middle / highest of them, Medicare's hospital outpatient rate, and how many hospitals' cash
                                 price is below the middle of their own in-network rates.
  cash_files                     each hospital file once (hospital, city, file date, link); cash_hosp and oon_hosp rows point
                                 to it by market + "f", which keeps the files small. The page joins them.
  cash_posted                    providers' own posted cash prices (DFW Price Finder only), as copied from their websites.
Out of network:
  oon_hosp, oon_hosp_2           every hospital-file line labelled out-of-network for a featured procedure (product type 5,
                                 or the same label rule as site/h2_build.py for files built before Oct 30), with the same
                                 file's in-network middle for that insurer beside it for reference. Never mixed into
                                 in-network figures.
  oon_ins_files                  insurers' allowed-amount (out-of-network) files, newest month: files, empty, with data,
                                 failed, services and payments listed, size (from plans/allowed_amounts.py's parquet).
  oon_ins_amounts, _2 .. _N      every payment those files list for a featured procedure: insurer, plan, provider tax ID,
                                 allowed amount, billed charge, number of NPIs, file (packed by procedure).
  oon_ins_sources                each of those files' link, once.
  oon_ins_areas                  how many of those payments fall in each live area (provider NPI in the area's Price Finder
                                 provider list); each payment row carries its areas, provider and city.

  python dashboard/build_cash_oon.py [--only DFW,AUS] [--out out/cash_oon] [--skip-insurers]
Env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (STORAGE_ENDPOINT / STORAGE_REGION when set).
"""
import argparse, base64, datetime, gzip, io, json, os, re, sys, tarfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import city_page as CP   # the live area list (same as build_prices.py)

ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
ap.add_argument("--out", default="out/cash_oon")
ap.add_argument("--skip-insurers", action="store_true", help="skip the insurer allowed-amount files")
ARGS = ap.parse_args()
E = {k: "".join(v.split()) if k.startswith("R2_") else v for k, v in os.environ.items()}
BUCKET = E["R2_BUCKET"]
s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                  region_name=(os.environ.get("STORAGE_REGION") or "auto"))
def get_bytes(key): return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
def get_text(key): return get_bytes(key).decode().strip()
def exists(key):
    try: s3.head_object(Bucket=BUCKET, Key=key); return True
    except Exception: return False
def ls(prefix, dirs=False):
    pg = s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix, **({"Delimiter": "/"} if dirs else {}))
    return [c["Prefix"] for p in pg for c in p.get("CommonPrefixes", [])] if dirs else [o["Key"] for p in pg for o in p.get("Contents", [])]
def page_data(html):
    a = html.find('<script type="application/json" id="data">'); a = html.find(">", a) + 1
    return json.loads(html[a:html.find("</script>", a)])

FEATURED = {"00811", "00812", "19120", "216", "22551", "27130", "27447", "29826", "29827", "29881", "29888", "42820", "43235", "43239", "43644", "43775", "45378", "45380", "45385", "45391", "460", "470", "473", "47562", "49505", "55250", "55700", "55866", "59400", "59510", "59610", "62322", "62323", "63030", "64483", "64721", "66821", "66984", "70450", "70551", "70553", "72110", "72148", "72193", "73721", "74177", "743", "75571", "76700", "76805", "76830", "77065", "77066", "77067", "80048", "80053", "80055", "80061", "80069", "80076", "81000", "81001", "81002", "81003", "84153", "84154", "84443", "85025", "85027", "85610", "85730", "88305", "90832", "90834", "90837", "90846", "90847", "90853", "93000", "93452", "95810", "97110", "99203", "99204", "99205", "99243", "99244", "99385", "99386"}
TODAY = datetime.date.today()
OLDKEY = {"austin": "AUS", "san-antonio": "SAT", "houston": "HOU", "el-paso": "ELP"}   # same market keys as build_prices.py
# same rule as site/h2_build.py and site/match_pilot.py (Betsy, Oct 29: out-of-network is kept, labelled, never in-network)
OON_RE = re.compile(r'\bOON\b|out[\s-]*of[\s-]*network|\bnon[\s-]*par(ticipating)?\b', re.I)
IN_NET = (0, 1, 4)   # product types counted as in-network: commercial, marketplace, not labelled (2 MA, 3 Medicaid, 5 out of network)
MAX_BYTES = 7_000_000   # a control-center file must stay under 8 MB


def pdate(x):
    x = str(x or "").strip()[:10]
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try: return datetime.datetime.strptime(x, f).date()
        except ValueError: pass
    return None

def mid(v):
    """the middle value of a sorted list (lower middle when even), as build_prices.py: an actual amount, not an average"""
    return v[(len(v) - 1) // 2] if v else None

def rnd(v): return None if v is None else round(float(v), 2)


# ---------- DFW page (national Medicare rates, posted cash prices, DFW hospital files) ----------
DFW = page_data(get_bytes("site/deploy/price-finder.html").decode("utf-8"))
NATIONAL = DFW["med"]["codes"]
NAMES = {c: v["name"] for c, v in DFW["codes"].items() if c in FEATURED}

def medicare_hosp(code):
    """Medicare's national hospital outpatient rate for the code (or lab fee), and what it is"""
    n = NATIONAL.get(code, {})
    if (n.get("opps") or [None])[0]: return n["opps"][0], "Medicare hospital outpatient rate (national)"
    if n.get("lab"): return n["lab"], "Medicare lab fee schedule"
    return None, ""

_cur = f"site/every/{get_text('site/every/CURRENT')}/"
MARKETS = {"DFW": {"name": "Dallas–Fort Worth", "state": "TX", "hidx": DFW["hosp"], "h": _cur + "h/"}}
AREAS = {"DFW": {"name": "Dallas–Fort Worth", "npis": _cur + "npis.json", "fac": DFW["fac"],   # every live area's provider list
                 "registry": "data/2026-09-29/dfw_npis_all.parquet"}}
for slug, (name, *_rest) in CP.CITIES.items():
    key, st = OLDKEY.get(slug, slug), CP.STATE_OF.get(slug, "TX")
    months = sorted(d for d in ls(f"{CP.root(slug)}{slug}/", dirs=True) if exists(d + "embed.json"))
    if months: AREAS[key] = {"name": name, "npis": months[-1] + "npis.json", "embed": months[-1] + "embed.json", "registry": CP.npis_key(slug)}
    for d_ in reversed(months):   # newest finished build with the area's own hospital files (as city_page.py picks them)
        if exists(d_ + "hosp/hosp_index.json"):
            MARKETS[key] = {"name": name, "state": st, "hidx": json.loads(get_bytes(d_ + "hosp/hosp_index.json")), "h": d_ + "hosp/h/"}
            break
    else:
        print(f"{name}: no hospital price files yet, skipped")
if ARGS.only: MARKETS = {k: v for k, v in MARKETS.items() if k in ARGS.only.split(",")}
print(len(MARKETS), "areas with hospital price files")


def hfile(prefix, code):
    try: t = get_bytes(prefix + f"{code}.txt")
    except Exception: return None   # no hospital file lists this code
    try: return json.loads(t)
    except ValueError: return json.loads(gzip.decompress(base64.b64decode(t)))


def build_market(key, m):
    H = m["hidx"]; src = H["src"]; ins_names = H.get("ins") or []; gplans = H.get("plans") or []
    cash_rows, oon_rows, proc_rows, used = [], [], [], set()
    for code in sorted(FEATURED):
        f = hfile(m["h"], code)
        med, med_what = medicare_hosp(code)
        if not f:
            proc_rows.append({"id": f"{key}|{code}", "market": key, "area": m["name"], "code": code, "procedure": NAMES.get(code, code), "hospitals_cash": 0,
                              "hospitals_any": 0, "cash_lowest": None, "cash_middle": None, "cash_highest": None, "medicare": rnd(med),
                              "medicare_what": med_what, "middle_x_medicare": None, "cash_below_own_middle": 0, "compared": 0})
            continue
        plans = f.get("p") or gplans; capped = (f.get("x") or {}).get("r") or {}
        plan_of = lambda r: plans[r[3]] if isinstance(r[3], int) and r[3] < len(plans) else ""
        ins_of = lambda r: ins_names[r[1]] if isinstance(r[1], int) and r[1] < len(ins_names) else str(r[1])
        is_oon = lambda r: r[2] == 5 or bool(OON_RE.search(f" {plan_of(r)} "))
        # in-network dollar rates by (file, fee type): [(value, setting, insurer)]
        inn = defaultdict(list)
        for r in f.get("r", []):
            if r[5] or r[9] or r[2] not in IN_NET or is_oon(r): continue   # percent-only, flat, MA/Medicaid, out of network
            inn[(r[0], r[4])].append((r[6], r[8], ins_of(r)))
        for r in f.get("r", []):   # out-of-network lines: listed on their own, never compared or counted as in-network
            if not is_oon(r): continue
            same = sorted(v for v, _, i in inn.get((r[0], r[4]), []) if i == ins_of(r))
            used.add(r[0])
            oon_rows.append({"market": key, "code": code, "f": r[0], "insurer": ins_of(r), "plan": plan_of(r), "pct": r[5], "amount": r[6],
                             "fee": r[4], "st": r[8] or "", "row": r[7], "inn_mid": rnd(mid(same)), "inn_n": len(same)})
        # cash: the lowest cash line per file x fee type x setting
        best = {}
        for c in f.get("c", []):
            k = (c[0], c[5], c[1])
            if c[2] and c[2] > 0 and (k not in best or c[2] < best[k][2]): best[k] = c
        per_file = {}
        for (s, fee, st), c in sorted(best.items()):
            v = sorted(x for x, st2, _ in inn.get((s, fee), []) if not st or not st2 or st == "b" or st2 == "b" or st2 == st)
            cash = c[2]; used.add(s)
            cash_rows.append({"market": key, "code": code, "f": s, "fee": fee, "st": st or "", "cash": rnd(cash), "list": rnd(c[3]) or None,
                              "row": c[4], "n": len(v), "lo": rnd(v[0]) if v else None, "mid": rnd(mid(v)), "hi": rnd(v[-1]) if v else None,
                              "below": sum(1 for x in v if x < cash), "cap": 1 if capped.get(str(s)) else 0,
                              "xmed": round(cash / med, 2) if med and fee == 0 else None})
            if fee == 0:   # area summary: one hospital-fee cash price per hospital file (its lowest across settings)
                if s not in per_file or cash < per_file[s][0]: per_file[s] = (cash, mid(v))
        vals = sorted(x for x, _ in per_file.values())
        comp = [(x, m_) for x, m_ in per_file.values() if m_]
        proc_rows.append({"id": f"{key}|{code}", "market": key, "area": m["name"], "code": code, "procedure": NAMES.get(code, code),
                          "hospitals_cash": len(vals), "hospitals_any": len({r[0] for r in f.get("r", [])} | {c[0] for c in f.get("c", [])}),
                          "cash_lowest": rnd(vals[0]) if vals else None, "cash_middle": rnd(mid(vals)), "cash_highest": rnd(vals[-1]) if vals else None,
                          "medicare": rnd(med), "medicare_what": med_what,
                          "middle_x_medicare": round(mid(vals) / med, 2) if vals and med else None,
                          "cash_below_own_middle": sum(1 for x, m_ in comp if x < m_), "compared": len(comp)})
    files = []
    for s in sorted(used):   # each hospital file once (rows above point to it by market + "f")
        sr = src[s] if s < len(src) else ["", "", "", "", ""]; dd = pdate(sr[3])
        files.append({"id": f"{key}|{s}", "market": key, "f": s, "hospital": sr[0], "city": sr[1], "file_date": dd.isoformat() if dd else None,
                      "days_old": (TODAY - dd).days if dd else None, "file_url": sr[4]})
    print(f"{m['name']}: {len(cash_rows):,} cash rows, {len(oon_rows):,} out-of-network rows, {len(files)} hospital files", flush=True)
    return cash_rows, oon_rows, proc_rows, files


OUT = Path(ARGS.out); OUT.mkdir(parents=True, exist_ok=True)

def save(name, rows): (OUT / f"{name}.json").write_text(json.dumps(rows, separators=(",", ":")))

def pack(name, rows, n, group):
    """whole groups (an area, an insurer) into n files under MAX_BYTES each, always n files (empty ones as [])"""
    by = defaultdict(list)
    for r in rows: by[r[group]].append(r)
    bins = [[] for _ in range(n)]; size = [0] * n
    for g, rs in sorted(by.items(), key=lambda kv: -len(json.dumps(kv[1], separators=(",", ":")))):
        b = len(json.dumps(rs, separators=(",", ":")))
        i = min(range(n), key=lambda j: size[j])
        if size[i] + b > MAX_BYTES:
            sys.exit(f"{name}: does not fit in {n} files of {MAX_BYTES:,} bytes; raise its file count here and in site/control_cash_oon/tab.html")
        bins[i] += rs; size[i] += b
    for i, rs in enumerate(bins):
        save(name if i == 0 else f"{name}_{i + 1}", rs)
    print(f"{name}: {len(rows):,} rows in {n} files ({', '.join(f'{x / 1e6:.1f}' for x in size)} MB)")


with ThreadPoolExecutor(8) as ex:
    built = list(ex.map(lambda kv: build_market(*kv), MARKETS.items()))
cash_rows = [r for b in built for r in b[0]]; oon_rows = [r for b in built for r in b[1]]; proc_rows = [r for b in built for r in b[2]]
pack("cash_hosp", cash_rows, 6, "market")
save("cash_files", [r for b in built for r in b[3]])
save("cash_proc", proc_rows)
pack("oon_hosp", oon_rows, 2, "market")
posted = [{"id": f"DFW|{i}", "market": "DFW", "code": c["code"], "procedure": NAMES.get(c["code"], c["code"]), "provider": c.get("name", ""),
           "city": c.get("city", ""), "price": c.get("v"), "price_high": c.get("hi") or None, "label": c.get("label", ""),
           "note": c.get("note", ""), "checked": c.get("chk", ""), "source": c.get("src", "")}
          for i, c in enumerate(DFW.get("cash", [])) if c.get("code") in FEATURED]
save("cash_posted", posted)
print("cash_posted:", len(posted), "posted cash prices (DFW)")


# ---------- insurers' allowed-amount (out-of-network) files ----------
def insurer_files():
    import pyarrow.parquet as pq
    keys = [k for k in ls("data/allowed/") if k.endswith(".parquet")]
    newest = {}   # insurer file stem -> newest month's key
    for k in keys:
        _, _, month, fn = k.split("/", 3)
        stem = fn[:-8]
        if stem not in newest or month > newest[stem][0]: newest[stem] = (month, k)
    files, amounts, sources = [], [], []
    for stem, (month, k) in sorted(newest.items()):
        t = pq.read_table(io.BytesIO(get_bytes(k))).to_pylist()
        from collections import Counter
        ent = Counter(r.get("reporting_entity_name") for r in t if r.get("reporting_entity_name"))
        name = next((r["insurer"] for r in t if r.get("insurer")), stem)
        if name == stem:   # the parquet names only a slug: use the files' own name when it reads like one, else the slug spelled out
            e = ent.most_common(1)[0][0] if ent else ""
            name = {"cigna": "Cigna", "uhc": "UnitedHealthcare"}.get(stem) or (e if " " in e and e.lower() != "healthplanname" else
                                                                             re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", stem)).strip().title())
        ok = [r for r in t if r.get("status") == "ok"]; full = [r for r in ok if r.get("services")]
        files.append({"id": stem, "insurer": name, "month": month, "files": len(t), "empty": len(ok) - len(full), "with_data": len(full),
                      "failed": len(t) - len(ok), "services": sum(r.get("services") or 0 for r in ok),
                      "payments": sum(r.get("payments") or 0 for r in ok), "megabytes": round(sum(r.get("bytes") or 0 for r in ok) / 1e6, 2),
                      "newest_file_date": max((str(r.get("last_updated_on") or "")[:10] for r in ok), default="") or None})
        if not full: continue
        meta = {r["file_name"]: r for r in full}
        try: tb = get_bytes(f"raw/allowed/{month}/{stem}.tar")
        except Exception as e: print(f"  {name}: raw files not readable ({e})"); continue
        n0, odd = len(amounts), []
        sources += [{"insurer": name, "file": r["file_name"], "url": r.get("source_url") or ""} for r in full]
        with tarfile.open(fileobj=io.BytesIO(tb)) as tar:
            for mem in tar:
                fm = meta.get(mem.name)
                if not fm or not mem.isfile(): continue
                b = tar.extractfile(mem).read()
                try: j = json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)
                except Exception: continue
                try: add_file(j, fm, mem.name, name, amounts)
                except Exception as e: odd.append(f"{mem.name}: {type(e).__name__}: {e}"[:200])
        if odd: print(f"  {name}: {len(odd)} files laid out differently, skipped; first: {odd[0]}")
        print(f"  {name} ({month}): {len(full)} files with data, {len(amounts) - n0:,} payments for featured procedures", flush=True)
    return files, amounts, sources


def add_file(j, fm, fname, name, amounts):
    """every payment one allowed-amount file lists for a featured procedure, as published"""
    for o in j.get("out_of_network") or []:
        code = str(o.get("billing_code", "")).strip().upper()
        if code not in FEATURED: continue
        for a in o.get("allowed_amounts") or []:
            tin = a.get("tin") or {}
            if isinstance(tin, list): tin = tin[0] if tin and isinstance(tin[0], dict) else {"value": ",".join(map(str, tin))}
            if not isinstance(tin, dict): tin = {"value": str(tin)}
            sc = a.get("service_code") or []
            sc = ",".join(map(str, sc)) if isinstance(sc, list) else str(sc)
            for p in a.get("payments") or []:
                for pv in p.get("providers") or [{}]:
                    npi = pv.get("npi") or []
                    npi = [str(x).strip() for x in (npi if isinstance(npi, list) else [npi]) if str(x).strip()]
                    listed = len(npi)
                    if str(tin.get("type", "")).lower() == "npi" and str(tin.get("value", "")).strip() not in npi: npi.append(str(tin.get("value", "")).strip())
                    npi = [n[:-2] if n.endswith(".0") else n for n in npi]   # a number written as 1234567890.0
                    amounts.append({"insurer": name, "plan": fm.get("plan_name") or "", "plan_market_type": fm.get("plan_market_type") or "",
                                    "file_date": str(fm.get("last_updated_on") or "")[:10] or None, "code": code,
                                    "description": (o.get("description") or "")[:60],
                                    "billing_class": a.get("billing_class") or p.get("billing_class") or "",
                                    "service_code": sc,
                                    "tin": f"{tin.get('type', '')} {tin.get('value', '')}".strip(),
                                    "allowed_amount": rnd(p.get("allowed_amount")), "billed_charge": rnd(pv.get("billed_charge")),
                                    "npis": listed, "file": fname, "_npi": npi})

def match_areas(amounts):
    """Oct 30, 2026 (Betsy): put each insurer out-of-network payment in the areas where its provider practices, by matching
    the payment's NPIs to each live area's Price Finder provider list (R2 <build>/npis.json, same order as the page's
    providers). A payment can be in more than one area (a group with doctors in two places), or in none (a provider in no
    live area's list yet). Adds areas ("DFW|AUS"), provider and city (the first matching provider, as the page names it)."""
    want = {n for r in amounts for n in r["_npi"]}
    hits = defaultdict(list)   # npi -> [(area key, provider position)]
    def one(kv):
        k, a = kv
        try: npis = json.loads(get_bytes(a["npis"]))
        except Exception as e: print(f"  {a['name']}: no provider list ({e})"); return k, []
        return k, [(str(n), i) for i, n in enumerate(npis) if str(n) in want]
    with ThreadPoolExecutor(8) as ex:
        for k, found in ex.map(one, AREAS.items()):
            for n, i in found: hits[n].append((k, i))
    fac = {}   # provider names only for areas that matched something (embed.json is large)
    for k in sorted({k for v in hits.values() for k, _ in v}):
        try: fac[k] = AREAS[k].get("fac") or json.loads(get_bytes(AREAS[k]["embed"]))["fac"]
        except Exception as e: print(f"  {AREAS[k]['name']}: provider names not readable ({e})"); fac[k] = []
    # second pass, for NPIs on no area's Price Finder list (out-of-network providers often aren't in any network):
    # each area's full provider list from the NPI registry, by practice location (the list every Price Finder build starts from)
    left = want - set(hits)
    reg = defaultdict(list)   # npi -> [(area key, name, city)]
    def two(kv):
        import pyarrow.parquet as pq, pyarrow.compute as pc, pyarrow as pa
        k, a = kv
        try: t = pq.read_table(io.BytesIO(get_bytes(a["registry"])))
        except Exception as e: print(f"  {a['name']}: no NPI registry list ({e})"); return k, []
        cols = [c for c in ("npi", "name", "city") if c in t.column_names]
        if "npi" not in cols: return k, []
        t = t.select(cols); t = t.filter(pc.is_in(pc.cast(t["npi"], pa.string()), value_set=pa.array(sorted(left), pa.string())))
        return k, [(str(r.get("npi")), r.get("name") or "", (r.get("city") or "").title()) for r in t.to_pylist()]
    if left:
        with ThreadPoolExecutor(4) as ex:
            for k, found in ex.map(two, AREAS.items()):
                for n, nm, ct in found: reg[n].append((k, nm, ct))
    per = defaultdict(lambda: [0, set()])
    by = {"Price Finder list": 0, "NPI registry": 0, "same tax ID": 0}
    for r in amounts:
        npi = r.pop("_npi")
        m = [h for n in npi for h in hits.get(n, [])]
        if m:
            ks = {k for k, _ in m}; k0, i0 = m[0]; f = fac.get(k0) or []
            r["provider"], r["city"] = (f[i0][0], f[i0][1]) if i0 < len(f) else ("", "")
            r["matched_by"] = "Price Finder list"
        else:
            g = [h for n in npi for h in reg.get(n, [])]
            ks = {k for k, _, _ in g}
            r["provider"], r["city"] = (g[0][1], g[0][2]) if g else ("", "")
            r["matched_by"] = "NPI registry" if g else ""
        ks = sorted(ks, key=lambda k: (k != "DFW", k))
        r["areas"] = "|".join(ks)
        if r["matched_by"]: by[r["matched_by"]] += 1
        for k in ks: per[k][0] += 1; per[k][1].add(r["insurer"])
    # third: a payment listed by tax ID only (no provider NPI) goes where that same tax ID's other payments were placed
    tin_areas = defaultdict(set)
    for r in amounts:
        if r["areas"] and r["tin"]: tin_areas[r["tin"]].update(r["areas"].split("|"))
    for r in amounts:
        if not r["areas"] and not r["npis"] and tin_areas.get(r["tin"]):
            ks = sorted(tin_areas[r["tin"]], key=lambda k: (k != "DFW", k))
            r["areas"], r["matched_by"] = "|".join(ks), "same tax ID"
            for k in ks: per[k][0] += 1; per[k][1].add(r["insurer"])
    miss = defaultdict(list)
    for r in amounts:
        if not r["areas"] and len(miss[r["insurer"]]) < 3: miss[r["insurer"]].append(r["tin"])
    print("  not in any area (sample tax IDs):", "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(miss.items())[:8]))
    rows = [{"market": k, "area": AREAS[k]["name"], "payments": n, "insurers": len(i)} for k, (n, i) in sorted(per.items(), key=lambda x: -x[1][0])]
    save("oon_ins_areas", rows)
    hit = sum(1 for r in amounts if r["areas"]); by["same tax ID"] = sum(1 for r in amounts if r.get("matched_by") == "same tax ID")
    print(f"oon_ins_areas: {hit:,} of {len(amounts):,} payments matched to {len(rows)} areas ({by['Price Finder list']:,} by Price Finder list, {by['NPI registry']:,} by NPI registry, {by['same tax ID']:,} by same tax ID)"
          + (f" (DFW {per['DFW'][0]:,})" if "DFW" in per else ""))


if ARGS.skip_insurers:
    print("insurer allowed-amount files skipped (--skip-insurers)")
else:
    files, amounts, sources = insurer_files()
    match_areas(amounts)
    save("oon_ins_files", files)
    save("oon_ins_sources", sources)   # each file's link once; payment rows name their file
    pack("oon_ins_amounts", amounts, 4, "code")
    print("oon_ins_files:", len(files), "insurers")
