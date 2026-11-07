"""Marketplace claim denials: CMS's Transparency in Coverage public use file (PUF) for marketplace (QHP) issuers.

Nov 7, 2026. Every marketplace issuer reports to CMS how many claims it received and denied and how many appeals were
filed and overturned. CMS publishes one small spreadsheet per plan year:
  https://download.cms.gov/marketplace-puf/<year>/transparency-in-coverage-puf.zip   (about 1 MB)
Covers issuers on HealthCare.gov states (federal marketplace and state-based marketplaces that use its platform) only.

This writes a Texas table: issuer, plan year, market (individual or small business/SHOP), in-network claims received,
in-network claims denied, denial rate, internal appeals filed and overturned, external appeals filed and overturned.

Rules:
  - Numbers are copied as CMS wrote them. "Suppressed" means CMS hid a small number (** in the file); the other codes
    (* not available, *** not required, N/A new to marketplace) (kept as CMS's own meaning). Those are never filled in.
  - The denial rate is denied / received, both from the same row of the file. It is blank when either is missing.
  - Issuer-level figures repeat on every plan row in CMS's sheet; each issuer is counted once per sheet.
  - The file says its claims data covers "services rendered during the calendar year January 1 to December 31" but does
    not name the year inside the file. The table shows the plan year of the file and says so.
  - A denial count is not proof of wrongdoing: issuers deny claims for many reasons (duplicates, missing information,
    services not covered). CMS's own disclaimer says this. The report repeats it.

Output: reports/denials/tx.csv and reports/denials/tx.md. The original zip of each year is kept untouched in
reports/denials/source/ only when --keep is given (they are public; CMS's link is in every row).

Run: python insurers/denials.py [--years 2024,2025,2026] [--state TX]
"""
import argparse
import csv
import hashlib
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "denials"
URL = "https://download.cms.gov/marketplace-puf/{y}/transparency-in-coverage-puf.zip"
UA = {"User-Agent": "Mozilla/5.0 (compatible; price-files-bot; +https://github.com/betsyflickinger-max/files.healthcare_price-files-bot)"}
SUPPRESSED = {"**": "suppressed", "*": "not available", "***": "not required", "N/A": "new to marketplace", "": "blank"}

# CMS's column names (cut off at 40 characters in the spreadsheet) -> our names. Matched on the start of the name.
COLS = {
    "Issuer_Claims_Received_In_Network": "in_network_claims_received",
    "Issuer_Claims_Denied_In_Network": "in_network_claims_denied",
    "Issuer_Internal_Appeals_Filed": "internal_appeals_filed",
    "Issuer_Number_Internal_Appeals_Overturne": "internal_appeals_overturned",
    "Issuer_External_Appeals_Filed": "external_appeals_filed",
    "Issuer_Number_External_Appeals_Overturne": "external_appeals_overturned",
}
FIELDS = ["state", "plan_year_file", "market", "issuer_name", "issuer_id", "in_network_claims_received", "in_network_claims_denied",
          "denial_rate", "internal_appeals_filed", "internal_appeals_overturned", "external_appeals_filed",
          "external_appeals_overturned", "plans_in_file", "source_url", "source_sha256", "checked_on"]


def clean(v):
    """CMS value -> (text as shown, number or None). Whole numbers lose the '.0' the spreadsheet adds."""
    s = str(v if v is not None else "").strip()
    if s in SUPPRESSED:
        return SUPPRESSED[s], None
    try:
        x = float(s.replace(",", ""))
    except ValueError:
        return s, None
    return (str(int(x)) if x.is_integer() else s), x


def market_of(sheet):
    s = sheet.lower()
    if "sadp" in s:
        return None          # stand-alone dental plans: not medical claims
    if "shop" in s:
        return "Small business (SHOP)"
    if "qhp" in s:
        return "Individual"
    return None


