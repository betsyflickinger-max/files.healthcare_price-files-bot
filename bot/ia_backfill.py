"""archive.org gap check (Oct 22, 2026; Betsy: "could this run like once a day?").

archive.org uploads failed from Oct 9 to Oct 20 (wrong keys), and any single upload can fail on a bad day. This compares
what we keep in R2 with what archive.org actually holds, sends whatever is missing, and confirms it arrived.

Checked, for this month and last month:
  hospitals  R2 raw/hospitals/<month>/<state>/<name>.zst  ->  item upfront-hospital-price-files-<state>-<month>
  employer   R2 raw/plans/<month>/<insurer>_indexes.tar   ->  item upfront-insurer-index-files-<month>
             (archive.org name <insurer>_employer_indexes_<month>.tar)
  receipts   R2 bot/receipts/<month>/receipts.csv.gz, summary.csv -> item upfront-insurer-file-receipts-<month>
             (archive.org names receipts_<month>.csv.gz, summary_<month>.csv)
(Insurer index files are not kept in R2; index_watch.py --deep re-sends them monthly.)

Output: R2 bot/ia_gaps/<date>.csv and latest.csv (one row per missing file: what, where, sent/failed); a summary for the
workflow page. Files are sent one at a time and deleted after, so disk stays small; a run stops sending after MAX_GB and
the next day's run picks up the rest.

Run: python bot/ia_backfill.py [--months 2026-10,2026-09] [--check-only] [--max-gb N]
"""
import argparse
import csv
import io
import os
import tempfile
import time
from datetime import date

import requests

import store

HOSP = "raw/hospitals/"


def months_default():
    t = date.today()
    prev = date(t.year - (t.month == 1), 12 if t.month == 1 else t.month - 1, 1)
    return [t.strftime("%Y-%m"), prev.strftime("%Y-%m")]


def ia_files(item, cache={}):
    if item not in cache:
        try:
            d = requests.get(f"https://archive.org/metadata/{item}", timeout=120).json()
            if not d.get("files"):
                # Oct 22: archive.org briefly answered {} for items that hold hundreds of files. Only treat an item as
                # empty if archive.org's search doesn't know it either; otherwise skip it today rather than re-send it all.
                q = requests.get("https://archive.org/advancedsearch.php", timeout=120,
                                 params={"q": f"identifier:{item}", "fl[]": "identifier", "output": "json"}).json()
                if q["response"]["numFound"]:
                    print(f"  {item}: archive.org didn't list its files just now; checking it tomorrow", flush=True)
                    cache[item] = None
                    return None
            cache[item] = {f["name"]: int(f.get("size") or 0) for f in d.get("files", [])}
        except Exception as e:
            print(f"! could not list {item}: {e}", flush=True)
            cache[item] = None  # unknown: don't send blindly
    return cache[item]


def r2_list(s3, b, prefix):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        for o in page.get("Contents", []):
            yield o["Key"], o["Size"]


def wanted(s3, b, month):
    """(r2_key, size, item, archive.org name, kind, ia metadata) for everything that should be on archive.org."""
    for key, size in r2_list(s3, b, f"{HOSP}{month}/"):
        parts = key.split("/")
        if len(parts) == 5 and key.endswith(".zst"):
            state = parts[3]
            yield key, size, store.ia_item(state, month), parts[4], "hospital", dict(state=state)
    for key, size in r2_list(s3, b, f"raw/plans/{month}/"):
        if key.endswith("_indexes.tar"):
            ins = key.rsplit("/", 1)[-1].replace("_indexes.tar", "")
            yield (key, size, f"upfront-insurer-index-files-{month}", f"{ins}_employer_indexes_{month}.tar", "employer indexes",
                   dict(title=f"Health insurer price-transparency index files, {month}"))
    for name, ia_name in (("receipts.csv.gz", f"receipts_{month}.csv.gz"), ("summary.csv", f"summary_{month}.csv")):
        for key, size in r2_list(s3, b, f"bot/receipts/{month}/{name}"):
            if key.endswith(name):
                yield (key, size, f"upfront-insurer-file-receipts-{month}", ia_name, "receipts",
                       dict(title=f"Health insurer price-file receipts, {month}"))


