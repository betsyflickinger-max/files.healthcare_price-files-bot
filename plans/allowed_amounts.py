"""Out-of-network ("allowed amount") files: save every one each month and count what's in them.

Insurers must post what they actually paid for out-of-network services, but only for a service paid out of network
at least 20 times for that plan in the reporting period, so most files are empty today. The Oct 5, 2026 final rule
combines them by market, drops the threshold to 11 claims and lengthens the period (effective about five months after
publication). Collecting now gives a before/after record, and the empty-file count is evidence for the Price File Watch.

Where the files are listed (checked Oct 13, 2026):
  cigna  every reporting structure in the table of contents names one allowed_amount_file (~1,466 distinct; ~24,000
         plans share one "empty" file). About 1.6 MB in all.
  uhc    the blob listing names ~80,000 *_allowed-amounts.json.gz files (one per employer plan); its index files don't
         link them. About 15 MB in all.

Output per insurer per month (R2):
  raw/allowed/<yyyy-mm>/<insurer>.tar         every file as downloaded (untouched bytes)
  data/allowed/<yyyy-mm>/<insurer>.parquet    one row per file: name, source url (no signature), bytes, sha256,
                                              last_updated_on, plan info in the file, services listed, payments
                                              listed, plans pointing to it (cigna), status
  reports/allowed/<yyyy-mm>.md                counts (committed to the repo by the workflow)
Nothing is estimated; the counts come from the files themselves.

Run: python plans/allowed_amounts.py [--insurers cigna,uhc] [--limit N] [--local]
"""
import argparse
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from employer_plans import MONTH, TODAY, UA, fname, get  # noqa: E402

import requests  # noqa: E402

COLS = ["insurer", "file_name", "source_url", "bytes", "sha256", "last_updated_on", "reporting_entity_name",
        "plan_name", "plan_id", "plan_market_type", "services", "payments", "plans_using", "status", "checked_on"]


def raw_get(url, tries=4, timeout=60):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def describe(b):
    """Read one allowed-amount file. Returns the fields it states about itself and how much it reports."""
    j = json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)
    oon = j.get("out_of_network") or []
    pays = sum(len(a.get("payments") or []) for o in oon for a in (o.get("allowed_amounts") or []))
    plans = j.get("reporting_plans") or [j]  # older layout: plan fields at the top level
    p = plans[0] if plans else {}
    return dict(last_updated_on=str(j.get("last_updated_on", "")), reporting_entity_name=j.get("reporting_entity_name", ""),
                plan_name=str(p.get("plan_name", "")), plan_id=str(p.get("plan_id", "")),
                plan_market_type=str(p.get("plan_market_type", "")), services=len(oon), payments=pays)


def cigna_list():
    latest = json.loads(get("https://www.cigna.com/static/mrf/latest.json"))
    url = next(f["url"] for m in latest["mrfs"] if m.get("kind") == "TOC" for f in m["files"])
    toc = json.loads(get(url, timeout=600))
    plans = Counter()
    for rs in toc.get("reporting_structure", []):
        a = rs.get("allowed_amount_file") or {}
        if a.get("location"):
            plans[a["location"]] += len(rs.get("reporting_plans", []))
    return [dict(url=u, plans_using=n) for u, n in plans.items()]


def uhc_list():
    listing = json.loads(get("https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/", timeout=600))
    blobs = listing["blobs"] if isinstance(listing, dict) else listing
    return [dict(url=b["downloadUrl"], plans_using="") for b in blobs if "allowed-amounts" in b["name"]]


def collect(insurer, items, workdir, workers=64):
    tar_path = workdir / f"{insurer}.tar"
    rows, names = [], set()

    def one(it):
        return it, raw_get(it["url"])

    with tarfile.open(tar_path, "w") as tar, cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, it) for it in items]
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                it, b = f.result()
            except Exception as e:
                rows.append(dict(insurer=insurer, file_name="", source_url="", status=f"download failed: {str(e)[:150]}"))
                continue
            name = fname(it["url"])
            if name in names:  # same name twice (shouldn't happen); keep both
                name = f"{hashlib.sha256(it['url'].encode()).hexdigest()[:8]}_{name}"
            names.add(name)
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime = len(b), int(time.time())
            tar.addfile(ti, io.BytesIO(b))
            row = dict(insurer=insurer, file_name=name, source_url=it["url"].split("?")[0], bytes=len(b),
                       sha256=hashlib.sha256(b).hexdigest(), plans_using=str(it["plans_using"]), checked_on=TODAY)
            try:
                row.update(describe(b), status="ok")
            except Exception as e:
                row.update(status=f"unreadable: {type(e).__name__}: {str(e)[:120]}")
            rows.append(row)
            if i % 10000 == 0:
                print(f"  {insurer} {i:,}/{len(items):,}", flush=True)
    for r in rows:
        for c in COLS:
            r.setdefault(c, "")
            if c not in ("bytes", "services", "payments"):
                r[c] = str(r[c])
    return rows, tar_path


