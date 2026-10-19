"""Hospitals tab (/hospitals/) and one profile page per Dallas-Fort Worth hospital (/hospitals/<slug>/).

Public records only, facts not grades: every section names its source and when it was read. Nothing is estimated.

  python site/hospital_profiles.py SITE_DIR        (SITE_DIR = a pulled site dir, the one that holds site/)

Inputs (all already used elsewhere on the site, except the three CMS lists, which are read fresh)
  CMS Provider Data Catalog: Hospital General Information (xubh-q36u), Long-Term Care Hospital General Information
    (azum-44iv), Inpatient Rehabilitation Facility General Information (7t8x-u3ir): name, address, county, type,
    ownership, emergency services, overall star rating
  SITE_DIR/site/price-finder/index.html          DFW Price Finder data block: providers (D.fac), networks, file dates/URLs,
                                                 hospital price files (D.hosp.src)
  SITE_DIR/site/price-finder/pf/q/quality.txt    which Price Finder provider / hospital file belongs to which CCN
  R2 site/every/<CURRENT>/npis.json              NPI of each Price Finder provider (same order as D.fac)
  R2 site/every/<CURRENT>/t|h/<code>.txt         insurer rates and hospital-file lines per billing code
  data/hospitals.csv                             the hospital price-file bot's list: each hospital's file link and read date
  SITE_DIR/site/price-file-watch/index.html      the Price File Watch's hospital entries (quoted by heading)
  SITE_DIR/site/surprise-bills/providers.json    Texas No Surprises Act arbitration by NPI (CMS IDR files)
  R2 data/idr/site/texas.json                    the quarters those arbitration counts cover
  CMS Hospital Enrollments + Hospital All Owners (data.cms.gov, newest monthly files): each hospital's enrolled NPI(s)
                                                 and the organizations reported as its owners or operators
  site/hospital_file_ccn.csv                     hand-checked corrections: which hospital a price file belongs to
  site/hospital_npi_manual.csv                   hand-checked NPIs for hospitals with no CMS enrollment record
DFW = the 11 counties of the Census Dallas-Fort Worth-Arlington metro (site/dfw_metro.json), plus hospitals the
Price Finder already lists from nearby counties (tagged "outside the DFW metro").
"""
import base64
import collections
import csv
import gzip
import html
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(ROOT / "site"))
import insurers_page  # noqa: E402  (page shell: same look and nav as /insurers/)

E = html.escape
TODAY = date.today().isoformat()
CMS = "https://data.cms.gov/provider-data/api/1/datastore/query/{}/0/download?format=csv"
META = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{}"
PAGE = {"xubh-q36u": "https://data.cms.gov/provider-data/dataset/xubh-q36u",
        "azum-44iv": "https://data.cms.gov/provider-data/dataset/azum-44iv",
        "7t8x-u3ir": "https://data.cms.gov/provider-data/dataset/7t8x-u3ir"}
FEDERAL = {"Veterans Health Administration", "Department of Defense", "Government - Federal"}
CODES = ["45378", "73721", "70450", "99284", "29888", "47562"]   # common outpatient services with DFW procedure pages
OWN_GROUP = [("Non-profit", ("voluntary non-profit", "non-profit", "nonprofit")),
             ("Government", ("government", "state", "county", "city", "district", "authority")),
             ("For-profit", ("proprietary", "for profit", "for-profit", "physician"))]


def slug(n):
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(n).lower().replace("&", " and ")))


def num(x):
    return f"{int(x):,}"


def money(v):
    return f"${v:,.2f}"


def day(iso):
    t = str(iso).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", t) or re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if not m:
        return t
    y, mo, d = (m.group(1), m.group(2), m.group(3)) if "-" in t[:5] else (m.group(3), m.group(1), m.group(2))
    return date(int(y), int(mo), int(d)).strftime("%B %-d, %Y")


def tidy(x):
    up = {"LLC", "LP", "LLP", "PA", "PLLC", "USA", "II", "III", "ER", "UT", "HEB", "JPS", "THR", "BSW", "USMD", "TX"}
    t = " ".join(w.upper() if w.upper().strip(",.()") in up else w for w in str(x).title().split())
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t).replace(" Of ", " of ").replace(" At ", " at ") \
        .replace(" And ", " and ").replace(" For ", " for ").replace(" The ", " the ").replace(" In ", " in ")


CITY_FIX = {"Mc Kinney": "McKinney", "De Soto": "DeSoto", "Fortworth": "Fort Worth"}


def city(c):
    t = str(c).title()
    return CITY_FIX.get(t, t)


def src(text):
    return f'<p class="src">Source: {text}</p>'


def dec(b):
    b = b.strip()
    try:
        return json.loads(gzip.decompress(base64.b64decode(b)))
    except Exception:
        try:
            return json.loads(gzip.decompress(b))
        except Exception:
            return json.loads(b)


TYPE_SHOW = {"Acute Care Hospitals": "Acute care hospital", "Psychiatric": "Psychiatric hospital", "Childrens": "Children's hospital",
             "Critical Access Hospitals": "Critical access hospital"}


def own_group(o):
    o = (o or "").lower()
    for g, keys in OWN_GROUP:
        if any(k in o for k in keys):
            return g
    return "Other or not stated"


HV_CSS = ".hv{display:inline-flex;border:1.5px solid var(--ink);border-radius:2px;overflow:hidden;margin:6px 0 4px}.hv button{font:700 14px var(--body);padding:6px 14px;border:0;background:transparent;color:var(--ink);cursor:pointer}.hv button[aria-pressed=true]{background:var(--ink);color:var(--paper)}"


def cms_list(ds, cache):
    p = cache / f"{ds}.csv"
    if not p.exists():
        r = requests.get(CMS.format(ds), timeout=300)
        r.raise_for_status()
        p.write_bytes(r.content)
    rows = list(csv.DictReader(io.StringIO(p.read_bytes().decode("utf-8-sig"))))
    try:
        m = requests.get(META.format(ds), timeout=60).json().get("modified", "")
    except Exception:
        m = ""
    return rows, m


