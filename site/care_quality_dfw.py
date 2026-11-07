"""CMS quality measures for Dallas-Fort Worth hospitals and surgery centers, one row per measure (Nov 7, 2026).

Extends site/care_compare.py (card #3), which keeps a few headline ratings per provider for the Price Finders. This
keeps every measure behind them for DFW facilities matched by CCN, each with its name, value, CMS's national figure,
data period and source link, from CMS's Provider Data Catalog (public CSVs, newest release, found by title):

  hospitals        Hospital General Information: overall star rating (or "not rated" with CMS's own footnote), and for
                   each of the five measure groups behind it (mortality, safety, readmission, patient experience,
                   timely and effective care) how many measures CMS uses, how many the hospital reported, and how many
                   were better / no different / worse than the national rate (CMS's own comparison).
                   Patient survey (HCAHPS) - Hospital and - National: every survey measure with a percent or a star,
                   with the national percent for the same measure and the survey period.
  surgery centers  Ambulatory Surgical Center Quality Measures (ASCQR) - Facility and - National: every ASC measure
                   rate, with CMS's national average and median (or national rate and CMS's own performance category).

Flags (labels only):
  not rated                 CMS publishes no value; the CMS footnote says why. Never shown as blank or zero.
  fewer measures reported   a hospital reported fewer than half of the measures CMS uses for the star rating across the
                            five groups, or a surgery center has a value for fewer than half of the ASCQR measures in
                            the file. A star or rate based on few measures says less.
No composite score, no ranking, and no sorting by price and quality together. Leapfrog data is not used.

DFW = the 11 counties of the Dallas-Fort Worth-Arlington metro (site/dfw_metro.json): hospitals by the county CMS lists,
surgery centers by ZIP code -> county (data/medicare_areas_zip.csv). Matched by CCN only.

Output: reports/care-compare/dfw-measures.csv (one row per facility x measure) and dfw-measures.md (summary).
Public government files only: no storage keys, nothing deployed.
Run: python site/care_quality_dfw.py [--work /tmp/cq]
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "care-compare"
PDC = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"
PAGE = "https://data.cms.gov/provider-data/dataset/{}"
DATASETS = {
    "gen": r"^Hospital General Information$",
    "hc": r"^Patient survey \(HCAHPS\) - Hospital$",
    "hcn": r"^Patient survey \(HCAHPS\) - National$",
    "asc": r"^Ambulatory Surgical Center Quality Measures - Facility$",
    "ascn": r"^Ambulatory Surgical Center Quality Measures - National$",
    "fn": r"^Footnote Crosswalk$",
}
GROUPS = {"MORT": "Mortality", "Safety": "Safety of care", "READM": "Readmission", "Pt Exp": "Patient experience",
          "TE": "Timely and effective care"}
ASC_NAMES = {
    "ASC-1": "Patient burn", "ASC-2": "Patient fall", "ASC-3": "Wrong site, side, patient, procedure or implant",
    "ASC-4": "All-cause hospital transfer or admission", "ASC-9": "Appropriate follow-up interval after colonoscopy",
    "ASC-11": "Improvement in visual function within 90 days after cataract surgery",
    "ASC-12": "Hospital visits within 7 days after outpatient colonoscopy",
    "ASC-13": "Normothermia (normal body temperature) outcome", "ASC-14": "Unplanned anterior vitrectomy",
    "ASC-17": "Hospital visits after orthopedic surgery", "ASC-18": "Hospital visits after urology surgery",
    "ASC-19": "Hospital visits after general surgery",
}
FEWER = 0.5
FIELDS = ["kind", "ccn", "facility", "city", "county", "measure_id", "measure_name", "value", "unit", "national_value",
          "cms_comparison", "data_period", "not_rated_reason", "fewer_measures_reported", "source_title", "source_link",
          "cms_release", "checked_on"]


def catalog():
    items = requests.get(PDC, timeout=300).json()
    out = {}
    for k, pat in DATASETS.items():
        m = [x for x in items if re.search(pat, x.get("title", ""), re.I)]
        if not m:
            raise SystemExit(f"CMS catalog: no dataset titled like {pat}")
        x = max(m, key=lambda x: x.get("modified", ""))
        url = next(d["downloadURL"] for d in x.get("distribution", []) if str(d.get("downloadURL", "")).lower().endswith(".csv"))
        out[k] = dict(id=x["identifier"], title=x["title"], modified=x.get("modified", ""), url=url, page=PAGE.format(x["identifier"]))
    return out


def fetch(meta, work):
    p = Path(work) / meta["url"].rsplit("/", 1)[-1]
    if not p.exists():
        with requests.get(meta["url"], stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for b in r.iter_content(8 << 20):
                    f.write(b)
    return p


def rows(p):
    return csv.DictReader(open(p, encoding="utf-8-sig", errors="replace", newline=""))


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def dfw():
    counties = {c.upper() for c in json.load(open(ROOT / "site" / "dfw_metro.json"))["msa_counties"]}
    zips = {r["zip5"]: r["county"].upper() for r in csv.DictReader(open(ROOT / "data" / "medicare_areas_zip.csv")) if r["state"] == "TX"}
    return counties, zips


def footnotes(p):
    out = {}
    for r in rows(p):
        k = next((v for c, v in r.items() if c and c.lower().startswith("footnote") and "text" not in c.lower()), "")
        t = next((v for c, v in r.items() if c and "text" in c.lower()), "")
        if k:
            out[str(k).strip()] = (t or "").strip()
    return out


def fn_text(fn, codes):
    parts = [c.strip() for c in re.split(r"[,;]", codes or "") if c.strip()]
    return "; ".join(f"CMS footnote {c}: {fn.get(c, 'see CMS footnote list')}" for c in parts)


def hospitals(P, cat, fn, counties, today):
    src = lambda k: dict(source_title=cat[k]["title"], source_link=cat[k]["page"], cms_release=cat[k]["modified"], checked_on=today)
    out, facs = [], {}
    stars = defaultdict(int)
    gen = list(rows(P["gen"]))
    for r in gen:
        if (r.get("Hospital overall rating") or "").isdigit():
            stars[r["Hospital overall rating"]] += 1
    rated = sum(stars.values())
    nat_star = "national: " + ", ".join(f"{s} star{'s' if s != '1' else ''} {100 * stars[s] / rated:.0f}%" for s in "12345") + f" of {rated:,} rated hospitals"
    for r in gen:
        if r.get("State") != "TX" or (r.get("County/Parish") or "").upper() not in counties:
            continue
        ccn = r["Facility ID"]
        base = dict(kind="hospital", ccn=ccn, facility=r["Facility Name"], city=r["City/Town"].title(), county=r["County/Parish"].title())
        used = reported = 0
        grp_rows = []
        for g, name in GROUPS.items():
            n_used, n_rep = num(r.get(f"{g} Group Measure Count")), num(r.get(f"Count of Facility {g} Measures"))
            used += n_used or 0
            reported += n_rep or 0
            cmp_ = ""
            if f"Count of {g} Measures Better" in r:
                cmp_ = (f"{r.get(f'Count of {g} Measures Better') or 0} better, {r.get(f'Count of {g} Measures No Different') or 0} no different, "
                        f"{r.get(f'Count of {g} Measures Worse') or 0} worse than the national rate")
            grp_rows.append(dict(base, measure_id=f"group:{g}", measure_name=f"{name}: measures reported (of those CMS uses)",
                                 value="" if n_rep is None else int(n_rep), unit="measures",
                                 national_value="" if n_used is None else f"CMS uses {int(n_used)}", cms_comparison=cmp_,
                                 data_period="as used for the overall star rating in this release",
                                 not_rated_reason=fn_text(fn, r.get(f"{g} Group Footnote")) if n_rep is None else "", **src("gen")))
        fewer = "yes" if used and reported / used < FEWER else ""
        star = r.get("Hospital overall rating") or ""
        out.append(dict(base, measure_id="overall_star", measure_name="Hospital overall star rating (1 to 5)",
                        value=star if star.isdigit() else "", unit="stars", national_value=nat_star, cms_comparison="",
                        data_period="as published in this release", fewer_measures_reported=fewer,
                        not_rated_reason="" if star.isdigit() else ("not rated. " + (fn_text(fn, r.get("Hospital overall rating footnote")) or "CMS gives no reason")),
                        **src("gen")))
        for g in grp_rows:
            g["fewer_measures_reported"] = fewer
        out += grp_rows
        facs[ccn] = base
    # HCAHPS: every measure with a percent or a star, with the national percent for the same measure
    nat = {r["HCAHPS Measure ID"]: (r.get("HCAHPS Answer Percent") or "", r.get("Start Date", ""), r.get("End Date", "")) for r in rows(P["hcn"])}
    for r in rows(P["hc"]):
        ccn = r["Facility ID"]
        if ccn not in facs:
            continue
        mid = r["HCAHPS Measure ID"]
        star, pct = r.get("Patient Survey Star Rating") or "", r.get("HCAHPS Answer Percent") or ""
        if star.isdigit():
            val, unit, fnc = star, "stars", r.get("Patient Survey Star Rating Footnote")
        elif pct not in ("", "Not Applicable"):
            val, unit, fnc = (pct if pct.replace(".", "").isdigit() else ""), "% of patients", r.get("HCAHPS Answer Percent Footnote")
        else:
            continue
        nv = nat.get(mid, ("",))[0]
        out.append(dict(facs[ccn], measure_id=mid, measure_name=r.get("HCAHPS Answer Description") or r.get("HCAHPS Question"), value=val, unit=unit,
                        national_value=(f"{nv}%" if unit != "stars" and nv not in ("", "Not Applicable") else ""),
                        cms_comparison="", data_period=f"surveys {r.get('Start Date')} to {r.get('End Date')}; {r.get('Number of Completed Surveys') or '?'} completed",
                        not_rated_reason="" if val else ("not rated. " + (fn_text(fn, fnc) or "CMS gives no reason")), **src("hc")))
    return out


def surgery_centers(P, cat, fn, counties, zips, today):
    src = dict(source_title=cat["asc"]["title"], source_link=cat["asc"]["page"], cms_release=cat["asc"]["modified"], checked_on=today)
    nat = next(rows(P["ascn"]), {})
    out = []
    for r in rows(P["asc"]):
        if r.get("State") != "TX" or zips.get((r.get("ZIP Code") or "")[:5], "") not in counties:
            continue
        base = dict(kind="surgery center", ccn=r["Facility ID"], facility=r["Facility Name"], city=(r.get("City/Town") or "").title(),
                    county=zips[(r.get("ZIP Code") or "")[:5]].title())
        recs = []
        for m, name in ASC_NAMES.items():
            if f"{m} Rate*" in r:           # rate measures
                v = r.get(f"{m} Rate*") or ""
                nv = f"national average {nat.get(f'Avg {m} Nat Rate*', '?')}, median {nat.get(f'Median {m} Nat Rate*', '?')}"
                recs.append(dict(base, measure_id=m, measure_name=name, value=v if num(v) is not None else "", unit="rate as CMS publishes it",
                                 national_value=nv, cms_comparison="", data_period=f"year {r.get('Year')} (as CMS labels it)",
                                 not_rated_reason="" if num(v) is not None else ("not rated. " + (fn_text(fn, r.get(f"{m} Footnote")) or "CMS gives no reason")), **src))
            elif f"{m} RSHV Rate" in r:     # risk-standardized hospital visit rates
                v = r.get(f"{m} RSHV Rate") or ""
                ok = num(v) is not None
                recs.append(dict(base, measure_id=m, measure_name=name, value=v if ok else "", unit="hospital visits per 1,000 procedures (risk-standardized)",
                                 national_value=f"national rate {nat.get(f'{m} Nat Rate', '?')}",
                                 cms_comparison=r.get(f"{m} Performance Category") if ok else "",
                                 data_period=f"year {r.get('Year')} (as CMS labels it)" + (f"; {r.get(f'{m} Total Cases')} cases" if num(r.get(f"{m} Total Cases")) is not None else ""),
                                 not_rated_reason="" if ok else ("not rated. " + ((r.get(f"{m} Performance Category") or "").replace("N/A", "") + " " + fn_text(fn, r.get(f"{m} Footnote"))).strip()).strip(), **src))
        have = sum(1 for x in recs if x["value"] != "")
        for x in recs:
            x["fewer_measures_reported"] = "yes" if recs and have / len(recs) < FEWER else ""
        out += recs
    return out


def write(out, cat):
    OUT.mkdir(parents=True, exist_ok=True)
    out.sort(key=lambda r: (r["kind"], r["facility"], r["ccn"], r["measure_id"]))
    with open(OUT / "dfw-measures.csv", "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(out)
    H = [r for r in out if r["measure_id"] == "overall_star"]
    A = defaultdict(list)
    for r in out:
        if r["kind"] == "surgery center":
            A[(r["facility"], r["ccn"])].append(r)
    L = ["# CMS quality measures: Dallas-Fort Worth hospitals and surgery centers", "",
         f"Built {date.today().isoformat()} by `site/care_quality_dfw.py` from CMS's Provider Data Catalog. Nothing deployed. "
         "Every value is CMS's own, with CMS's national figure, data period and a link. No composite score, no ranking; the "
         "lists below are in alphabetical order. \"Not rated\" always carries CMS's reason. \"Fewer measures reported\" means "
         "the facility reported under half of the measures CMS uses. Leapfrog data is not used.", "",
         "| Source | CMS release | Link |", "|---|---|---|"]
    L += [f"| {m['title']} | {m['modified']} | {m['page']} |" for m in cat.values()]
    L += ["", f"## Hospitals ({len(H)})", "", "| Hospital | CCN | Overall star | Measures reported / used | Fewer measures reported |", "|---|---|---|---|---|"]
    grp = defaultdict(lambda: [0, 0])
    for r in out:
        if r["measure_id"].startswith("group:"):
            grp[r["ccn"]][0] += int(r["value"] or 0)
            grp[r["ccn"]][1] += int((r["national_value"] or "CMS uses 0").split()[-1])
    for r in H:
        star = f"{r['value']} of 5" if r["value"] else "not rated"
        g = grp[r["ccn"]]
        rep_ = f"{g[0]} / {g[1]}" if g[1] else "none in CMS's star-rating data"
        L.append(f"| {r['facility']} | {r['ccn']} | {star} | {rep_} | {r['fewer_measures_reported'] or 'no'} |")
    L += ["", f"## Surgery centers ({len(A)})", "", "| Surgery center | CCN | ASC measures with a value | Fewer measures reported |", "|---|---|---|---|"]
    for (name, ccn), rs in sorted(A.items()):
        L.append(f"| {name} | {ccn} | {sum(1 for x in rs if x['value'] != '')} of {len(rs)} | {rs[0]['fewer_measures_reported'] or 'no'} |")
    L += ["", "Every measure, with values, national figures, periods and links: `reports/care-compare/dfw-measures.csv`."]
    (OUT / "dfw-measures.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/cq")
    a = ap.parse_args()
    Path(a.work).mkdir(parents=True, exist_ok=True)
    cat = catalog()
    P = {k: fetch(m, a.work) for k, m in cat.items()}
    fn = footnotes(P["fn"])
    counties, zips = dfw()
    today = date.today().isoformat()
    out = hospitals(P, cat, fn, counties, today) + surgery_centers(P, cat, fn, counties, zips, today)
    write(out, cat)
    print(f"{len(out):,} measure rows -> reports/care-compare/dfw-measures.md and .csv")


if __name__ == "__main__":
    main()
