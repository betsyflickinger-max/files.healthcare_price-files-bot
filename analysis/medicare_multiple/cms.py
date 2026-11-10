"""Medicare benchmark tables for one state, built from CMS's own public files (sources.py). No storage keys needed.

  python analysis/medicare_multiple/cms.py fetch CACHE            download every file in sources.py once (+ SHA-256)
  python analysis/medicare_multiple/cms.py build CACHE OUT --state TX          (or TX,OK or ALL)

OUT gets small CSVs (each row says which CMS file and year it came from, in sources.json):
  rbcs.csv      code -> RBCS category, subcategory, family (the newest assignment per code)
  pfs.csv       code, mod ('' | 26 | TC), locality, nonfacility, facility, status      Physician Fee Schedule by locality
                (locality key everywhere = Medicare carrier + locality, e.g. 04412-11 = Dallas)
                = (work RVU x work GPCI + PE RVU x PE GPCI + MP RVU x MP GPCI) x conversion factor, rounded to cents (CMS's formula)
  anes.csv      locality, cf                       anesthesia conversion factor (per unit)
  zip.csv       zip5, state, locality, rural       ZIP -> locality ('' urban, R rural, B super-rural)
  opps.csv      code, si, apc, rate, wage_adj      national OPPS rate; wage_adj = CMS wage-adjusts this status indicator
  asc.csv       code, pi, rate, wage_adj           national ASC rate
  clfs.csv      code, rate                         lab fee schedule (no locality)
  asp.csv       code, rate, unit                   Part B drug payment limit (ASP + 6%) per billing unit
  dme.csv       code, mod, state, nonrural, rural  DMEPOS fee schedule by state
  amb.csv       code, locality, urban, rural, super_rural   ambulance fee schedule, this state's localities
  drg.csv       drg, weight, title                 MS-DRG weights (FY2027, 10% cap applied)
  ipps.csv      ccn, name, wage_index, op_per_weight, cap_per_weight, ucp_per_claim, provider_type
                Medicare's amount for a stay at that hospital = weight x (op_per_weight + cap_per_weight) + ucp_per_claim
                (see ipps_rows for the formula; outlier payments are left out)
  wi2026.csv    ccn, wage_index                    FY2026 wage index (used by CY2026 OPPS) for hospital-file outpatient rows
  hosp_zip.csv  ccn, zip5, state                   hospital ZIP (Hospital General Information) for hospital-file doctor fees
  volumes.csv   state, kind, code, place, volume   Medicare use by state (2024): professional (by place O/F),
                                                   outpatient (HCPCS), inpatient (MS-DRG discharges), dme
  sources.json  every file: what, year, url, sha256, downloaded
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sources import CMS  # noqa: E402

STATE_NAMES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
               'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia',
               'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
               'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts',
               'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
               'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico',
               'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
               'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
               'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
               'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'}

# OPPS status indicators whose payment CMS adjusts by the hospital's wage index (60% labor share). Drugs and biologicals
# (G, K), pass-through devices (H), and items paid on other fee schedules (A labs, F, L) are not wage-adjusted.
OPPS_WAGE_SI = {"J1", "J2", "P", "Q1", "Q2", "Q3", "R", "S", "T", "U", "V", "X"}
OPPS_LABOR = 0.60
# ASC payment indicators that are wage-adjusted (50% labor share). J8 (device-intensive) is adjusted on its non-device
# portion only; we adjust the whole rate and say so in the report (the device share isn't in Addendum AA).
ASC_WAGE_PI = {"A2", "G2", "J8", "P2", "P3", "R2", "Z2", "Z3"}
ASC_LABOR = 0.50
PFS_PAYABLE = {"A", "R", "T"}   # active, restricted, paid only if no other service that day (CMS status codes)


def num(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ download

def fetch(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    man = {}
    for k, s in CMS.items():
        p = cache / (k + (".csv" if s["url"].lower().endswith(".csv") else ".zip"))
        if not p.exists():
            req = urllib.request.Request(s["url"], headers={"User-Agent": "files.healthcare research bot"})
            with urllib.request.urlopen(req, timeout=600) as r, open(str(p) + ".part", "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(str(p) + ".part", p)
        man[k] = dict(s, file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest(), downloaded=date.today().isoformat())
        print(f"  {k}: {p.stat().st_size / 1e6:,.1f} MB", flush=True)
    (cache / "sources.json").write_text(json.dumps(man, indent=1))
    return man


def _zip_member(path, pattern):
    """Text of the first member of zip `path` (zips inside zips too) whose name matches regex `pattern`."""
    def walk(zf):
        for n in zf.namelist():
            if n.startswith("__MACOSX"):
                continue
            if re.search(pattern, n, re.I):
                return zf.read(n)
            if n.lower().endswith(".zip"):
                hit = walk(zipfile.ZipFile(io.BytesIO(zf.read(n))))
                if hit is not None:
                    return hit
        return None
    b = walk(zipfile.ZipFile(path))
    if b is None:
        raise FileNotFoundError(f"{pattern} not in {path}")
    return b.decode("latin-1")


def _rows(text, first, delim=","):
    """csv rows after the header row whose first non-empty cell equals `first`."""
    L = list(csv.reader(io.StringIO(text), delimiter=delim))
    for i, r in enumerate(L):
        cells = [c.strip() for c in r]
        if cells and first in cells[:2]:
            off = cells.index(first)
            return [c.strip() for c in cells[off:]], [[c.strip() for c in x[off:]] for x in L[i + 1:]]
    raise ValueError(f"header {first!r} not found")


# ------------------------------------------------------------------ parsers (each takes file text, returns rows)

def rbcs_rows(text):
    """newest RBCS assignment per code (RBCS_Latest_Assignment = 1)"""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        c = r["HCPCS_Cd"].strip().upper()
        if r.get("RBCS_Latest_Assignment", "1").strip() == "1" or c not in out:
            out[c] = dict(code=c, rbcs_id=r["RBCS_Id"], cat=r["RBCS_Cat"], cat_desc=r["RBCS_Cat_Desc"],
                          subcat=r["RBCS_Cat_Subcat"], subcat_desc=r["RBCS_Subcat_Desc"], family=r["RBCS_Family_Desc"])
    return list(out.values())


def gpci_rows(text, states):
    """{carrier-locality: (work, pe, mp, name, state)}; carrier + locality is Medicare's unique locality key"""
    h, body = _rows(text, "Medicare Administrative Contractor (MAC)")
    return {f"{r[0].strip()}-{r[2].zfill(2)}": (num(r[4]), num(r[5]), num(r[6]), r[3], r[1])
            for r in body if len(r) > 6 and r[1] in states and num(r[4])}


