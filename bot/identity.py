"""Is this price file really this hospital's? (Oct 15, 2026)

Every CMS price file must give the hospital's own street address (hospital_address). Medicare publishes every hospital's
address by its ID (CCN; reference/geo/medicare_hospitals.csv, from Hospital General Information). A file is ruled the
WRONG HOSPITAL'S when it lists addresses but none of them is in the hospital's state within MILES of its ZIP code.
Found Oct 15 by the map: 16 hospitals on the site were showing another hospital's prices (Baytown Medical Center with
Boston Medical Center's file, Mountain View Hospital AL with an Idaho Falls file, Wellstar Spalding with Wellstar
Paulding's, ...), matched by name similarity years apart from any address check.

Verdicts live in data/wrong_files.csv (kept in git, by hand: verdict "ok" overrides a wrong call, "wrong" adds one) and
R2 bot/manifest/wrong_files.csv (written by the daily run and bot/audit_files.py). Used by:
  run.py          checks each file it downloads; a hospital on a wrong file gets status "wrong hospital's file"
  discover.py     never picks a ruled-out link for that hospital again (from its cms-hpt.txt or the known link)
  search_files.py treats ruled-out links as rejected and searches again for those hospitals
  hosp_area.py / geo_build.py   leave wrong files off the Price Finder pages and maps
"""
import csv
import io
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MILES = 30
WRONG_STATUS = "wrong hospital's file"
FIELDS = ["ccn", "mrf_url", "verdict", "reason", "file_address", "checked_at", "by"]
_MED, _ZIP = None, None


def medicare():
    global _MED
    if _MED is None:
        _MED = {r["ccn"]: r for r in csv.DictReader(open(ROOT / "reference" / "geo" / "medicare_hospitals.csv", encoding="utf-8"))}
    return _MED


def zips():
    global _ZIP
    if _ZIP is None:
        _ZIP = {r["zip"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(ROOT / "reference" / "geo" / "zip_points.csv"))}
    return _ZIP


