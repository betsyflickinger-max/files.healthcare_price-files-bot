"""CMS Provider Data Catalog history as query-ready tables (Nov 24, 2026, Betsy: "pull these into a database").

Step 2 after quality/pdc_archive.py. Reads the CMS zips already saved in raw/cms_provider_data/ and writes tables that
DuckDB / MotherDuck can query in place. Nothing is estimated, averaged or dropped: every value is CMS's own text.

  tables   Every CSV in every release, converted as-is (all columns kept as text, CMS's own column names), plus three
           columns saying where each row came from: _release, _source_zip, _source_file.
             reference/cms_provider_data/tables/<topic>/<table>/<release>.parquet
             reference/cms_provider_data/catalog.csv      one row per file: rows, columns, status (and why, if not converted)
  trends   Hospitals only, built from the tables above:
             reference/cms_provider_data/hospitals/hospital_general.parquet    one row per hospital per release (stars, type, owner)
             reference/cms_provider_data/hospitals/hospital_measures.parquet   one row per hospital, measure and release
             reference/cms_provider_data/hospitals/measure_changes.csv         each measure's first and last release and names used
           Hospitals are keyed by CCN (CMS Certification Number), kept as CMS wrote it, left-padded to 6 digits.

A CSV that cannot be read cleanly is NOT partly loaded: it is listed in the catalog with the reason.
Run: python quality/pdc_tables.py tables [--work /mnt/pdc] [--topics hospitals] ; python quality/pdc_tables.py trends
"""
import argparse
import csv
import datetime as dt
import io
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import duckdb

E = os.environ
B = E.get("R2_BUCKET") or "upfrontdfwdata"
TODAY = dt.date.today().isoformat()
MANIFEST = "bot/cms_provider_data/manifest.csv"
OUT = "reference/cms_provider_data/"
CATALOG = OUT + "catalog.csv"
DONE = OUT + "tables/_done.csv"
CAT_COLS = ["topic", "table", "release", "rows", "columns", "status", "note", "source_zip", "source_file", "key", "built_on"]
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"