def load(site, cache):
    import store
    s3, B = store.r2()
    cache.mkdir(parents=True, exist_ok=True)
    pf = (site / "price-finder/index.html").read_text(encoding="utf-8")
    i = pf.index('id="data"')
    D = json.loads(pf[pf.index(">", i) + 1:pf.index("</script>", i)])
    Q = dec((site / "price-finder/pf/q/quality.txt").read_bytes())
    cur = s3.get_object(Bucket=B, Key="site/every/CURRENT")["Body"].read().decode().strip()
    npis = json.loads(s3.get_object(Bucket=B, Key=f"site/every/{cur}/npis.json")["Body"].read())
    assert len(npis) == len(D["fac"]), "npis.json is not aligned with the Price Finder provider list"
    T, H = {}, {}
    for c in CODES:
        T[c] = dec(s3.get_object(Bucket=B, Key=f"site/every/{cur}/t/{c}.txt")["Body"].read()).get("f", {})
        H[c] = dec(s3.get_object(Bucket=B, Key=f"site/every/{cur}/h/{c}.txt")["Body"].read())
    gen, gen_mod = cms_list("xubh-q36u", cache)
    ltch, ltch_mod = cms_list("azum-44iv", cache)
    irf, irf_mod = cms_list("7t8x-u3ir", cache)
    bot = {r["ccn"]: r for r in csv.DictReader(open(ROOT / "data/hospitals.csv", encoding="utf-8"))}
    metro = json.loads((ROOT / "site/dfw_metro.json").read_text())
    counties = {c.upper() for c in metro["msa_counties"]}
    try:
        prov = json.loads((site / "surprise-bills/providers.json").read_text())
        tx = json.loads(s3.get_object(Bucket=B, Key="data/idr/site/texas.json")["Body"].read())
        idr_q = tx["src"]["quarters"]
        idr_read = tx["src"].get("checked", "")
    except Exception:
        prov, idr_q, idr_read = [], [], ""
    pfw = (site / "price-file-watch/index.html").read_text(encoding="utf-8")
    nf = cache / "tx_npis_all.parquet"
    if not nf.exists():
        s3.download_file(B, "data/scope/tx_npis_all.parquet", str(nf))
    nsrc = s3.get_object(Bucket=B, Key="data/scope/tx_npis_all.parquet.source.txt")["Body"].read().decode().split()[0]
    import duckdb
    org = duckdb.connect().execute(f"""select npi, name, taxonomy_1, address, zip5, city from read_parquet('{nf}')
        where entity_type = '2' and deactivated is null and (taxonomy_1 like '28%' or taxonomy_1 like '27%')""").fetchall()
    fnames = json.loads(s3.get_object(Bucket=B, Key="reference/geo/names.json")["Body"].read())   # file:<id> -> [address, type_2_npi]
    en, own, own_meta = cms_owners(cache)
    file_fix = list(csv.DictReader(open(ROOT / "site/hospital_file_ccn.csv", encoding="utf-8")))
    npi_manual = list(csv.DictReader(open(ROOT / "site/hospital_npi_manual.csv", encoding="utf-8")))
    return dict(en=en, own=own, own_meta=own_meta, file_fix=file_fix, npi_manual=npi_manual, org=org, nppes_src=nsrc, fnames=fnames, D=D, Q=Q, npis=npis, T=T, H=H, gen=gen, ltch=ltch, irf=irf, mods=dict(gen=gen_mod, ltch=ltch_mod, irf=irf_mod),
                bot=bot, counties=counties, prov=prov, idr_q=idr_q, idr_read=idr_read, pfw=pfw, cur=cur)


def watch_entries(pfw):
    """The Price File Watch's hospital entries: (status heading, entry name, entry text)."""
    i = pfw.find(">Hospitals</h2>")
    if i < 0:
        return []
    j = pfw.find("<h2", i + 10)
    part = pfw[i:j if j > 0 else None]
    out, head = [], ""
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>|<h4[^>]*>(.*?)</h4>", part, re.S):
        if m.group(1):
            head = html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip()
        else:
            name = html.unescape(re.sub("<[^>]+>", "", m.group(2))).strip()
            out.append((head, name))
    return out


# Price File Watch hospital entries -> CCNs (checked by hand against Medicare's names and cities, Oct 18, 2026)
WATCH_CCN = {"Medical City Mental Health and Wellness Center Frisco": ["454161"],
             "Texas Institute for Surgery at Texas Health Presbyterian Dallas": ["450889"],
             "North Texas Medical Center": ["450090"],
             "Children's Medical Center Dallas and Plano": ["453302", "453316"]}


def norm(n):
    n = n.lower().replace("&", " and ").replace("’", "'")
    n = re.sub(r"\b(the|of|at|hospital|medical|center|health|llc|lp|inc)\b", " ", n)
    return set(re.sub(r"[^a-z0-9 ]", " ", n).split())


