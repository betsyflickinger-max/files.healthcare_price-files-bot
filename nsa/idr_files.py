"""No Surprises Act arbitration files (CMS Federal IDR public use files): save the originals, build national tables.

When an out-of-network provider and a health plan can't agree on a surprise-bill payment, a certified arbitrator
(IDR entity) picks one side's offer. CMS publishes every dispute line, twice a year (2023 Q1 onward):
https://www.cms.gov/nosurprises/policies-and-resources/Reports

Three tables per quarter, national, every row kept:
  disputes       emergency and non-emergency disputes: provider name + NPI, plan/issuer name, state of service,
                 specialty, service code, who won, offers and prevailing offer as a share of the QPA
  air_ambulance  the same for air ambulance disputes
  qpa_offers     the dollar amounts: QPA, both offers, prevailing offer, by service code and metro area (MSA);
                 CMS doesn't link these rows to the dispute tables. Blanked ("^") where a code had fewer than 10
                 lines in a region.
Every value is kept exactly as CMS wrote it. Dollar and percent columns also get a plain numeric copy
(<column>_num; percents as a ratio, so 164% = 1.64), because CMS writes them differently by year ("1,046%",
"$660.00", 1.64). Symbols like ^, N/A, N/R and * stay in the text column and are blank in the numeric one.

Output (R2):
  raw/idr/<sha12>_<file name>            every CMS file as downloaded (PUFs, data dictionary, supplemental tables)
  data/idr/<table>/<yyyy-qN>.parquet     the national tables (all text columns + _num columns + period, source)
  bot/idr/manifest.csv                   what was saved and when
  reports/idr/latest.md                  row counts per quarter (committed to the repo)

Run: python nsa/idr_files.py [--force] [--only 2025-q4] [--local]
"""
import argparse
import csv
import hashlib
import io
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))

PAGE = "https://www.cms.gov/nosurprises/policies-and-resources/Reports"
UA = {"User-Agent": "Mozilla/5.0 (compatible; price-files-bot; +https://github.com/betsyflickinger-max/price-files-bot)"}
TODAY = date.today().isoformat()
ROOT = Path(__file__).resolve().parent.parent
MAN_KEY = "bot/idr/manifest.csv"
MAN_FIELDS = ["url", "name", "kind", "period", "etag", "last_modified", "size", "sha256", "r2_key", "first_saved",
              "last_checked", "tables_built"]
MONEY = {"qpa", "provider_facility_offer", "health_plan_issuer_offer", "prevailing_offer", "idre_compensation",
         "cost_sharing_amount", "initial_payment_amount"}
csv.field_size_limit(sys.maxsize)


# ---------------------------------------------------------------- storage (R2, or ./local when testing)

class Store:
    def __init__(self, local):
        self.local = local
        if not local:
            import store
            self.s3, self.bucket = store.r2()

    def put(self, key, data=None, path=None):
        if self.local:
            p = ROOT / "local" / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if data is not None else Path(path).read_bytes())
        elif path:
            self.s3.upload_file(str(path), self.bucket, key)
        else:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key):
        try:
            if self.local:
                return (ROOT / "local" / key).read_bytes()
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            return None


# ---------------------------------------------------------------- finding and saving the files

def list_files():
    """Every PUF, data dictionary and supplemental-table link on CMS's reports page."""
    html = requests.get(PAGE, headers=UA, timeout=120).text
    out = {}
    for href in re.findall(r'href="([^"]+\.(?:zip|xlsx|csv))"', html, re.I):
        url = href if href.startswith("http") else "https://www.cms.gov" + href
        name = url.rsplit("/", 1)[-1]
        if "federal-idr" not in name.lower():
            continue
        m = re.search(r"(20\d\d)-q([1-4])", name.lower())
        kind = "puf" if "federal-idr-puf-20" in name.lower() else ("dictionary" if "dictionary" in name.lower() else "supplemental")
        out[url] = dict(url=url, name=name, kind=kind, period=f"{m.group(1)}-q{m.group(2)}" if m else "")
    return list(out.values())


def head(url):
    r = requests.head(url, headers=UA, timeout=60, allow_redirects=True)
    h = r.headers
    return dict(etag=h.get("ETag", ""), last_modified=h.get("Last-Modified", ""), size=h.get("Content-Length", ""))


def download(url, dest):
    with requests.get(url, headers=UA, timeout=600, stream=True) as r:
        r.raise_for_status()
        sha = hashlib.sha256()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                sha.update(chunk)
    return sha.hexdigest()


