"""Medicare's own groupings for every CPT/HCPCS code in the crosswalk (Nov 3, 2026; Betsy: add the codes the crosswalk
is missing). Reads the site's Medicare benchmark file (R2 reference/site/med_all.json, built by site/build_med_all.py
from CMS OPPS Addendum B July 2026, ASC Addendum AA July 2026, the 2026 physician fee schedule and the lab fee
schedule) and writes reference/care_items/medicare_codes.csv: code, APC, OPPS status indicator, ASC payment indicator,
and which Medicare fee schedules price it. Codes only; no prices are copied into the crosswalk.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bot"))
import store  # noqa: E402

s3, b = store.r2()
med = json.loads(s3.get_object(Bucket=b, Key="reference/site/med_all.json")["Body"].read())
med = med.get("med", med)
codes = sorted({r["code"] for r in csv.DictReader(open(os.path.join(HERE, "crosswalk_codes.csv")))
                if r["code_system"] in ("CPT", "HCPCS Level II", "anesthesia CPT")} | {"G0121", "G0105", "G0438", "G0439", "36415"})
rows = []
for c in codes:
    m = med.get(c, {})
    o, a = m.get("opps") or [None, "", ""], m.get("asc") or [None, ""]
    rows.append(dict(code=c, apc=o[2] if len(o) > 2 else "", opps_status_indicator=o[1] if len(o) > 1 else "",
                     asc_payment_indicator=a[1] if len(a) > 1 else "",
                     physician_fee_schedule="yes" if m.get("pfs") or m.get("pfs26") else "",
                     professional_component_26="yes" if m.get("pfs26") else "",
                     lab_fee_schedule="yes" if m.get("lab") else ""))
with open(os.path.join(HERE, "medicare_codes.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows)} codes; with an APC: {sum(1 for r in rows if r['apc'])}; ASC-payable: {sum(1 for r in rows if r['asc_payment_indicator'])}")
for r in rows:
    print(",".join(r.values()))