def build(L):
    D, Q = L["D"], L["Q"]
    # hospitals: CMS lists, DFW metro counties, plus any CCN the Price Finder already ties to a DFW provider/file
    tied = set(Q.get("h", {}).values()) | set(Q.get("hs", {}).values()) | set(Q.get("pm", {}).values()) \
        | set(Q.get("H", {}).keys()) | set(Q.get("PR", {}).keys())
    hosp = {}
    for r in L["gen"]:
        if r["State"] != "TX" or r["Hospital Ownership"] in FEDERAL:
            continue
        ccn = r["Facility ID"]
        inm = r["County/Parish"].upper() in L["counties"]
        if inm or ccn in tied:
            hosp[ccn] = dict(ccn=ccn, name=r["Facility Name"], addr=r["Address"], city=r["City/Town"], zip=r["ZIP Code"],
                             county=r["County/Parish"], phone=r["Telephone Number"], type=r["Hospital Type"],
                             own=r["Hospital Ownership"], er=r["Emergency Services"], star=r["Hospital overall rating"],
                             star_fn=r.get("Hospital overall rating footnote", ""), metro=inm, ds="xubh-q36u")
    for rows, ds, typ in ((L["ltch"], "azum-44iv", "Long-term care hospital"), (L["irf"], "7t8x-u3ir", "Inpatient rehabilitation hospital")):
        for r in rows:
            ccn = r["CMS Certification Number (CCN)"]
            if r["State"] != "TX" or ccn in hosp:
                continue
            if ds == "7t8x-u3ir" and not ccn[2:].isdigit():
                continue   # rehab units inside another hospital (CCN with a letter): their prices are in the parent's file
            inm = r["County/Parish"].upper() in L["counties"]
            if inm or ccn in tied:
                hosp[ccn] = dict(ccn=ccn, name=r["Provider Name"], addr=(r["Address Line 1"] + " " + r.get("Address Line 2", "")).strip(),
                                 city=r["City/Town"], zip=r["ZIP Code"], county=r["County/Parish"], phone=r["Telephone Number"],
                                 type=typ, own=r["Ownership Type"], er="", star="", star_fn="", metro=inm, ds=ds)
    # Price Finder ties. Hospital price files: quality.txt "hs" (file index -> CCN; file indexes are kept stable between
    # builds). Providers: by NPI. A hospital's NPIs = NPPES organization records with a hospital taxonomy that fits its
    # CMS type, at the same ZIP and street number as Medicare's address for it (quality.txt's provider indexes are not
    # used: they can drift from the provider list's order between builds).
    file_ccn = {int(s_): ccn for s_, ccn in Q.get("hs", {}).items()}
    for i, x in enumerate(D["hosp"]["src"]):   # hand-checked corrections, matched by the file's own web address
        for f in L["file_fix"]:
            if f["url_contains"] in (x[4] or ""):
                file_ccn[i] = f["ccn"]
    src_of = collections.defaultdict(list)
    for s_, ccn in file_ccn.items():
        src_of[ccn].append(int(s_))
    manual = collections.defaultdict(list)
    for r in L["npi_manual"]:
        manual[r["ccn"]].append(r)
    pos = {n: i for i, n in enumerate(L["npis"]) if n}
    TAX = {"Long-term care hospital": ("282E",), "Inpatient rehabilitation hospital": ("283X",),
           "Psychiatric": ("283Q", "282N"), "Childrens": ("282N",), "Acute Care Hospitals": ("282N",),
           "Critical Access Hospitals": ("282N",)}
    by_zip, by_city = collections.defaultdict(list), collections.defaultdict(list)
    for npi, nm, tax, addr, z, cty in L["org"]:
        by_zip[(z or "")[:5]].append((npi, nm, tax or "", addr or ""))
        by_city[(cty or "").upper()].append((npi, nm, tax or "", addr or ""))
    stno = lambda a: (re.match(r"\s*(\d+)", a or "") or [None, None])[1]
    # slugs (unique)
    seen = collections.Counter()
    for h in sorted(hosp.values(), key=lambda x: x["ccn"]):
        s = slug(tidy(h["name"]) + " " + city(h["city"])) if h["city"].lower() not in h["name"].lower() else slug(tidy(h["name"]))
        seen[s] += 1
        h["slug"] = s if seen[s] == 1 else f"{s}-{h['ccn']}"
        st = stno(h["addr"])
        fits = lambda r: r[2].startswith(TAX.get(h["type"], ("28",)))
        m = [r for r in by_zip.get(h["zip"][:5], []) if st and stno(r[3]) == st and fits(r)]
        if not m:   # NPPES may list another street address: same city, same name (all distinctive words shared)
            k = norm(h["name"])
            m = [r for r in by_city.get(h["city"].upper(), []) if fits(r) and k and norm(r[1]) and
                 len(k & norm(r[1])) / len(k | norm(r[1])) >= .75]
        own_file = set()
        for s_ in src_of.get(h["ccn"], []):   # NPIs the hospital's own price file lists (type_2_npi, required by CMS)
            v = L["fnames"].get(f'file:{D["hosp"]["src"][s_][5]}') or [None, None]
            own_file |= set(re.findall(r"\b\d{10}\b", str(v[1] or "")))
        enrolled = {e["NPI"] for e in L["en"].get(h["ccn"], []) if e.get("NPI")}
        hand = {r["npi"] for r in manual.get(h["ccn"], [])}
        h["npi_file"] = sorted(own_file)
        h["npi_enrolled"] = sorted(enrolled)
        h["npi_how"] = {}
        for n in sorted({r[0] for r in m} | own_file | enrolled | hand):
            how = []
            if n in enrolled:
                how.append("CMS Hospital Enrollments lists it for this CCN")
            if n in own_file:
                how.append("the hospital's own price file lists it")
            if n in {r[0] for r in m}:
                how.append("NPPES hospital-type organization record at the same street address")
            if n in hand:
                how.append(next(r["evidence"] for r in manual[h["ccn"]] if r["npi"] == n))
            h["npi_how"][n] = how
        h["npi_all"] = sorted(h["npi_how"])
        h["npi"] = [n for n in h["npi_all"] if n in pos]
        # the hospital's own NPIs: every Price Finder record for them except individual clinicians (the Price Finder
        # sometimes files a hospital's NPI under "surgery center" or "group", by its NPPES taxonomy)
        h["fac"] = sorted(pos[n] for n in h["npi"] if D["fac"][pos[n]][2] != "P")
        h["owners"] = owners_of(h["ccn"], L["en"], L["own"])
        sy = systems_of(h["owners"])
        h["system"], h["jv"] = (sy[0], sy[1:]) if sy else (NO_SYSTEM, [])
        h["src"] = sorted(set(src_of.get(h["ccn"], [])))
        if len(h["name"]) >= 50:   # CMS cuts names at 50 characters; use the NPPES name when it starts the same way
            full = next((r[1] for r in m if re.sub(r"\W", "", r[1].upper()).startswith(re.sub(r"\W", "", h["name"].upper())[:40])), None)
            h["name"] = full or h["name"].rstrip() + "…"
        h["group"] = own_group(h["own"])
    return hosp


