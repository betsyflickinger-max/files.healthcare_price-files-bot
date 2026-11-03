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
for _m in [0]:
    for k, d in got:
        ins = d.get("insurer") or d.get("reporting_entity_name") or k.split("/")[4]
        for v in d.get("values", {}).get("billing_code_type", {}).get("top", []):
            total[v["value"]] += v["rows"]
            if "DRG" in str(v["value"]).upper() or str(v["value"]).upper() in ("APR", "APC", "EAPG"):
                by_ins[v["value"]][ins] += v["rows"]
                tables[(v["value"], ins)] += 1
lines = ["## Billing code types in insurer files (last two census months)", "", "| Code type | Rows |", "|---|---|"]
lines += [f"| {t} | {n:,} |" for t, n in total.most_common()]
for t, c in by_ins.items():
    lines += ["", f"### {t}: by insurer", "", "| Insurer | Rows | Tables |", "|---|---|---|"]
    lines += [f"| {i} | {n:,} | {tables[(t, i)]} |" for i, n in c.most_common(40)]
lines += ["", f"({len(skipped)} census files could not be read)"]
text = "\n".join(lines)
print(text)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")
