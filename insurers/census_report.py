"""Roll this month's insurer file inventories into one readable report.

Reads R2 bot/insurers/census/<yyyy-mm>/<scope>/<table>.json (written by 06f via worker.py) and writes
reports/census/<yyyy-mm>.csv (one row per file) and reports/census/<yyyy-mm>.md (what the files contain).
Research only: these are counts of what insurers put in their files, never prices shown on the site.
Run: python insurers/census_report.py [YYYY-MM]   (needs the R2_* secrets)
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import boto3

E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"] or "upfrontdfwdata"
MONTH = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m")
OUT = Path(__file__).resolve().parent.parent / "reports" / "census"
FIELDS = ["description", "additional_information", "bundled_codes", "covered_services", "billing_code_modifier",
          "service_code", "expiration_date", "setting", "billing_code_type_version"]


def load():
    s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                      aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
    out = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=f"bot/insurers/census/{MONTH}/"):
        for o in page.get("Contents", []):
            if o["Key"].endswith(".json"):
                d = json.loads(s3.get_object(Bucket=B, Key=o["Key"])["Body"].read())
                d["scope"] = o["Key"].split("/")[4]
                out.append(d)
    return out


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else ""


def main():
    files = load()
    if not files:
        print(f"No inventories for {MONTH} yet.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    top = lambda f, c: ", ".join(f"{t['value'] or '(blank)'} {pct(t['rows'], f['rows'])}" for t in f.get("values", {}).get(c, {}).get("top", [])[:4])
    cols = ["scope", "insurer", "network", "source_file", "checked_on", "rows", "billing_codes", "npis"] + \
           [f"{c}_filled" for c in FIELDS] + ["percent_of_charges_rows", "arrangements", "rate_types", "classes", "settings"]
    files.sort(key=lambda f: (f["scope"], f.get("header", {}).get("reporting_entity_name", ""), f.get("network", "")))
    with open(OUT / f"{MONTH}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in files:
            rv, n = f.get("rows_with_value", {}), f.get("rows", 0)
            w.writerow([f["scope"], f.get("header", {}).get("reporting_entity_name", ""), f.get("network", ""), f.get("source_file", ""),
                        f.get("checked_on", ""), n, f.get("distinct_approx", {}).get("billing_codes", ""), f.get("distinct_approx", {}).get("npis", "")]
                       + [pct(rv.get(c, 0), n) for c in FIELDS]
                       + [pct(f.get("percent_of_charges_rows", 0), n), top(f, "negotiation_arrangement"), top(f, "negotiated_type"),
                          top(f, "billing_class"), top(f, "setting")])

    # Plain-language summary: which details show up, where, and the most common insurer notes
    total = sum(f.get("rows", 0) for f in files)
    filled = Counter()
    has = defaultdict(set)
    notes = Counter()
    arr = Counter()
    for f in files:
        ins = f.get("header", {}).get("reporting_entity_name", "") or f.get("network", "")
        for c in FIELDS:
            k = f.get("rows_with_value", {}).get(c, 0)
            filled[c] += k
            if k:
                has[c].add(ins)
        for t in f.get("values", {}).get("additional_information", {}).get("top", []):
            if t["value"]:
                notes[t["value"][:160]] += t["rows"]
        for t in f.get("values", {}).get("negotiation_arrangement", {}).get("top", []):
            arr[t["value"] or "(blank)"] += t["rows"]
    L = [f"# What's in the insurer files: {MONTH}", "",
         f"{len(files)} files read so far this month, {total:,} in-scope price rows. Counts are real, not sampled. "
         "Research only: nothing here is shown on the site as a price.", "",
         "## How often each detail is filled in", "", "| Detail | Rows with it | Insurers that use it |", "|---|---|---|"]
    for c in FIELDS:
        L.append(f"| {c} | {pct(filled[c], total)} | {', '.join(sorted(has[c])[:6]) + (' …' if len(has[c]) > 6 else '') or '—'} |")
    L += ["", "## Contract types (negotiation arrangement)", ""] + [f"- {k}: {v:,} rows" for k, v in arr.most_common(8)]
    pc = sum(f.get("percent_of_charges_rows", 0) for f in files)
    L += ["", f"Percent-of-charges rates: {pc:,} rows ({pct(pc, total)}).", "",
          "## Most common insurer notes (\"additional information\")", ""]
    L += [f"- {k} ({v:,} rows)" for k, v in notes.most_common(15)] or ["- none yet"]
    L += ["", f"Per-file detail: `reports/census/{MONTH}.csv`."]
    (OUT / f"{MONTH}.md").write_text("\n".join(L) + "\n")
    print(f"{len(files)} inventories -> reports/census/{MONTH}.md and .csv")


if __name__ == "__main__":
    main()
