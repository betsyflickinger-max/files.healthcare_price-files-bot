"""The crosswalk: one row per care item, every code in its own column by code type (Nov 2, 2026; Betsy: "break out
related codes ... listed by which specific code it is by column ... Goal is to be a crosswalk to aligning all codes").

Run by build_care_items.py after it writes care_items.csv and care_item_bills.csv. It
  1. splits the bills' free-text related_codes into typed columns (related_cpt, drg_with_cc, drg_with_mcc,
     drg_other, anesthesia_base_units) and rewrites care_item_bills.csv
  2. writes crosswalk.csv: one row per care item, one column per kind of code
MS-DRG families: "usual" = no complications; "with CC" = with complications or comorbidities; "with MCC" = with major
complications. Other DRGs that apply in a named situation (both knees, done for cancer, ...) go in drg_other as
"code (when)", separated by " | ".
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

XW_FIELDS = ["item_id", "plain_name", "kind", "usual_setting", "shoppable",
             "doctor_cpt", "doctor_cpt_related", "facility_or_lab_cpt", "facility_fee_hcpcs",
             "drg_usual", "drg_with_cc", "drg_with_mcc", "drg_other", "icd10pcs_example",
             "anesthesia_cpt", "anesthesia_cpt_alternate", "anesthesia_base_units", "anesthesia_cpt_related",
             "pathology_cpt", "other_related_cpt", "split_billing_modifiers",
             "drg_confidence", "anesthesia_confidence", "notes"]
BILL_SPLIT = ["related_cpt", "drg_with_cc", "drg_with_mcc", "drg_other", "anesthesia_base_units"]
CODES = re.compile(r"^\s*((?:\d{3}(?:-\d{3})?)(?:\s*/\s*\d{3}(?:-\d{3})?)*)\s*(.*)$")


def split_drgs(text):
    """'472 (complications); 471 (major complications); 429-430 (front + back fusion)' -> cc, mcc, other."""
    cc, mcc, other = [], [], []
    for part in (text or "").replace(". ", "; ").split(";"):
        part = part.strip()
        m = CODES.match(part)
        if not part or not m:
            if part:
                other.append(part)
            continue
        code, rest = m.group(1).replace(" ", ""), m.group(2).strip()
        note = (rest[1:-1] if rest.startswith("(") and rest.endswith(")") else rest).strip()
        low = note.lower()
        if low == "complications":
            cc.append(code)
        elif low.startswith("major complications") and "with " not in low[:5]:
            mcc.append(code if low == "major complications" else f"{code} ({note})")
        else:
            other.append(f"{code} ({re.sub(r'^if ', 'if ', note)})" if note else code)
    return " | ".join(cc), " | ".join(mcc), " | ".join(other)


def anes_units(text):
    """'00600: 10 / 00670: 13' -> {'00600': '10', '00670': '13'}"""
    return dict(re.findall(r"(\d{5})\s*:\s*(\d+)", text or ""))


def main():
    items = list(csv.DictReader(open(os.path.join(HERE, "care_items.csv"), encoding="utf-8")))
    bills = list(csv.DictReader(open(os.path.join(HERE, "care_item_bills.csv"), encoding="utf-8")))
    src = {r["surgeon_cpt"]: r for r in csv.DictReader(open(os.path.join(HERE, "source_crosswalk_oct.csv"),
                                                              encoding="utf-8-sig"))}
    # 1. bills: typed columns instead of one free-text related_codes
    for b in bills:
        rel = b.pop("related_codes", "") or ""
        b.update({k: "" for k in BILL_SPLIT})
        if b["code_system"] == "MS-DRG":
            b["drg_with_cc"], b["drg_with_mcc"], b["drg_other"] = split_drgs(rel)
        elif b["code_system"] == "anesthesia CPT":
            u = anes_units(rel)
            b["anesthesia_base_units"] = " | ".join(f"{k}: {v}" for k, v in u.items())
            if not u and rel:
                b["related_cpt"] = " | ".join(x for x in rel.split("|") if x and x not in b["codes"].split("|"))
        elif rel:
            b["related_cpt"] = " | ".join(x for x in rel.split("|") if x and x not in b["codes"].split("|"))
    fields = [f for f in bills[0].keys()]
    with open(os.path.join(HERE, "care_item_bills.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(bills)

    # 2. crosswalk: one row per item
    rows = []
    for it in items:
        bs = [b for b in bills if b["item_id"] == it["item_id"]]
        x = {k: "" for k in XW_FIELDS}
        x.update({k: it[k] for k in ("item_id", "plain_name", "kind", "usual_setting", "shoppable")})
        notes, modifiers = [], set()
        for b in bs:
            who, sys_, codes = b["bill"], b["code_system"], b["codes"]
            if sys_ == "CPT" and b["billing_class"] == "professional" and not x["doctor_cpt"]:
                x["doctor_cpt"], x["doctor_cpt_related"] = codes, b["related_cpt"]
            elif sys_ == "CPT" and b["billing_class"] in ("institutional", "either") and not x["facility_or_lab_cpt"]:
                x["facility_or_lab_cpt"] = codes
                if not x["doctor_cpt"] and b["billing_class"] == "either":
                    x["doctor_cpt"] = ""   # a lab test: one bill, kept as the facility/lab code
            if sys_.startswith("HCPCS"):
                x["facility_fee_hcpcs"] = codes.split(" ")[0] + " (hospital-owned clinic)"
            if sys_ == "MS-DRG":
                x["drg_usual"] = codes
                x["drg_with_cc"], x["drg_with_mcc"], x["drg_other"] = b["drg_with_cc"], b["drg_with_mcc"], b["drg_other"]
                x["drg_confidence"] = b["confidence"]
                if b["source"].startswith("AAPC"):
                    notes.append(b["source"])
            if who == "anesthesia":
                x["anesthesia_confidence"] = b["confidence"]
                if codes:
                    a = codes.split("|")
                    x["anesthesia_cpt"] = a[0]
                    if b["source"] == "packages/packages.csv":
                        x["anesthesia_cpt_related"] = " | ".join(c for c in (b["related_cpt"] or "").split(" | ") if c)
                        if len(a) > 1:
                            x["anesthesia_cpt_related"] = " | ".join(filter(None, [" | ".join(a[1:]), x["anesthesia_cpt_related"]]))
                    elif len(a) > 1:
                        x["anesthesia_cpt_alternate"] = " | ".join(a[1:])
                    x["anesthesia_base_units"] = b["anesthesia_base_units"]
            if "pathology" in who:
                x["pathology_cpt"] = codes if it["kind"] != "pathology (tissue check)" else ""
            if "36415" in b["when"]:
                x["other_related_cpt"] = "36415 (blood draw)"
            if "modifier 26" in b["source"] or "(TC)" in b["source"]:
                modifiers.update(["TC (technical part)", "26 (doctor's reading)"])
        s = src.get(it["main_cpt"])
        if s:
            x["icd10pcs_example"] = s["icd10pcs_example"]
            if not x["anesthesia_base_units"]:
                x["anesthesia_base_units"] = " | ".join(f"{k}: {v}" for k, v in anes_units(s["anesthesia_base_units_cms"]).items())
        if it["kind"] == "pathology (tissue check)":
            x["doctor_cpt"] = x["doctor_cpt"] or it["main_cpt"]
        x["split_billing_modifiers"] = " | ".join(sorted(modifiers))
        x["notes"] = " | ".join(notes)
        rows.append(x)
    with open(os.path.join(HERE, "crosswalk.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, XW_FIELDS)
        w.writeheader()
        w.writerows(rows)
    filled = {k: sum(1 for r in rows if r[k]) for k in XW_FIELDS[5:-3]}
    print(f"crosswalk: {len(rows)} rows; filled per column: " + ", ".join(f"{k} {v}" for k, v in filled.items()))


if __name__ == "__main__":
    main()
