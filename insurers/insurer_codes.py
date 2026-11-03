"""Insurer-made codes, tied back to standard codes (Nov 3, 2026; Betsy: "I want all ... insurers' independent codes
added to this list, because that's part of the issue, and they have to tie back to at least something").

Insurers may price services under codes they make up (billing_code_type CSTM-ALL, LOCAL, ...) or under misspelled
code types (REV, revCode, Local ...). This lists every such code in every insurer table we've read, from the code
lists the reader keeps per table (R2 <area>/codes/<table>.parquet: code type, code, the insurer's description), names
the insurer and network (each area's manifest), and ties each code back to a standard code or care item:

  same as CPT/HCPCS     the "custom" code is itself a valid-looking CPT/HCPCS code (e.g. LOCAL 27447)
  revenue code          a 4-digit 0xxx code, or a REV/revCode type (hospital department code)
  DRG number            a 3-digit code, or the description names a DRG
  codes in description  the insurer's own description names standard codes ("CPT 45378 ...")
  care item by name     the description names one of our care items or its usual aliases ("total knee arthroplasty")
  no tie found          nothing in the code or description ties it to a standard code: a finding in itself

Writes reference/care_items/insurer_codes.csv (one row per insurer x code type x code) and insurer_codes_summary.md.
Run: python insurers/insurer_codes.py   (workflow "Insurer-made codes")
"""
import ast
import csv
import io
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "bot"))
import store  # noqa: E402

STANDARD = {"CPT", "HCPCS", "MS-DRG", "APR-DRG", "AP-DRG", "RC", "ICD", "NDC", "CDT", "HIPPS", "CMG", "APC", "EAPG"}
OUT = ROOT / "reference" / "care_items"