def pfs_rows(rvu_text, gpci):
    """[(code, mod, locality, nonfacility, facility, status)] for mods '', 26, TC with payable status"""
    h, body = _rows(rvu_text, "HCPCS")
    out = []
    for r in body:
        if len(r) < 26 or r[3] not in PFS_PAYABLE or r[1] not in ("", "26", "TC"):
            continue
        w, pen, nfna, pef, fna, mp, cf = num(r[5]), num(r[6]), r[7], num(r[8]), r[9], num(r[10]), num(r[25])
        if None in (w, pen, pef, mp, cf):
            continue
        for loc, (gw, gp, gm, _, _) in gpci.items():
            nf = None if nfna == "NA" else round((w * gw + pen * gp + mp * gm) * cf, 2)
            fa = None if fna == "NA" else round((w * gw + pef * gp + mp * gm) * cf, 2)
            if (nf or 0) <= 0 and (fa or 0) <= 0:
                continue
            out.append((r[0].upper(), r[1], loc, nf, fa, r[3]))
    return out


def zip_rows(text, states):
    """ZIP5 file (fixed width): state 1-2, zip 3-7, carrier 8-12, locality 13-14, rural 15 -> (zip5, state, locality key, rural)"""
    out = {}
    for line in text.splitlines():
        if line[:2] in states and len(line) >= 15:
            out[line[2:7]] = (line[:2], f"{line[7:12].strip()}-{line[12:14]}", line[14].strip())
    return [(z, st, loc, rur) for z, (st, loc, rur) in sorted(out.items())]


def anes_rows(text, carriers):  # -> {carrier-locality: cf}
    """CMS anesthesia CF csv -> {locality: cf} for this state's Medicare contractors (from the ZIP file); column
    "Non-Qualifying APM National Anes CF" (the same CF the physician fee schedule uses for most clinicians)"""
    out = {}
    rd = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    hi = next(i for i, r in enumerate(rd) if r and r[0].strip() == "Contractor")
    ci = next(i for i, c in enumerate(rd[hi]) if c.strip().lower().startswith("non-qualifying"))
    for r in rd[hi + 1:]:
        if len(r) > ci and r[0].strip() in carriers and num(r[ci]):
            out[f"{r[0].strip()}-{r[1].strip().zfill(2)}"] = num(r[ci])
    return out