def prices(h, L):
    D, out, nets = L["D"], [], collections.defaultdict(set)
    fac = set(h["fac"])
    srcs = set(h["src"])
    slugs = {r["code"]: r["slug"] for r in csv.DictReader(open(ROOT / "site/procedure_slugs.csv", encoding="utf-8"))}
    for c in CODES:
        row = dict(code=c, name=D["codes"].get(c, {}).get("name", c), slug=slugs.get(c))
        # its own price file (45 CFR 180): discounted cash price and dollar negotiated rates
        Hc = L["H"][c]
        cash = [x[2] for x in Hc.get("c", []) if x[0] in srcs and x[2]]
        # rows: [file, insurer, product (0 employer/individual, 1 marketplace, 2 MA, 3 Medicaid, 4 not stated), plan, fee,
        #        1 = % of charges, value, line, setting, 1 = flat case rate]; commercial dollar rates, no flat case rates
        neg = [x[6] for x in Hc.get("r", []) if x[0] in srcs and x[2] in (0, 1) and not x[5] and not x[9] and x[6]]
        row["cash"] = min(cash) if cash else None
        row["neg"] = (min(neg), max(neg), len(neg)) if neg else None
        # insurer files (Transparency in Coverage): this hospital's providers, dollar rates, not flagged low/zero
        per = {}
        for fi in fac:   # rows per provider: [network, 0 facility / 1 professional, 1 = % of charges, value, flags, ...]
            for r in L["T"][c].get(str(fi), []):
                if r[1] == 0 and r[2] == 0 and not (r[4] & (2 | 4)) and r[3]:
                    per.setdefault(r[0], []).append(r[3])
        for ni in per:
            nets[D["nets"][ni]].add(c)
        # BCBSTX ParPlan is a provider contract, not a network a member picks (BCBSTX's own ParPlan page); until Betsy
        # decides how to show it, it stays listed but out of the range and network count (same rule as procedure pages)
        perx = {ni: x for ni, x in per.items() if "ParPlan" not in D["nets"][ni]}
        if perx:
            v = [min(x) for x in perx.values()]
            row["ins"] = (min(v), max(v), len(perx))
        else:
            row["ins"] = None
        if row["cash"] or row["neg"] or row["ins"]:
            out.append(row)
    return out, nets


CSS = """
.prof h2{font:600 26px/1.15 var(--display);margin:40px 0 6px}
.prof .tags{display:flex;flex-wrap:wrap;gap:8px}
.prof section{border-top:2px solid var(--ink);margin-top:36px;padding-top:4px}
.prof section > p{max-width:70ch}
.prof .src{font-size:13px;color:var(--ink-2);margin:12px 0 0;max-width:76ch}
.prof .src a{color:inherit}
.tag{display:inline-block;font:700 11px var(--body);letter-spacing:.08em;text-transform:uppercase;padding:2px 8px;border:1.5px solid var(--ink);border-radius:999px}
.facts{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 18px;margin:10px 0;font-size:15px}
.facts dt{color:var(--ink-2)}.facts dd{margin:0}
@media(max-width:560px){.facts{grid-template-columns:1fr;gap:0}.facts dd{margin-bottom:8px}}
.tbl{width:100%;border-collapse:collapse;font-size:14.5px;margin-top:8px}
.tbl th{text-align:left;font:700 12px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1.5px solid var(--ink)}
.tbl td{padding:8px 8px 8px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.tbl td.n,.tbl th.n{text-align:right;font-family:var(--type);font-variant-numeric:tabular-nums;white-space:nowrap}
.tw{overflow-x:auto}
.note{padding:12px 14px;border:2px solid var(--ink);border-left-width:8px;max-width:72ch;margin:10px 0}
.back{display:inline-block;margin-top:18px;font-weight:600}
.prof > header{border-bottom:0}
.hl-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0}
.hl-tools input{font:16px var(--body);padding:9px 12px;border:1.5px solid var(--ink);border-radius:2px;background:transparent;color:var(--ink);width:100%;max-width:360px}
.hl-tools select{font:15px var(--body);padding:8px;border:1.5px solid var(--rule);border-radius:2px;background:var(--paper);color:var(--ink)}
.hl h3{font:600 22px var(--display);margin:30px 0 4px}
.muted{color:var(--ink-2);font-size:13.5px}
"""


CATALOG = "https://data.cms.gov/data.json"
OWN_PAGE = {"Hospital Enrollments": "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-enrollments",
            "Hospital All Owners": "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-all-owners"}
# Health systems, recognized only by the owner and operator names hospitals report to Medicare (CMS Hospital All Owners).
# Order matters: when a hospital reports owners from more than one listed system, the first one listed here is shown as
# its system and the others as joint-venture partners.
SYSTEMS = [("Baylor Scott & White Health", ("BAYLOR",)), ("Texas Health Resources", ("TEXAS HEALTH RESOURCES",)),
           ("Methodist Health System", ("METHODIST HOSPITALS OF DALLAS",)), ("Children's Health", ("CHILDREN'S HEALTH SYSTEM OF TEXAS",)),
           ("Cook Children's", ("COOK CHILDREN",)), ("UT Southwestern Medical Center", ("UNIVERSITY OF TEXAS SOUTHWESTERN",)),
           ("Parkland (Dallas County Hospital District)", ("DALLAS COUNTY HOSPITAL DISTRICT",)),
           ("JPS (Tarrant County Hospital District)", ("TARRANT COUNTY HOSPITAL DISTRICT",)),
           ("HCA Healthcare (Medical City)", ("HCA HEALTHCARE", "HCA INC")), ("Tenet Healthcare (USPI)", ("TENET HEALTHCARE",)),
           ("Community Health Systems", ("COMMUNITY HEALTH SYSTEMS",)), ("Universal Health Services", ("UNIVERSAL HEALTH SERVICES",)),
           ("Prime Healthcare", ("PRIME HEALTHCARE",)), ("Select Medical", ("SELECT MEDICAL CORPORATION",)),
           ("Encompass Health", ("ENCOMPASS HEALTH CORPORATION",)), ("Lifepoint Health", ("LIFEPOINT HEALTH", "LIFEPOINT BEHAVIORAL", "LIFEPOINT REHAB")),
           ("Kindred Healthcare", ("KINDRED HEALTHCARE",)), ("Ernest Health", ("ERNEST HEALTH",)), ("Surgery Partners", ("SURGERY PARTNERS",)),
           ("ClearSky Health", ("CLEARSKY",)), ("Emerus", ("EMERUS",)), ("Adventist Health System", ("ADVENTIST HEALTH SYSTEM",))]