def read_puf(data, year, url, sha, state):
    """Rows for one PUF zip (bytes). One row per issuer per medical sheet in `state`."""
    from python_calamine import CalamineWorkbook
    z = zipfile.ZipFile(io.BytesIO(data))
    name = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
    wb = CalamineWorkbook.from_filelike(io.BytesIO(z.read(name)))
    out = []
    for sheet in wb.sheet_names:
        market = market_of(sheet)
        if not market:
            continue
        rows = wb.get_sheet_by_name(sheet).to_python()
        hi = next(i for i, r in enumerate(rows) if "Issuer_Name" in [str(x).strip() for x in r])
        head = [str(x).strip().rstrip('"') for x in rows[hi]]
        ix = {h: i for i, h in enumerate(head)}
        col = {ours: next((i for h, i in ix.items() if h.startswith(cms)), None) for cms, ours in COLS.items()}
        issuers = {}
        for r in rows[hi + 1:]:
            if str(r[ix["State"]]).strip().upper() != state:
                continue
            iid = clean(r[ix["Issuer_ID"]])[0]
            rec = issuers.get(iid)
            if rec is None:
                rec = dict(state=state, plan_year_file=year, market=market, issuer_name=str(r[ix["Issuer_Name"]]).strip(),
                           issuer_id=iid, plans_in_file=0, source_url=url, source_sha256=sha, checked_on=date.today().isoformat())
                nums = {}
                for ours, i in col.items():
                    rec[ours], nums[ours] = clean(r[i]) if i is not None else ("not in file", None)
                rcv, den = nums["in_network_claims_received"], nums["in_network_claims_denied"]
                rec["denial_rate"] = f"{100 * den / rcv:.1f}%" if rcv and den is not None else ""
                issuers[iid] = rec
            rec["plans_in_file"] += 1
        out += sorted(issuers.values(), key=lambda x: x["issuer_name"])
    return out


def fetch(year):
    url = URL.format(y=year)
    r = requests.get(url, headers=UA, timeout=300)
    if r.status_code == 404:
        return url, None
    r.raise_for_status()
    return url, r.content


def write(rows, state, years, missing):
    OUT.mkdir(parents=True, exist_ok=True)
    st = state.lower()
    with open(OUT / f"{st}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    L = [f"# Marketplace claim denials: {state}", "",
         f"Built {date.today().isoformat()} by `insurers/denials.py` from CMS's Transparency in Coverage public use files "
         "for marketplace issuers (HealthCare.gov platform only). Every number is copied from CMS's file; the denial rate is "
         "denied ÷ received from the same row. \"Suppressed\" = CMS hid a small number (** in the file); \"not available\" (*), "
         "\"not required\" (***) and \"new to marketplace\" (N/A) are CMS's own codes. Nothing is filled in or estimated.", "",
         "**What this is not.** A denial count does not show that a claim was wrongly denied. Issuers deny claims for many "
         "reasons (duplicates, missing information, services the plan doesn't cover). CMS: \"Claims denials are not "
         "necessarily indicative of issuer strength or plan quality.\" These are in-network claims for marketplace plans "
         "only, not employer plans.", "",
         "**Which year.** Each file is named for a plan year. CMS says the claims data covers services in one calendar year "
         "but does not name the year inside the file, so the table shows the file's plan year.", ""]
    for y in years:
        yr = [r for r in rows if r["plan_year_file"] == y]
        if y in missing:
            L += [f"## Plan year {y} file", "", f"CMS has no file at {URL.format(y=y)} yet.", ""]
            continue
        L += [f"## Plan year {y} file", "", f"Source: {URL.format(y=y)}", "",
              "| Issuer | Market | In-network claims received | Denied | Denial rate | Internal appeals filed | Overturned | External appeals filed | Overturned |",
              "|---|---|---|---|---|---|---|---|---|"]
        n = lambda v: f"{int(v):,}" if str(v).isdigit() else v
        for r in yr:
            L.append(f"| {r['issuer_name'].strip()} | {r['market']} | {n(r['in_network_claims_received'])} | {n(r['in_network_claims_denied'])} | "
                     f"{r['denial_rate'] or '—'} | {n(r['internal_appeals_filed'])} | {n(r['internal_appeals_overturned'])} | "
                     f"{n(r['external_appeals_filed'])} | {n(r['external_appeals_overturned'])} |")
        L.append("")
    L += [f"One row per issuer per market and file. Full table with source links and file fingerprints: `reports/denials/{st}.csv`."]
    (OUT / f"{st}.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2024,2025,2026")
    ap.add_argument("--state", default="TX")
    a = ap.parse_args()
    years = [y.strip() for y in a.years.split(",") if re.fullmatch(r"\d{4}", y.strip())]
    rows, missing = [], set()
    for y in years:
        url, data = fetch(y)
        if data is None:
            missing.add(y)
            print(f"{y}: no file at {url}")
            continue
        sha = hashlib.sha256(data).hexdigest()
        got = read_puf(data, y, url, sha, a.state.upper())
        print(f"{y}: {len(data) / 1e6:.1f} MB, sha256 {sha[:12]}, {len(got)} {a.state.upper()} issuer rows")
        rows += got
    if not rows:
        sys.exit("no rows")
    write(rows, a.state.upper(), years, missing)
    print(f"-> reports/denials/{a.state.lower()}.md and .csv")


if __name__ == "__main__":
    main()
