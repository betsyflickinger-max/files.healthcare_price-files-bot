"""Which Medicare hospital (CMS number, CCN) each hospital price file belongs to, from what the file says about itself
(Nov 10, 2026). Rebuilt on every run; data/hospitals.csv is only the fallback.

What a file says about itself (CMS template, 45 CFR 180.50):
  type 2 NPIs        `type_2_npi` (required since the v2.2 template): the hospital's organization NPIs. CMS's Hospital
                     Enrollments file (R2 data/names/hospital_enrollments.csv: CCN, NPI) and site/med_local (NPI -> CCN)
                     turn them into CMS numbers.
  CCN                a 6-character CMS number written in the file's license field, hospital name or location name.
  state license      `license_number` + state (v2.2+; the bot reads it from every file's header into its file manifest,
                     bot/manifest/files/<state>.csv). There is no public license -> CCN list, so a license matches a CCN
                     only when a file matched by NPI or CCN in this same run carries the same license.
  EIN                CMS's file-name rule (<EIN>_<hospital name>_standardcharges.<ext>), or an `ein` field when the file
                     has one. Same rule as the license: it matches only through another file of this run that was matched
                     by NPI or CCN and has the same EIN, and only when that EIN points to exactly one hospital.
Order: type 2 NPI, CCN in the file, license, EIN, then the bot's hospital list (data/hospitals.csv) as the labeled fallback.
A file whose NPIs point to several hospitals (one file for a whole system) takes the one its CCN text or the bot's list
names among them, and says so.
"""
import re

NPI_RE = re.compile(r"\b\d{10}\b")
CCN_RE = re.compile(r"\b\d{2}[0-9A-Z]\d{3}\b")
EIN_RE = re.compile(r"(?:^|/)(\d{2}-?\d{7})_[^/]*standardcharges", re.I)
M_NPI, M_NPI_CCN, M_NPI_LIST = ("type 2 NPI in the file", "type 2 NPI in the file + CCN in the file (file covers several hospitals)",
                                "type 2 NPI in the file (file covers several hospitals; the bot's list picks one)")
M_CCN, M_LIC, M_EIN = ("CCN written in the file", "state license number in the file (same license as a file matched by NPI/CCN)",
                       "EIN in the file's name (same EIN as a file matched by NPI/CCN, one hospital)")
M_LIST, M_NONE = "bot's hospital list (data/hospitals.csv), fallback", "not matched"
METHODS = (M_NPI, M_NPI_CCN, M_NPI_LIST, M_CCN, M_LIC, M_EIN, M_LIST, M_NONE)


def ein_of(f):
    e = re.sub(r"\D", "", str(f.get("ein") or ""))
    if len(e) == 9:
        return e
    m = EIN_RE.search(str(f.get("url") or ""))
    return re.sub(r"\D", "", m.group(1)) if m else ""


def lic_of(f):
    n = re.sub(r"[^0-9A-Z]", "", str(f.get("license_number") or "").upper())
    return (str(f.get("license_state") or f.get("state") or "").upper(), n) if n else None


def match_files(files, npi_ccn, known, fallback=None):
    """files: [dict(key, state, type_2_npi, license_number, license_state, url, ein, hospital_name, location_name)]
    npi_ccn: {npi: {ccn, ...}}; known: {ccn: state} (CMS hospital records); fallback: {key: ccn} (data/hospitals.csv).
    Returns {key: dict(ccn, method, npis, fallback_ccn, agrees_with_list)}."""
    fallback = fallback or {}
    out, pending = {}, []
    for f in files:
        npis = sorted(set(NPI_RE.findall(str(f.get("type_2_npi") or ""))))
        st = f.get("state")
        ok = lambda c: c in known and (not st or known[c] == st)
        by_npi = {c for n in npis for c in npi_ccn.get(n, ()) if ok(c)}
        text = " ".join(str(f.get(k) or "") for k in ("license_number", "hospital_name", "location_name")).upper()
        by_text = {c for c in CCN_RE.findall(text) if ok(c)}
        fb = fallback.get(f["key"])
        ccn = method = None
        if len(by_npi) == 1:
            ccn, method = next(iter(by_npi)), M_NPI
        elif len(by_npi) > 1 and len(by_text & by_npi) == 1:
            ccn, method = next(iter(by_text & by_npi)), M_NPI_CCN
        elif len(by_npi) > 1 and fb in by_npi:
            ccn, method = fb, M_NPI_LIST
        elif len(by_text) == 1:
            ccn, method = next(iter(by_text)), M_CCN
        out[f["key"]] = dict(ccn=ccn, method=method, npis=npis, fallback_ccn=fb or "")
        if not ccn:
            pending.append(f)
    # license and EIN: only through files matched above in this run, and only when they point to one hospital
    lic, ein = {}, {}
    for f in files:
        m = out[f["key"]]
        if m["ccn"]:
            if lic_of(f):
                lic.setdefault(lic_of(f), set()).add(m["ccn"])
            if ein_of(f):
                ein.setdefault(ein_of(f), set()).add(m["ccn"])
    for f in pending:
        m = out[f["key"]]
        L, E = lic.get(lic_of(f) or ("", ""), set()), ein.get(ein_of(f), set()) if ein_of(f) else set()
        if len(L) == 1:
            m.update(ccn=next(iter(L)), method=M_LIC)
        elif len(E) == 1:
            m.update(ccn=next(iter(E)), method=M_EIN)
        elif m["fallback_ccn"]:
            m.update(ccn=m["fallback_ccn"], method=M_LIST)
        else:
            m.update(method=M_NONE)
    for m in out.values():
        m["agrees_with_list"] = "" if not m["fallback_ccn"] or not m["ccn"] else ("yes" if m["ccn"] == m["fallback_ccn"] else "no")
    return out


def counts(matches):
    c = {k: 0 for k in METHODS}
    for m in matches.values():
        c[m["method"]] = c.get(m["method"], 0) + 1
    return c
