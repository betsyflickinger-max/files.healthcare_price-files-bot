"""Network access & overlap data for the Price Transparency Metrics dashboard ("Network access" tab), for DFW and every live
Price Finder area (the Texas cities and metro areas, small-town Texas, and the first national batch of states).

Moved from Healthcare/16_build_network_access.py (run by hand; DFW + 5 Texas markets) into the bot on Oct 15, 2026 and run
daily by .github/workflows/dashboard.yml (job "network"). Same areas and market keys as dashboard/build_prices.py: an area is
included once its build is finished (embed.json), and a broken build is skipped with a WARNING.

Writes to --out (default out/network):
  net_access.json                      one row per network (and per insurer) per market: providers by type, share of the
                                       market, providers no other insurer lists, procedures priced, prices vs the market
  net_ov_<area>.json (_2, _3 ...)      one row per ordered pair (A, B): share of A's providers (and hospitals) also in B, and
                                       at the providers both list, how often A's rate is lower and A's typical rate as a share of B's
                                       (packed as arrays; see write_areas)
  net_pr_<area>.json (_2, _3 ...)      one row per network per featured procedure per fee type: providers, lowest / middle rate,
                                       middle vs the market middle, providers priced in the market's cheapest quarter
  net_parts.json                       per area: how many of each file, and the middle overlap for the headline
Since Oct 31, 2026 each area has its own files (under 7 MB each; a control-center file must stay under 8 MB), loaded only when
the area is picked. Until then every area was in net_overlap / net_proc parts joined on load (300+ MB by Oct 31).

Membership = a provider has at least one rate line for one of the 89 featured procedures in that network's file.
Prices: dollar rates only; $99,999+ placeholders and percent-of-charge rates are left out. A provider's rate in a network =
its lowest dollar rate there for that code and fee type. "Market middle" and "cheapest quarter" pool every (provider, network)
rate for that code and fee type. No averages: middles are medians, comparisons are counts.

  python dashboard/build_network.py [--only DFW,alabama] [--out DIR]
Env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
"""
import argparse, base64, gzip, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import boto3, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import city_page as CP   # the live area list (same as build_prices.py)

