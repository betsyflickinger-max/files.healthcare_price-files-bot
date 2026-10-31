"""Care Compare quality and patient-experience ratings for every area (card #3, Betsy OK'd Oct 31, 2026). Builds and previews;
switching the ratings on in the Price Finders is a separate step Betsy OKs.

Same shape as the DFW ratings (R2 reference/site/quality_dfw_by_npi.json, site/quality_rekey.py), one file per state, so
quality_rekey.render() places them for any page by NPI. A rating is stored ONLY under the CMS ID it belongs to (hospital and
surgery-center CCN, clinician NPI); a page provider gets it only through an NPI -> CCN match from public records:
  * site/med_local.py (R2 site/med_local/2026.json): NPPES practice address = CMS Provider of Services address, one match only
  * CMS Hospital Enrollments (the original already saved in raw/utilization/ by card #2): the NPI each hospital enrolled with
If the two disagree, or an NPI matches more than one CCN, it gets no rating. Nothing is estimated or averaged.

Ratings (CMS Provider Data Catalog, newest release, found by title; each original saved untouched in raw/care_compare/):
  hospitals        Hospital General Information: overall star rating (1-5) and CMS's footnote when there is none
                   Patient survey (HCAHPS) - Hospital: summary star rating, "rated the hospital 9 or 10", "would definitely
                   recommend", completed surveys, survey period
  surgery centers  ASC Quality Measures - Facility: hospital visits within 7 days (ASC-12 colonoscopy, ASC-17/18/19 surgery)
                   OAS CAHPS survey for ASCs - Facility: "rated the facility 9 or 10", "would definitely recommend"
  clinicians       Doctors and Clinicians National Downloadable File (specialty, medical school, graduation year), the newest
                   "Clinician Public Reporting: Overall MIPS Performance" (final MIPS score), Facility Affiliation Data
Every rating carries its source (title, link, CMS release date). A provider with no rating is "not rated", with the reason.

  python site/care_compare.py build [--work DIR]        R2 reference/site/quality/<st>.json for every state we cover
  python site/care_compare.py preview [--area illinois]  reports/care-compare/<area>.md + <area>.html (+ DFW cross-check)
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(HERE))
TODAY = dt.date.today().isoformat()
PDC = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"
PAGE = "https://data.cms.gov/provider-data/dataset/{}"
OUT = "reference/site/quality/{}.json"
# key: (title pattern, newest-first sort on the title's year if several match)
DATASETS = {
    "gen": r"^Hospital General Information$",
    "hc": r"^Patient survey \(HCAHPS\) - Hospital$",
    "asc": r"^Ambulatory Surgical Center Quality Measures - Facility$",
    "oas": r"OAS CAHPS.*ambulatory surgical cent.*Facility",
    "ndf": r"^(Doctors and Clinicians )?National Downloadable File$",
    "mips": r"Clinician Public Reporting: Overall MIPS Performance",
    "aff": r"^Facility Affiliation Data$",
}
ASC_MEASURES = ("ASC-12", "ASC-17", "ASC-18", "ASC-19")
NOT_RATED = {
    "H": "not rated: CMS gives no star when a hospital reports too few measures, and does not rate some hospital types",
    "A": "not rated: CMS publishes no rating for this surgery center's procedure",
    "P": "not rated: no public source rates individual doctors; no MIPS score (many clinicians are exempt)",
    "nomatch": "not rated: we couldn't match this provider to one Medicare record, so we show no rating rather than risk the wrong one",
}


def s3():
    import store
    return store.r2()


def catalog():
    items = requests.get(PDC, timeout=300).json()
    found = {}
    for k, pat in DATASETS.items():
        m = [x for x in items if re.search(pat, x.get("title", ""), re.I)]
        if not m:
            found[k] = None
            continue
        x = max(m, key=lambda x: (re.findall(r"\b(20\d\d)\b", x["title"]) or ["0"])[0] + x.get("modified", ""))
        dl = next((d.get("downloadURL") for d in x.get("distribution", []) if str(d.get("downloadURL", "")).lower().endswith(".csv")), None)
        found[k] = dict(id=x["identifier"], title=x["title"], modified=x.get("modified", ""), url=dl, page=PAGE.format(x["identifier"]))
    return found


def fetch_and_save(c, B, k, meta, W, manifest):
    """Download one CMS file, save the original once (zstd) in raw/care_compare/<id>/<modified>/, return the local path."""
    import zstandard
    p = W / f"{k}.csv"
    h, n = hashlib.sha256(), 0
    with requests.get(meta["url"], stream=True, timeout=900) as r, open(p, "wb") as f:
        r.raise_for_status()
        for b in r.iter_content(8 << 20):
            f.write(b)
            h.update(b)
            n += len(b)
    sha = h.hexdigest()
    key = f"raw/care_compare/{meta['id']}/{meta['modified'] or TODAY}/{sha[:12]}_{meta['url'].rsplit('/', 1)[-1]}.zst"
    try:
        c.head_object(Bucket=B, Key=key)
    except Exception:
        z = p.with_suffix(".csv.zst")
        with open(p, "rb") as fi, open(z, "wb") as fo:
            zstandard.ZstdCompressor(level=10, threads=-1).copy_stream(fi, fo)
        c.upload_file(str(z), B, key)
        z.unlink()
    manifest.append(dict(source=k, dataset=meta["id"], title=meta["title"], modified=meta["modified"], url=meta["url"], key=key,
                         sha256=sha, bytes=n, checked_on=TODAY))
    return p


def cols(con, p):
    """lower-cased, punctuation-free column name -> real name"""
    names = [r[0] for r in con.execute(f"describe select * from read_csv('{p}', header=true, all_varchar=true, sample_size=-1)").fetchall()]
    return {re.sub(r"[^a-z0-9]", "", x.lower()): x for x in names}


def pick(cm, *opts, need=True):
    for o in opts:
        k = re.sub(r"[^a-z0-9]", "", o.lower())
        if k in cm:
            return f'"{cm[k]}"'
    if need:
        raise SystemExit(f"column not found: {opts} in {sorted(cm)[:40]}")
    return "null"


def build(work):
    import duckdb
    c, B = s3()
    W = Path(work)
    W.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(W / "cc.duckdb"))
    con.execute("set memory_limit='5GB'; set preserve_insertion_order=false")
    cat = catalog()
    missing = [k for k, v in cat.items() if not v or not v["url"]]
    if missing:
        raise SystemExit(f"CMS catalog: no CSV found for {missing}: {json.dumps(cat, indent=1)}")
    man, P, colsrep = [], {}, {}
    for k, m in cat.items():
        P[k] = fetch_and_save(c, B, k, m, W, man)
        colsrep[k] = sorted(cols(con, P[k]).values())
    rd = lambda k: f"read_csv('{P[k]}', header=true, all_varchar=true, sample_size=-1)"
    src = {k: [m["title"], m["page"], m["modified"]] for k, m in cat.items()}

    # ---- hospitals: overall star + HCAHPS ----
    g = cols(con, P["gen"])
    con.execute(f"""create table gen as select {pick(g, 'Facility ID')} as ccn, {pick(g, 'Facility Name')} as name, {pick(g, 'State')} as state,
        {pick(g, 'Hospital Type')} as type, {pick(g, 'Hospital overall rating')} as star,
        {pick(g, 'Hospital overall rating footnote', need=False)} as star_fn from {rd('gen')}""")
    hc = cols(con, P["hc"])
    mid, ans = pick(hc, "HCAHPS Measure ID"), pick(hc, "HCAHPS Answer Percent")
    con.execute(f"""create table hcp as select {pick(hc, 'Facility ID')} as ccn,
        max(case when {mid} = 'H_STAR_RATING' then {pick(hc, 'Patient Survey Star Rating')} end) hc,
        max(case when {mid} = 'H_HSP_RATING_9_10' then {ans} end) hc_9,
        max(case when {mid} = 'H_RECMND_DY' then {ans} end) hc_rec,
        max(try_cast({pick(hc, 'Number of Completed Surveys')} as integer))::varchar as hc_n,
        max({pick(hc, 'Start Date')}) s, max({pick(hc, 'End Date')}) e
        from {rd('hc')} group by 1""")
    H = {}
    for ccn, name, st, typ, star, fn, hcv, h9, hr, hn_, s_, e_ in con.execute(
            "select g.ccn, g.name, g.state, g.type, g.star, g.star_fn, h.hc, h.hc_9, h.hc_rec, h.hc_n, h.s, h.e from gen g left join hcp h using (ccn)").fetchall():
        rec = dict(name=name, st=st, type=typ, star=star if (star or "").isdigit() else "", star_fn=fn or "", m={})
        if (hcv or "").isdigit():
            rec.update(hc=hcv, hc_n=hn_ if (hn_ or "").isdigit() else "", hc_p=f"surveys {s_} to {e_}" if s_ and e_ else "")
        if (h9 or "").isdigit():
            rec["hc_9"] = h9
        if (hr or "").isdigit():
            rec["hc_rec"] = hr
        H[ccn] = rec

    # ---- surgery centers ----
    a = cols(con, P["asc"])
    ascm = {}
    long_ = pick(a, "Measure Code", "Measure ID", need=False)
    if long_ != "null":     # one row per measure
        q = f"""select {pick(a, 'Facility ID')} as ccn, {pick(a, 'Facility Name')} as name, {long_} m, {pick(a, 'Rate', 'Score')} as rate,
                       {pick(a, 'Comparison', 'Compared to National', need=False)} as cat, {pick(a, 'Number of Cases', 'Denominator', need=False)} as n,
                       {pick(a, 'Year', 'Data collection period', 'Measure Start Date', need=False)} as yr
                from {rd('asc')} where {long_} in {ASC_MEASURES}"""
        rows = con.execute(q).fetchall()
    else:                   # one row per facility, measure columns side by side ("ASC-12 Rate*", ...)
        rows = []
        cm = a
        cur = con.execute(f"select * from {rd('asc')}")
        names = [x[0] for x in cur.description]
        for t_ in cur.fetchall():
            r = dict(zip(names, t_))
            for m in ASC_MEASURES:
                mk = m.lower().replace("-", "")
                rate = next((r[cm[x]] for x in cm if x.startswith(mk) and "rate" in x), None)
                catv = next((r[cm[x]] for x in cm if x.startswith(mk) and ("comparison" in x or "category" in x)), None)
                n = next((r[cm[x]] for x in cm if x.startswith(mk) and ("cases" in x or "denominator" in x)), None)
                rows.append((r[cm["facilityid"]], r.get(cm.get("facilityname", ""), ""), m, rate, catv, n, r.get(cm.get("year", ""), "")))
    for ccn, name, m, rate, catv, n, yr in rows:
        x = ascm.setdefault(ccn, dict(ccn=ccn, name=name, yr=yr or cat["asc"]["modified"][:4]))
        x[m] = {k2: v for k2, v in dict(rate=rate if rate and re.match(r"^[\d.]+$", str(rate)) else "", cat=catv or "", cases=n if (n or "").isdigit() else "").items()}
    o = cols(con, P["oas"])
    try:
        nine = next(v for k2, v in o.items() if "910" in k2 or "9or10" in k2)
        rec_ = next(v for k2, v in o.items() if "recommend" in k2 and ("definitely" in k2 or "yes" in k2 or "percent" in k2))
        for ccn, n9, nr in con.execute(f'select {pick(o, "Facility ID")}, "{nine}", "{rec_}" from {rd("oas")}').fetchall():
            if ccn in ascm or (n9 or "").isdigit():
                x = ascm.setdefault(ccn, dict(ccn=ccn, name="", yr=cat["oas"]["modified"][:4]))
                if (n9 or "").isdigit():
                    x["oas_9"] = n9
                if (nr or "").isdigit():
                    x["oas_rec"] = nr
    except StopIteration:
        print("OAS CAHPS: columns for 9-10 / recommend not found:", sorted(o.values())[:30])

    # ---- NPI -> CCN (two public sources; disagreement or ambiguity = no rating) ----
    ml = json.loads(c.get_object(Bucket=B, Key="site/med_local/2026.json")["Body"].read())["npi"]
    cand = defaultdict(set)
    for n, v in ml.items():
        if v and v[0] in ("H", "A") and v[2]:
            cand[str(n)].add(str(v[2]))
    enr_n = 0
    try:
        man_u = list(csv.DictReader(io.StringIO(c.get_object(Bucket=B, Key="bot/utilization/manifest.csv")["Body"].read().decode())))
        r = max((x for x in man_u if x["source"] == "hospital_enrollments"), key=lambda x: (x["label"], x["checked_on"]))
        import zstandard
        raw = c.get_object(Bucket=B, Key=r["key"])["Body"].read()
        raw = zstandard.ZstdDecompressor().decompress(raw, max_output_size=1 << 31) if r["key"].endswith(".zst") else raw
        (W / "enr.csv").write_bytes(raw)
        e = cols(con, W / "enr.csv")
        for ccn, npi in con.execute(f"select distinct {pick(e, 'CCN')}, {pick(e, 'NPI')} from read_csv('{W / 'enr.csv'}', header=true, all_varchar=true)").fetchall():
            if ccn and npi:
                cand[str(npi)].add(str(ccn))
                enr_n += 1
        src["enr"] = ["CMS Hospital Enrollments", r["url"], r["label"]]
    except Exception as ex:
        print("Hospital Enrollments not read:", ex)
    npi_ccn = {n: next(iter(v)) for n, v in cand.items() if len(v) == 1}
    ambiguous = sum(len(v) > 1 for v in cand.values())

    # ---- clinicians ----
    d = cols(con, P["ndf"])
    con.execute(f"""create table ndf as select {pick(d, 'NPI')} as npi, any_value({pick(d, 'pri_spec')}) s, any_value({pick(d, 'Med_sch')}) m,
        any_value({pick(d, 'Grd_yr')}) y from {rd('ndf')} group by 1""")
    mp = cols(con, P["mips"])
    con.execute(f"""create table mips as select {pick(mp, 'NPI')} as npi, max(try_cast({pick(mp, 'final_MIPS_score', 'Final MIPS Score')} as double)) as q
        from {rd('mips')} group by 1""")
    f = cols(con, P["aff"])
    con.execute(f"""create table aff as select distinct {pick(f, 'NPI')} as npi, {pick(f, 'Facility Affiliations Certification Number')} as ccn
        from {rd('aff')} where {pick(f, 'facility_type')} ilike '%hospital%'""")
    hn = sorted({x[0] for x in con.execute("select distinct ccn from aff").fetchall()} & set(H))
    hn_ix = {ccn: i for i, ccn in enumerate(hn)}
    hn_list = [[ccn, H[ccn]["name"]] for ccn in hn]

    # ---- one file per state we cover (npi lists in data/scope/) ----
    keys = [o_["Key"] for pg in c.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="data/scope/")
            for o_ in pg.get("Contents", []) if o_["Key"].endswith("_npis_all.parquet")]
    parts = []
    for k in keys:
        label = k.rsplit("/", 1)[-1][:-len("_npis_all.parquet")]
        p = W / f"scope_{label}.parquet"
        c.download_file(B, k, str(p))
        cc = [x[0] for x in con.execute(f"describe select * from read_parquet('{p}')").fetchall()]
        one = label.upper() if len(label) == 2 else {"nyhf": "NY", "skipil": "IL"}.get(label)
        stx = f"coalesce(nullif(upper(state), ''), {repr(one) if one else 'null'})" if "state" in cc else (repr(one) if one else None)
        if stx:
            parts.append(f"select npi::varchar npi, {stx} state from read_parquet('{p}')")
    con.execute(f"create table npi_st as select distinct npi, state from ({' union all '.join(parts)}) where state is not null")
    states = [r[0] for r in con.execute("select distinct state from npi_st where length(state) = 2 order by 1").fetchall()]
    summary = []
    for st in states:
        docs = {}
        for npi, s_, m_, y_, q_ in con.execute(f"""select n.npi, n.s, n.m, n.y, mi.q from npi_st x join ndf n using (npi)
                                                     left join mips mi using (npi) where x.state = '{st}'""").fetchall():
            r = dict(n=npi, s=s_ or "", m=m_ or "", y=y_ or "")
            if q_ is not None:
                r["q"] = int(round(q_))
            docs[npi] = r
        for npi, ccn in con.execute(f"select a.npi, a.ccn from aff a join npi_st x using (npi) where x.state = '{st}'").fetchall():
            if npi in docs and ccn in hn_ix:
                docs[npi].setdefault("a", []).append(hn_ix[ccn])
        nst = {n for (n,) in con.execute(f"select npi from npi_st where state = '{st}'").fetchall()}
        S = dict(base=dict(H=H, PR={}, src=src, nat={}, hn=hn_list, hs={}, nr=NOT_RATED),
                 asc=ascm, docs=docs, npi_ccn={n: v for n, v in npi_ccn.items() if n in nst},
                 note=f"Care Compare ratings by CCN/NPI for {st}, built {TODAY} by site/care_compare.py; quality_rekey.render() places them.")
        c.put_object(Bucket=B, Key=OUT.format(st.lower()), Body=json.dumps(S, separators=(",", ":")).encode(), ContentType="application/json")
        summary.append((st, sum(1 for h in H.values() if h["st"] == st), sum(1 for h in H.values() if h["st"] == st and h["star"]),
                        sum(1 for h in H.values() if h["st"] == st and h.get("hc")), len(S["npi_ccn"]), len(docs),
                        sum(1 for x in docs.values() if "q" in x)))
    # manifest + report
    key = "bot/care_compare/manifest.csv"
    try:
        old = list(csv.DictReader(io.StringIO(c.get_object(Bucket=B, Key=key)["Body"].read().decode())))
    except Exception:
        old = []
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(man[0]))
    w.writeheader()
    w.writerows(old + [r for r in man if (r["key"], r["checked_on"]) not in {(o_["key"], o_["checked_on"]) for o_ in old}])
    c.put_object(Bucket=B, Key=key, Body=buf.getvalue().encode())
    L = [f"# Care Compare ratings: build {TODAY}", "", "Built by site/care_compare.py build (card #3). Nothing deployed.", "",
         "## CMS files used (originals saved in raw/care_compare/)", "", "| Key | Title | CMS release | Size | Link |", "|---|---|---|---|---|"]
    L += [f"| {r['source']} | {r['title']} | {r['modified']} | {int(r['bytes']) / 1e6:,.0f} MB | {cat[r['source']]['page']} |" for r in man]
    L += ["", f"NPI -> CCN matches: {len(npi_ccn):,} (address matches + {enr_n:,} Hospital Enrollments pairs; {ambiguous:,} NPIs with more than one CCN get no rating)",
          f"Surgery centers with a rating: {len(ascm):,}. Hospitals: {len(H):,} ({sum(1 for h in H.values() if h['star']):,} with a CMS star, "
          f"{sum(1 for h in H.values() if h.get('hc')):,} with a patient-survey star).", "",
          "## By state", "", "| State | Hospitals | With CMS star | With survey star | NPI->CCN matches | Clinicians | With MIPS score |",
          "|---|---|---|---|---|---|---|"]
    L += [f"| {s} | {a_:,} | {b_:,} | {c_:,} | {d_:,} | {e_:,} | {f_:,} |" for s, a_, b_, c_, d_, e_, f_ in summary]
    L += ["", "## Columns read (for checking)", ""] + [f"- {k}: {', '.join(v[:40])}" for k, v in colsrep.items()]
    rp = ROOT / "reports" / "care-compare"
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "build.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ------------------------------------------------------------------ preview (nothing deployed)
def esc(x):
    return html.escape(str(x or ""))


def card(kind, fi, fac, Q, S, npi):
    """One provider's rating block, in plain text + links, as the Price Finder would show it."""
    src = Q["src"]

    def link(k):
        s = src.get(k)
        return f' <a href="{esc(s[1])}">CMS {esc(s[2][:10])} ↗</a>' if s else ""
    k = str(fi)
    if kind == "H":
        ccn = Q["h"].get(k)
        if not ccn:
            return f"<p>{NOT_RATED['nomatch']}</p>", "nomatch"
        h = Q["H"][ccn]
        star = f"<b>{h['star']} of 5</b>" if h["star"] else f"<i>{NOT_RATED['H']}</i>"
        hc = (f"<b>{h['hc']} of 5</b>" + (f" · {int(h['hc_n']):,} surveys" if h.get("hc_n") else "") + f" · {esc(h.get('hc_p'))}") if h.get("hc") \
            else "<i>not rated: CMS shows no patient-survey star for this hospital</i>"
        extra = "".join(f" · {lbl} {h[x]}%" for x, lbl in (("hc_9", "rated it 9 or 10:"), ("hc_rec", "would definitely recommend:")) if h.get(x))
        return (f"<p>{esc(h['name'])} · Medicare ID {esc(ccn)}</p><p>CMS overall rating: {star} ({esc(h['type'])}){link('gen')}</p>"
                f"<p>Patient survey rating: {hc}{extra}{link('hc')}</p>"), ("rated" if h["star"] or h.get("hc") else "notrated")
    if kind in ("A", "G"):
        a = Q["a"].get(k)
        if not a:
            ccn = S["npi_ccn"].get(str(npi))
            if kind == "A":
                return f"<p>{NOT_RATED['nomatch'] if not ccn else NOT_RATED['A']}</p>", ("nomatch" if not ccn else "notrated")
            return "", "none"
        lines = []
        for m in ASC_MEASURES:
            x = a.get(m)
            if x:
                lines.append(f"<p>{m}: " + (f"<b>{esc(x['rate'])}</b>" if x.get("rate") else "<i>not rated (not reported)</i>")
                             + (f" · CMS: {esc(x['cat'])}" if x.get("cat") else "") + (f" · {esc(x['cases'])} cases" if x.get("cases") else "") + "</p>")
        if a.get("oas_9") or a.get("oas_rec"):
            lines.append(f"<p>Patient survey: rated it 9 or 10: <b>{esc(a.get('oas_9') or 'not rated')}%</b> · would definitely recommend: "
                         f"<b>{esc(a.get('oas_rec') or 'not rated')}%</b>{link('oas')}</p>")
        return f"<p>{esc(a.get('name'))} · Medicare ID {esc(a['ccn'])}{link('asc')}</p>" + "".join(lines), "rated"
    if kind == "P":
        d = Q["d"].get(k)
        if not d:
            return f"<p><i>{NOT_RATED['P']}</i></p>", "notrated"
        q = f"<b>{d['q']} of 100</b>" if "q" in d else "<i>not rated: no MIPS score (many clinicians are exempt)</i>"
        aff = "; ".join(esc(Q["hn"][i][1]) for i in d.get("a", []))
        return (f"<p>Medicare specialty: <b>{esc(d['s'].lower() or 'not listed')}</b>{link('ndf')}</p><p>MIPS final score: {q}{link('mips')}</p>"
                + (f"<p>Hospital affiliations: {aff}{link('aff')}</p>" if aff else "")), ("rated" if "q" in d else "notrated")
    return "", "none"


