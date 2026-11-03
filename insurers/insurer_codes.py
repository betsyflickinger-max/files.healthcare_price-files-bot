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
        if r["code_system"] in ("CPT", "HCPCS Level II", "anesthesia CPT", "MS-DRG", "APR-DRG", "revenue code"):
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


def tie(ctype, code, desc, by_code, phrases):
    c = (code or "").strip().upper()
    t = (ctype or "").strip().upper()
    d = desc or ""

    def items(system, codes):
        return "; ".join(sorted({i for k in codes for i in by_code.get((system, k), ())}))
    if t in ("REV", "REVCODE", "REVENUE", "RC") or re.fullmatch(r"0\d{3}", c):
        return "revenue code", "revenue code", c.zfill(4), items("revenue code", [c.zfill(4)]), "high"
    if re.fullmatch(r"\d{4}[0-9A-Z]|[A-V]\d{4}", c):
        sysname = "CPT" if c[0].isdigit() else "HCPCS Level II"
        return "same as a CPT/HCPCS code", sysname, c, items("CPT", [c]) or items("HCPCS Level II", [c]), "high"
    found = re.findall(r"\b(\d{4}[0-9A-Z]|[A-V]\d{4})\b", d.upper())
    if found:
        return ("codes in description", "CPT/HCPCS", " | ".join(dict.fromkeys(found)),
                items("CPT", found), "medium")
    drg = re.findall(r"\bDRG\s*#?\s*(\d{3})\b", d.upper())
    if drg or re.fullmatch(r"\d{3}", c):
        ds = drg or [c]
        return "DRG number", "MS-DRG (assumed)", " | ".join(ds), items("MS-DRG", ds), "medium" if drg else "low"
    nd = norm(d)
    hits = sorted({item for p, item in phrases.items() if f" {p} " in f" {nd} "})
    if hits:
        return "care item by name", "", "", "; ".join(hits), "low (name match)"
    return "no tie found", "", "", "", ""


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

    out_rows = []
    for (ins, ct, code, desc), e in rows.items():
        how, sysname, tied, items, conf = tie(ct, code, desc, by_code, phrases)
        out_rows.append(dict(insurer=ins, code_type_as_written=ct, code=code, insurer_description=desc,
                             ties_to=how, tied_code_system=sysname, tied_code=tied, tied_care_items=items,
                             how_sure=conf, networks=len(e["networks"]), areas=" | ".join(sorted(e["areas"])),
                             example_network=sorted(e["networks"])[0] if e["networks"] else ""))
    out_rows.sort(key=lambda r: (r["insurer"], r["code_type_as_written"], r["code"]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "insurer_codes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(out_rows[0].keys()) if out_rows else ["insurer"])
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
    md += [f"| {t or '(blank)'} | {n:,} |" for t, n in by_type.most_common(40)]
    md += ["", "## How they tie back", "", "| Ties to | Codes |", "|---|---|"]
    md += [f"| {t} | {n:,} |" for t, n in by_tie.most_common()]
    md += ["", "## By insurer", "", "| Insurer | Codes | With no tie |", "|---|---|---|"]
    md += [f"| {i or '(unknown table)'} | {n:,} | {no_tie.get(i, 0):,} |" for i, n in by_ins.most_common(60)]
    (OUT / "insurer_codes_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