def opps_rows(text):
    h, body = _rows(text, "HCPCS Code", delim="\t")
    iS, iA, iR = h.index("SI"), h.index("APC"), h.index("Payment Rate")
    out = []
    for r in body:
        if len(r) > iR and r[0] and num(r[iR]):
            out.append((r[0].upper(), r[iS], r[iA], num(r[iR]), r[iS] in OPPS_WAGE_SI))
    return out


def asc_rows(text):
    h, body = _rows(text, "HCPCS Code")
    iP = next(i for i, c in enumerate(h) if "Payment Indicator" in c)
    iR = next(i for i, c in enumerate(h) if "Payment Rate" in c)
    out = []
    for r in body:
        if len(r) > iR and r[0] and num(r[iR]):
            out.append((r[0].upper(), r[iP], num(r[iR]), r[iP] in ASC_WAGE_PI))
    return out


def clfs_rows(text):
    h, body = _rows(text, "YEAR")
    out = []
    for r in body:
        if len(r) > 5 and r[1] and r[2] == "" and num(r[5]):
            out.append((r[1].upper(), num(r[5])))
    return out


def asp_rows(text):
    h, body = _rows(text, "HCPCS Code")
    iL, iD = h.index("Payment Limit"), h.index("HCPCS Code Dosage")
    return [(r[0].upper(), num(r[iL]), r[iD]) for r in body if len(r) > iL and r[0] and num(r[iL])]


def dme_rows(text, states):
    """(code, mods, state, nonrural, rural) for every state column in the file"""
    h, body = _rows(text, "HCPCS")
    out = {}
    for st in sorted(states):
        if f"{st} (NR)" not in h:
            continue
        nr, ru = h.index(f"{st} (NR)"), h.index(f"{st} (R)")
        for r in body:
            if len(r) > ru and r[0]:
                mods = "+".join(m for m in (r[1], r[2]) if m)
                a, b = num(r[nr]), num(r[ru])
                if (a or 0) > 0 or (b or 0) > 0:
                    out[(r[0].upper(), mods, st)] = (a if a and a > 0 else None, b if b and b > 0 else None)
    return [(c, m, st, a, b) for (c, m, st), (a, b) in sorted(out.items())]


def amb_rows(text, carriers):
    """AFS PUF (tab): carrier, locality, HCPCS, RVU, GPCI, base, urban, rural, rural lowest quartile (super-rural)"""
    out = []
    for line in text.splitlines()[1:]:
        r = [c.strip().strip('"') for c in line.split("\t")]
        if len(r) >= 9 and r[0] in carriers:
            out.append((r[2].upper(), f"{r[0]}-{r[1].zfill(2)}", num(r[6]), num(r[7]), num(r[8]) or num(r[7])))
    return out


def drg_rows(text):
    h, body = _rows(text, "MS-DRG", delim="\t")
    iW = next(i for i, c in enumerate(h) if "10% Cap" in c or "Cap Applied" in c)
    iT = next(i for i, c in enumerate(h) if "Title" in c)
    return [(r[0].lstrip("0") or "0", num(r[iW]), r[iT]) for r in body if len(r) > iW and r[0].isdigit() and num(r[iW])]


def ipps_rates(text):
    """(labor>1, nonlabor>1, labor<=1, nonlabor<=1, capital) for hospitals that submit quality data and are meaningful EHR
    users (the full update; Tables 1A, 1B, 1D)."""
    vals = [num(x) for x in re.findall(r'"?\$([\d,]+\.\d\d) ?"?', text)]
    # order in the file: 1A (4 pairs), 1B (4 pairs), 1C (2 pairs), 1D capital, 1E LTCH...
    a_l, a_n, b_l, b_n = vals[0], vals[1], vals[8], vals[9]
    cap = num(re.search(r"TABLE 1D.*?National\s+\$([\d,]+\.\d\d)", text, re.S).group(1))
    return a_l, a_n, b_l, b_n, cap