def miles(a, b):
    t = math.pi / 180
    h = math.sin((b[0] - a[0]) * t / 2) ** 2 + math.cos(a[0] * t) * math.cos(b[0] * t) * math.sin((b[1] - a[1]) * t / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def address_text(text):
    """The hospital_address value(s) from the top of a CMS price file (CSV or JSON), as one string ('' if none)."""
    head = text[:300000]
    if head.lstrip()[:1] in "{[":
        out = []
        for m in re.finditer(r'"hospital_address"\s*:\s*(\[[^\]]*\]|"[^"]*")', head):
            try:
                v = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            out += v if isinstance(v, list) else [v]
        return " | ".join(str(x) for x in out)
    rows = list(csv.reader(io.StringIO("\n".join(head.splitlines()[:3]))))
    if len(rows) < 2:
        return ""
    return " | ".join(rows[1][i] for i, c in enumerate(rows[0]) if c.strip().lower().startswith("hospital_address") and i < len(rows[1]))


def places(addr):
    """[(state, zip5)] for each street address in a hospital_address value; P.O. boxes (billing addresses) skipped."""
    out = []
    for part in re.split(r"\s*[|;]\s*|\n", addr or ""):
        if re.search(r"\bP\.?\s*O\.?\s*BOX\b|\bPOB\b|\bPO DRAWER\b", part, re.I):
            continue
        out += [(m.group(1).upper(), m.group(2)) for m in re.finditer(r"\b([A-Za-z]{2})\b\.?,?\s+(\d{5})(?:-\d{4})?\b", part)
                if m.group(1).upper() in STATES]
    return out


def names_text(text):
    """hospital_name / location_name values from the top of a CMS price file."""
    head = text[:300000]
    out = []
    if head.lstrip()[:1] in "{[":
        for k in ("hospital_name", "location_name"):
            for m in re.finditer(rf'"{k}"\s*:\s*(\[[^\]]*\]|"[^"]*")', head):
                try:
                    v = json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
                out += v if isinstance(v, list) else [v]
    else:
        rows = list(csv.reader(io.StringIO("\n".join(head.splitlines()[:3]))))
        if len(rows) >= 2:
            for i, c in enumerate(rows[0]):
                if i < len(rows[1]) and c.strip().lower().startswith(("hospital_name", "location_name")):
                    out += rows[1][i].split("|")
    return [str(x).strip() for x in out if str(x).strip()]


def _city(s):
    s = re.sub(r"[^A-Z ]", " ", (s or "").upper().replace("SAINT ", "ST ").replace("FORT ", "FT ").replace("MOUNT ", "MT "))
    return " ".join(s.split())


def check(ccn, addr, names=(), other_names=()):
    """('', '') when the file fits the hospital or can't be judged; ('wrong', why) when it is another hospital's file;
    ('check', why) when the address is elsewhere in the state but the file names this hospital (a system file listing its
    headquarters, or a sister hospital with the same name): left in place and listed for a hand check.
    Fits = an address in the hospital's state within MILES of its Medicare ZIP code, or naming its Medicare city (a few
    files have a mistyped ZIP code)."""
    h = medicare().get(ccn)
    ps = places(addr)
    if not h or not ps:
        return "", ""
    Z = zips()
    hz = Z.get(h["zip"])
    for st, z in ps:
        if st == h["state"] and (not hz or not Z.get(z) or miles(hz, Z[z]) <= MILES):
            return "", ""
    city = _city(h["city"])
    if city and any(st == h["state"] for st, _ in ps) and re.search(rf"\b{re.escape(city)}\b", _city(addr)):
        return "", ""
    far = [f"{st} {z}" + (f" ({round(miles(hz, Z[z]))} mi away)" if hz and Z.get(z) else "") for st, z in ps[:3]]
    why = (f"file gives its address as {', '.join(far)}; Medicare's address for {h['name'].title()} (CCN {ccn}) is "
           f"{h['address'].title()}, {h['city'].title()} {h['state']} {h['zip']}")
    from name_ok import name_ok
    ours = [h["name"], *other_names]
    named = [n for n in names if any(name_ok(o, n) and name_ok(n, o) for o in ours)]
    if named and any(st == h["state"] for st, _ in ps):
        return "check", why + f"; but the file names '{named[0][:60]}'"
    return "wrong", why


def from_file(path):
    """(address, names) a downloaded original gives for itself; ('', []) when unreadable. Never raises."""
    try:
        import reader
        with reader.sniff_open(path) as f:
            t = f.read(1_500_000).decode("utf-8-sig", "replace")
        return address_text(t), names_text(t)
    except Exception:
        return "", []


def load(s3=None, bucket=None):
    """{(ccn, url): row} from data/wrong_files.csv and (if given) R2; hand rows win over automatic ones."""
    out = {}
    if s3 is not None:
        try:
            body = s3.get_object(Bucket=bucket, Key="bot/manifest/wrong_files.csv")["Body"].read().decode()
            for r in csv.DictReader(io.StringIO(body)):
                out[(r["ccn"], r["mrf_url"])] = r
        except Exception:
            pass
    p = ROOT / "data" / "wrong_files.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            out[(r["ccn"], r["mrf_url"])] = dict(r, by=r.get("by") or "hand")
    return out


def is_wrong(table, ccn, url):
    """Ruled another hospital's file (automatically or by hand), and not overruled by a hand "ok"."""
    r = table.get((ccn, url))
    return bool(r) and r.get("verdict") == "wrong"


def save(s3, bucket, new_rows, checked=None):
    """Merge rows into R2 bot/manifest/wrong_files.csv (never overwrites a hand verdict). checked: every (ccn, url) just
    re-checked, so an automatic verdict that no longer holds is dropped."""
    cur = {}
    try:
        body = s3.get_object(Bucket=bucket, Key="bot/manifest/wrong_files.csv")["Body"].read().decode()
        cur = {(r["ccn"], r["mrf_url"]): r for r in csv.DictReader(io.StringIO(body))}
    except Exception:
        pass
    for k in list(checked or ()):
        if cur.get(k, {}).get("by") not in (None, "hand"):
            cur.pop(k, None)
    for r in new_rows:
        k = (r["ccn"], r["mrf_url"])
        if cur.get(k, {}).get("by") == "hand":
            continue
        cur[k] = r
    out = io.StringIO()
    w = csv.DictWriter(out, FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(sorted(cur.values(), key=lambda r: (r["ccn"], r["mrf_url"])))
    s3.put_object(Bucket=bucket, Key="bot/manifest/wrong_files.csv", Body=out.getvalue().encode(), ContentType="text/csv")


STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
             "PA PR RI SC SD TN TX UT VT VA WA WV WI WY".split())