def upload(insurer, rows, tar_path, local):
    import pyarrow as pa
    import pyarrow.parquet as pq
    tbl = pa.table({c: [(r[c] if r[c] != "" else None) if c in ("bytes", "services", "payments") else r[c] for r in rows]
                    for c in COLS})
    buf = io.BytesIO()
    pq.write_table(tbl, buf, compression="zstd")
    keys = {f"data/allowed/{MONTH}/{insurer}.parquet": buf.getvalue(), f"raw/allowed/{MONTH}/{insurer}.tar": tar_path.read_bytes()}
    if local:
        for k, v in keys.items():
            p = Path("local") / k
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(v)
            print(f"  wrote {p}")
        return
    import boto3
    E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
    for k, v in keys.items():
        s3.put_object(Bucket=E["R2_BUCKET"], Key=k, Body=v)
        print(f"  uploaded {k} ({len(v) / 1e6:.1f} MB)")


def summary(by):
    L = [f"# Out-of-network (allowed amount) files: {MONTH}", "",
         "Every file each insurer lists, downloaded and counted. A file is \"empty\" when it lists no services. "
         "Insurers only have to report a service paid out of network 20+ times in the period (11+ once the "
         "Oct 2026 rule takes effect).", "",
         "| Insurer | Files | Empty | With data | Services listed | Payments listed | Total size | Failed |",
         "|---|---|---|---|---|---|---|---|"]
    for ins, rows in sorted(by.items()):
        ok = [r for r in rows if r["status"] == "ok"]
        full = [r for r in ok if r["services"]]
        L.append(f"| {ins} | {len(rows):,} | {len(ok) - len(full):,} | {len(full):,} | {sum(r['services'] for r in ok):,} | "
                 f"{sum(r['payments'] for r in ok):,} | {sum(r['bytes'] or 0 for r in ok) / 1e6:.1f} MB | {len(rows) - len(ok):,} |")
    for ins, rows in sorted(by.items()):
        counted = [r for r in rows if r["status"] == "ok" and r["plans_using"].isdigit()]
        if counted:
            tot = sum(int(r["plans_using"]) for r in counted)
            empty = sum(int(r["plans_using"]) for r in counted if not r["services"])
            L += ["", f"{ins}: {empty:,} of {tot:,} plans in the table of contents point to an empty file."]
    for ins, rows in sorted(by.items()):
        full = sorted((r for r in rows if r["status"] == "ok" and r["services"]), key=lambda r: -r["services"])
        if full:
            L += ["", f"## {ins}: files with data (most services first)", ""]
            L += [f"- {r['file_name']}: {r['services']:,} services, {r['payments']:,} payments" for r in full[:25]]
            if len(full) > 25:
                L.append(f"- ... and {len(full) - 25:,} more (R2 data/allowed/{MONTH}/{ins.lower()}.parquet)")
    out = Path(__file__).resolve().parent.parent / "reports" / "allowed" / f"{MONTH}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"  summary -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insurers", default="cigna,uhc")
    ap.add_argument("--limit", type=int, default=0, help="test: only this many files per insurer")
    ap.add_argument("--local", action="store_true", help="write to ./local/ instead of R2")
    a = ap.parse_args()
    work = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "allowed"
    work.mkdir(parents=True, exist_ok=True)
    by = {}
    for ins in [x.strip() for x in a.insurers.split(",") if x.strip()]:
        if ins not in ("cigna", "uhc"):
            print(f"  unknown insurer {ins}"); continue
        t0 = time.time()
        try:
            items = {"cigna": cigna_list, "uhc": uhc_list}[ins]()
            if a.limit:
                items = items[:a.limit]
            rows, tar_path = collect(ins, items, work)
            upload(ins, rows, tar_path, a.local)
            by[{"cigna": "Cigna", "uhc": "UnitedHealthcare"}[ins]] = rows
            print(f"{ins}: {len(rows):,} files in {time.time() - t0:.0f} s", flush=True)
        except Exception as e:  # one insurer failing must not stop the others
            print(f"! {ins} failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
    if by:
        summary(by)


if __name__ == "__main__":
    main()