def send(s3, b, key, item, name, kind, meta, month):
    if kind == "hospital":
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, name)
            s3.download_file(b, key, p)
            err = store.ia_upload(p, meta["state"], month, name)
        return err
    from internetarchive import upload
    md = dict(title=meta["title"], mediatype="data", collection="opensource_media",
              description="Health insurer Transparency in Coverage files and records (45 CFR 147.212), saved as collected. "
                          "Collected for public price-transparency research.",
              subject="healthcare; price transparency; transparency in coverage; insurer prices")
    try:
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, name)
            s3.download_file(b, key, p)
            rs = upload(item, files={name: p}, metadata=md, access_key=store.env("IA_ACCESS_KEY"),
                        secret_key=store.env("IA_SECRET_KEY"), retries=5, retries_sleep=30)
        bad = [r for r in rs if getattr(r, "status_code", 200) >= 300]
        return f"archive.org HTTP {bad[0].status_code}" if bad else ""
    except Exception as e:
        return f"archive.org: {type(e).__name__}: {str(e)[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default=",".join(months_default()))
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--max-gb", type=float, default=60, help="stop sending after this much; tomorrow's run continues")
    a = ap.parse_args()
    s3, b = store.r2()
    today = date.today().isoformat()
    rows, total, sent_bytes = [], 0, 0
    for month in [m.strip() for m in a.months.split(",") if m.strip()]:
        for key, size, item, name, kind, meta in wanted(s3, b, month):
            total += 1
            have = ia_files(item)
            if have is None or name in have:
                continue
            row = dict(checked_on=today, month=month, kind=kind, item=item, name=name, r2_key=key, bytes=size, result="missing")
            if not a.check_only and store.ia_enabled() and sent_bytes + size <= a.max_gb * 1e9:
                err = send(s3, b, key, item, name, kind, meta, month)
                sent_bytes += size if not err else 0
                row["result"] = f"failed: {err}" if err else "sent"
                print(f"{row['result'][:80]}: {item}/{name} ({size / 1e6:,.0f} MB)", flush=True)
            rows.append(row)
    # confirm what was sent really arrived (archive.org can take a few minutes to list a new file)
    sent = [r for r in rows if r["result"] == "sent"]
    if sent:
        time.sleep(180)
        for item in {r["item"] for r in sent}:
            ia_files.__defaults__[0].pop(item, None)
        for r in sent:
            if r["name"] in (ia_files(r["item"]) or {}):
                r["result"] = "sent, confirmed"
            else:
                r["result"] = "sent, not listed yet"
    from collections import Counter
    c = Counter((r["kind"], r["result"].split(":")[0]) for r in rows)
    lines = [f"## archive.org gap check {today}", "", f"{total:,} files checked for {a.months}; {len(rows):,} were missing on archive.org.", ""]
    lines += [f"- {k}: {res} {n:,}" for (k, res), n in sorted(c.items())] or ["- nothing missing"]
    left = [r for r in rows if r["result"] == "missing"]
    if left:
        lines.append(f"\n{len(left):,} still missing ({sum(r['bytes'] for r in left) / 1e9:,.1f} GB), sent in later runs.")
    summary = "\n".join(lines) + "\n"
    print(summary)
    os.makedirs("out", exist_ok=True)
    open("out/ia_gaps.md", "w").write(summary)
    fields = ["checked_on", "month", "kind", "item", "name", "r2_key", "bytes", "result"]
    store.write_csv(s3, b, f"bot/ia_gaps/{today}.csv", rows, fields)
    store.write_csv(s3, b, "bot/ia_gaps/latest.csv", rows, fields)


if __name__ == "__main__":
    main()
