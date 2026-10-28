"""Employer plan lists: which employer (and individual) plans use which insurer network files.

Insurers' table-of-contents ("index") files name every plan they cover: the plan sponsor (the employer), its
EIN or HIOS id, the plan name and market type, and the in-network rate files that plan uses. Joining those file
names to the networks we already read tells an HR team which network, and so which negotiated rates, its plan pays.

Insurers so far (Oct 13, 2026):
  cigna  one public table of contents (cigna.com/static/mrf/latest.json), ~26,000 plans
  uhc    one index file per employer (~68,000) listed at transparency-in-coverage.uhc.com/api/v1/uhc/blobs/

Originals (Oct 20, 2026; Betsy: "what happens if they delete or move them?"): every index file, exactly as downloaded,
goes into one tar per insurer per month with a manifest (name, url, bytes, sha256), saved to
R2 raw/plans/<yyyy-mm>/<insurer>_indexes.tar and to archive.org (item upfront-insurer-index-files-<yyyy-mm>, the same
item index_watch.py uses), so there is a public record even if the insurer later removes or changes a file.

Output, one row per plan per insurer (R2 data/plans/<yyyy-mm>/<insurer>.parquet):
  insurer, plan_sponsor_name, plan_id, plan_id_type, plan_name, plan_market_type, issuer_name,
  in_network_files (file names, ' | '-joined), n_files, source_url, last_updated_on, checked_on
Every row links back to the index it came from. Nothing is estimated.

Run: python plans/employer_plans.py [--insurers cigna,uhc] [--limit N] [--local]
"""
import argparse
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; price-files-bot; +https://github.com/betsyflickinger-max/price-files-bot)"}
TODAY = date.today().isoformat()
MONTH = TODAY[:7]
COLS = ["insurer", "plan_sponsor_name", "plan_id", "plan_id_type", "plan_name", "plan_market_type", "issuer_name",
        "in_network_files", "n_files", "source_url", "last_updated_on", "checked_on"]


ORIGINALS = {}  # insurer -> list of (name, url, raw bytes as downloaded)
_LOCK = threading.Lock()


def get(url, tries=4, timeout=120, keep=None, name=None):
    """Download and (if gzipped) unzip. With keep=<insurer>, also keep the untouched bytes for the archive."""
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            b = r.content
            if keep:
                with _LOCK:
                    ORIGINALS.setdefault(keep, []).append((name or fname(url), url.split("?")[0], b))
            return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def fname(loc):
    return loc.split("?")[0].rstrip("/").split("/")[-1]


def rows_from_toc(insurer, toc, source_url):
    """One row per reporting plan, with the names of every in-network file its reporting structure lists."""
    out = []
    for rs in toc.get("reporting_structure", []):
        files = sorted({fname(f.get("location", "")) for f in rs.get("in_network_files", []) if f.get("location")})
        for p in rs.get("reporting_plans", []):
            pid = str(p.get("plan_id", "")).strip()
            if str(p.get("plan_id_type", "")).lower() == "ein":
                pid = re.sub(r"\D", "", pid)
            out.append(dict(insurer=insurer, plan_sponsor_name=(p.get("plan_sponsor_name") or "").strip(), plan_id=pid,
                            plan_id_type=str(p.get("plan_id_type", "")).lower(), plan_name=(p.get("plan_name") or "").strip(),
                            plan_market_type=(p.get("plan_market_type") or "").lower(), issuer_name=(p.get("issuer_name") or "").strip(),
                            in_network_files=" | ".join(files), n_files=len(files), source_url=source_url,
                            last_updated_on=toc.get("last_updated_on", ""), checked_on=TODAY))
    return out


def cigna(limit=0):
    latest = json.loads(get("https://www.cigna.com/static/mrf/latest.json"))
    url = next(f["url"] for m in latest["mrfs"] if m.get("kind") == "TOC" for f in m["files"])
    toc = json.loads(get(url, timeout=600, keep="cigna"))
    return rows_from_toc("Cigna", toc, url.split("?")[0])


def uhc(limit=0, workers=48):
    listing = json.loads(get("https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/", timeout=600))
    blobs = listing["blobs"] if isinstance(listing, dict) else listing
    idx = [b for b in blobs if b["name"].endswith("_index.json")]
    if limit:
        idx = idx[:limit]
    out, failed = [], []

    def one(b):
        return rows_from_toc("UnitedHealthcare", json.loads(get(b["downloadUrl"], timeout=60, keep="uhc", name=b["name"])), b["downloadUrl"])

    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(one, b): b for b in idx}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                out += f.result()
            except Exception as e:
                failed.append((futs[f]["name"], str(e)[:120]))
            if i % 5000 == 0:
                print(f"  uhc {i:,}/{len(idx):,} index files, {len(out):,} plans, {len(failed)} failed", flush=True)
    print(f"  uhc: {len(idx):,} index files, {len(out):,} plans, {len(failed)} failed", flush=True)
    return out, failed


def save(rows, insurer, local, failed=()):
    import pyarrow as pa
    import pyarrow.parquet as pq
    tbl = pa.table({c: [r[c] for r in rows] for c in COLS})
    buf = io.BytesIO()
    pq.write_table(tbl, buf, compression="zstd")
    key = f"data/plans/{MONTH}/{insurer}.parquet"
    if local:
        p = Path("local") / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(buf.getvalue())
        print(f"  wrote {p} ({len(rows):,} rows)")
        return
    import boto3
    E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    s3.put_object(Bucket=E["R2_BUCKET"], Key=key, Body=buf.getvalue())
    if failed:
        s3.put_object(Bucket=E["R2_BUCKET"], Key=f"data/plans/{MONTH}/{insurer}_failed.json", Body=json.dumps(failed).encode())
    print(f"  uploaded {key} ({len(rows):,} rows)")


