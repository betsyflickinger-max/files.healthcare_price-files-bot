"""One code per cell (Nov 3, 2026; Betsy: "Why are there some codes that are still not broken out by column?").

Run last by build_care_items.py. Takes the crosswalk build_crosswalk.py made (which still had lists like
"45380 | 45384 | 45385", ranges like "461-462" and notes inside code cells) and rewrites:
  crosswalk.csv          one row per care item; every code in its own numbered column (doctor_cpt_related_1, _2, ...;
                         drg_other_1, drg_other_1_when, ...). Ranges are expanded (461-462 -> 461, 462) and every
                         "when" note sits in its own column next to its code.
  crosswalk_codes.csv    the same codes, one row per code: item, code, code system, role, when, base units. The easiest
                         form to filter, sort, or join to price data.
  care_item_bills.csv    one row per bill, one column per code type (CPT, Anesthesia CPT, MS-DRG, HCPCS Level II);
                         related codes now live only in the two crosswalk files.
"""
import csv
import os
import re

import extra_codes

EXTRA = {"apc": ("facility: Medicare outpatient group", "APC"), "opps_si": ("facility: OPPS status indicator", "OPPS SI"),
         "asc_pi": ("facility: ASC payment indicator", "ASC PI"),
         "hcpcs_medicare": ("Medicare's own code for this", "HCPCS Level II"),
         "pos": ("place of service", "POS"), "modifier": ("modifier", "CPT/HCPCS modifier"),
         "revenue": ("facility claim line", "revenue code")}

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


BASE = {"item_id": "Procedure ID", "plain_name": "Procedure", "kind": "Kind", "usual_setting": "Usual setting",
        "shoppable": "Shoppable", "split_billing_modifiers": "Split billing modifiers (TC / 26)",
        "apc": "APC: Medicare outpatient facility group", "opps_si": "OPPS status indicator",
        "asc_pi": "ASC payment indicator", "hcpcs_medicare": "HCPCS Level II: Medicare's version",
        "pos": "Place of service (POS)", "modifier": "Modifier", "revenue": "Revenue code (facility claim)",
        "drg_confidence": "MS-DRG link: how sure", "apr_drg_confidence": "APR-DRG link: how sure",
        "apr_drg_usual": "APR-DRG: usual", "apr_drg_other": "APR-DRG: other situation",
        "apr_drg_severity": "APR-DRG: severity levels (added to the code)", "anesthesia_confidence": "Anesthesia link: how sure", "notes": "Notes",
        "doctor_cpt": "CPT: doctor (main)", "doctor_cpt_related": "CPT: doctor related",
        "facility_or_lab_cpt": "CPT: facility or lab (same day)",
        "facility_fee_hcpcs": "HCPCS Level II: hospital-clinic facility fee",
        "drg_usual": "MS-DRG: usual (no complications)", "drg_with_cc": "MS-DRG: with complications (CC)",
        "drg_with_mcc": "MS-DRG: with major complications (MCC)", "drg_other": "MS-DRG: other situation",
        "icd10pcs": "ICD-10-PCS: inpatient procedure", "anesthesia_cpt": "Anesthesia CPT: main",
        "anesthesia_cpt_alternate": "Anesthesia CPT: other possible", "anesthesia_cpt_related": "Anesthesia CPT: related",
        "pathology_cpt": "CPT: pathology", "other_related_cpt": "CPT: blood draw"}


def label(col):
    """'drg_other_2_when' -> 'MS-DRG: other situation 2, when'; 'anesthesia_cpt_base_units' -> '... base units'."""
    tail = ""
    for suf, t in (("_when", " - when"), ("_base_units", " - base units")):
        if col.endswith(suf):
            col, tail = col[: -len(suf)], t
    if col == "apr_drg_usual" and tail:
        tail = " - name"
    m = re.fullmatch(r"(.+)_(\d+)", col)
    if m and m.group(1) in BASE:
        return f"{BASE[m.group(1)]} {m.group(2)}{tail}"
    return BASE.get(col, col) + tail