def ipps_rows(impact_text, rates):
    """Each IPPS hospital's Medicare amount per unit of DRG weight (no outliers):
         operating = (labor x wage index x COLA + nonlabor) x (VBP x readmission + IME + DSH)   [IME/DSH on the base]
         capital   = capital rate x GAF x capital COLA x (1 + capital IME + capital DSH)
         + the uncompensated-care amount per claim (a flat amount per stay, not per weight).
       Labor share 66% when the wage index is above 1, else 62% (Tables 1A/1B). Sole community / Medicare-dependent
       hospitals can be paid on their own hospital-specific rate instead; we always use the federal rate and say so."""
    a_l, a_n, b_l, b_n, cap = rates
    L = impact_text.splitlines()
    hi = next(i for i, x in enumerate(L) if x.startswith("Provider Number"))
    h = [c.strip() for c in L[hi].split("\t")]
    ix = lambda *names: next(i for i, c in enumerate(h) if any(c.startswith(n) for n in names))
    iW, iC, iTO, iTC, iDO, iDC = ix("FY 2027 Wage Index", "FY 2026 Wage Index"), ix("Cost of Living"), ix("TCHOP"), ix("TCHCP"), ix("DSHOPP"), ix("DSHCPP")
    iU, iG, iCC, iV, iR, iT = ix("UCP Per Claim", "UCP and IHS"), ix("GAF"), ix("Capital Cost of Living"), ix("Proxy Value"), ix("Proxy Readmission"), ix("Provider Type")
    out = []
    for line in L[hi + 1:]:
        r = [c.strip() for c in line.split("\t")]
        if len(r) <= iT or not re.fullmatch(r"\d{2}[0-9A-Z]\d{3}", r[0] or ""):
            continue
        wi = num(r[iW])
        if not wi:
            continue
        lab, non = (a_l, a_n) if wi > 1 else (b_l, b_n)
        cola, ccola = num(r[iC]) or 1.0, num(r[iCC]) or 1.0
        base = lab * wi * cola + non
        op = base * ((num(r[iV]) or 1.0) * (num(r[iR]) or 1.0) + (num(r[iTO]) or 0) + (num(r[iDO]) or 0))
        cp = cap * (num(r[iG]) or 1.0) * ccola * (1 + (num(r[iTC]) or 0) + (num(r[iDC]) or 0))
        out.append((r[0], r[1], wi, round(op, 4), round(cp, 4), num(r[iU]) or 0.0, r[iT]))
    return out


def wi_rows(impact_text):
    L = impact_text.splitlines()
    hi = next(i for i, x in enumerate(L) if x.startswith("Provider Number"))
    h = [c.strip() for c in L[hi].split("\t")]
    iW = next(i for i, c in enumerate(h) if re.match(r"FY 20\d\d Wage Index", c))
    return [(r[0], num(r[iW])) for r in (x.split("\t") for x in L[hi + 1:]) if len(r) > iW and num(r[iW])]


def hgi_rows(text, states):
    return [(r["Facility ID"], r["ZIP Code"][:5], r["State"]) for r in csv.DictReader(io.StringIO(text)) if r["State"] in states]


def volume_rows(phy, out_, inp, dme, states):
    """[(state, kind, code, place, volume, source)] Medicare use by state (2024). Office (O) and facility (F) kept apart
    for doctor fees. CMS leaves out cells under 11; those are absent here too, never filled in."""
    by_name = {STATE_NAMES[s]: s for s in states}
    st = lambda d: by_name.get(d) or (d if d in states else None)
    agg = {}

    def add(s_, kind, code, place, v, src):
        if s_ and v:
            k = (s_, kind, code, place, src)
            agg[k] = agg.get(k, 0) + v
    for r in csv.DictReader(io.StringIO(phy)):
        if r["Rndrng_Prvdr_Geo_Lvl"] == "State":
            add(st(r["Rndrng_Prvdr_Geo_Desc"]), "professional", r["HCPCS_Cd"].strip().upper(), r["Place_Of_Srvc"], num(r["Tot_Srvcs"]), "vol_physician")
    for r in csv.DictReader(io.StringIO(out_)):   # a HCPCS appears under each APC it was paid in: added up per code
        if r["Rndrng_Prvdr_Geo_Lvl"] == "State" and r["HCPCS_Cd"]:
            add(st(r["Rndrng_Prvdr_Geo_Desc"]), "outpatient", r["HCPCS_Cd"].strip().upper(), "", num(r["CAPC_Srvcs"]), "vol_outpatient")
    for r in csv.DictReader(io.StringIO(inp)):
        if r["Rndrng_Prvdr_Geo_Lvl"] == "State":
            add(st(r["Rndrng_Prvdr_Geo_Desc"]), "inpatient", r["DRG_Cd"].lstrip("0"), "", num(r["Tot_Dschrgs"]), "vol_inpatient")
    for r in csv.DictReader(io.StringIO(dme)):
        if r["Rfrg_Prvdr_Geo_Lvl"] == "State" and r["HCPCS_Cd"]:
            add(st(r["Rfrg_Prvdr_Geo_Desc"]), "dme", r["HCPCS_Cd"].strip().upper(), r.get("Suplr_Rentl_Ind", ""), num(r["Tot_Suplr_Srvcs"]), "vol_dme")
    return [(s_, k, c, p, v, src) for (s_, k, c, p, src), v in sorted(agg.items())]


# ------------------------------------------------------------------ build