def scopes():
    tree = ast.parse((HERE / "bot.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SCOPES" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def care_index():
    """standard code -> care items; name phrases -> care item"""
    by_code = defaultdict(set)
    for r in csv.DictReader(open(OUT / "crosswalk_codes.csv", encoding="utf-8")):
        # revenue codes and modifiers are shared by many items, so they don't tie a code to one item
        if r["code_system"] in ("CPT", "HCPCS Level II", "anesthesia CPT", "MS-DRG", "APR-DRG", "ICD-10-PCS") \
                and not r["role"].startswith(("doctor: related", "anesthesia: related")):
            by_code[(r["code_system"], r["code"])].add(r["item_id"])
    phrases = {}
    for r in csv.DictReader(open(OUT / "care_items.csv", encoding="utf-8")):
        n = norm(re.sub(r"\(.*?\)", "", r["plain_name"]))
        if len(n) > 5:
            phrases[n] = r["item_id"]
    tree = ast.parse((ROOT / "site" / "procedure_pages.py").read_text(encoding="utf-8"))
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SEARCH_NAMES" for t in node.targets):
            names = ast.literal_eval(node.value)
    code_item = {}
    for (sysname, code), items in by_code.items():
        if sysname == "CPT":
            code_item.setdefault(code, sorted(items)[0])
    for code, (name, aliases) in names.items():
        item = code_item.get(code)
        if not item:
            continue
        for p in [name] + list(aliases):
            n = norm(re.sub(r"\(.*?\)", "", p))
            if len(n) > 5:
                phrases.setdefault(n, item)
    return by_code, phrases


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


PCS = re.compile(r"^[0-9A-HJ-NP-Z]{7}$")
DX = re.compile(r"^[A-TV-Z]\d[0-9A-Z]\.[0-9A-Z]{1,4}$")
STD = re.compile(r"^(\d{4}[0-9A-Z]|[A-V]\d{4})$")


CATEGORY_RC = [   # description words -> the revenue code(s) hospitals use for that kind of service (NUBC)
    (r"PART(IAL)? HOSP", ["0912", "0913"], "partial hospitalization"),
    (r"\bEKG\b|\bECG\b|ELECTROCARDIO", ["0730"], "EKG"),
    (r"HOSPICE", ["0651", "0655"], "hospice"),
    (r"INHALATION|RESPIRATORY|NEBULIZ|PULMONARY", ["0410"], "respiratory therapy"),
    (r"\bPOCT\b|POINT OF CARE", ["0300"], "lab test (point of care)"),
    (r"CONSULT", ["0510"], "consult"),
    (r"DIALYSIS", ["0821", "0831"], "dialysis"),
    (r"\bMRI\b|MAGNETIC RES", ["0610"], "MRI"),
    (r"\bCT\b|COMPUTED TOMOG|CAT SCAN", ["0350"], "CT scan"),
    (r"ULTRASOUND|\bECHO", ["0402"], "ultrasound"),
    (r"X-?RAY|RADIOGRAPH", ["0320"], "x-ray"),
    (r"MAMMO", ["0401"], "mammogram"),
    (r"PHYSICAL THERAPY|\bPT\b", ["0420"], "physical therapy"),
    (r"OCCUPATIONAL THERAPY|\bOT\b", ["0430"], "occupational therapy"),
    (r"SPEECH", ["0440"], "speech therapy"),
    (r"EMERGENCY|\bER\b", ["0450"], "emergency room"),
    (r"OBSERVATION", ["0762"], "observation"),
    (r"AMBULANCE", ["0540"], "ambulance"),
    (r"\bDME\b|DURABLE MEDICAL", ["0290"], "medical equipment"),
    (r"INFUSION", ["0260"], "IV therapy / infusion"),
    (r"CHEMO", ["0335"], "chemotherapy"),
    (r"RADIATION|RADIOTHERAPY", ["0333"], "radiation therapy"),
    (r"LAB\b|LABORATORY|PANEL|CULTURE|ASSAY|\bAG\b|CONFIRM", ["0300"], "lab test"),
    (r"SURG|ECTOMY|OTOMY|PLASTY|REPAIR|REVISION", ["0360"], "surgery"),
    (r"VAGINAL DEL|VAGNIAL|DELIVERY|OBSTET|MATERNITY", ["0720"], "labor and delivery"),
    (r"PSYCH|BEHAVIORAL|MENTAL HEALTH", ["0900"], "behavioral health"),
    (r"TRANSPLANT", ["0810"], "organ acquisition / transplant"),
    (r"VACCINE|IMMUNIZ", ["0771"], "vaccine"),
    (r"CLINIC|VISIT|APPT|REFERRAL", ["0510"], "clinic visit or referral"),
]


def found_codes(ctype, code, desc):
    """Every standard code an insurer-made code or its description names: [(system, code)]."""
    c, d, t = (code or "").upper().strip(), (desc or "").upper(), (ctype or "").upper().strip()
    text = f"{c} {d}"
    out = []
    if t in ("REV", "REVCODE", "REVENUE", "RC") and re.fullmatch(r"\d{3,4}", c):
        out.append(("revenue code", c.zfill(4)))
    m = re.fullmatch(r"(0\d{3})-(\d{4}[0-9A-Z]|[A-V]\d{4})", c)   # BCBS MA style: revenue code - CPT
    if m:
        out += [("revenue code", m.group(1)), ("CPT" if m.group(2)[0].isdigit() else "HCPCS Level II", m.group(2))]
    m = re.fullmatch(r"(\d{4}[0-9A-Z]|[A-V]\d{4})[A-Z]{1,2}", c)   # a CPT/HCPCS code with the insurer's own suffix
    if m and not out:
        out.append(("CPT" if m.group(1)[0].isdigit() else "HCPCS Level II", m.group(1)))
    if STD.match(c) and not out:
        out.append(("CPT" if c[0].isdigit() else "HCPCS Level II", c))
    for r in re.findall(r"(\d{3,4})\s*/\s*REV|REV\s*(\d{3,4})", d):   # Aetna style: 131/REV, REV 148
        out.append(("revenue code", (r[0] or r[1]).zfill(4)))
    toks = re.split(r"[^0-9A-Z.]+", text)
    for tok in toks:
        tok = tok.strip(".")
        if DX.match(tok):
            out.append(("ICD-10-CM", tok))
        elif PCS.match(tok) and ("ICD10PX" in text or "PCS" in text or " PX" in text) and re.search(r"\d", tok) \
                and re.search(r"[A-Z]", tok):
            out.append(("ICD-10-PCS", tok))
    for tok in re.findall(r"\b(\d{4}[0-9A-Z]|[A-V]\d{4})\b", d):
        out.append(("CPT" if tok[0].isdigit() else "HCPCS Level II", tok))
    for tok in re.findall(r"\bDRG\s*#?\s*(\d{3})\b", d):
        out.append(("MS-DRG", tok))
    return list(dict.fromkeys(out))


def tie(ctype, code, desc, by_code, phrases):
    """-> (ties_to, [(system, code)], care items, how sure)"""
    c, t, d = (code or "").strip().upper(), (ctype or "").strip().upper(), desc or ""
    codes = found_codes(ctype, code, desc)
    cw = {"CPT": "CPT", "HCPCS Level II": "HCPCS Level II", "revenue code": "revenue code", "MS-DRG": "MS-DRG",
          "ICD-10-PCS": "ICD-10-PCS"}
    items = sorted({i for s_, k in codes for i in by_code.get((cw.get(s_, s_), k), ())})
    D = d.upper()
    if "PDPM" in D:
        return ("nursing-home payment group (HIPPS / SNF PDPM)", [("HIPPS (SNF PDPM)", c)], "", "high")
    if re.search(r"(EARLY|LATE) EPISODE|CLINICAL=|CLINICAL SEVERITY", D):
        return ("home health payment group (HIPPS / PDGM)", [("HIPPS (home health)", c)], "", "high")
    if re.search(r"INCLUDE MEMBERS|AGE RANGE|INAPPROPRIATE BILLING|BAD DEBT|CONVERSION$", D):
        return "not a service (a plan or billing rule)", [], "", "medium"
    if codes:
        systems = {s_ for s_, _ in codes}
        how = ("standard codes inside the insurer's code" if len(codes) > 1 or len(systems) > 1
               else "same as a standard code")
        conf = "high" if STD.match(c) or "-" in c or t in ("REV",) else "medium"
        return how, codes, "; ".join(items), conf
    if re.fullmatch(r"\d{3}", c):
        return "DRG number (assumed)", [("MS-DRG (assumed)", c)], "; ".join(sorted(by_code.get(("MS-DRG", c), ()))), "low"
    nd = norm(d)
    hits = sorted({item for p, item in phrases.items() if f" {p} " in f" {nd} "})
    if hits:
        return "care item by name", [], "; ".join(hits), "low (name match)"
    for pat, rc, what in CATEGORY_RC:   # a service category whose hospital department code is standard
        if re.search(pat, D):
            return f"service category: {what}", [("revenue code", x) for x in rc], "", "low (by description)"
    if t == "CSTM-ALL":
        return "insurer service category (no standard code)", [], "", ""
    return "no tie found", [], "", ""


def write(out_rows):
    out_rows.sort(key=lambda r: (r["insurer"], r["code_type_as_written"], r["code"]))
    with open(OUT / "insurer_codes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    from collections import Counter
    by_type = Counter(r["code_type_as_written"] for r in out_rows)
    by_tie = Counter(r["ties_to"] for r in out_rows)
    by_ins = Counter(r["insurer"] for r in out_rows)
    no_tie = Counter(r["insurer"] for r in out_rows if r["ties_to"] == "no tie found")
    md = ["# Insurer-made codes (Nov 3, 2026)", "",
          f"{len(out_rows):,} distinct insurer-made codes (insurer x code type x code) in every insurer table read so far.",
          "", "## By code type as written", "", "| Code type | Codes |", "|---|---|"]
    md += [f"| {t or '(blank)'} | {n:,} |" for t, n in by_type.most_common(12)]
    md += ["", "## How they tie back", "", "| Ties to | Codes |", "|---|---|"]
    md += [f"| {t} | {n:,} |" for t, n in by_tie.most_common()]
    md += ["", "## By insurer", "", "| Insurer | Codes | With no tie |", "|---|---|---|"]
    md += [f"| {i or '(unknown table)'} | {n:,} | {no_tie.get(i, 0):,} |" for i, n in by_ins.most_common(60)]
    (OUT / "insurer_codes_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(md) + "\n")


def row_out(ins, ct, code, desc, networks, areas, example, by_code, phrases):
    how, codes, items, conf = tie(ct, code, desc, by_code, phrases)
    r = dict(insurer=ins, code_type_as_written=ct, code=code, insurer_description=desc, ties_to=how)
    for i in range(1, 5):   # one code per cell: tied code 1-4, each with its code type
        s_, k = codes[i - 1] if i <= len(codes) else ("", "")
        r[f"tied_code_{i}_type"], r[f"tied_code_{i}"] = s_, k
    r.update(tied_care_items=items, how_sure=conf, networks=networks, areas=areas, example_network=example)
    return r


def retie():
    """Recompute the ties from the saved list (no storage reads): python insurers/insurer_codes.py --retie"""
    by_code, phrases = care_index()
    rows = [row_out(r["insurer"], r["code_type_as_written"], r["code"], r["insurer_description"], r["networks"],
                    r["areas"], r["example_network"], by_code, phrases)
            for r in csv.DictReader(open(OUT / "insurer_codes.csv", encoding="utf-8"))]
    write(rows)


def main():
    s3, b = store.r2()
    by_code, phrases = care_index()
    rows = defaultdict(lambda: dict(networks=set(), areas=set(), tables=0))
    for scope, (state, _plist, out) in scopes().items():
        man = store.read_csv(s3, b, state + "manifest.csv")
        tab = {}
        for m in man:
            for k in ("table", "prev_table"):
                if m.get(k):
                    tab[m[k]] = (m.get("insurer", ""), m.get("network_label") or m.get("slot", ""))
        keys, tok = [], None
        while True:
            kw = dict(Bucket=b, Prefix=f"{out}codes/")
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in r.get("Contents", []) if o["Key"].endswith(".parquet")]
            if not r.get("IsTruncated"):
                break
            tok = r["NextContinuationToken"]

        def read(k):
            for _ in range(3):
                try:
                    return k, pq.read_table(io.BytesIO(s3.get_object(Bucket=b, Key=k)["Body"].read()))
                except Exception:
                    pass
            return k, None
        with ThreadPoolExecutor(32) as ex:
            got = list(ex.map(read, keys))
        n_custom = 0
        for k, t in got:
            if t is None or "billing_code_type" not in t.column_names:
                continue
            table = k.rsplit("/", 1)[-1][: -len(".parquet")]
            ins, net = tab.get(table, ("", table))
            for r in t.to_pylist():
                ct = (r.get("billing_code_type") or "").strip()
                if ct.upper() in STANDARD and ct == ct.upper():
                    continue
                n_custom += 1
                key = (ins, ct, r.get("billing_code") or "", (r.get("description") or "")[:300])
                e = rows[key]
                e["networks"].add(net)
                e["areas"].add(scope)
                e["tables"] += 1
        print(f"{scope}: {len(keys)} code lists, {n_custom} insurer-made code rows", flush=True)

    out_rows = [row_out(ins, ct, code, desc, len(e["networks"]), " | ".join(sorted(e["areas"])),
                        sorted(e["networks"])[0] if e["networks"] else "", by_code, phrases)
                for (ins, ct, code, desc), e in rows.items()]
    OUT.mkdir(parents=True, exist_ok=True)
    write(out_rows)

if __name__ == "__main__":
    retie() if "--retie" in sys.argv else main()
