"""Labor share of hospital operating costs, from Medicare cost reports (Nov 7, 2026).

Every hospital paid by Medicare files a yearly cost report (form CMS-2552-10). CMS publishes them all in HCRIS:
  https://downloads.cms.gov/FILES/HCRIS/HOSP10FY<year>.ZIP   (about 135 MB; one zip per federal fiscal year in which
  the hospital's reporting period began). Three files inside: _rpt (one row per report: CCN, period, status),
  _nmrc (every number: report, worksheet, line, column, value), _alpha (every text field).

For each Dallas-Fort Worth hospital (matched by CCN; DFW = the 11 metro counties in site/dfw_metro.json, using the
county the hospital writes on its own report, Worksheet S-2 Part I line 2), per report:

  salaries         Worksheet A, line 200 (total), column 1 (salaries)          A000000 / 20000 / 00100
  benefits         Worksheet S-3 Part V, line 1 (total), column 2 (benefits)   S300005 / 00100 / 00200
  contract labor   Worksheet S-3 Part V, line 1 (total), column 1              S300005 / 00100 / 00100
                   (direct patient care contract labor, per the Part V instructions)
  operating costs  Worksheet G-3, line 4 (total operating expenses), column 1  G300000 / 00400 / 00100
  labor share      (salaries + benefits + contract labor) / operating costs, from the same report

Worksheet, line and column come from CMS's instructions for form 2552-10 (Provider Reimbursement Manual Part 2,
chapter 40, sections 4005.5, 4013 and 4040.3; NBER copy https://m.nber.org/hcris/2552-10/manual/pr2_40.pdf). Part V is
completed by every hospital type; Part II (wage index) is not, so it isn't used. Checked on Baylor University Medical
Center (CCN 450021, FY2024 file): Worksheet A salaries equal S-3 Part II line 1, Part V contract labor equals Part II
line 11, and G-3 line 4 equals Worksheet A column 3 line 200, as the instructions say they must.

Rules: every number is copied from the report; the share is one division on one report. A blank input leaves the share
blank (never filled in), with one stated exception: HCRIS stores only the cells a hospital filled in, so when a report
has Part V line 1 benefits but no contract-labor cell, contract labor is shown as $0 and the row says so
(contract_labor_note). Some hospitals (for example Children's Medical Center Dallas, FY2024 file) filed no Part V at
all; their labor share stays blank, and salaries_share (salaries / operating costs, salaries only) is shown instead,
labeled as salaries only. A hospital can file more than one report for a period (amended, reopened); every report is
listed with CMS's status code and processing date, and "latest" marks the most recently processed one per period.

Output: reports/labor-share/dfw.csv and dfw.md.
Run: python costreports/labor_share.py [--years 2022,2023,2024,2025] [--work /tmp/hcris]
"""
import argparse
import csv
import json
import zipfile
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "labor-share"
URL = "https://downloads.cms.gov/FILES/HCRIS/HOSP10FY{y}.ZIP"
CELLS = {"salaries": ("A000000", "20000", "00100"), "benefits": ("S300005", "00100", "00200"),
         "contract_labor": ("S300005", "00100", "00100"), "operating_costs": ("G300000", "00400", "00100")}
STATUS = {"1": "as submitted", "2": "settled without audit", "3": "settled with audit", "4": "reopened", "5": "amended"}
FIELDS = ["ccn", "hospital", "city", "county", "hospital_type", "fy_file", "period_start", "period_end", "report_status",
          "processed", "latest_for_period", "salaries", "benefits", "contract_labor", "operating_costs", "labor_share",
          "salaries_share", "contract_labor_note", "rpt_rec_num", "source_url"]


def kind(ccn):
    """Hospital type from the CCN's number range (CMS State Operations Manual numbering)."""
    try:
        n = int(ccn[2:6])
    except ValueError:
        return "other"
    for lo, hi, t in ((1, 879, "short-term acute"), (1300, 1399, "critical access"), (2000, 2299, "long-term care"),
                      (3025, 3099, "rehabilitation"), (3300, 3399, "children's"), (4000, 4499, "psychiatric")):
        if lo <= n <= hi:
            return t
    return f"other (CCN {ccn[2:4]}xx range)"