def s3():
    import boto3
    return boto3.client("s3", endpoint_url=(E.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                        aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                        region_name=E.get("STORAGE_REGION") or "auto")


def get_csv(c, key):
    try:
        return list(csv.DictReader(io.StringIO(c.get_object(Bucket=B, Key=key)["Body"].read().decode())))
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return []
        raise


def put_csv(c, key, rows, cols):
    s = io.StringIO()
    w = csv.DictWriter(s, cols)
    w.writeheader()
    w.writerows(rows)
    c.put_object(Bucket=B, Key=key, Body=s.getvalue().encode(), ContentType="text/csv")


def table_name(member):
    """One steady table name for the same CMS file across years (CMS renames files; the catalog shows every mapping)."""
    n = member.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    n = re.sub(r"^[A-Za-z0-9]+-[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}_", "", n).lower()
    n = re.sub(r"[^a-z0-9]+", "_", n)
    n = re.sub(rf"_({MONTHS})_\d{{4}}", "", n)
    n = re.sub(r"_\d{1,2}_\d{1,2}_\d{2,4}(?=_|$)", "", n)
    n = re.sub(r"_\d{4}_\d{2}_\d{2}(?=_|$)", "", n)
    n = re.sub(r"_pr\d\dq\d_\d\dq\d", "", n)
    n = re.sub(r"(^|_)fy_?\d{4}(?=_|$)", r"\1fy", n)
    n = re.sub(r"_\d$", "", n)
    return re.sub(r"_+", "_", n).strip("_") or "unnamed"


def q(s):
    return str(s).replace("'", "''")


def to_parquet(con, src, out, release, source_zip, member, clean=False):
    """CSV -> parquet, every column as text. Raises if any row cannot be read (nothing is skipped or padded)."""
    opts = ", delim=',', quote='\"', escape='\"'" if clean else ""
    con.execute(
        f"copy (select *, '{q(release)}' as _release, '{q(source_zip)}' as _source_zip, '{q(member)}' as _source_file "
        f"from read_csv('{q(src)}', all_varchar=true, header=true, parallel=false, max_line_size=50000000{opts})) "
        f"to '{q(out)}' (format parquet, compression zstd)")
    n = con.execute(f"select count(*) from read_parquet('{q(out)}')").fetchone()[0]
    cols = len(con.execute(f"describe select * from read_parquet('{q(out)}')").fetchall()) - 3
    return n, cols


def rewrite_clean(src):
    """Second try for files DuckDB will not read as they are (older CMS files: UTF-16 or Windows-1252 text, mixed line
    endings, loose quoting). Python's CSV reader re-saves the same cells as standard UTF-8 CSV. Guard: every row must
    have exactly as many cells as the header, otherwise the file is refused. Returns (path, rows)."""
    raw = Path(src).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
    del raw
    csv.field_size_limit(1 << 30)
    tab = text[:2000].count("\t") > text[:2000].count(",")
    rd = csv.reader(io.StringIO(text, newline=""), delimiter="\t" if tab else ",")
    dst = str(src) + ".clean.csv"
    n = 0
    try:
        with open(dst, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
            head = next(rd)
            w.writerow(head)
            for i, row in enumerate(rd, 2):
                if not any(row):
                    continue   # blank line
                if len(row) != len(head):
                    raise ValueError(f"line {i} has {len(row)} cells, the header has {len(head)}")
                w.writerow(row)
                n += 1
    except Exception:
        Path(dst).unlink(missing_ok=True)
        raise
    return dst, n


def convert_release(con, zpath, topic, release, source_zip, W, upload):
    """Every CSV in one release zip -> one parquet each. Returns catalog rows."""
    rows = []
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            if m.endswith("/") or not m.lower().endswith(".csv"):
                continue
            t = table_name(m)
            key = f"{OUT}tables/{topic}/{t}/{release}.parquet"
            src = W / "in.csv"
            out = W / "out.parquet"
            with z.open(m) as fi, open(src, "wb") as fo:
                shutil.copyfileobj(fi, fo, 8 << 20)
            row = dict(topic=topic, table=t, release=release, rows="", columns="", status="", note="",
                       source_zip=source_zip, source_file=m, key="", built_on=TODAY)
            try:
                if src.stat().st_size == 0:
                    raise ValueError("empty file")
                try:
                    n, k = to_parquet(con, src, out, release, source_zip, m)
                except Exception:
                    u, expect = rewrite_clean(src)
                    try:
                        n, k = to_parquet(con, u, out, release, source_zip, m, clean=True)
                        if n != expect:
                            raise ValueError(f"row count changed on re-save: {expect} read, {n} loaded")
                        row["note"] = "re-saved as standard CSV before loading (same cells; every row matched the header)"
                    finally:
                        Path(u).unlink(missing_ok=True)
                upload(str(out), key)
                row.update(rows=n, columns=k, status="converted", key=key)
            except Exception as e:
                row.update(status="NOT converted", note=str(e).replace("\n", " ")[:300])
            rows.append(row)
            src.unlink(missing_ok=True)
            out.unlink(missing_ok=True)
    return rows


def releases_in(zpath, row, W):
    """(release, path to a release zip). Yearly zips hold one zip per release; a release zip is itself."""
    if row["kind"] != "yearly":
        yield row["release"], zpath
        return
    with zipfile.ZipFile(zpath) as z:
        inner = [m for m in z.namelist() if m.lower().endswith(".zip")]
        if not inner:   # a yearly zip with CSVs directly inside
            yield row["release"], zpath
            return
        for m in sorted(inner):
            d = re.search(r"(\d{4}-\d{2}-\d{2})", m)
            p = W / "inner.zip"
            with z.open(m) as fi, open(p, "wb") as fo:
                shutil.copyfileobj(fi, fo, 8 << 20)
            yield (d.group(1) if d else m.rsplit("/", 1)[-1][:-4]), p
            p.unlink(missing_ok=True)


def cmd_tables(a):
    W = Path(a.work)
    W.mkdir(parents=True, exist_ok=True)
    c = s3()
    con = duckdb.connect()
    t0 = time.time()
    man = get_csv(c, MANIFEST)
    if a.topics:
        man = [r for r in man if r["topic"] in a.topics.split(",")]
    size = {}
    for r in man:
        size[r["topic"]] = size.get(r["topic"], 0) + int(r["bytes"])
    man.sort(key=lambda r: (size[r["topic"]], r["topic"], r["release"]))   # smallest topics first
    cat = get_csv(c, CATALOG)
    done = {(r["source_zip"], r["release"]) for r in get_csv(c, DONE)}
    zips_done = {r["source_zip"] for r in get_csv(c, DONE) if r.get("whole_zip") == "yes"}
    done_rows = get_csv(c, DONE)
    new, left = 0, 0
    for r in man:
        if r["key"] in zips_done:
            continue
        if time.time() - t0 > a.minutes * 60:
            left += 1
            continue
        zp = W / "outer.zip"
        c.download_file(B, r["key"], str(zp))
        for rel, p in releases_in(zp, r, W):
            if (r["key"], rel) in done:
                continue
            rows = convert_release(con, p, r["topic"], rel, r["key"], W, lambda f, k: c.upload_file(f, B, k))
            cat += rows
            new += len(rows)
            done_rows.append(dict(source_zip=r["key"], release=rel, whole_zip=""))
            done.add((r["key"], rel))
            ok = sum(1 for x in rows if x["status"] == "converted")
            print(f"{r['topic']:38s} {rel}  {ok} of {len(rows)} files converted", flush=True)
        done_rows.append(dict(source_zip=r["key"], release="", whole_zip="yes"))
        put_csv(c, CATALOG, cat, CAT_COLS)
        put_csv(c, DONE, done_rows, ["source_zip", "release", "whole_zip"])
        zp.unlink(missing_ok=True)
    report(cat, new, left)


def report(cat, new, left):
    by = {}
    for r in cat:
        d = by.setdefault(r["topic"], dict(rel=set(), tab=set(), ok=0, bad=0, rows=0))
        d["rel"].add(r["release"])
        if r["status"] == "converted":
            d["ok"] += 1
            d["tab"].add(r["table"])
            d["rows"] += int(r["rows"] or 0)
        else:
            d["bad"] += 1
    bad = [r for r in cat if r["status"] != "converted"]
    L = ["# CMS quality history: query-ready tables", "",
         f"Run {TODAY}. Built from the CMS zips saved in `raw/cms_provider_data/` (list: `{MANIFEST}`). Every CSV is converted "
         f"as-is, all values kept as CMS's own text. Tables: `{OUT}tables/<topic>/<table>/<release>.parquet`. "
         f"Full file list: `{CATALOG}`.", "",
         f"- Files converted this run: {new}", f"- Zips not started (time limit, re-run to finish): {left}",
         f"- Files that could not be converted (listed below, nothing partly loaded): {len(bad)}", "",
         "| Topic | Releases | Tables | Files converted | Rows | Not converted |", "|---|---|---|---|---|---|"]
    L += [f"| {t} | {len(d['rel'])} | {len(d['tab'])} | {d['ok']:,} | {d['rows']:,} | {d['bad']} |" for t, d in sorted(by.items())]
    if bad:
        L += ["", "## Not converted", "", "| Topic | Release | File | Why |", "|---|---|---|---|"]
        L += [f"| {r['topic']} | {r['release']} | {r['source_file']} | {r['note'][:160].replace('|', '/')} |" for r in bad[:200]]
        if len(bad) > 200:
            L.append(f"\n({len(bad) - 200} more in the catalog.)")
    out = "\n".join(L) + "\n"
    print(out)
    Path("reports/cms-provider-data").mkdir(parents=True, exist_ok=True)
    Path("reports/cms-provider-data/tables.md").write_text(out)


# ---- hospital trend tables -------------------------------------------------------------------------------------------

ID_COLS = ["facility_id", "provider_id", "provider_number", "cms_certification_number", "ccn"]
MEASURE_COLS = ["measure_id", "hcahps_measure_id", "oas_cahps_measure_id", "payment_measure_id", "triss_measure_id"]
PICK = {   # output column -> CMS column names it may come from (after lower-casing and _ for punctuation), first match wins
    "measure_name": ["measure_name", "hcahps_question", "oas_cahps_question", "payment_measure_name", "measure_description", "triss_question"],
    "score": ["score", "payment", "measure_response"],
    "compared_to_national": ["compared_to_national", "payment_category", "value_of_care_category"],
    "denominator": ["denominator", "number_of_completed_surveys", "sample"],
    "lower_estimate": ["lower_estimate"],
    "higher_estimate": ["higher_estimate"],
    "star_rating": ["patient_survey_star_rating"],
    "answer_percent": ["hcahps_answer_percent"],
    "linear_mean": ["hcahps_linear_mean_value"],
    "start_date": ["start_date", "measure_start_date"],
    "end_date": ["end_date", "measure_end_date"],
    "footnote": ["footnote", "score_footnote", "patient_survey_star_rating_footnote"],
}
GENERAL = {
    "facility_name": ["facility_name", "hospital_name"], "city": ["city_town", "city"], "state": ["state"],
    "zip_code": ["zip_code"], "county": ["county_parish", "county_name"], "hospital_type": ["hospital_type"],
    "hospital_ownership": ["hospital_ownership"], "emergency_services": ["emergency_services"],
    "overall_rating": ["hospital_overall_rating"], "overall_rating_footnote": ["hospital_overall_rating_footnote"],
}


def norm(col):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", col.lower())).strip("_")


def pick(cols, names):
    """SQL for the first CMS column that exists, else NULL."""
    for n in names:
        if n in cols:
            return f'"{cols[n].replace(chr(34), chr(34) * 2)}"'
    return "NULL"


CCN = "case when regexp_matches(trim({c}), '^[0-9]{{1,5}}$') then lpad(trim({c}), 6, '0') else trim({c}) end"


def build_trends(con, files, outdir):
    """files: [(table, local parquet path)] for the hospitals topic. Writes the three outputs into outdir."""
    con.execute("create or replace table hm (release varchar, cms_table varchar, ccn varchar, measure_id varchar, "
                + ", ".join(f"{k} varchar" for k in PICK) + ", source_zip varchar, source_file varchar)")
    con.execute("create or replace table hg (release varchar, ccn varchar, " + ", ".join(f"{k} varchar" for k in GENERAL)
                + ", source_zip varchar, source_file varchar)")
    used, skipped = set(), set()
    for table, p in files:
        cols = {}
        for x in con.execute(f"describe select * from read_parquet('{q(p)}')").fetchall():
            cols.setdefault(norm(x[0]), x[0])
        idc = pick(cols, ID_COLS)
        if idc == "NULL":
            skipped.add(table)
            continue
        ccn = CCN.format(c=idc)
        if table == "hospital_general_information":
            con.execute(f"insert into hg select _release, {ccn}, " + ", ".join(pick(cols, v) for v in GENERAL.values())
                        + f", _source_zip, _source_file from read_parquet('{q(p)}')")
            used.add(table)
            continue
        mc = pick(cols, MEASURE_COLS)
        if mc == "NULL":
            skipped.add(table)
            continue
        con.execute(f"insert into hm select _release, '{q(table)}', {ccn}, {mc}, " + ", ".join(pick(cols, v) for v in PICK.values())
                    + f", _source_zip, _source_file from read_parquet('{q(p)}')")
        used.add(table)
    o = Path(outdir)
    con.execute(f"copy (select * from hg order by ccn, release) to '{q(o / 'hospital_general.parquet')}' (format parquet, compression zstd)")
    con.execute(f"copy (select * from hm order by cms_table, measure_id, ccn, release) to '{q(o / 'hospital_measures.parquet')}' (format parquet, compression zstd)")
    con.execute(f"""copy (select cms_table, measure_id, min(release) first_release, max(release) last_release,
        count(distinct release) releases, count(distinct ccn) hospitals_ever, count(distinct measure_name) names_used,
        string_agg(distinct measure_name, ' || ') measure_names
        from hm group by all order by cms_table, measure_id) to '{q(o / 'measure_changes.csv')}' (header, delimiter ',')""")
    st = dict(
        general_rows=con.execute("select count(*) from hg").fetchone()[0],
        general_releases=con.execute("select count(distinct release) from hg").fetchone()[0],
        general_hospitals=con.execute("select count(distinct ccn) from hg").fetchone()[0],
        measure_rows=con.execute("select count(*) from hm").fetchone()[0],
        measure_releases=con.execute("select count(distinct release) from hm").fetchone()[0],
        measures=con.execute("select count(*) from (select distinct cms_table, measure_id from hm)").fetchone()[0],
        first=con.execute("select min(release) from hm").fetchone()[0], last=con.execute("select max(release) from hm").fetchone()[0],
        ended=con.execute("select count(*) from (select cms_table, measure_id from hm group by all having max(release) < (select max(release) from hm))").fetchone()[0],
        used=sorted(used), skipped=sorted(skipped))
    return st


def cmd_trends(a):
    W = Path(a.work) / "trends"
    W.mkdir(parents=True, exist_ok=True)
    c = s3()
    (W / "t.duckdb").unlink(missing_ok=True)
    con = duckdb.connect(str(W / "t.duckdb"))   # on disk: the full history is tens of millions of rows
    want = {r["key"] for r in get_csv(c, MANIFEST) if r["topic"] == "hospitals"}
    have = {r["source_zip"] for r in get_csv(c, DONE) if r.get("whole_zip") == "yes"}
    if want - have:   # never build trends from part of the history and present it as the whole
        raise SystemExit(f"Hospital tables are not complete yet: {len(want & have)} of {len(want)} saved zips converted. "
                         "Run the tables step again, then trends.")
    cat = [r for r in get_csv(c, CATALOG) if r["topic"] == "hospitals" and r["status"] == "converted"]
    if not cat:
        raise SystemExit("No hospital tables yet. Run: python quality/pdc_tables.py tables --topics hospitals")
    files = []
    for i, r in enumerate(cat):
        p = W / f"{i}.parquet"
        c.download_file(B, r["key"], str(p))
        files.append((r["table"], str(p)))
    st = build_trends(con, files, W)
    for f in ("hospital_general.parquet", "hospital_measures.parquet", "measure_changes.csv"):
        c.upload_file(str(W / f), B, OUT + "hospitals/" + f)
    L = ["# Hospital quality over time (CMS), keyed by CCN", "",
         f"Run {TODAY}. Built from every hospitals release CMS has in its archive, {st['first']} to {st['last']}. "
         "Every value is CMS's own; nothing is estimated or averaged. Each row names the CMS zip and file it came from.", "",
         f"- `{OUT}hospitals/hospital_general.parquet`: {st['general_rows']:,} rows, {st['general_hospitals']:,} hospitals, {st['general_releases']} releases (overall star rating, type, ownership)",
         f"- `{OUT}hospitals/hospital_measures.parquet`: {st['measure_rows']:,} rows, {st['measures']:,} measures, {st['measure_releases']} releases",
         f"- `{OUT}hospitals/measure_changes.csv`: each measure's first and last release and every name CMS used for it; "
         f"{st['ended']:,} measures are not in the newest release (ended or renamed)", "",
         "Caution for trend lines: CMS adds, drops and redefines measures, and changed how the overall star rating is "
         "worked out for the April 2021 release. Check `measure_changes.csv` before comparing across years.", "",
         "## CMS tables used (" + str(len(st["used"])) + ")", "", ", ".join(st["used"]), "",
         "## CMS tables not in the trend tables (no hospital number or no measure column; still query-ready as-is) (" + str(len(st["skipped"])) + ")", "",
         ", ".join(st["skipped"])]
    out = "\n".join(L) + "\n"
    print(out)
    Path("reports/cms-provider-data").mkdir(parents=True, exist_ok=True)
    Path("reports/cms-provider-data/hospital-trends.md").write_text(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["tables", "trends"])
    p.add_argument("--work", default="/tmp/pdc")
    p.add_argument("--topics", default="")
    p.add_argument("--minutes", type=int, default=300)
    a = p.parse_args()
    (cmd_tables if a.cmd == "tables" else cmd_trends)(a)


if __name__ == "__main__":
    main()
