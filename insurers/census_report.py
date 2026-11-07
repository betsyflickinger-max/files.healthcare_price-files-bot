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
FIELDS = ["additional_information", "bundled_codes", "covered_services", "billing_code_modifier",
          "service_code", "expiration_date", "setting", "billing_code_type_version"]


def load():
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                      aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
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


def rate_label_section(files):
    """Nov 7, 2026: counts of the "may never be used" labels (insurers/pipeline/rate_labels.py). Labels only: every rate
    stays in the tables and on the site, in price order."""
    have = [f for f in files if isinstance(f.get("rate_labels"), dict) and "rows" in f["rate_labels"]]
    L = ["", "## Rates that may never be used (labels only)", "",
         "Insurer files list rates for many provider-and-service pairs that are unlikely ever to be billed. These labels mark "
         "the usual signs. Nothing is removed, re-ranked or hidden; the counts are research, not findings about an insurer."]
    if not have:
        return L + ["", "Not counted yet: the label counts are switched off in the census until Betsy turns them on "
                    "(`insurers/pipeline/rate_labels.py`, IN_CENSUS)."]
    tot = Counter()
    for f in have:
        for k, v in f["rate_labels"].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                tot[k] += v
    th = have[0]["rate_labels"].get("thresholds", {})
    d = tot["dollar_rows"]
    L += ["", f"{len(have)} of {len(files)} files counted. {d:,} dollar rates in them.", "",
          "| Label | Rates | Share of dollar rates |", "|---|---|---|",
          f"| Below {th.get('low', 0.5):.0%} or above {th.get('high', 8):g}× Medicare's rate for the same code "
          f"(of {tot['with_medicare_figure']:,} rates with a Medicare figure) | {tot['far_from_medicare']:,} "
          f"({tot['below_half_medicare']:,} below, {tot['above_8x_medicare']:,} above) | {pct(tot['far_from_medicare'], d)} |",
          f"| Same amount listed more than once for the same service at the same provider | {tot['repeated_amount_rows']:,} "
          f"({tot['repeated_amount_extra_copies']:,} extra copies) | {pct(tot['repeated_amount_rows'], d)} |",
          f"| One identical amount for {th.get('many_codes', 10)}+ codes in {th.get('many_families', 3)}+ code families "
          f"at the same provider | {tot['one_amount_many_codes']:,} | {pct(tot['one_amount_many_codes'], d)} |",
          f"| Any of the three | {tot['any_label']:,} | {pct(tot['any_label'], d)} |"]
    return L


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
    # Contract end dates, as written in the files (insurers use 9999-12-31 / 2999-12-31 for "no set end")
    ends, per_ins = Counter(), defaultdict(Counter)
    for f in files:
        ins = f.get("header", {}).get("reporting_entity_name", "") or f.get("network", "")
        for e in f.get("contract_ends_by_month", []):
            ends[e["month"]] += e["prices"]
            per_ins[ins]["dated" if e["month"] not in ("blank", "no set end") else e["month"]] += e["prices"]
            if e["month"] not in ("blank", "no set end") and e["month"] <= f"{int(MONTH[:4]) + 1}{MONTH[4:]}":
                per_ins[ins]["within a year"] += e["prices"]
    if ends:
        L += ["", "## Contract end dates (as written in the files)", "",
              "Prices whose contract ends in each of the next 12 months, summed across files. 'No set end' = the insurer wrote "
              "9999-12-31 or 2999-12-31. Per-provider dates: `<scope>/ends/<table>.parquet` in R2.", "",
              "| Month | Prices ending |", "|---|---|"]
        nxt = sorted(m for m in ends if m not in ("blank", "no set end") and m >= MONTH)[:12]
        L += [f"| {m} | {ends[m]:,} |" for m in nxt]
        tot = sum(ends.values())
        L += ["", f"No set end: {pct(ends['no set end'], tot)} of prices. Blank: {pct(ends['blank'], tot)}. "
              f"Already past their end date: {pct(sum(v for m, v in ends.items() if m not in ('blank', 'no set end') and m < MONTH), tot)}.",
              "", "| Insurer | Prices with a real end date | Ending within a year | No set end |", "|---|---|---|---|"]
        for ins, c in sorted(per_ins.items()):
            t = sum(v for k, v in c.items() if k != "within a year")
            L.append(f"| {ins} | {pct(c['dated'], t)} | {pct(c['within a year'], t)} | {pct(c['no set end'], t)} |")
    L += rate_label_section(files)
    L += ["", f"Per-file detail: `reports/census/{MONTH}.csv`."]
    (OUT / f"{MONTH}.md").write_text("\n".join(L) + "\n")
    print(f"{len(files)} inventories -> reports/census/{MONTH}.md and .csv")


if __name__ == "__main__":
    main()