NO_SYSTEM = "Not part of a system listed here"


def cms_owners(cache):
    """Newest CMS Hospital Enrollments and Hospital All Owners files: {ccn: [enrollment rows]}, {enrollment id: [owner rows]}."""
    meta, files = {}, {}
    for key in OWN_PAGE:
        p = cache / f"{key.replace(' ', '_')}.csv"
        if not p.exists():
            cat = requests.get(CATALOG, timeout=300).json()
            best = max(((x.get("title", ""), x["downloadURL"]) for d in cat["dataset"] for x in d.get("distribution", [])
                        if x.get("title", "").startswith(key + " :") and str(x.get("downloadURL", "")).endswith(".csv")))
            r = requests.get(best[1], timeout=600)
            r.raise_for_status()
            p.write_bytes(r.content)
            (cache / f"{p.stem}.title").write_text(best[0] + "\n" + best[1])
        t = (cache / f"{p.stem}.title").read_text().split("\n") if (cache / f"{p.stem}.title").exists() else [key, ""]
        u = t[1] if len(t) > 1 else ""
        m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", u)   # the date in CMS's file name, e.g. Hospital_All_Owners_2026.07.31
        meta[key] = dict(title=t[0], url=u, date=day(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m else day(t[0].split(":")[-1].strip()))
        files[key] = list(csv.DictReader(io.StringIO(p.read_bytes().decode("latin-1"))))
    en, own = collections.defaultdict(list), collections.defaultdict(list)
    for r in files["Hospital Enrollments"]:
        en[r["CCN"]].append(r)
    for r in files["Hospital All Owners"]:
        own[r["ENROLLMENT ID"]].append(r)
    return en, own, meta


def owners_of(ccn, en, own):
    """Organizations reported to Medicare as owning (5% or more, any role) or operating this hospital, largest share first."""
    seen = {}
    for e in en.get(ccn, []):
        for o in own.get(e["ENROLLMENT ID"], []):
            if o["TYPE - OWNER"] != "O" or not o["ORGANIZATION NAME - OWNER"].strip():
                continue
            nm = o["ORGANIZATION NAME - OWNER"].strip()
            try:
                pct = float(o["PERCENTAGE OWNERSHIP"] or 0)
            except ValueError:
                pct = 0
            role = o["ROLE TEXT - OWNER"].strip().lower()
            cur = seen.get(nm)
            if not cur or pct > cur[1]:
                seen[nm] = (nm, pct, role)
    return sorted(seen.values(), key=lambda x: (-x[1], x[0]))


def systems_of(owners):
    found = []
    for sysname, keys in SYSTEMS:
        if any(any(k in nm.upper() for k in keys) for nm, _, _ in owners):
            found.append(sysname)
    return found


def shell(title, desc, url, current_hospitals=True):
    head = insurers_page.TEMPLATE[:insurers_page.TEMPLATE.index("</nav>") + 6]
    head = (head.replace('content="https://files.healthcare/insurers/"', f'content="{url}"')
            .replace("Who Owns Your Health Plan · The Healthcare Files", f"{E(title)} · The Healthcare Files")
            .replace(head[head.index('<meta name="description" content="'):head.index('">', head.index('<meta name="description" content="')) + 2],
                     f'<meta name="description" content="{E(desc)}">')
            .replace("</style>\n</head>", CSS + HV_CSS + "</style>\n</head>", 1))
    # nav: Insurers is no longer current; Hospitals (added after it) is
    head = head.replace('<a href="/insurers/" aria-current="page">Insurers</a>', '<a href="/insurers/">Insurers</a>')
    if 'href="/hospitals/"' not in head:
        head = head.replace('<a href="/insurers/">Insurers</a>',
                            '<a href="/insurers/">Insurers</a><a href="/hospitals/"' + (' aria-current="page"' if current_hospitals else '') + '>Hospitals</a>', 1)
    return head


def gen_src(h, L):
    ds = h["ds"]
    name = {"xubh-q36u": "CMS Hospital General Information", "azum-44iv": "CMS Long-Term Care Hospital General Information",
            "7t8x-u3ir": "CMS Inpatient Rehabilitation Facility General Information"}[ds]
    mod = L["mods"][{"xubh-q36u": "gen", "azum-44iv": "ltch", "7t8x-u3ir": "irf"}[ds]]
    return f'<a href="{PAGE[ds]}" target="_blank" rel="noopener">{name}</a>' + (f", updated by CMS {day(mod)}" if mod else "") + f" · read {day(TODAY)}"


def profile(h, L, watch):
    D, sec = L["D"], []
    name = tidy(h["name"])
    tags = [f'<span class="tag">{E(h["group"])}</span>']
    if not h["metro"]:
        tags.append('<span class="tag">Outside the DFW metro</span>')
    # Who it is
    facts = [("Type", TYPE_SHOW.get(h["type"], h["type"])), ("Ownership (as CMS lists it)", h["own"] or "not stated"),
             ("Address", f'{tidy(h["addr"])}, {city(h["city"])}, TX {h["zip"]}'), ("County", h["county"].title()),
             ("Phone", h["phone"])]
    if h["er"]:
        facts.append(("Emergency services", h["er"]))
    if h["system"] != NO_SYSTEM:
        facts.insert(1, ("Health system", h["system"] + (" · joint venture with " + " and ".join(h["jv"]) if h["jv"] else "")))
    if h["owners"]:
        facts.insert(3, ("Owners and operators reported to Medicare",
                         "; ".join(f'{tidy(nm)}{f" ({pct:g}%)" if pct else ""}' for nm, pct, _ in h["owners"][:6])
                         + (f"; and {len(h['owners']) - 6} more" if len(h["owners"]) > 6 else "")))
    facts.append(("CMS Certification Number (CCN)", h["ccn"]))
    if h["npi_all"]:
        facts.append(("NPI" + ("s" if len(h["npi_all"]) > 1 else ""), ", ".join(h["npi_all"])))
    body = '<dl class="facts">' + "".join(f"<dt>{E(k)}</dt><dd>{E(v)}</dd>" for k, v in facts) + "</dl>"
    ways = sorted({w.split(":")[0] if "No CMS enrollment" not in w else "checked by hand against NPPES" for n in h["npi_all"] for w in h["npi_how"][n]})
    body += src(gen_src(h, L) + ("; NPIs: " + "; ".join(ways).replace("NPPES", '<a href="https://download.cms.gov/nppes/NPI_Files.html" target="_blank" rel="noopener">NPPES</a>', 1)
                                 if h["npi_all"] else ""))
    om = L["own_meta"]
    if h["owners"] or h["npi_enrolled"]:
        body += src(f'<a href="{OWN_PAGE["Hospital All Owners"]}" target="_blank" rel="noopener">CMS Hospital All Owners</a> and '
                    f'<a href="{OWN_PAGE["Hospital Enrollments"]}" target="_blank" rel="noopener">Hospital Enrollments</a> '
                    f'(files dated {E(om["Hospital All Owners"]["date"])}) · read {day(TODAY)}. The health system is the listed system whose name '
                    "appears among the owners and operators the hospital reports to Medicare; ownership percentages are as reported.")
    sec.append(("Who it is", body))

    # CMS star rating (hospital general information only)
    if h["ds"] == "xubh-q36u":
        if h["star"] and h["star"].isdigit():
            body = (f"<p>CMS overall hospital star rating: <b>{h['star']} of 5</b>. CMS combines measures of deaths, safety, "
                    "readmissions, patient experience and timely care into one rating.</p>")
        else:
            body = "<p>CMS does not publish an overall star rating for this hospital" + (" (it says it has too few measures or isn't rated)" if h["star_fn"] else "") + ".</p>"
        body += src(gen_src(h, L))
        sec.append(("Medicare's quality rating", body))

    # Price file
    b = L["bot"].get(h["ccn"])
    body = ""
    if b and b.get("mrf_url"):
        when = (b.get("last_archived_run") or "")[:10]
        body += (f'<p>Its price file, as linked from its website: <a href="{E(b["mrf_url"])}" target="_blank" rel="noopener">{E(b["mrf_url"][:90])}'
                 f'{"…" if len(b["mrf_url"]) > 90 else ""}</a>.' + (f" Our bot last downloaded it {day(when)}." if re.match(r"\d{4}-\d\d-\d\d", when) else "") + "</p>")
    if h["src"]:
        s0 = [D["hosp"]["src"][s] for s in h["src"]]
        dates = sorted({x[3] for x in s0 if x[3]})
        body += (f"<p>The Price Finder reads {len(s0)} of its price file{'s' if len(s0) > 1 else ''}"
                 + (f", dated {', '.join(day(d) for d in dates)} in the file itself" if dates else ", which carries no date") + ".</p>")
    elif b:
        body += "<p>Its file isn't in the DFW Price Finder yet.</p>"
    w = [(hd, nm) for hd, nm in watch if h["ccn"] in WATCH_CCN.get(nm, [])]
    for hd, nm in w:
        body += f'<p class="note">The <a href="/price-file-watch/">Price File Watch</a> lists “{E(nm)}” under <b>{E(hd)}</b>. See that page for what was found and when.</p>'
    if not body:
        body = "<p>We haven't recorded a price file for this hospital yet.</p>"
    body += src("the hospital's own website and price file (45 CFR 180); the hospital price-file bot's list"
                + (f" · read {day(TODAY)}" if b else "")
                + '. Hospital price files we read are also sent to the <a href="https://archive.org/search?query=upfront-hospital-price-files" target="_blank" rel="noopener">Internet Archive</a>.')
    sec.append(("Price file", body))

    # Prices
    rows, nets = prices(h, L)
    if rows:
        tr = ""
        for r in rows:
            link = f'/costs/dallas-fort-worth/{r["slug"]}/' if r["slug"] else f'/price-finder/?code={r["code"]}'
            tr += (f'<tr><td><a href="{link}">{E(r["name"])}</a><div class="muted">CPT {r["code"]}</div></td>'
                   f'<td class="n">{money(r["cash"]) if r["cash"] else "—"}</td>'
                   f'<td class="n">{(money(r["neg"][0]) + (" to " + money(r["neg"][1]) if r["neg"][1] != r["neg"][0] else "")) if r["neg"] else "—"}'
                   f'{"<div class=muted>" + num(r["neg"][2]) + " lines</div>" if r["neg"] else ""}</td>'
                   f'<td class="n">{(money(r["ins"][0]) + (" to " + money(r["ins"][1]) if r["ins"][1] != r["ins"][0] else "")) if r["ins"] else "—"}'
                   f'{"<div class=muted>" + num(r["ins"][2]) + " network" + ("s" if r["ins"][2] > 1 else "") + "</div>" if r["ins"] else ""}</td></tr>')
        body = ("<p>Its facility fee for a few common services: the cash price and the employer and marketplace plan rates its own price file lists "
                "(flat case rates, Medicare Advantage and Medicaid left out), and the lowest rate "
                "each insurer network's file lists for it (BCBSTX ParPlan, a provider contract, left out). Facility fee only; the doctor bills separately. Click a service for every place "
                "and every network.</p>"
                '<div class="tw"><table class="tbl"><thead><tr><th>Service</th><th class="n">Cash price<br>(its file)</th>'
                '<th class="n">Employer and marketplace<br>plan rates (its file)</th><th class="n">Insurer files<br>(lowest per network)</th></tr></thead><tbody>'
                + tr + "</tbody></table></div>")
        dts = sorted(set(D["dates"]))
        body += src("the hospital's own price file (45 CFR 180) and insurers' Transparency in Coverage files dated "
                    f"{day(dts[0])} to {day(dts[-1])}, as read for the <a href=\"/price-finder/\">Price Finder</a>. Percent-of-charges rates, "
                    "$0 lines and rates flagged unusually low are left out. Read for the Price Finder build of "
                    f"{day(L['cur'])}.")
        sec.append(("Prices", body))
    if nets:
        lst = sorted(nets, key=lambda n: (n.split("|")[0], n))
        body = ("<p>Networks whose rate files list a dollar rate for this hospital for at least one of the services above. "
                "A rate in a file shows a contract for that service; it is not a full list of the networks the hospital is in.</p><ul>"
                + "".join(f"<li>{E(n.split('|')[0])}: {E(n.split('|', 1)[1])}"
                          + (' <span class="muted">(a BCBSTX provider contract, not a network a member picks; left out of the ranges above. '
                             '<a href="https://bwww.bcbstx.com/provider/network/parplan.html" target="_blank" rel="noopener">BCBSTX</a>)</span>'
                             if "ParPlan" in n else "") + "</li>" for n in lst) + "</ul>")
        body += src("insurers' Transparency in Coverage in-network rate files read for the <a href=\"/price-finder/\">Price Finder</a>")
        sec.append(("Insurer networks with a published rate", body))

    # Surprise-bill arbitration (CMS IDR files, matched by NPI)
    np_set = set(h["npi_all"])
    idr = [p for p in L["prov"] if str(p[0]) in np_set]
    if idr and L["idr_q"]:
        lines = sum(p[1] for p in idr); disp = sum(p[2] for p in idr); won = sum(p[3] for p in idr)
        q = L["idr_q"]
        per = f"{q[0].replace('-q', ' Q')} to {q[-1].replace('-q', ' Q')}"
        body = (f"<p>Federal No Surprises Act arbitration in Texas, {per}, where the provider's NPI is one of this hospital's: "
                f"<b>{num(disp)}</b> disputes, <b>{num(lines)}</b> disputed lines; the arbitrator picked the provider's offer on "
                f"{round(100 * won / lines) if lines else 0}% of lines. An award is the offer chosen, not proof of payment. "
                'More on the <a href="/surprise-bills/">Surprise Bills</a> page.</p>')
        body += src('CMS federal independent dispute resolution public use files (<a href="https://www.cms.gov/nosurprises/policies-and-resources/Reports" '
                    f'target="_blank" rel="noopener">CMS reports</a>)' + (f" · read {day(L['idr_read'])}" if L["idr_read"] else ""))
        sec.append(("Surprise-bill arbitration", body))

    url = f"https://files.healthcare/hospitals/{h['slug']}/"
    desc = f"{name}, {city(h['city'])}: public records on its ownership, price file, prices and Medicare rating."
    head = shell(f"{name} · Hospital profile", desc, url)
    body = "".join(f"<section><h2>{E(t)}</h2>{b}</section>" for t, b in sec)
    return (head + f"""
<main class="prof">
<header>
  <div class="eyebrow">Hospital profile · public records only</div>
  <h1>{E(name)}</h1>
  <p class="lede">{E(city(h['city']))}, {E(h['county'].title())} County. Everything here comes from public records and the hospital's own files. Each section names its source and when we read it. Nothing is estimated or graded.</p>
  <div class="tags">{"".join(tags)}</div>
</header>
{body}
<a class="back" href="/hospitals/">← Back to every hospital</a>
<p class="src" style="margin-top:28px">See something wrong? <a href="/corrections/">Report it</a>. Checked {day(TODAY)}.</p>
</main>
</div>
</body></html>
""")


def index(hosp, L):
    hs = sorted(hosp.values(), key=lambda h: (["Non-profit", "Government", "For-profit", "Other or not stated"].index(h["group"]), tidy(h["name"])))
    cnt = collections.Counter(h["group"] for h in hs)
    in_pf = sum(1 for h in hs if h["src"])

    def row(h, by_system):
        sub = (h["own"] if not by_system else (" · ".join(filter(None, ["joint venture with " + " and ".join(h["jv"]) if h["jv"] else "", h["own"]]))))
        return (f'<tr data-q="{E((tidy(h["name"]) + " " + h["city"] + " " + h["own"] + " " + h["system"] + " " + " ".join(n for n, _, _ in h["owners"])).lower())}" '
                f'data-t="{E(TYPE_SHOW.get(h["type"], h["type"]))}">'
                f'<td><a href="/hospitals/{h["slug"]}/">{E(tidy(h["name"]))}</a><div class="muted">{E(sub)}'
                f'{" · outside the DFW metro" if not h["metro"] else ""}</div></td>'
                f'<td>{E(city(h["city"]))}</td><td>{E(TYPE_SHOW.get(h["type"], h["type"]))}</td>'
                f'<td class="n">{h["star"] if h["star"].isdigit() else "—"}</td><td>{"Yes" if h["src"] else "Not yet"}</td></tr>')

    def table(title, part, by_system):
        return (f'<section class="hl" data-g="{E(title)}"><h3>{E(title)} <span class="muted">· {len(part)} hospital{"s" if len(part) != 1 else ""}</span></h3>'
                '<div class="tw"><table class="tbl"><thead><tr><th>Hospital</th><th>City</th><th>Type</th><th class="n">CMS stars</th>'
                '<th>Price file in the Price Finder</th></tr></thead><tbody>' + "".join(row(h, by_system) for h in part) + "</tbody></table></div></section>")
    groups = "".join(table(g, [h for h in hs if h["group"] == g], False)
                     for g in ["Non-profit", "Government", "For-profit", "Other or not stated"] if any(h["group"] == g for h in hs))
    order = [n for n, _ in SYSTEMS]
    by_sys = collections.defaultdict(list)
    for h in hs:
        by_sys[h["system"]].append(h)
    sys_names = sorted((k for k in by_sys if k != NO_SYSTEM), key=lambda k: (-len(by_sys[k]), order.index(k)))
    systems = "".join(table(k, sorted(by_sys[k], key=lambda h: tidy(h["name"])), True) for k in sys_names)
    if by_sys.get(NO_SYSTEM):
        systems += table(NO_SYSTEM, sorted(by_sys[NO_SYSTEM], key=lambda h: tidy(h["name"])), True)
    om = L["own_meta"]["Hospital All Owners"]
    types = sorted({TYPE_SHOW.get(h["type"], h["type"]) for h in hs})
    head = shell("Hospitals in Dallas–Fort Worth", "Every Dallas–Fort Worth hospital from Medicare's public lists: who owns it, its "
                 "price file, its prices and its Medicare rating, each with the source.", "https://files.healthcare/hospitals/")
    return head + f"""
<main class="prof">
<header>
  <div class="eyebrow">Hospitals · Dallas–Fort Worth · public records only</div>
  <h1>Hospitals in Dallas–Fort Worth</h1>
  <p class="lede">Every hospital Medicare lists in the 11-county Dallas–Fort Worth metro, plus a few nearby ones the Price Finder already reads. Open one for who owns it, its price file, what it charges for common services and its Medicare rating. Every fact links to its source.</p>
  <div class="tags"><span class="tag">{len(hs)} hospitals</span><span class="tag">{cnt["Non-profit"]} non-profit</span><span class="tag">{cnt["For-profit"]} for-profit</span><span class="tag">{cnt["Government"]} government</span><span class="tag">{in_pf} with a file in the Price Finder</span></div>
</header>
<div class="hl-tools">
  <input type="search" id="hq" placeholder="Find a hospital, city or owner" aria-label="Find a hospital">
  <select id="ht" aria-label="Type"><option value="">Every type</option>{"".join(f'<option>{E(t)}</option>' for t in types)}</select>
  <span class="muted" id="hc"></span>
</div>
<div class="vt hv" role="group" aria-label="Group hospitals by"><button type="button" data-v="sys" aria-pressed="true">By health system</button><button type="button" data-v="own" aria-pressed="false">By ownership type</button></div>
<div id="v-sys">
<p class="muted">Grouped by health system: the system whose name appears among the owners and operators each hospital reports to Medicare (<a href="{OWN_PAGE['Hospital All Owners']}" target="_blank" rel="noopener">CMS Hospital All Owners</a>, file dated {E(om["date"])}). Many hospitals are joint ventures; the partner is shown under the name. Ownership changes after that file aren't reflected. “Not yet” means we haven't matched a usable price file for that hospital in the DFW Price Finder; see the <a href="/price-file-watch/">Price File Watch</a>.</p>
{systems}
</div>
<div id="v-own" hidden>
<p class="muted">Grouped by ownership type as CMS lists it (non-profit, government, for-profit). “Not yet” means we haven't matched a usable price file for that hospital in the DFW Price Finder; see the <a href="/price-file-watch/">Price File Watch</a>.</p>
{groups}
</div>
<p class="src" style="margin-top:28px">Sources: <a href="{PAGE['xubh-q36u']}" target="_blank" rel="noopener">CMS Hospital General Information</a>, <a href="{PAGE['azum-44iv']}" target="_blank" rel="noopener">Long-Term Care Hospital</a> and <a href="{PAGE['7t8x-u3ir']}" target="_blank" rel="noopener">Inpatient Rehabilitation Facility</a> lists (VA and military hospitals left out: the federal price-file rule doesn't cover them); hospital price files and insurer rate files as read for the Price Finder. Read {day(TODAY)}. See something wrong? <a href="/corrections/">Report it</a>.</p>
</main>
</div>
<script>
(function(){{var q=document.getElementById('hq'),t=document.getElementById('ht'),c=document.getElementById('hc');
function f(){{var s=q.value.trim().toLowerCase(),ty=t.value,n=0;
document.querySelectorAll('tr[data-q]').forEach(function(r){{var ok=(!s||r.getAttribute('data-q').indexOf(s)>=0)&&(!ty||r.getAttribute('data-t')===ty);r.hidden=!ok;if(ok&&!r.parentNode.closest('#v-sys[hidden],#v-own[hidden]'))n++;}});
document.querySelectorAll('section.hl').forEach(function(x){{x.hidden=!x.querySelector('tr[data-q]:not([hidden])');}});
c.textContent=n+' shown';}}
q.addEventListener('input',f);t.addEventListener('change',f);f();
document.querySelectorAll('.hv button').forEach(function(b){{b.addEventListener('click',function(){{var v=b.getAttribute('data-v');
document.querySelectorAll('.hv button').forEach(function(x){{x.setAttribute('aria-pressed',x===b);}});
document.getElementById('v-sys').hidden=v!=='sys';document.getElementById('v-own').hidden=v!=='own';f();}});}});}})();
</script>
</body></html>
"""


def main(site_dir, cache=None):
    site = Path(site_dir) / "site"
    L = load(site, Path(cache or (Path(site_dir) / ".hosp_cache")))
    hosp = build(L)
    watch = watch_entries(L["pfw"])
    (site / "hospitals").mkdir(parents=True, exist_ok=True)
    (site / "hospitals/index.html").write_text(index(hosp, L), encoding="utf-8")
    for h in hosp.values():
        d = site / "hospitals" / h["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(profile(h, L, watch), encoding="utf-8")
    with open(ROOT / "site/hospital_npi_matches.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ccn", "hospital", "npi", "in_price_finder", "evidence"])
        for h in sorted(hosp.values(), key=lambda x: x["ccn"]):
            if not h["npi_all"]:
                w.writerow([h["ccn"], h["name"], "", "", "no NPI found in CMS Hospital Enrollments, the hospital's own price file or NPPES at its address"])
            for n in h["npi_all"]:
                w.writerow([h["ccn"], h["name"], n, "yes" if n in h["npi"] else "no", "; ".join(h["npi_how"][n])])
    print(f"wrote /hospitals/ and {len(hosp)} hospital profiles ({sum(1 for h in hosp.values() if h['src'])} with a Price Finder file)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