# ---------------------------------------------------------------- reading the files

def col_name(h):
    s = str(h).strip().lower().replace("%", " pct ").replace("percent", "pct").replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return {"ambulance_vehicle_type": "air_ambulance_vehicle_type",
            "ambulance_vehicle_clinical_capacity_level": "air_ambulance_vehicle_clinical_capacity_level"}.get(s, s)


def table_for(label):
    l = re.sub(r"[-_]+", " ", label.lower())
    if "qpa" in l:
        return "qpa_offers"
    if "air ambulance" in l:
        return "air_ambulance"
    if "emergency" in l:
        return "disputes"
    return None


def text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def number(col, v):
    """Numeric copy of a dollar or percent value, exactly as written. Blank for symbols (^, N/A, N/R, *)."""
    s = v.replace(",", "").replace("$", "").strip()
    pct = s.endswith("%")
    s = s.rstrip("%").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return x / 100 if pct else x


def num_cols(cols):
    return [c for c in cols if c in MONEY or "_pct_" in f"_{c}_"]


def rows_xlsx(path):
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(str(path))
    for sheet in wb.sheet_names:
        t = table_for(sheet)
        if t:
            yield t, wb.get_sheet_by_name(sheet).iter_rows()


def rows_zip(path):
    z = zipfile.ZipFile(path)
    for info in z.infolist():
        if info.filename.lower().endswith(".csv"):
            t = table_for(info.filename)
            if t:
                yield t, csv.reader(io.TextIOWrapper(z.open(info), encoding="utf-8-sig", errors="replace", newline=""))


def build_tables(path, f, store, batch=250_000):
    """Write data/idr/<table>/<period>.parquet for each table in one CMS file. Returns {table: rows}."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    counts = {}
    reader = rows_zip(path) if path.suffix == ".zip" else rows_xlsx(path)
    for table, it in reader:
        header = None
        out = ROOT / "work" / f"{table}_{f['period']}.parquet"
        out.parent.mkdir(exist_ok=True)
        writer, buf, n, t0 = None, [], 0, time.time()

        def flush():
            nonlocal writer
            if not buf:
                return
            cols = {c: [r[i] for r in buf] for i, c in enumerate(header)}
            for c in num_cols(header):
                cols[c + "_num"] = [number(c, v) for v in cols[c]]
            cols.update(period=[f["period"]] * len(buf), source_file=[f["name"]] * len(buf),
                        source_url=[f["url"]] * len(buf), checked_on=[TODAY] * len(buf))
            tbl = pa.table(cols)
            if writer is None:
                writer = pq.ParquetWriter(out, tbl.schema, compression="zstd")
            writer.write_table(tbl)
            buf.clear()

        for raw in it:
            vals = [text(v) for v in raw]
            if header is None:
                if sum(1 for v in vals if v) >= 5:  # first real header row
                    header = [col_name(v) or f"col_{i}" for i, v in enumerate(vals)]
                continue
            if sum(1 for v in vals if v) < 3:  # blank rows and footnotes
                continue
            vals = (vals + [""] * len(header))[:len(header)]
            if "provider_facility_npi_number" in header:
                i = header.index("provider_facility_npi_number")
                vals[i] = re.sub(r"\.0$", "", vals[i])
            buf.append(vals)
            n += 1
            if len(buf) >= batch:
                flush()
        flush()
        if writer:
            writer.close()
            store.put(f"data/idr/{table}/{f['period']}.parquet", path=out)
            out.unlink()
        counts[table] = n
        print(f"    {table}: {n:,} rows ({time.time() - t0:.0f} s)", flush=True)
    return counts


# ---------------------------------------------------------------- report

def report(man, counts_by_period, store):
    """Counts only, from the tables just built plus the previous report's counts for periods not rebuilt."""
    L = ["# No Surprises Act arbitration files (CMS Federal IDR PUFs)", "",
         f"Checked {TODAY}. Source: {PAGE}. Originals saved untouched in R2 raw/idr/; national tables in "
         "data/idr/<table>/<quarter>.parquet. Counts only; nothing estimated.", "",
         "| Quarter | Dispute lines (emergency + non-emergency) | Air ambulance lines | QPA + offer lines | Texas dispute lines | Dallas-Fort Worth QPA lines | Provider won (dispute lines) |",
         "|---|---|---|---|---|---|---|"]
    for p in sorted(counts_by_period, reverse=True):
        c = counts_by_period[p]
        L.append(f"| {p} | {c.get('disputes', 0):,} | {c.get('air_ambulance', 0):,} | {c.get('qpa_offers', 0):,} | "
                 f"{c.get('tx', 0):,} | {c.get('dfw', 0):,} | {c.get('provider_won', 0):,} |")
    L += ["", "## Files saved", ""] + [f"- {m['name']} ({int(m['size'] or 0) / 1e6:,.1f} MB), first saved {m['first_saved']}: `{m['r2_key']}`"
                                        for m in sorted(man.values(), key=lambda m: m["name"])]
    out = ROOT / "reports" / "idr" / "latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    store.put("bot/idr/counts.csv", "\n".join(
        ["period,disputes,air_ambulance,qpa_offers,tx,dfw,provider_won"] +
        [f"{p}," + ",".join(str(c.get(k, 0)) for k in ("disputes", "air_ambulance", "qpa_offers", "tx", "dfw", "provider_won"))
         for p, c in sorted(counts_by_period.items())]).encode())
    print(f"  report -> {out}")


