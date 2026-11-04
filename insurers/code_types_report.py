"""Which billing code types insurers' files use, from the monthly census (Nov 3, 2026; Betsy asked to add APR-DRG to
the code crosswalk: this shows which insurers price hospital stays with APR-DRG and how much).

Reads R2 bot/insurers/census/<latest month>/**/*.json (insurers/pipeline/inventory.py, values.billing_code_type) and
prints rows per code type, overall and per insurer for the DRG-type codes. Research only.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot"))
import store  # noqa: E402

s3, b = store.r2()
months, tok = set(), None
keys = []
while True:
    kw = dict(Bucket=b, Prefix="bot/insurers/census/")
    if tok:
        kw["ContinuationToken"] = tok
    r = s3.list_objects_v2(**kw)
    keys += [o["Key"] for o in r.get("Contents", []) if o["Key"].endswith(".json")]
    if not r.get("IsTruncated"):
        break
    tok = r["NextContinuationToken"]
months = sorted({k.split("/")[3] for k in keys})
print("census months:", months)
total, by_ins, tables = Counter(), defaultdict(Counter), Counter()
skipped = []


def get(k):
    for _ in range(3):
        try:
            return k, json.loads(s3.get_object(Bucket=b, Key=k)["Body"].read())
        except Exception:
            pass
    skipped.append(k)
    return k, {}


from concurrent.futures import ThreadPoolExecutor  # noqa: E402
want = [k for k in keys if k.split("/")[3] in months[-2:]]
print(f"{len(want)} census files")
with ThreadPoolExecutor(16) as ex:
    got = list(ex.map(get, want))
# Keep one census per file per area: a file re-read in both months would otherwise be counted twice (latest wins).
latest = {}
for k, d in sorted(got, key=lambda kd: kd[0].split("/")[3]):
    latest[(k.split("/")[4], d.get("source_file") or k)] = (k, d)
print(f"{len(got) - len(latest)} older duplicate census files dropped")
zero = {"tables": 0, "tables_with_zero": 0, "zero_rows": 0, "dollar_rows": 0, "insurers": set(), "insurers_with_zero": set()}
for k, d in latest.values():
    # Insurer name as written in the file header (same as census_report.py); the R2 folder name only as a last resort
    ins = (d.get("header", {}).get("reporting_entity_name") or d.get("insurer") or d.get("reporting_entity_name")
           or d.get("network") or k.split("/")[4])
    if "zero_dollar_rows" in d:  # census v2+ (Oct 13, 2026): $0.00 dollar-type prices, a placeholder that tells a patient nothing
        zero["tables"] += 1
        zero["insurers"].add(ins)
        zero["zero_rows"] += d["zero_dollar_rows"]
        zero["dollar_rows"] += d["zero_dollar_rows"] + d.get("dollar_rows", 0)
        if d["zero_dollar_rows"]:
            zero["tables_with_zero"] += 1
            zero["insurers_with_zero"].add(ins)
    for v in d.get("values", {}).get("billing_code_type", {}).get("top", []):
        total[v["value"]] += v["rows"]
        if "DRG" in str(v["value"]).upper() or str(v["value"]).upper() in ("APR", "APC", "EAPG"):
            by_ins[v["value"]][ins] += v["rows"]
            tables[(v["value"], ins)] += 1
lines = ["## Billing code types in insurer files (last two census months, one census per file)", "", "| Code type | Rows |", "|---|---|"]
lines += [f"| {t} | {n:,} |" for t, n in total.most_common()]
for t, c in by_ins.items():
    lines += ["", f"### {t}: by insurer", "", "| Insurer | Rows | Tables |", "|---|---|---|"]
    lines += [f"| {i} | {n:,} | {tables[(t, i)]} |" for i, n in c.most_common(40)]
z = zero
lines += ["", "## $0.00 prices (census v2+ tables)", "",
          f"- Tables measured: {z['tables']:,} from {len(z['insurers']):,} insurers",
          f"- Tables with at least one $0.00 price: {z['tables_with_zero']:,} from {len(z['insurers_with_zero']):,} insurers",
          f"- $0.00 prices: {z['zero_rows']:,} of {z['dollar_rows']:,} dollar-type prices"
          + (f" ({100 * z['zero_rows'] / z['dollar_rows']:.1f}%)" if z['dollar_rows'] else "")]
lines += ["", f"({len(skipped)} census files could not be read)"]
text = "\n".join(lines)
print(text)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")