def main():
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk.csv"), encoding="utf-8")))
    bills = list(csv.DictReader(open(os.path.join(HERE, "care_item_bills.csv"), encoding="utf-8")))
    long_rows, wide = [], []
    # Nov 3 (Betsy): APR-DRG, the 3M/Solventum hospital-stay system some insurers price with (census: ~12 million
    # rows in 54 insurer tables vs ~528 million MS-DRG rows). Matched by name to the APR-DRG list; see apr_drg_map.csv.
    apr_names = {r["apr_drg"]: r for r in csv.DictReader(open(os.path.join(HERE, "apr_drg_names.csv"), encoding="utf-8"))}
    apr_map = {r["item_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "apr_drg_map.csv"), encoding="utf-8"))}

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
        am = apr_map.get(x["item_id"], {})
        au = [c for c in [am.get("apr_drg_usual", "")] if c]
        put("apr_drg_usual", au, "hospital stay (APR-DRG): usual", "APR-DRG",
            [apr_names.get(c, {}).get("name", "").capitalize() for c in au])
        ao = drg_atoms(am.get("apr_drg_other", ""))
        put("apr_drg_other", [c for c, _ in ao], "hospital stay (APR-DRG): other situation", "APR-DRG", [w for _, w in ao])
        x["apr_drg_confidence"] = am.get("confidence", "")
        x["apr_drg_severity"] = "1 minor, 2 moderate, 3 major, 4 extreme" if au else ""
        pcs = [p.strip() for p in (x["icd10pcs_example"] or "").split("+") if p.strip()]
        put("icd10pcs", pcs, "hospital: procedure code (inpatient)" + (", coded together" if len(pcs) > 1 else ""),
            "ICD-10-PCS")
        put("anesthesia_cpt", plain_codes(x["anesthesia_cpt"]), "anesthesia: main code", "anesthesia CPT")
        put("anesthesia_cpt_alternate", plain_codes(x["anesthesia_cpt_alternate"]), "anesthesia: other possible code",
            "anesthesia CPT")
        put("anesthesia_cpt_related", plain_codes(x["anesthesia_cpt_related"]), "anesthesia: related code", "anesthesia CPT")
        put("pathology_cpt", plain_codes(x["pathology_cpt"]), "pathology: if tissue is sent", "CPT")
        put("other_related_cpt", plain_codes(x["other_related_cpt"]), "add-on: blood draw", "CPT")
        for col, pairs in extra_codes.for_item(x):   # Nov 3: APC, POS, modifiers, revenue codes, Medicare versions
            role, system = EXTRA[col]
            put(col, [c for c, _ in pairs], role, system, [w for _, w in pairs])
        r["_lists"] = lists
        r["_units"] = units
        r["_tail"] = {k: x[k] for k in ("apr_drg_severity", "apr_drg_confidence",
                                        "drg_confidence", "anesthesia_confidence", "notes")}
        wide.append(r)

    # wide: as many numbered columns as the busiest item needs
    order = []
    for w in wide:   # every list column any item has, in the order first seen
        order += [c for c in w["_lists"] if c not in order]
    width = {c: max(len(w["_lists"].get(c, ([], None))[0]) for w in wide) for c in order}
    with_when = {"drg_usual", "drg_with_mcc", "drg_other", "apr_drg_usual", "apr_drg_other", "hcpcs_medicare", "pos",
                 "modifier", "revenue"}
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
    fields += ["apr_drg_severity", "apr_drg_confidence", "drg_confidence",
               "anesthesia_confidence", "notes"]
    out = []
    for w in wide:
        row = {k: w[k] for k in ("item_id", "plain_name", "kind", "usual_setting", "shoppable")}
        for c in order:
            codes, whens = w["_lists"].get(c, ([], None))
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
        wr = csv.writer(f)
        wr.writerow([label(c) for c in fields])   # Nov 3 (Betsy): every code column says its code type
        wr.writerows([[r.get(c, "") for c in fields] for r in out])
    with open(os.path.join(HERE, "crosswalk_codes.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, ["item_id", "plain_name", "role", "code_system", "code", "when", "anesthesia_base_units"])
        wr.writeheader()
        wr.writerows(long_rows)

    # bills: one column per code type (Nov 3, Betsy: say whether it's a CPT code, a DRG, ...); related codes live in
    # the crosswalk files
    TYPE_COLS = {"CPT": "CPT", "anesthesia CPT": "Anesthesia CPT", "MS-DRG": "MS-DRG", "APR-DRG": "APR-DRG",
                 "HCPCS / revenue code": "HCPCS Level II"}
    code_cols = []
    for t in TYPE_COLS.values():
        code_cols += [t, f"{t} (other possible)"]
    bf = ["item_id", "bill", "setting", "code_system"] + code_cols + ["billing_class", "priced_as", "when",
                                                                       "confidence", "source"]
    for b in bills:
        cs = plain_codes(b.get("codes", "").replace("|", " | "))
        t = TYPE_COLS.get(b.get("code_system", ""))
        if b.get("code_system") == "MS-DRG" and cs and "-" in cs[0]:
            fam = expand(cs[0])
            if len(fam) == 3:   # a DRG family given as a range: CMS numbers them MCC, CC, none
                b["when"] = f"{b['when']}; {fam[1]} with complications, {fam[0]} with major complications"
                cs = [fam[2]]
            else:
                cs = fam
        if b.get("code_system") == "MS-DRG" and apr_map.get(b["item_id"], {}).get("apr_drg_usual"):
            b["APR-DRG"] = apr_map[b["item_id"]]["apr_drg_usual"]   # the same stay, if the insurer uses APR-DRG
        if t and cs:
            b[t] = cs[0]
            if len(cs) > 1:
                b[f"{t} (other possible)"] = cs[1]
            if len(cs) > 2:
                b["when"] = f"{b['when']}; also {', '.join(cs[2:])}"
    bf = [c for c in bf if c not in code_cols or any(b.get(c) for b in bills)]   # drop code columns nothing uses
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