def save_originals(insurer, local):
    """One tar of every index file as downloaded, plus manifest.csv; to R2 and archive.org. Never stops the run."""
    files = ORIGINALS.pop(insurer, [])
    if not files:
        return
    import csv
    tmp = Path(tempfile.mkdtemp()) / f"{insurer}_employer_indexes_{MONTH}.tar"
    man = io.StringIO()
    w = csv.writer(man)
    w.writerow(["name", "url", "bytes", "sha256", "downloaded_on"])
    seen = set()
    with tarfile.open(tmp, "w") as tar:
        for name, url, b in sorted(files):
            if name in seen:  # retries can fetch a file twice
                continue
            seen.add(name)
            w.writerow([name, url, len(b), hashlib.sha256(b).hexdigest(), TODAY])
            ti = tarfile.TarInfo(name)
            ti.size = len(b)
            tar.addfile(ti, io.BytesIO(b))
        mb = man.getvalue().encode()
        ti = tarfile.TarInfo("manifest.csv")
        ti.size = len(mb)
        tar.addfile(ti, io.BytesIO(mb))
    size = tmp.stat().st_size
    print(f"  originals: {len(seen):,} {insurer} index files, {size / 1e6:,.0f} MB", flush=True)
    if local:
        p = Path("local") / f"raw/plans/{MONTH}/{insurer}_indexes.tar"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(tmp.read_bytes())
        print(f"  wrote {p}")
        return
    try:
        import boto3
        E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
        s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                          aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
        s3.upload_file(str(tmp), E["R2_BUCKET"], f"raw/plans/{MONTH}/{insurer}_indexes.tar")
        s3.put_object(Bucket=E["R2_BUCKET"], Key=f"raw/plans/{MONTH}/{insurer}_indexes_manifest.csv", Body=mb, ContentType="text/csv")
        print(f"  R2 raw/plans/{MONTH}/{insurer}_indexes.tar", flush=True)
    except Exception as e:
        print(f"! R2 originals {insurer}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    ak, sk = ("".join(os.environ.get(k, "").split()) for k in ("IA_ACCESS_KEY", "IA_SECRET_KEY"))
    if not (ak and sk):
        print("  archive.org keys not set; originals kept in R2 only", flush=True)
        return
    try:
        from internetarchive import upload
        md = dict(title=f"Health insurer price-transparency index files, {MONTH}", mediatype="data", collection="opensource_media",
                  description=("Table-of-contents (index) files that U.S. health insurers post under the Transparency in Coverage "
                               "rule (45 CFR 147.212), saved as posted, so there is a record of which rate files each insurer "
                               "and employer plan said it published that month. Collected for public price-transparency research."),
                  subject="healthcare; price transparency; transparency in coverage; insurer prices; employer health plans")
        rs = upload(f"upfront-insurer-index-files-{MONTH}", files={tmp.name: str(tmp)}, metadata=md,
                    access_key=ak, secret_key=sk, retries=5, retries_sleep=30)
        bad = [r for r in rs if getattr(r, "status_code", 200) >= 300]
        print(f"  archive.org: {'HTTP ' + str(bad[0].status_code) if bad else 'saved'} {tmp.name}", flush=True)
    except Exception as e:  # never let archive.org stop the run
        print(f"! archive.org {insurer}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    finally:
        tmp.unlink(missing_ok=True)


def summary(all_rows):
    """reports/plans/<month>.md: plain counts, committed to the repo by the workflow."""
    from collections import Counter
    L = [f"# Employer plan lists: {MONTH}", "", "Which plans use which insurer network files, from the insurers' own index files. "
         "Counts only; nothing estimated.", "", "| Insurer | Plans | Employer (group) | Individual | Distinct sponsors |", "|---|---|---|---|---|"]
    by = {}
    for r in all_rows:
        by.setdefault(r["insurer"], []).append(r)
    for ins, rs in sorted(by.items()):
        mt = Counter(r["plan_market_type"] for r in rs)
        L.append(f"| {ins} | {len(rs):,} | {mt.get('group', 0):,} | {mt.get('individual', 0):,} | {len({r['plan_id'] or r['plan_sponsor_name'] for r in rs}):,} |")
    for ins, rs in sorted(by.items()):
        files = Counter(f for r in rs for f in r["in_network_files"].split(" | ") if f)
        L += ["", f"## {ins}: network files used by the most plans", ""] + [f"- {f} ({n:,} plans)" for f, n in files.most_common(12)]
    out = Path(__file__).resolve().parent.parent / "reports" / "plans" / f"{MONTH}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"  summary -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insurers", default="cigna,uhc")
    ap.add_argument("--limit", type=int, default=0, help="test: only this many UHC index files")
    ap.add_argument("--local", action="store_true", help="write to ./local/ instead of R2")
    a = ap.parse_args()
    every = []
    for ins in [x.strip() for x in a.insurers.split(",") if x.strip()]:
        t0 = time.time()
        try:
            if ins == "cigna":
                rows, failed = cigna(), []
            elif ins == "uhc":
                rows, failed = uhc(a.limit)
            else:
                print(f"  unknown insurer {ins}"); continue
            save(rows, ins, a.local, failed)
            save_originals(ins, a.local)
            every += rows
            print(f"{ins}: {len(rows):,} plans in {time.time() - t0:.0f} s", flush=True)
        except Exception as e:  # one insurer failing must not stop the others
            print(f"! {ins} failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
    if every:
        summary(every)


if __name__ == "__main__":
    main()