def dfw_counties():
    return {c.upper() for c in json.load(open(ROOT / "site" / "dfw_metro.json"))["msa_counties"]}


def zip_county():
    return {r["zip5"]: r["county"].upper() for r in csv.DictReader(open(ROOT / "data" / "medicare_areas_zip.csv")) if r["state"] == "TX"}


def fetch(year, work):
    p = Path(work) / f"HOSP10FY{year}.ZIP"
    if not p.exists():
        with requests.get(URL.format(y=year), stream=True, timeout=900) as r:
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with open(p, "wb") as f:
                for b in r.iter_content(8 << 20):
                    f.write(b)
    return p


def read_year(con, year, zpath, work, counties, zips):
    z = zipfile.ZipFile(zpath)
    names = {n.lower().rsplit("_", 1)[-1].split(".")[0]: n for n in z.namelist()}
    d = Path(work) / str(year)
    for k in ("rpt", "nmrc", "alpha"):
        if not (d / names[k]).exists():
            z.extract(names[k], d)
    f = {k: str(d / names[k]) for k in ("rpt", "nmrc", "alpha")}
    con.execute(f"""create or replace table rpt as select column00 rpt, column02 ccn, column04 status, column05 fy_bgn,
                    column06 fy_end, column07 proc_dt from read_csv('{f['rpt']}', header=false, all_varchar=true)
                    where left(column02, 2) = '45'""")      # Texas CCNs start with 45, 67 (and 74 for some types)
    con.execute(f"""insert into rpt select column00, column02, column04, column05, column06, column07
                    from read_csv('{f['rpt']}', header=false, all_varchar=true) where left(column02, 2) in ('67', '74')""")
    con.execute(f"""create or replace table al as select column0 rpt, column2 line, column3 col, column4 val
                    from read_csv('{f['alpha']}', header=false, all_varchar=true, columns={{'column0':'VARCHAR','column1':'VARCHAR','column2':'VARCHAR','column3':'VARCHAR','column4':'VARCHAR'}})
                    where column1 = 'S200001' and column2 in ('00200', '00300') and column0 in (select rpt from rpt)""")
    con.execute(f"""create or replace table nm as select column0 rpt, column1 w, column2 l, column3 c, column4 v
                    from read_csv('{f['nmrc']}', header=false, columns={{'column0':'VARCHAR','column1':'VARCHAR','column2':'VARCHAR','column3':'VARCHAR','column4':'DOUBLE'}})
                    where column0 in (select rpt from rpt) and column1 in ('A000000', 'S300005', 'G300000')""")
    text = {}
    for rpt, line, col, val in con.execute("select * from al").fetchall():
        text[(rpt, line, col)] = (val or "").strip()
    nums = {}
    for rpt, w, l, c, v in con.execute("select * from nm").fetchall():
        nums[(rpt, w, l, c)] = v
    out = []
    for rpt, ccn, st, b, e, p in con.execute("select * from rpt").fetchall():
        state = text.get((rpt, "00200", "00200"), "").upper()
        county = text.get((rpt, "00200", "00400"), "").upper().replace(" COUNTY", "").strip()
        zp = text.get((rpt, "00200", "00300"), "")[:5]
        if state != "TX":
            continue
        if county not in counties:
            county = zips.get(zp, county)
            if county not in counties:
                continue
        r = dict(ccn=ccn, hospital=text.get((rpt, "00300", "00100"), ""), city=text.get((rpt, "00200", "00100"), "").title(),
                 county=county.title(), hospital_type=kind(ccn), fy_file=year, period_start=b, period_end=e,
                 report_status=STATUS.get(st, st), processed=p, rpt_rec_num=rpt, source_url=URL.format(y=year))
        for k, cell in CELLS.items():
            v = nums.get((rpt,) + cell)
            r[k] = int(round(v)) if v is not None else ""
        r["contract_labor_note"] = ""
        if r["benefits"] != "" and r["contract_labor"] == "":
            r["contract_labor"] = 0
            r["contract_labor_note"] = "Part V filed; no contract-labor amount entered, shown as $0"
        r["salaries_share"] = (f"{100 * r['salaries'] / r['operating_costs']:.1f}%"
                               if r["salaries"] != "" and r["operating_costs"] not in ("", 0) else "")
        lab = [r["salaries"], r["benefits"], r["contract_labor"]]
        r["labor_share"] = (f"{100 * sum(lab) / r['operating_costs']:.1f}%"
                            if all(x != "" for x in lab) and r["operating_costs"] not in ("", 0) else "")
        out.append(r)
    return out


