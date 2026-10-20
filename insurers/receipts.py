"""National file receipts (Oct 20, 2026; Betsy: "yes" to a receipt for every insurer file, every month).

Keeping every insurer rate file is not affordable (UnitedHealthcare alone posts ~94 TB a month), so instead the bot keeps a
receipt for each one: the file's name, link, size and date as the insurer's own server reported them, and whether the
link answered. If a file later disappears or quietly changes, the receipt shows it existed and what it looked like.
Nothing is downloaded for this; the numbers come from the insurer's listings and server answers.

Sources, every insurer we know of:
  uhc                         the public file listing (every file: in-network, out-of-network, prescription; name + size)
  anthem, cigna, aetna, hcsc  the monthly insurer catalog (catalog.py): every rate file its index names, with size, date
                              and whether the link answered
  everyone else               the monthly deep check (index_watch.py --deep): every rate file each index names (up to
                              20,000 per index, evenly sampled above that), from the server's answer

Output:
  R2 bot/receipts/<YYYY-MM>/receipts.csv.gz   one row per file
  R2 bot/receipts/<YYYY-MM>/summary.csv       one row per insurer
  archive.org item upfront-insurer-file-receipts-<YYYY-MM> (both files), so the record is public and permanent
  reports/receipts/<YYYY-MM>.md               plain counts, committed by the workflow

Run: python insurers/receipts.py [--month YYYY-MM] [--local]
"""
import argparse
import csv
import gzip
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bot"))
import store  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; price-files-bot; +https://github.com/betsyflickinger-max/price-files-bot)"}
FIELDS = ["month", "insurer", "state", "network", "file_kind", "file_name", "url", "bytes", "last_modified", "http",
          "answered", "listed_in", "checked_on", "how"]
CATALOG = {"anthem": "Anthem (Elevance)", "cigna": "Cigna", "aetna": "Aetna", "hcsc": "BCBS TX/IL/OK/NM/MT (HCSC)"}


def kind(name):
    n = name.lower()
    return ("out-of-network" if "allowed" in n else "index" if "index" in n or "table-of-contents" in n
            else "prescription" if "prescription" in n or "drug" in n else "in-network")


def uhc(month):
    r = requests.get("https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/", headers=UA, timeout=600)
    r.raise_for_status()
    blobs = r.json()["blobs"]
    today = date.today().isoformat()
    for b in blobs:
        if b["name"].endswith("_index.json"):
            continue  # employer indexes are kept whole by plans/employer_plans.py
        yield dict(month=month, insurer="UnitedHealthcare", state="", network="", file_kind=kind(b["name"]),
                   file_name=b["name"], url=b["downloadUrl"].split("?")[0], bytes=b.get("size") or "", last_modified="",
                   http="", answered="listed", listed_in="transparency-in-coverage.uhc.com/api/v1/uhc/blobs/",
                   checked_on=today, how="insurer's public file listing")


def catalog(s3, bucket, ins, month):
    try:
        cat = json.loads(s3.get_object(Bucket=bucket, Key=f"bot/catalog/{ins}/{month}/catalog.json")["Body"].read())
    except Exception:
        m = (json.loads(s3.get_object(Bucket=bucket, Key=f"bot/catalog/{ins}/latest.json")["Body"].read()) or {}).get("month")
        print(f"  {ins}: no {month} catalog, using {m}", flush=True)
        cat = json.loads(s3.get_object(Bucket=bucket, Key=f"bot/catalog/{ins}/{m}/catalog.json")["Body"].read())
    built = (cat.get("built") or "")[:10]
    seen = set()
    for net in cat.get("networks", []):
        for f in net.get("files", []):
            url = (f.get("url") or "").split("?")[0]
            if not url or url in seen:
                continue
            seen.add(url)
            http = str(f.get("http") or "")
            yield dict(month=month, insurer=cat.get("name") or CATALOG[ins], state=net.get("state", ""),
                       network=net.get("network", ""), file_kind="in-network", file_name=f.get("fname") or url.rsplit("/", 1)[-1],
                       url=url, bytes=f.get("bytes") or "", last_modified=f.get("modified", ""), http=http,
                       answered="yes" if http.startswith("2") else ("no" if http else ""), listed_in=cat.get("index", ""),
                       checked_on=built, how="insurer index, read whole (catalog)")


def watch(s3, bucket, month):
    pre = f"bot/receipts/{month}/watch/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=pre):
        for o in page.get("Contents", []):
            for r in store.read_csv(s3, bucket, o["Key"]):
                yield dict(month=month, insurer=r["insurer"], state=r["state"], network="", file_kind=kind(r["file_name"]),
                           file_name=r["file_name"], url=r["url"], bytes=r["bytes"], last_modified=r["last_modified"],
                           http=r["http"], answered=r["answered"], listed_in=r["index_url"], checked_on=r["checked_on"],
                           how="insurer index, every file link checked")