def preview(area_slug):
    import procedure_pages as pp
    import quality_rekey as qr
    d = "/tmp/ccprev"
    os.makedirs(d, exist_ok=True)
    store = pp.Store(d)
    c, B = store.s3, store.B
    c.download_file(B, "site/deploy/current.tgz", f"{d}/site.tgz")
    with tarfile.open(f"{d}/site.tgz") as t:
        mem = {m.name.lstrip("./"): m for m in t.getmembers() if m.isfile()}
        areas = json.load(t.extractfile(mem["site/cities.json"]))
        a = next((x for x in areas if x["slug"] == area_slug), None)
        if a is None:
            raise SystemExit(f"no area {area_slug!r}; areas: {[x['slug'] for x in areas]}")
        want = f"site/{a['path'].strip('/')}/index.html"
        os.makedirs(os.path.dirname(f"{d}/{want}"), exist_ok=True)
        open(f"{d}/{want}", "wb").write(t.extractfile(mem[want]).read())
    D = pp.page_data(f"{d}/{want}")[0]
    fac = D["fac"]
    pre = store.prefix(a, "t")
    npis = json.loads(c.get_object(Bucket=B, Key=pre[:-2] + "npis.json")["Body"].read())
    assert len(npis) == len(fac), "npis.json is not aligned with the page providers"
    try:
        sc = json.load(open(HERE / "state_scopes.json"))
        st = {slug: code for k, v in sc.items() if not k.startswith("_") for code, slug in v.items()}.get(a["slug"], pp.area_state(a))
    except Exception:
        st = pp.area_state(a)
    S = json.loads(c.get_object(Bucket=B, Key=OUT.format(st.lower()))["Body"].read())
    Q = qr.render(S, npis, fac)
    tally = Counter()
    samples = defaultdict(list)
    for i, x in enumerate(fac):
        kind = x[2]
        body, res = card(kind, i, fac, Q, S, npis[i])
        if res == "none":
            continue
        tally[(kind, res)] += 1
        if len(samples[(kind, res)]) < 4:
            samples[(kind, res)].append((x[0], npis[i], body))
    KIND = {"H": "Hospitals", "A": "Surgery centers", "P": "Clinicians", "G": "Group practices and other places"}
    RES = {"rated": "Rated", "notrated": "Not rated (CMS gives no rating)", "nomatch": "Not rated (no single Medicare match)"}
    L = [f"# Card #3 preview: Care Compare ratings on the {a['name']} Price Finder", "",
         f"Built {TODAY} by site/care_compare.py preview. Nothing deployed. Ratings file: {OUT.format(st.lower())}.", "",
         "| Kind | " + " | ".join(RES.values()) + " |", "|---|---|---|---|"]
    for k in ("H", "A", "P"):
        L.append(f"| {KIND[k]} | " + " | ".join(f"{tally[(k, r)]:,}" for r in RES) + " |")
    # cross-check against the hand-built DFW ratings: same CCN for the same NPI, same star for the same CCN
    chk = []
    try:
        old = json.loads(c.get_object(Bucket=B, Key=qr.KEY)["Body"].read())
        tx = json.loads(c.get_object(Bucket=B, Key=OUT.format("tx"))["Body"].read())
        both = set(old["npi_ccn"]) & set(tx["npi_ccn"])
        same = sum(old["npi_ccn"][n] == tx["npi_ccn"][n] for n in both)
        diff = [(n, old["npi_ccn"][n], tx["npi_ccn"][n]) for n in both if old["npi_ccn"][n] != tx["npi_ccn"][n]]
        hb = set(old["base"].get("H", {})) & set(tx["base"]["H"])
        hs = sum(str(old["base"]["H"][x].get("star", "")) == str(tx["base"]["H"][x].get("star", "")) for x in hb)
        db = set(old.get("docs", {})) & set(tx["docs"])
        dq = sum(old["docs"][n].get("q") == tx["docs"][n].get("q") for n in db)
        chk = ["", "## Check against the DFW ratings built by hand in October (reference/site/quality_dfw_by_npi.json)", "",
               f"- NPI -> CCN: {len(both):,} NPIs in both; {same:,} give the same CCN, {len(diff):,} differ" + (f" (first: {diff[:5]})" if diff else ""),
               f"- Hospital overall star: {len(hb):,} hospitals in both; {hs:,} the same (differences can be a newer CMS release)",
               f"- Clinician MIPS score: {len(db):,} clinicians in both; {dq:,} the same"]
    except Exception as e:
        chk = ["", f"DFW cross-check not run: {type(e).__name__}: {e}"]
    L += chk
    h_ = [f"<!doctype html><meta charset=utf-8><title>Care Compare preview: {esc(a['name'])}</title>",
          "<style>body{font:15px/1.5 Georgia,serif;max-width:860px;margin:2em auto;padding:0 16px;color:#222;background:#fbf8f2}"
          "h1,h2{font-weight:normal}.p{border-top:1px solid #ddd;padding:.6em 0}.p b{color:#8b2c1a}i{color:#666}a{color:#8b2c1a}</style>",
          f"<h1>Care Compare ratings preview: {esc(a['name'])}</h1><p>Nothing deployed. Samples of each kind, as they would read on the Price Finder.</p>"]
    for (k, r), xs in sorted(samples.items()):
        h_.append(f"<h2>{KIND.get(k, k)}: {RES[r]} ({tally[(k, r)]:,})</h2>")
        for name, npi, body in xs:
            h_.append(f"<div class=p><strong>{esc(name)}</strong> · NPI {esc(npi)}{body}</div>")
    rp = ROOT / "reports" / "care-compare"
    rp.mkdir(parents=True, exist_ok=True)
    (rp / f"{a['slug']}.md").write_text("\n".join(L) + "\n")
    (rp / f"{a['slug']}.html").write_text("\n".join(h_) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "preview"])
    ap.add_argument("--work", default="/tmp/care_compare")
    ap.add_argument("--area", default="illinois")
    A = ap.parse_args()
    if A.cmd == "build":
        build(A.work)
    else:
        import traceback
        for x in A.area.split(","):
            try:
                preview(x)
            except BaseException:      # keep going; the error goes into the report folder so it can be read from the repo
                rp = ROOT / "reports" / "care-compare"
                rp.mkdir(parents=True, exist_ok=True)
                (rp / f"{x}-error.txt").write_text(traceback.format_exc())
                print(traceback.format_exc())