def mark_latest(rows):
    def d(s):
        m, dd, y = (s or "01/01/1900").split("/")
        return f"{y}-{m}-{dd}"
    best = {}
    for r in rows:
        k = (r["ccn"], r["period_start"], r["period_end"])
        if k not in best or d(r["processed"]) > d(best[k]["processed"]):
            best[k] = r
    for r in rows:
        r["latest_for_period"] = "yes" if best[(r["ccn"], r["period_start"], r["period_end"])] is r else ""


def write(rows, years, missing):
    OUT.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["hospital"], r["period_start"], r["processed"]))
    with open(OUT / "dfw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    m = lambda v: f"${v / 1e6:,.1f}M" if isinstance(v, int) else "—"
    L = ["# Labor share of hospital operating costs: Dallas-Fort Worth", "",
         f"Built {date.today().isoformat()} by `costreports/labor_share.py` from CMS Medicare cost reports (HCRIS, form 2552-10), "
         f"files for federal fiscal years {', '.join(y for y in years if y not in missing)}. "
         "Labor share = (salaries + employee benefits + direct patient care contract labor) ÷ total operating expenses, "
         "all from the same report. Every number is copied from the report; a blank stays blank.", "",
         "Where each number comes from: salaries, Worksheet A line 200 column 1; benefits and contract labor, Worksheet S-3 "
         "Part V line 1 columns 2 and 1; total operating expenses, Worksheet G-3 line 4. Contract labor here is direct "
         "patient care only (management contracts are not in Part V).", "",
         "**What this is not.** A cost report is the hospital's own accounting for Medicare. It shows how its costs split, not "
         "what any patient or insurer paid. Hospital systems can book shared costs (like a central office) in different ways.", ""]
    if missing:
        L += [f"No CMS file yet for: {', '.join(sorted(missing))}.", ""]
    L += ["The newest fiscal-year file keeps filling in as hospitals file (reports are due five months after a period ends).", ""]
    L += ["Latest report for each period shown; every report (including earlier versions) is in `reports/labor-share/dfw.csv`.", "",
          "\"Salaries only\" is shown for hospitals whose report has no Part V (benefits and contract labor); it is not a labor share.", "",
          "| Hospital | CCN | Type | Period | Salaries | Benefits | Contract labor | Operating costs | Labor share | Salaries only | Report status |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["latest_for_period"]:
            L.append(f"| {r['hospital']} | {r['ccn']} | {r['hospital_type']} | {r['period_start']}–{r['period_end']} | {m(r['salaries'])} | "
                     f"{m(r['benefits'])} | {m(r['contract_labor'])}{'*' if r['contract_labor_note'] else ''} | {m(r['operating_costs'])} | "
                     f"{r['labor_share'] or '—'} | {r['salaries_share'] if not r['labor_share'] else ''} | {r['report_status']} |")
    L += ["", "\\* No contract-labor amount entered on a filed Part V; shown as $0 (cost report files store only filled-in cells)."]
    (OUT / "dfw.md").write_text("\n".join(L) + "\n")


def main():
    import duckdb
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2022,2023,2024,2025")
    ap.add_argument("--work", default="/tmp/hcris")
    a = ap.parse_args()
    Path(a.work).mkdir(parents=True, exist_ok=True)
    years = [y.strip() for y in a.years.split(",") if y.strip()]
    con = duckdb.connect()
    counties, zips = dfw_counties(), zip_county()
    rows, missing = [], set()
    for y in years:
        p = fetch(y, a.work)
        if not p:
            missing.add(y)
            continue
        got = read_year(con, y, p, a.work, counties, zips)
        print(f"FY{y}: {len(got)} DFW reports", flush=True)
        rows += got
    mark_latest(rows)
    write(rows, years, missing)
    print(f"-> reports/labor-share/dfw.md and .csv ({len(rows)} reports)")


if __name__ == "__main__":
    main()