def ia_upload(paths, month):
    ak, sk = store.env("IA_ACCESS_KEY"), store.env("IA_SECRET_KEY")
    if not (ak and sk):
        return "archive.org keys not set"
    from internetarchive import upload
    md = dict(title=f"Health insurer price-file receipts, {month}", mediatype="data", collection="opensource_media",
              description=("One row for every price file U.S. health insurers posted under the Transparency in Coverage "
                           "rule (45 CFR 147.212) that month, as their own servers and indexes reported it: file name, "
                           "link, size, date, and whether the link answered. A public record of what each insurer "
                           "published, kept because the files themselves are too large to keep. Collected for public "
                           "price-transparency research."),
              subject="healthcare; price transparency; transparency in coverage; insurer prices")
    try:
        rs = upload(f"upfront-insurer-file-receipts-{month}", files={Path(p).name: p for p in paths}, metadata=md,
                    access_key=ak, secret_key=sk, retries=5, retries_sleep=30)
        bad = [r for r in rs if getattr(r, "status_code", 200) >= 300]
        if bad:
            return f"archive.org HTTP {bad[0].status_code}"
        # Oct 20: an upload once reported success with nothing saved, so confirm the files are really in the item.
        import time
        for _ in range(6):
            have = {f["name"] for f in requests.get(f"https://archive.org/metadata/upfront-insurer-file-receipts-{month}",
                                                    timeout=60).json().get("files", [])}
            if all(Path(p).name in have for p in paths):
                return "archive.org: saved"
            time.sleep(30)
        return "archive.org: upload reported OK but the files are not in the item (check the archive.org keys)"
    except Exception as e:  # never let archive.org stop the run
        return f"archive.org: {type(e).__name__}: {str(e)[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--local", action="store_true", help="UHC listing only, written to ./local/ (no R2 keys needed)")
    a = ap.parse_args()
    out = Path("local" if a.local else "/tmp") / "receipts" / a.month
    out.mkdir(parents=True, exist_ok=True)
    rec_path, sum_path = out / f"receipts_{a.month}.csv.gz", out / f"summary_{a.month}.csv"
    tot = defaultdict(lambda: dict(files=0, bytes=0, answered=0, not_answered=0, kinds=defaultdict(int)))
    s3 = b = None
    if not a.local:
        s3, b = store.r2()
    gens = [("uhc", lambda: uhc(a.month))]
    if s3:
        gens += [(k, (lambda k=k: catalog(s3, b, k, a.month))) for k in CATALOG] + [("watch", lambda: watch(s3, b, a.month))]
    seen = set()
    with gzip.open(rec_path, "wt", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for name, g in gens:
            n = 0
            try:
                for r in g():
                    if r["url"] in seen:  # an insurer's catalog and the deep check can both list a file
                        continue
                    seen.add(r["url"])
                    w.writerow(r)
                    n += 1
                    t = tot[r["insurer"]]
                    t["files"] += 1
                    t["bytes"] += int(r["bytes"]) if str(r["bytes"]).isdigit() else 0
                    t["answered"] += r["answered"] in ("yes", "listed")
                    t["not_answered"] += r["answered"] == "no"
                    t["kinds"][r["file_kind"]] += 1
            except Exception as e:  # one source failing must not stop the others
                print(f"! {name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
            print(f"  {name}: {n:,} files", flush=True)
    rows = [dict(month=a.month, insurer=k, files=v["files"], terabytes=round(v["bytes"] / 1e12, 3), answered=v["answered"],
                 not_answered=v["not_answered"], kinds="; ".join(f"{x} {c:,}" for x, c in sorted(v["kinds"].items())))
            for k, v in sorted(tot.items(), key=lambda kv: -kv[1]["files"])]
    with open(sum_path, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]) if rows else ["month"])
        w.writeheader()
        w.writerows(rows)
    print(f"receipts: {len(seen):,} files from {len(rows)} insurers -> {rec_path} ({rec_path.stat().st_size / 1e6:.1f} MB)")
    ia = ""
    if s3:
        s3.upload_file(str(rec_path), b, f"bot/receipts/{a.month}/receipts.csv.gz")
        s3.upload_file(str(sum_path), b, f"bot/receipts/{a.month}/summary.csv")
        ia = ia_upload([str(rec_path), str(sum_path)], a.month)
        print(ia, flush=True)
    L = [f"# Insurer file receipts: {a.month}", "",
         "One receipt per price file each insurer posted: name, link, size and date as the insurer reported them, and "
         "whether the link answered. Nothing estimated. Full list: R2 bot/receipts/" + a.month + "/receipts.csv.gz"
         + (f" and archive.org item upfront-insurer-file-receipts-{a.month}" if ia.endswith("saved") else "") + ".", "",
         "| Insurer | Files | Size (TB) | Answered | Did not answer |", "|---|---|---|---|---|"]
    L += [f"| {r['insurer']} | {r['files']:,} | {r['terabytes']:,} | {r['answered']:,} | {r['not_answered']:,} |" for r in rows]
    rep = HERE.parent / "reports" / "receipts" / f"{a.month}.md"
    if not a.local:
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
