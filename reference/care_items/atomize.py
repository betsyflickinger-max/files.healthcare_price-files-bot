"""One code per cell (Nov 3, 2026; Betsy: "Why are there some codes that are still not broken out by column?").

Run last by build_care_items.py. Takes the crosswalk build_crosswalk.py made (which still had lists like
"45380 | 45384 | 45385", ranges like "461-462" and notes inside code cells) and rewrites:
  crosswalk.csv          one row per care item; every code in its own numbered column (doctor_cpt_related_1, _2, ...;
                         drg_other_1, drg_other_1_when, ...). Ranges are expanded (461-462 -> 461, 462) and every
                         "when" note sits in its own column next to its code.
  crosswalk_codes.csv    the same codes, one row per code: item, code, code system, role, when, base units. The easiest
                         form to filter, sort, or join to price data.
  care_item_bills.csv    one row per bill with code_1 / code_2 (the second only when there are two possible codes);
                         related codes now live only in the two crosswalk files.
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SEP = " | "


def expand(token):
    """'461-462' -> ['461', '462']; '426-428/447-448' -> 426..428, 447..448; '039' stays '039'."""
    out = []
    for part in re.split(r"\s*/\s*", token.strip()):
        m = re.fullmatch(r"(\d{3})-(\d{3})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += [f"{n:03d}" for n in range(a, b + 1)]
        elif re.fullmatch(r"\d{3}", part):
            out.append(part)
    return out


def drg_atoms(cell, default_when=""):
    """'450 (major complications, front only)' -> [('450', 'major complications, front only')];
    '461-462 (both knees) | 521-522 (if for a hip fracture)' -> [('461','both knees'), ('462','both knees'), ...]"""
    atoms = []
    for piece in (cell or "").split(SEP):
        piece = piece.strip()
        m = re.match(r"^((?:\d{3}(?:-\d{3})?)(?:\s*/\s*\d{3}(?:-\d{3})?)*)\s*(.*)$", piece)
        if not m:
            continue
        note = m.group(2).strip()
        note = (note[1:-1] if note.startswith("(") and note.endswith(")") else note).strip() or default_when
        atoms += [(c, note) for c in expand(m.group(1))]
    return atoms


def plain_codes(cell):
    """'45380 | 45384 | 45385' or '00630|00670' or 'G0463 (hospital-owned clinic)' -> ['45380', ...]"""
    return [re.sub(r"\s*\(.*\)$", "", x).strip() for x in re.split(r"\s*\|\s*", cell or "") if x.strip()]


def main():
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk.csv"), encoding="utf-8")))
    bills = list(csv.DictReader(open(os.path.join(HERE, "care_item_bills.csv"), encoding="utf-8")))
    long_rows, wide = [], []

    def add(item, role, system, code, when="", units=""):
        long_rows.append(dict(item_id=item["item_id"], plain_name=item["plain_name"], role=role, code_system=system,
                              code=code, when=when, anesthesia_base_units=units))

    for x in xw:
        units = dict(re.findall(r"(\d{5})\s*:\s*(\d+)", x["anesthesia_base_units"]))
        r = {k: x[k] for k in ("item_id", "plain_name", "kind", "usual_setting", "shoppable")}
        lists = {}

        def put(col, codes, role, system, whens=None):
            lists[col] = (codes, whens)
            for i, c in enumerate(codes):
                add(x, role, system, c, (whens or [""] * len(codes))[i], units.get(c, ""))

        put("doctor_cpt", plain_codes(x["doctor_cpt"]), "doctor: main code", "CPT")
        put("doctor_cpt_related", plain_codes(x["doctor_cpt_related"]), "doctor: related procedure code", "CPT")
        put("facility_or_lab_cpt", plain_codes(x["facility_or_lab_cpt"]), "facility or lab: same-day code", "CPT")
        put("facility_fee_hcpcs", plain_codes(x["facility_fee_hcpcs"]), "facility fee: hospital-owned clinic", "HCPCS Level II")
        usual = drg_atoms(re.sub(r"\s*\(medical\)", " (medical DRG: groups by the diagnosis)", x["drg_usual"]))
        cc = drg_atoms(x["drg_with_cc"])
        mcc = drg_atoms(x["drg_with_mcc"])
        if len(usual) == 3 and not cc and not mcc and not any(w for _, w in usual):
            # a three-DRG family given as a range (ectopic pregnancy 817-819): CMS numbers them MCC, CC, none
            mcc, cc, usual = [usual[0]], [usual[1]], [usual[2]]
        mcc = [(c, "" if w == "major complications" else w) for c, w in mcc]
        put("drg_usual", [c for c, _ in usual], "hospital stay: usual (no complications)", "MS-DRG", [w for _, w in usual])
        put("drg_with_cc", [c for c, _ in cc], "hospital stay: with complications (CC)", "MS-DRG", [w for _, w in cc])
        put("drg_with_mcc", [c for c, _ in mcc], "hospital stay: with major complications (MCC)", "MS-DRG", [w for _, w in mcc])
        oth = drg_atoms(x["drg_other"])
        put("drg_other", [c for c, _ in oth], "hospital stay: other situation", "MS-DRG", [w for _, w in oth])
        pcs = [p.strip() for p in (x["icd10pcs_example"] or "").split("+") if p.strip()]
        put("icd10pcs", pcs, "hospital: procedure code (inpatient)" + (", coded together" if len(pcs) > 1 else ""),
            "ICD-10-PCS")
        put("anesthesia_cpt", plain_codes(x["anesthesia_cpt"]), "anesthesia: main code", "anesthesia CPT")
        put("anesthesia_cpt_alternate", plain_codes(x["anesthesia_cpt_alternate"]), "anesthesia: other possible code",
            "anesthesia CPT")
        put("anesthesia_cpt_related", plain_codes(x["anesthesia_cpt_related"]), "anesthesia: related code", "anesthesia CPT")
        put("pathology_cpt", plain_codes(x["pathology_cpt"]), "pathology: if tissue is sent", "CPT")
        put("other_related_cpt", plain_codes(x["other_related_cpt"]), "add-on: blood draw", "CPT")
        r["_lists"] = lists
        r["_units"] = units
        r["_tail"] = {k: x[k] for k in ("split_billing_modifiers", "drg_confidence", "anesthesia_confidence", "notes")}
        wide.append(r)

    # wide: as many numbered columns as the busiest item needs
    order = list(wide[0]["_lists"].keys()) if wide else []
    width = {c: max(len(w["_lists"][c][0]) for w in wide) for c in order}
    with_when = {"drg_usual", "drg_with_mcc", "drg_other"}
    fields = ["item_id", "plain_name", "kind", "usual_setting", "shoppable"]
    for c in order:
        n = width[c]
        if not n:
            continue
        for i in range(1, n + 1):
            col = c if n == 1 else f"{c}_{i}"
            fields.append(col)
            if c in with_when:
                fields.append(f"{col}_when")
            if c.startswith("anesthesia_cpt"):
                fields.append(f"{col}_base_units")
    fields += ["split_billing_modifiers", "drg_confidence", "anesthesia_confidence", "notes"]
    out = []
    for w in wide:
        row = {k: w[k] for k in ("item_id", "plain_name", "kind", "usual_setting", "shoppable")}
        for c in order:
            codes, whens = w["_lists"][c]
            n = width[c]
            for i, code in enumerate(codes, 1):
                col = c if n == 1 else f"{c}_{i}"
                row[col] = code
                if c in with_when and whens:
                    row[f"{col}_when"] = whens[i - 1]
                if c.startswith("anesthesia_cpt"):
                    row[f"{col}_base_units"] = w["_units"].get(code, "")
        row.update(w["_tail"])
        out.append(row)
    with open(os.path.join(HERE, "crosswalk.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fields)
        wr.writeheader()
        wr.writerows(out)
    with open(os.path.join(HERE, "crosswalk_codes.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, ["item_id", "plain_name", "role", "code_system", "code", "when", "anesthesia_base_units"])
        wr.writeheader()
        wr.writerows(long_rows)

    # bills: one code per cell (code_1, code_2 when there are two possible codes); related codes live in the crosswalk
    bf = ["item_id", "bill", "setting", "code_system", "code_1", "code_2", "billing_class", "priced_as", "when",
          "confidence", "source"]
    for b in bills:
        cs = plain_codes(b.get("codes", "").replace("|", " | "))
        if b.get("code_system") == "MS-DRG":
            cs = expand(cs[0]) if cs and "-" in cs[0] else cs
        b["code_1"], b["code_2"] = (cs + ["", ""])[:2]
        if len(cs) > 2:
            b["when"] = f"{b['when']}; also {', '.join(cs[2:])}"
    with open(os.path.join(HERE, "care_item_bills.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, bf, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(bills)
    multi = sum(1 for r in out for k, v in r.items() if k not in ("item_id", "plain_name", "notes", "kind", "usual_setting", "shoppable",
                                                                  "split_billing_modifiers", "drg_confidence",
                                                                  "anesthesia_confidence") and not k.endswith("_when")
                and v and (SEP.strip() in v or re.search(r"\d-\d", v)))
    print(f"one code per cell: crosswalk {len(out)} rows x {len(fields)} columns; {len(long_rows)} codes in "
          f"crosswalk_codes.csv; cells still holding more than one code: {multi}")


if __name__ == "__main__":
    main()
