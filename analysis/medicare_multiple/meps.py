"""Third total: weighted to how privately insured people under 65 spend on care (MEPS), Nov 10, 2026.

Source: AHRQ Medical Expenditure Panel Survey, Household Component, 2024 Full Year Consolidated Data File (HC-256), the
newest year in the MEPS-HC summary tables ("Use, expenditures, and population": total expenditures by event type, for
people under 65 with any private insurance). The shares are computed here from that public use file with the same
variables the summary table uses, and saved in meps_2024_under65_private.csv (committed, so a run needs no download):

  people    AGELAST < 65 and INSCOV24 = 1 (any private coverage in 2024), weighted by PERWT24F
  dollars   sum of PERWT24F x each event type's total expenditure (all payers: what was paid for that care)

  MEPS event type (variable)                         -> group of our kinds of care
  office-based visits (OBVEXP24), outpatient          -> Doctor and clinician fees: every RBCS doctor-fee category,
    doctor (OPDEXP24), ER doctor (ERDEXP24),             anesthesia, lab tests, Part B drugs
    inpatient doctor (IPDEXP24)
  outpatient facility (OPFEXP24), ER facility         -> Hospital outpatient facility fees (and surgery centers, which have
    (ERFEXP24)                                           no Medicare volume, so they carry no weight inside the group)
  inpatient facility (IPFEXP24)                       -> Hospital stays
  other medical equipment and services (OTHEXP24)     -> Durable medical equipment and supplies, ambulance
  prescribed medicines (RXEXP24), dental (DVTEXP24),  -> no kind of care here: their share is reported, not weighted
    home health (HHAEXP24 + HHNEXP24), glasses and
    contacts (VISEXP24)

Total (c) = sum over groups of (MEPS share x the group's Medicare-use weighted multiple) / sum of the shares of groups with
a figure. Inside each group, codes are weighted by Medicare's volumes as in total (a).

Regenerate (needs pandas):  python analysis/medicare_multiple/meps.py build h256dta.zip analysis/medicare_multiple/meps_2024_under65_private.csv
"""
import csv
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARES = HERE / "meps_2024_under65_private.csv"
YEAR = 2024
EVENTS = [  # (variable stem, plain name, group)
    ("OBVEXP", "Office-based visits", "Doctor and clinician fees"),
    ("OPDEXP", "Hospital outpatient: doctor", "Doctor and clinician fees"),
    ("ERDEXP", "Emergency room: doctor", "Doctor and clinician fees"),
    ("IPDEXP", "Inpatient stays: doctor", "Doctor and clinician fees"),
    ("OPFEXP", "Hospital outpatient: facility", "Hospital outpatient and ER facility fees"),
    ("ERFEXP", "Emergency room: facility", "Hospital outpatient and ER facility fees"),
    ("IPFEXP", "Inpatient stays: facility", "Hospital stays"),
    ("OTHEXP", "Other medical equipment and services", "Equipment, supplies and ambulance"),
    ("RXEXP", "Prescribed medicines", ""),
    ("DVTEXP", "Dental visits", ""),
    ("HHAEXP", "Home health: agency", ""),
    ("HHNEXP", "Home health: non-agency", ""),
    ("VISEXP", "Glasses and contact lenses", ""),
]
GROUP_VIEWS = {
    "Doctor and clinician fees": {"professional", "anesthesia", "lab", "drug"},
    "Hospital outpatient and ER facility fees": {"outpatient_hospital", "asc"},
    "Hospital stays": {"inpatient"},
    "Equipment, supplies and ambulance": {"dme", "ambulance"},
}
LABEL = "weighted to how privately insured people under 65 use care (MEPS)"
TABLE = ("AHRQ MEPS Household Component, 2024 Full Year Consolidated Data File (HC-256); same measure as the MEPS-HC summary "
         "table \"Use, expenditures, and population: total expenditures by event type\", people under 65 with any private insurance")


def shares_from_frame(d, year=YEAR):
    """d: a DataFrame with AGELAST, INSCOVyy, PERWTyyF and the <stem>yy expenditure columns -> rows with dollars and shares."""
    yy = str(year)[2:]
    s = d[(d["AGELAST"] < 65) & (d[f"INSCOV{yy}"] == 1) & (d[f"PERWT{yy}F"] > 0)]
    w = s[f"PERWT{yy}F"]
    tot = float((s[f"TOTEXP{yy}"] * w).sum())
    rows = []
    for stem, name, group in EVENTS:
        v = float((s[f"{stem}{yy}"] * w).sum())
        rows.append(dict(year=year, variable=f"{stem}{yy}", event_type=name, group=group, dollars=round(v), share=round(v / tot, 5)))
    rows.append(dict(year=year, variable=f"TOTEXP{yy}", event_type="All care", group="(total)", dollars=round(tot), share=1.0))
    return rows, len(s)


def build(zip_path, out_csv):
    import pandas as pd
    import zipfile
    yy = str(YEAR)[2:]
    cols = ["AGELAST", f"PERWT{yy}F", f"INSCOV{yy}", f"TOTEXP{yy}"] + [f"{stem}{yy}" for stem, _, _ in EVENTS]
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".dta"))
        with z.open(name) as f:
            d = pd.read_stata(f, columns=cols, convert_categoricals=False)
    rows, people = shares_from_frame(d)
    sha = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]) + ["source_file", "source_sha256", "sample_people"])
        w.writeheader()
        for r in rows:
            w.writerow(dict(r, source_file="https://meps.ahrq.gov/data_files/pufs/h256/h256dta.zip", source_sha256=sha, sample_people=people))
    return rows


def load_shares(path=SHARES):
    """{group: share} for the groups that map to kinds of care, and the full rows (for the report)."""
    rows = list(csv.DictReader(open(path)))
    g = {}
    for r in rows:
        if r["group"] and r["group"] != "(total)":
            g[r["group"]] = g.get(r["group"], 0.0) + float(r["share"])
    return g, rows


def meps_total(code_rows, weighted, path=SHARES):
    """code_rows: one figure's code rows with a figure and a Medicare weight (summarize.py); weighted: summarize._weighted.
    Returns (total, [per-group dict(group, share, multiple, codes)])."""
    shares, _ = load_shares(path)
    parts = []
    for g, views in GROUP_VIEWS.items():
        rs = [r for r in code_rows if r["view"] in views]
        parts.append(dict(group=g, meps_share=round(shares.get(g, 0.0), 4), multiple=weighted(rs) if rs else None, codes=len(rs)))
    have = [p for p in parts if p["multiple"] is not None and p["meps_share"] > 0]
    den = sum(p["meps_share"] for p in have)
    return (round(sum(p["meps_share"] * p["multiple"] for p in have) / den, 3) if den else None), parts


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "build":
        for r in build(sys.argv[2], sys.argv[3]):
            print(r)
    else:
        print(__doc__)