ap = argparse.ArgumentParser(); ap.add_argument("--out", default="out/network"); ap.add_argument("--only", default=""); ap.add_argument("--rollups", action="store_true", help="make the roll-ups even with --only (testing)")
ARGS = ap.parse_args()
E = {k: "".join(os.environ[k].split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
BUCKET = E["R2_BUCKET"]
s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"),
                  config=boto3.session.Config(max_pool_connections=32))
def get_bytes(key): return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
def get_text(key): return get_bytes(key).decode().strip()
def exists(key):
    try: s3.head_object(Bucket=BUCKET, Key=key); return True
    except Exception: return False
def ls_dirs(prefix): return [c["Prefix"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix, Delimiter="/") for c in pg.get("CommonPrefixes", [])]
def page_data(html):
    a = html.find('<script type="application/json" id="data">'); a = html.find(">", a) + 1
    return json.loads(html[a:html.find("</script>", a)])

# same 89 featured procedures as build_prices.py
FEATURED = {"00811", "00812", "19120", "216", "22551", "27130", "27447", "29826", "29827", "29881", "29888", "42820", "43235", "43239", "43644", "43775", "45378", "45380", "45385", "45391", "460", "470", "473", "47562", "49505", "55250", "55700", "55866", "59400", "59510", "59610", "62322", "62323", "63030", "64483", "64721", "66821", "66984", "70450", "70551", "70553", "72110", "72148", "72193", "73721", "74177", "743", "75571", "76700", "76805", "76830", "77065", "77066", "77067", "80048", "80053", "80055", "80061", "80069", "80076", "81000", "81001", "81002", "81003", "84153", "84154", "84443", "85025", "85027", "85610", "85730", "88305", "90832", "90834", "90837", "90846", "90847", "90853", "93000", "93452", "95810", "97110", "99203", "99204", "99205", "99243", "99244", "99385", "99386"}
FEATURED_EXTRA = "description as written in the insurer file"
OLDKEY = {"austin": "AUS", "san-antonio": "SAT", "houston": "HOU", "el-paso": "ELP"}   # as build_prices.py
KIND = {"H": "hospitals", "A": "surgery_centers", "G": "clinics_groups", "P": "clinicians"}
FEE = {0: "Facility fee", 1: "Doctor fee"}
MIN_NET, MIN_MKT = 5, 20   # a network middle needs 5+ providers, a market middle 20+ (provider, network) rates
NET_PAIR_MAX = 800   # Nov 3, 2026: an area with more networks than this gets insurer-level pairs only (Michigan had 2,708 networks:
                     # the network-pair grid would be 7.3M pairs and the price counters asked for 175 GB, which stopped the job daily from Nov 1)
PART_MAX = 7_000_000
ACCESS_PARTS = 6   # net_access.json + net_access_2 ... _6 (site/control_overlap.py joins the same six)   # a control-center file must stay under 8 MB. Oct 31: files are now per area (see write_areas); the all-areas join had passed 300 MB

# ---------- markets (loaded one at a time in build(), so 30+ areas fit in memory) ----------
_CUR = get_text('site/every/CURRENT')
MARKETS = {"DFW": {"name": "Dallas–Fort Worth", "page": "site/deploy/price-finder.html", "codes": f"site/every/{_CUR}/t/", "npis": f"site/every/{_CUR}/npis.json", "slug": "dfw"}}
for slug, (name, *_rest) in CP.CITIES.items():
    months = sorted(d for d in ls_dirs(f"{CP.root(slug)}{slug}/") if exists(d + "embed.json"))
    if not months: print(f"{name}: not finished yet, skipped"); continue
    MARKETS[OLDKEY.get(slug, slug)] = {"name": name, "embed": months[-1] + "embed.json", "codes": months[-1] + "t/", "npis": months[-1] + "npis.json", "slug": slug}
if ARGS.only: MARKETS = {k: v for k, v in MARKETS.items() if k in ARGS.only.split(",")}

def med(v): return float(np.median(v)) if len(v) else None
def gram(X, step=200_000):
    """X.T @ X for a boolean providers x groups matrix: how many providers each pair of groups shares (diagonal = group size).
    In float32 chunks (exact below 16.7M per chunk) so a national matrix never has to be copied whole."""
    C = np.zeros((X.shape[1], X.shape[1]))
    for i in range(0, X.shape[0], step):
        x = X[i:i + step].astype(np.float32); C += x.T @ x
    return np.rint(C).astype(np.int64)

# ---------- Nov 3, 2026 (Betsy): roll-ups, so the tab goes from the whole country down to one area ----------
# Each area's membership is kept packed (NPI, provider type, which networks list it). After every area is built:
#   US       "United States": insurers combined only (thousands of networks nationally is not one grid)
#   TX       "Texas": DFW + every Texas area, insurer and network level
#   <ST>     a state split into regions with no whole-state area of its own, same as Texas
# A provider in two areas is counted once (union by NPI). Counts only: no prices at roll-up level (prices are compared
# inside one area, where the market middle is the same for everyone).
KEPT = {}
def KEEP_AREA(key, m, D, nets, member, kinds):
    if ARGS.only and not ARGS.rollups: return
    try: npis = json.loads(get_bytes(m["npis"]))
    except Exception as e: print(f"WARNING {m['name']}: no npis.json, left out of the roll-ups:", e); return
    if len(npis) != len(D["fac"]): print(f"WARNING {m['name']}: npis.json has {len(npis)} providers, the page {len(D['fac'])}; left out of the roll-ups"); return
    ids = np.array([int(n) if str(n).isdigit() else -1 for n in npis], dtype=np.int64)
    keep = (ids > 0) & member.any(axis=1)
    KEPT[key] = {"npi": ids[keep], "kind": kinds[keep], "nets": [tuple(n) for n in nets], "bits": np.packbits(member[keep], axis=1)}

def rollup(key, name, keys, with_networks):
    parts = [KEPT[k] for k in keys if k in KEPT]
    if not parts: return [], [], {}
    allnpi = np.unique(np.concatenate([p["npi"] for p in parts])); U = len(allnpi)
    ins = sorted({n[0] for p in parts for n in p["nets"]}); ii_of = {x: i for i, x in enumerate(ins)}
    netl = sorted({n for p in parts for n in p["nets"]}) if with_networks else []; nn_of = {x: i for i, x in enumerate(netl)}
    Xi = np.zeros((U, len(ins)), dtype=bool); Xn = np.zeros((U, len(netl)), dtype=bool) if with_networks else None
    kind = np.full(U, "", dtype="<U1")
    for p in parts:
        row = np.searchsorted(allnpi, p["npi"]); mem = np.unpackbits(p["bits"], axis=1, count=len(p["nets"])).astype(bool)
        unset = kind[row] == ""; kind[row[unset]] = p["kind"][unset]
        for c, n in enumerate(p["nets"]):
            r = row[mem[:, c]]; Xi[r, ii_of[n[0]]] = True
            if with_networks: Xn[r, nn_of[n]] = True
        del mem
    H = kind == "H"; total = U; total_h = int(H.sum()); nins = Xi.sum(axis=1); nnet = Xn.sum(axis=1) if with_networks else None
    groups = [("insurer", Xi[:, i], i, x, f"All {x} networks", f"All {x} networks") for i, x in enumerate(ins)]
    if with_networks: groups = [("network", Xn[:, j], ii_of[n[0]], n[0], n[1], f"{n[0]} {n[1]}") for j, n in enumerate(netl)] + groups
    access, sets = [], {}
    for level, s, i, insurer, nm, lab in groups:
        cnt = int(s.sum())
        if not cnt: continue
        gid = f"{key}|{level}|{insurer}|{nm}"; sets[gid] = (level, insurer, lab, s)
        others = (nins - Xi[:, i]) > 0
        only = s & ((nnet == 1) if level == "network" else (nins == 1))
        row = {"id": gid, "market": key, "level": level, "insurer": insurer, "network": nm, "label": lab,
               "providers": cnt, "market_providers": total, "share_of_market": r4(cnt / total)}
        row.update({v: int((s & (kind == k)).sum()) for k, v in KIND.items()})
        row.update({"market_hospitals": total_h, "hospital_share": r4(int((s & H).sum()) / max(1, total_h)),
                    "only_this": int(only.sum()), "only_this_insurer": int((s & ~others).sum()),
                    "in_other_insurer_share": r4(int((s & others).sum()) / cnt),
                    "procedures_priced": None, "price_comparisons": 0, "typical_vs_market": None, "cheap_share": None, "priced_rates": 0,
                    "rollup_areas": len(parts)})
        access.append(row)
    overlap = []
    for lvl in ("network", "insurer"):
        g = [x for x in sets if sets[x][0] == lvl]
        if not g: continue
        S = np.stack([sets[x][3] for x in g], axis=1); C = gram(S); CH = gram(S[H])
        for i, ga in enumerate(g):
            for j, gb in enumerate(g):
                if i == j: continue
                sh, ha, shh = int(C[i, j]), int(CH[i, i]), int(CH[i, j])
                overlap.append({"id": f"{ga}>{gb}", "market": key, "level": lvl, "a": sets[ga][2], "b": sets[gb][2], "a_insurer": sets[ga][1], "b_insurer": sets[gb][1],
                                "shared": sh, "a_providers": int(C[i, i]), "share_of_a_in_b": r4(sh / max(1, int(C[i, i]))),
                                "jaccard": r4(sh / max(1, int(C[i, i] + C[j, j]) - sh)),
                                "shared_hospitals": shh, "a_hospitals": ha, "hospital_share_of_a_in_b": r4(shh / ha) if ha else None,
                                "matched_prices": None, "a_lower_share": None, "same_share": None, "a_vs_b_middle": None})
    print(f"{name}: {U:,} providers (by NPI) from {len(parts)} areas, {len(ins)} insurers, {len(netl)} networks, {len(overlap)} pairs")
    info = {"providers": U, "hospitals": total_h, "surgery_centers": int((kind == "A").sum()), "insurers": len(ins),
            "networks": len(netl) if with_networks else len({n for p in parts for n in p["nets"]})}
    return access, overlap, info
def r2(x): return None if x is None else round(x, 2)
def r4(x): return None if x is None else round(x, 4)

def load(m):
    D = page_data(get_bytes(m["page"]).decode("utf-8")) if "page" in m else json.loads(get_bytes(m["embed"]))
    lines = sum(c.get("n", 0) for c in D["codes"].values()); have = sum(c in D["codes"] for c in FEATURED)
    if lines == 0 or have < 45:
        print(f"WARNING {m['name']}: {len(D['codes'])} codes, {lines} rate lines, {have} of 89 featured codes; skipped as a broken build"); return None
    return D

def fetch_codes(m, D):
    """every featured code's rate file for this market, downloaded a few ahead in parallel (was one at a time: ~4 min per
    market) but decoded and handed over one at a time, so memory holds one code's rows, not all 89 (8 GB ran out)"""
    codes = [c for c, v in D["codes"].items() if c in FEATURED and v.get("cat") != FEATURED_EXTRA]
    def raw(code):
        try: return get_text(m["codes"] + f"{code}.txt")
        except Exception as e: print("could not read", code, e); return None
    AHEAD = 6
    with ThreadPoolExecutor(AHEAD) as ex:
        futs = [ex.submit(raw, c) for c in codes[:AHEAD]]
        for i, code in enumerate(codes):
            t = futs[i].result(); futs[i] = None
            if i + AHEAD < len(codes): futs.append(ex.submit(raw, codes[i + AHEAD]))
            if t is None: continue
            f = json.loads(gzip.decompress(base64.b64decode(t)))["f"]; del t
            yield code, f

def build(key, m):
    D = load(m)
    if D is None: return [], [], []
    nets = [n.split("|", 1) for n in D["nets"]]; NN = len(nets); NP = len(D["fac"])
    kinds = np.array([f[2] for f in D["fac"]])
    member = np.zeros((NP, NN), dtype=bool)
    # head-to-head counters per ordered pair (a, b): matched, a lower, same; ratios a/b collected for the middle
    big = NN > NET_PAIR_MAX
    if big: print(f"WARNING {m['name']}: {NN} networks (over {NET_PAIR_MAX}); network-by-network pairs and head-to-head prices left out, insurer pairs kept")
    PN = 1 if big else NN   # the counters are only made when network pairs are kept
    h_n = np.zeros((PN, PN), dtype=np.int64); h_lo = np.zeros((PN, PN), dtype=np.int64); h_eq = np.zeros((PN, PN), dtype=np.int64)
    # A/B ratios binned on a log2 scale (0.005 wide, about 0.35%) so the middle can be read without keeping every ratio
    BW, LIM = 0.005, 8.0; NB = int(2 * LIM / BW) + 1
    h_hist = np.zeros((PN, PN, NB), dtype=np.int64)
    proc_rows = []; net_ratios = [[] for _ in range(NN)]; net_cheap = np.zeros(NN, dtype=np.int64); net_priced = np.zeros(NN, dtype=np.int64)
    net_codes = [set() for _ in range(NN)]
    for code, f in fetch_codes(m, D):
        c = D["codes"][code]
        best = {0: {}, 1: {}}   # fee -> {(provider, net): lowest dollar rate}
        for fi, rows in f.items():
            fi = int(fi)
            for r in rows:
                member[fi, r[0]] = True; net_codes[r[0]].add(code)
                if r[2] != 0 or not r[3] or r[3] <= 0 or r[3] >= 99999: continue
                d = best[1 if r[1] == 1 else 0]; k = (fi, r[0])
                if k not in d or r[3] < d[k]: d[k] = r[3]
        for fee, d in best.items():
            if not d: continue
            provs = sorted({p for p, _ in d}); pidx = {p: i for i, p in enumerate(provs)}
            M = np.full((len(provs), NN), np.nan)
            for (p, n), v in d.items(): M[pidx[p], n] = v
            pooled = M[~np.isnan(M)]
            if len(pooled) < MIN_MKT: continue
            mkt_mid = float(np.median(pooled)); mkt_p25 = float(np.percentile(pooled, 25, method="lower"))
            for n in range(NN):
                v = M[:, n]; v = v[~np.isnan(v)]
                if not len(v): continue
                cheap = int((v <= mkt_p25).sum()); net_cheap[n] += cheap; net_priced[n] += len(v)
                mid = med(v) if len(v) >= MIN_NET else None
                if mid is not None: net_ratios[n].append(mid / mkt_mid)
                proc_rows.append({"id": f"{key}|{code}|{fee}|{n}", "market": key, "code": code, "procedure": c["name"], "category": c["cat"],
                                  "fee": FEE[fee], "insurer": nets[n][0], "network": nets[n][1], "label": f"{nets[n][0]} {nets[n][1]}",
                                  "providers": int(len(v)), "lowest": r2(float(v.min())), "middle": r2(mid),
                                  "vs_market": r4(mid / mkt_mid) if mid is not None else None,
                                  "cheap_providers": cheap, "market_middle": r2(mkt_mid), "market_cheap_cutoff": r2(mkt_p25)})
            have = ~np.isnan(M)
            for a in (() if big else range(NN)):
                for b in range(a + 1, NN):
                    both = have[:, a] & have[:, b]; k = int(both.sum())
                    if not k: continue
                    va, vb = M[both, a], M[both, b]
                    h_n[a, b] += k; h_n[b, a] += k
                    lo = int((va < vb).sum()); hi = int((va > vb).sum())
                    h_lo[a, b] += lo; h_lo[b, a] += hi; h_eq[a, b] += k - lo - hi; h_eq[b, a] += k - lo - hi
                    bins = np.clip(np.rint((np.log2(va / vb) + LIM) / BW).astype(int), 0, NB - 1)
                    cnt = np.bincount(bins, minlength=NB); h_hist[a, b] += cnt; h_hist[b, a] += cnt[::-1]

    # ---------- network rows and insurer rows ----------
    ins = sorted({i for i, _ in nets}); groups = [("network", [n], nets[n][0], nets[n][1]) for n in range(NN)] + \
        [("insurer", [n for n in range(NN) if nets[n][0] == i], i, f"All {i} networks") for i in ins]
    anyp = member.any(axis=1); total = int(anyp.sum())
    ins_of = np.array([ins.index(nets[n][0]) for n in range(NN)])
    ins_member = np.zeros((NP, len(ins)), dtype=bool)
    for n in range(NN): ins_member[:, ins_of[n]] |= member[:, n]
    access = []; sets = {}
    for level, ns, insurer, name in groups:
        s = member[:, ns].any(axis=1); cnt = int(s.sum())
        if not cnt: continue
        gid = f"{key}|{level}|{insurer}|{name}"; sets[gid] = (level, insurer, name, s, ns)
        others = np.delete(ins_member, ins.index(insurer), axis=1).any(axis=1)
        net_only = member[:, [x for x in range(NN) if x not in ns]].any(axis=1)
        ratios = sum((net_ratios[n] for n in ns), []); priced = int(net_priced[ns].sum()); cheap = int(net_cheap[ns].sum())
        row = {"id": gid, "market": key, "level": level, "insurer": insurer, "network": name, "label": name if level == "insurer" else f"{insurer} {name}",
               "providers": cnt, "market_providers": total, "share_of_market": r4(cnt / total)}
        row.update({v: int((s & (kinds == k)).sum()) for k, v in KIND.items()})
        row.update({"market_hospitals": int((anyp & (kinds == "H")).sum()),
                    "hospital_share": r4(int((s & (kinds == "H")).sum()) / max(1, int((anyp & (kinds == "H")).sum()))),
                    "only_this": int((s & ~net_only).sum()),
                    "only_this_insurer": int((s & ~others).sum()),
                    "in_other_insurer_share": r4(int((s & others).sum()) / cnt),
                    "procedures_priced": len(set().union(*(net_codes[n] for n in ns))),
                    "price_comparisons": len(ratios),
                    "typical_vs_market": r4(med(ratios)) if level == "network" and len(ratios) >= 5 else None,
                    "cheap_share": r4(cheap / priced) if level == "network" and priced else None,
                    "priced_rates": priced})
        access.append(row)
    def hist_mid(h):
        c = np.cumsum(h); i = int(np.searchsorted(c, (c[-1] + 1) // 2)); return 2 ** (i * BW - LIM)
    # ---------- pairs ----------
    overlap = []; label = {r["id"]: r["label"] for r in access}
    KEEP_AREA(key, m, D, nets, member, kinds)   # Nov 3: kept (packed) for the Texas / National roll-ups
    # Nov 3, 2026: shared counts for every pair at once from matrix products (was one pair at a time: 7.3M pairs for Michigan)
    for lvl in ("network", "insurer"):
        g = [x for x in sets if sets[x][0] == lvl]
        if not g or (lvl == "network" and big): continue
        S = np.stack([sets[x][3] for x in g], axis=1); C = gram(S); CH = gram(S[kinds == "H"])
        for i, ga in enumerate(g):
            la, ia, na, sa, nsa = sets[ga]
            for j, gb in enumerate(g):
                if i == j: continue
                lb, ib, nb, sb, nsb = sets[gb]
                sh = int(C[i, j]); ha = int(CH[i, i]); shh = int(CH[i, j])
                row = {"id": f"{ga}>{gb}", "market": key, "level": la, "a": label[ga], "b": label[gb], "a_insurer": ia, "b_insurer": ib,
                       "shared": sh, "a_providers": int(C[i, i]), "share_of_a_in_b": r4(sh / max(1, int(C[i, i]))),
                       "jaccard": r4(sh / max(1, int(C[i, i] + C[j, j]) - sh)),
                       "shared_hospitals": shh, "a_hospitals": ha, "hospital_share_of_a_in_b": r4(shh / ha) if ha else None,
                       "matched_prices": None, "a_lower_share": None, "same_share": None, "a_vs_b_middle": None}
                if la == "network":
                    a, b = nsa[0], nsb[0]; k = int(h_n[a, b])
                    if k:
                        row.update({"matched_prices": k, "a_lower_share": r4(h_lo[a, b] / k), "same_share": r4(h_eq[a, b] / k),
                                    "a_vs_b_middle": r4(hist_mid(h_hist[a, b]))})
                overlap.append(row)
    print(f"{m['name']}: {total:,} providers, {NN} networks, {len(proc_rows):,} network-procedure rows, {len(overlap)} pairs")
    return access, overlap, proc_rows

PAIR_KEYS = ["level", "a", "b", "shared", "a_providers", "share_of_a_in_b", "jaccard", "shared_hospitals", "a_hospitals",
             "hospital_share_of_a_in_b", "matched_prices", "a_lower_share", "same_share", "a_vs_b_middle"]

def file_id(prefix, key): return prefix + key.lower().replace("-", "_")

def write_split(out, fid, rows, head=None):
    """one area's rows in as few files as fit under PART_MAX: <fid>.json, <fid>_2.json, ... (each starts with head, if given)"""
    parts, cur, size = [], [], 2
    hb = len(json.dumps(head, separators=(",", ":"))) + 1 if head else 0
    for r in rows:
        b = len(json.dumps(r, separators=(",", ":"))) + 1
        if cur and size + hb + b > PART_MAX: parts.append(cur); cur, size = [], 2
        cur.append(r); size += b
    parts.append(cur)
    for j, rows in enumerate(parts):
        (out / (f"{fid}.json" if j == 0 else f"{fid}_{j + 1}.json")).write_text(json.dumps(([head] if head else []) + rows, separators=(",", ":")))
    return len(parts)

def write_areas(out, O, PR, META=None):
    """Oct 31, 2026: one set of files per area, loaded by the control center only when that area is picked (all areas in
    one join had grown past 300 MB once California and Idaho had 550+ networks each). Pairs are packed as arrays:
    the first item is {"market", "labels", "keys"}, then [level (0 network, 1 insurer), a, b (label numbers), ...the rest of
    PAIR_KEYS]. net_parts lists every area's file counts and its middle overlap (share of one network's providers in another)."""
    idx = []
    for k in O:
        labels = sorted({r["a"] for r in O[k]} | {r["b"] for r in O[k]}); li = {x: i for i, x in enumerate(labels)}
        packed = [[0 if r["level"] == "network" else 1, li[r["a"]], li[r["b"]]] + [r[f] for f in PAIR_KEYS[3:]] for r in O[k]]
        ov = sorted(r["share_of_a_in_b"] for r in O[k] if r["level"] == "network" and r["share_of_a_in_b"] is not None)
        n_ov = write_split(out, file_id("net_ov_", k), packed, {"market": k, "labels": labels, "keys": PAIR_KEYS})
        n_pr = write_split(out, file_id("net_pr_", k), PR[k])
        idx.append({"market": k, "pairs": len(O[k]), "pair_files": n_ov, "proc_rows": len(PR[k]), "proc_files": n_pr,
                    "overlap_mid": ov[(len(ov) - 1) // 2] if ov else None, **((META or {}).get(k, {}))})
        print(f"{k}: {len(O[k])} pairs in {n_ov} file(s), {len(PR[k])} procedure rows in {n_pr} file(s)")
    (out / "net_parts.json").write_text(json.dumps(idx, separators=(",", ":")))

OUT = Path(ARGS.out); OUT.mkdir(parents=True, exist_ok=True)
A, O, PR = [], {}, {}
for k, m in MARKETS.items():
    t0 = time.time()
    a, o, p = build(k, m)
    if a: A += a; O[k] = o; PR[k] = p
    print(f"  {k} took {round(time.time() - t0)} s", flush=True)
# ---------- roll-ups (Nov 3) ----------
META = {k: {"name": m["name"], "parent": "TX" if m["slug"] == "dfw" or m["slug"] not in CP.STATE_OF else CP._regions.PARENT.get(m["slug"])} for k, m in MARKETS.items() if k in O}
for k in META:
    p = META[k]["parent"]
    if p and p != "TX" and p not in O: META[k]["parent"] = CP.STATE_OF[p]   # a region whose state has no whole-state area: under the state roll-up
    if not META[k]["parent"]: META[k]["parent"] = "US"
ROLL = [("TX", "Texas", [k for k in META if META[k]["parent"] == "TX"], True)]
for st in sorted({META[k]["parent"] for k in META if META[k]["parent"] not in ("US", "TX") and META[k]["parent"] not in O}):
    sl = next(s for s, a in CP.STATE_OF.items() if a == st and s not in CP._regions.PARENT)
    ROLL.append((st, CP.CITIES[sl][0], [k for k in META if META[k]["parent"] == st], True))
ROLL.append(("US", "United States", list(O), False))
if KEPT:
    for rk, rname, keys, nets_too in ROLL:
        t0 = time.time(); a, o, info = rollup(rk, rname, keys, nets_too)
        if not a: continue
        A += a; O[rk] = o; PR[rk] = []
        META[rk] = {"name": rname, "state": None if rk == "US" else rname, "parent": None if rk == "US" else "US", "rollup": True, "areas": [k for k in keys if k in KEPT],
                    "network_pairs": nets_too, **info}
        print(f"  {rk} took {round(time.time() - t0)} s", flush=True)
    KEPT.clear()
# Nov 3, 2026: net_access in parts (net_access.json, _2 ... _6; unused parts written empty) since it was nearing 8 MB;
# the control center joins them. DFW goes first, so net_access.json always has it.
n_acc = write_split(OUT, "net_access", A)
if n_acc > ACCESS_PARTS: sys.exit(f"STOP: net_access needs {n_acc} parts; the control center reads {ACCESS_PARTS}")
for j in range(n_acc + 1, ACCESS_PARTS + 1): (OUT / f"net_access_{j}.json").write_text("[]")
print("net_access", len(A), "rows in", n_acc, "part(s)")
write_areas(OUT, O, PR, META)
print("network access: markets", ",".join(O))