def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def build(cache, out, states=("TX",)):
    """Benchmark tables for one or more states (two-letter codes, or ALL). Locality key = carrier-locality."""
    cache, out = Path(cache), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    states = set(STATE_NAMES) if "ALL" in states else set(states)
    z = lambda k, pat: _zip_member(cache / f"{k}.zip", pat)
    t = lambda k: (cache / f"{k}.csv").read_text(encoding="latin-1")
    n = {}
    n["rbcs"] = write(out / "rbcs.csv", ["code", "rbcs_id", "cat", "cat_desc", "subcat", "subcat_desc", "family"],
                      [list(r.values()) for r in rbcs_rows(t("rbcs"))])
    gp = gpci_rows(z("pfs", r"GPCI2026\.csv$"), states)
    n["pfs"] = write(out / "pfs.csv", ["code", "mod", "locality", "nonfacility", "facility", "status"],
                     pfs_rows(z("pfs", r"PPRRVU2026_Oct_nonQPP\.csv$"), gp))
    write(out / "localities.csv", ["locality", "name", "state", "gpci_work", "gpci_pe", "gpci_mp"],
          [(k, v[3], v[4], v[0], v[1], v[2]) for k, v in sorted(gp.items())])
    zr = zip_rows(z("zip_locality", r"ZIP5_.*\.txt$"), states)
    n["zip"] = write(out / "zip.csv", ["zip5", "state", "locality", "rural"], zr)
    carriers = {loc.split("-")[0] for _, _, loc, _ in zr}
    n["anes"] = write(out / "anes.csv", ["locality", "cf"], sorted(anes_rows(z("anes", r"_508\.csv$"), carriers).items()))
    n["opps"] = write(out / "opps.csv", ["code", "si", "apc", "rate", "wage_adj"], opps_rows(z("opps", r"Addendum_B.*\.txt$")))
    n["asc"] = write(out / "asc.csv", ["code", "pi", "rate", "wage_adj"], asc_rows(z("asc", r"ASC-AA\.csv$")))
    n["clfs"] = write(out / "clfs.csv", ["code", "rate"], clfs_rows(z("clfs", r"PUF_CLFS.*\.csv$")))
    n["asp"] = write(out / "asp.csv", ["code", "rate", "unit"], asp_rows(z("asp", r"Payment Limit File.*\.csv$")))
    n["dme"] = write(out / "dme.csv", ["code", "mod", "state", "nonrural", "rural"], dme_rows(z("dme", r"DMEPOS_[A-Z]+\.csv$"), states))
    n["amb"] = write(out / "amb.csv", ["code", "locality", "urban", "rural", "super_rural"],
                     amb_rows(z("ambulance", r"AFS\d{4}_PUF.*\.txt$"), carriers))
    n["drg"] = write(out / "drg.csv", ["drg", "weight", "title"], drg_rows(z("ipps_weights", r"CN Table 5\.txt$")))
    rates = ipps_rates(z("ipps_rates", r"CN Tables 1A - 1E\.txt$"))
    n["ipps"] = write(out / "ipps.csv", ["ccn", "name", "wage_index", "op_per_weight", "cap_per_weight", "ucp_per_claim", "provider_type"],
                      ipps_rows(z("ipps_impact", r"Impact File - Correction Notice\.txt$"), rates))
    n["wi2026"] = write(out / "wi2026.csv", ["ccn", "wage_index"], wi_rows(z("ipps_impact_2026", r"Impact File\.txt$")))
    n["hosp_zip"] = write(out / "hosp_zip.csv", ["ccn", "zip5", "state"], hgi_rows(t("hgi"), states))
    n["volumes"] = write(out / "volumes.csv", ["state", "kind", "code", "place", "volume", "source"],
                         volume_rows(t("vol_physician"), t("vol_outpatient"), t("vol_inpatient"), t("vol_dme"), states))
    man = json.loads((cache / "sources.json").read_text()) if (cache / "sources.json").exists() else {k: dict(v) for k, v in CMS.items()}
    man["_built"] = dict(states=sorted(states), on=date.today().isoformat(), rows=n,
                         ipps_rates=dict(zip(["labor_wi_over_1", "nonlabor_wi_over_1", "labor_wi_1_or_less", "nonlabor_wi_1_or_less", "capital"], rates)))
    (out / "sources.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(n), flush=True)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "build"])
    ap.add_argument("cache")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--state", default="TX", help="two-letter code(s), comma-separated, or ALL")
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.cache)
    else:
        build(a.cache, a.out, [x.strip().upper() for x in a.state.split(",")])


if __name__ == "__main__":
    main()