def extra_counts(store, period):
    """Texas lines, DFW lines and provider wins for one quarter, read back from the saved tables."""
    import pyarrow.parquet as pq
    c = {}
    for table, fn in (("disputes", "tx"), ("qpa_offers", "dfw")):
        b = store.get(f"data/idr/{table}/{period}.parquet")
        if not b:
            continue
        cols = ["location_of_service", "payment_determination_outcome"] if table == "disputes" else ["geographical_region"]
        t = pq.read_table(io.BytesIO(b), columns=[x for x in cols if x in pq.read_schema(io.BytesIO(b)).names]).to_pydict()
        if table == "disputes":
            c["tx"] = sum(1 for s in t.get("location_of_service", []) if s.upper() == "TX")
            c["provider_won"] = sum(1 for s in t.get("payment_determination_outcome", []) if "provider" in s.lower())
        else:
            c["dfw"] = sum(1 for s in t.get("geographical_region", []) if s.lower().startswith("dallas"))
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild tables even if CMS's files are unchanged")
    ap.add_argument("--only", default="", help="only this quarter, e.g. 2025-q4")
    ap.add_argument("--local", action="store_true", help="write to ./local/ instead of R2")
    a = ap.parse_args()
    store = Store(a.local)
    prev = store.get(MAN_KEY)
    man = {r["url"]: r for r in csv.DictReader(io.StringIO(prev.decode()))} if prev else {}
    prev_counts = store.get("bot/idr/counts.csv")
    counts = {r["period"]: {k: int(v) for k, v in r.items() if k != "period"}
              for r in csv.DictReader(io.StringIO(prev_counts.decode()))} if prev_counts else {}
    files = list_files()
    print(f"{len(files)} files on CMS's page", flush=True)
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    for f in sorted(files, key=lambda f: f["name"]):
        if a.only and f["period"] != a.only:
            continue
        m = man.get(f["url"], {})
        h = head(f["url"])
        same = m.get("sha256") and any(h.values()) and all(h[k] == m.get(k) for k in ("etag", "last_modified", "size") if h[k])
        need_tables = f["kind"] == "puf" and (a.force or m.get("tables_built") != m.get("sha256") or not same)
        m = dict(m, **f, last_checked=TODAY)
        if same and not need_tables:
            man[f["url"]] = m
            continue
        print(f"  {f['name']}", flush=True)
        path = work / f["name"]
        sha = download(f["url"], path)
        m.update(h, sha256=sha)
        if sha != man.get(f["url"], {}).get("sha256"):
            key = f"raw/idr/{sha[:12]}_{f['name']}"
            store.put(key, path=path)
            m.update(r2_key=key, first_saved=TODAY)
            print(f"    saved original -> {key}", flush=True)
        if f["kind"] == "puf":
            try:
                c = build_tables(path, f, store)
                counts[f["period"]] = dict(c, **extra_counts(store, f["period"]))
                m["tables_built"] = sha
            except Exception as e:
                print(f"  ! tables failed for {f['name']}: {type(e).__name__}: {str(e)[:200]}", flush=True)
        path.unlink(missing_ok=True)
        man[f["url"]] = m
        store.put(MAN_KEY, "\n".join([",".join(MAN_FIELDS)] + [
            ",".join('"' + str(r.get(k, "")).replace('"', '""') + '"' for k in MAN_FIELDS) for r in man.values()]).encode())
    report(man, counts, store)


if __name__ == "__main__":
    main()
