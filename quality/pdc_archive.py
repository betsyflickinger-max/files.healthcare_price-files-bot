"""CMS Provider Data Catalog history (Nov 24, 2026, Betsy OK'd: every topic, doctors included from the start).

Saves CMS's own quality-data zips, untouched, for all ten Provider Data Catalog topics (hospitals, doctors and clinicians,
nursing homes, dialysis, home health, hospice, inpatient rehab, long-term care hospitals, supplier directory, physician
office visit costs), 2019 to now. This is the raw material for quality trends over time. Prices are not in these files.

Where the list comes from: CMS's own archive listing, one call per topic:
  https://data.cms.gov/provider-data/api/1/archive/aggregate/theme/<topic>/relative
What is saved: for past years the one yearly zip CMS publishes; for the current year each dated release, so nothing is
saved twice and a monthly run only adds what is new.

  raw/cms_provider_data/<topic>/<sha12>_<file>.zip    CMS originals, never overwritten (raw/ is locked by the file locker)
  bot/cms_provider_data/manifest.csv                  one row per saved file: CMS link, CMS's stated size, our size,
                                                      fingerprint, files inside, day downloaded
  reports/cms-provider-data/README.md                 plain-English summary of the run

A file is only saved if the zip opens and its size equals the size CMS lists (or, where CMS's listing is wrong, equals
what CMS's server sent and every file inside passes the zip's own check; the manifest keeps both sizes). Re-runs skip what the manifest has.
Run: python quality/pdc_archive.py [--work /mnt/pdc] [--topics hospitals,nursing-homes] [--dry]
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import time
import zipfile
from pathlib import Path

import requests

E = os.environ
B = E.get("R2_BUCKET") or "upfrontdfwdata"
TODAY = dt.date.today().isoformat()
YEAR = str(dt.date.today().year)
SITE = "https://data.cms.gov"
API = SITE + "/provider-data/api/1/archive/aggregate/"
PREFIX = "raw/cms_provider_data/"
MANIFEST = "bot/cms_provider_data/manifest.csv"
COLS = ["topic", "kind", "release", "url", "cms_bytes", "bytes", "sha256", "files_inside", "key", "downloaded_on"]
UA = {"User-Agent": "files.healthcare price-files-bot (https://github.com/betsyflickinger-max/files.healthcare_price-files-bot)"}


def s3():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", config=Config(retries={"max_attempts": 10, "mode": "standard"}, read_timeout=300),
                        endpoint_url=(E.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                        aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                        region_name=E.get("STORAGE_REGION") or "auto")


def get_json(url):
    for i in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=90)
            r.raise_for_status()
            return r.json()["data"]
        except Exception:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


def wanted(rows):
    """Past years: the yearly zip. Current year: each dated release. Returns (kind, release, url, cms_bytes)."""
    out = []
    for x in rows:
        if x.get("access_level", "public") != "public" or not x.get("url"):
            continue
        if x["type"] == "annual_theme":
            y = x["name"].rstrip(")")[-4:]
            if y != YEAR:
                out.append(("yearly", y, SITE + x["url"], int(x["size"] or 0)))
        elif x["type"] == "theme" and str(x.get("date", "")).startswith(YEAR):
            out.append(("release", x["date"], SITE + x["url"], int(x["size"] or 0)))
    return sorted(set(out), key=lambda t: t[1])


def download(url, path):
    h, n = hashlib.sha256(), 0
    with requests.get(url, headers=UA, stream=True, timeout=900) as r, open(path, "wb") as f:
        r.raise_for_status()
        for b in r.iter_content(8 << 20):
            f.write(b)
            h.update(b)
            n += len(b)
        served = int(r.headers.get("Content-Length") or 0)
    return h.hexdigest(), n, served


def load_manifest(c):
    try:
        t = c.get_object(Bucket=B, Key=MANIFEST)["Body"].read().decode()
        return list(csv.DictReader(io.StringIO(t)))
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return []
        raise


def save_manifest(c, rows):
    s = io.StringIO()
    w = csv.DictWriter(s, COLS)
    w.writeheader()
    w.writerows(sorted(rows, key=lambda r: (r["topic"], r["release"], r["url"])))
    c.put_object(Bucket=B, Key=MANIFEST, Body=s.getvalue().encode(), ContentType="text/csv")


def gb(n):
    return f"{n / 1e9:.2f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work", default="/tmp/pdc")
    p.add_argument("--topics", default="")
    p.add_argument("--dry", action="store_true", help="list what would be saved; download nothing")
    p.add_argument("--minutes", type=int, default=320, help="stop starting new files after this long (re-run resumes)")
    a = p.parse_args()
    W = Path(a.work)
    W.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    topics = sorted(x["theme"] for x in get_json(API + "current/theme/all/relative"))
    if a.topics:
        topics = [t for t in topics if t in a.topics.split(",")]
    c = None if a.dry else s3()
    man = [] if a.dry else load_manifest(c)
    have = {(r["url"], r["cms_bytes"]) for r in man}
    saved, skipped, failed, left = [], 0, [], 0
    plan = {}
    # smallest topics first, so a short run still finishes most of the catalog
    for t in topics:
        plan[t] = wanted(get_json(API + f"theme/{t}/relative"))
    for t in sorted(topics, key=lambda t: sum(x[3] for x in plan[t])):
        for kind, rel, url, size in plan[t]:
            if (url, str(size)) in have:
                skipped += 1
                continue
            if a.dry:
                print(f"would save  {t:38s} {kind:8s} {rel:10s} {gb(size):>9s}  {url}")
                saved.append(dict(topic=t, bytes=size))
                continue
            if time.time() - t0 > a.minutes * 60:
                left += 1
                continue
            path = W / url.rsplit("/", 1)[-1]
            try:
                sha, n, served = download(url, path)
                with zipfile.ZipFile(path) as z:
                    inside = len(z.namelist())
                    if size and n != size:
                        # CMS's listing is sometimes wrong (Nov 24, 2026: 4 files). Accept the file only if it is exactly
                        # what CMS's server said it was sending and every file inside passes the zip's own check.
                        bad = z.testzip()
                        if not served or n != served or bad:
                            raise ValueError(f"got {n} bytes, CMS lists {size}, server sent {served}, bad file inside: {bad}")
                        print(f"note   {t} {rel}: CMS lists {size} bytes but the complete file is {n}; saved, both sizes in the manifest", flush=True)
                key = f"{PREFIX}{t}/{sha[:12]}_{path.name}"
                c.upload_file(str(path), B, key)
                row = dict(topic=t, kind=kind, release=rel, url=url, cms_bytes=size, bytes=n, sha256=sha,
                           files_inside=inside, key=key, downloaded_on=TODAY)
                man.append(row)
                saved.append(row)
                save_manifest(c, man)   # after every file, so a stopped run loses nothing
                print(f"saved  {t:38s} {rel:10s} {gb(n):>9s}  {inside} files inside", flush=True)
            except Exception as e:
                failed.append((t, rel, url, str(e)[:200]))
                print(f"FAILED {t} {rel} {url}: {e}", flush=True)
            finally:
                path.unlink(missing_ok=True)

    by = {}
    for r in man if not a.dry else saved:
        d = by.setdefault(r["topic"], [0, 0])
        d[0] += 1
        d[1] += int(r["bytes"])
    L = [f"# CMS Provider Data Catalog history{' (dry run, nothing saved)' if a.dry else ''}", "",
         f"Run {TODAY}. Source: CMS archive listing, {API}theme/<topic>/relative. CMS originals are saved untouched in "
         f"storage under `{PREFIX}`; the full file list with links and fingerprints is `{MANIFEST}`.", "",
         f"- Saved this run: {len(saved)} files ({gb(sum(int(r['bytes']) for r in saved))})",
         f"- Already saved, skipped: {skipped}", f"- Failed: {len(failed)}", f"- Not started (time limit, re-run to finish): {left}", "",
         "| Topic | Files saved so far | Size |", "|---|---|---|"]
    L += [f"| {t} | {v[0]} | {gb(v[1])} |" for t, v in sorted(by.items())]
    if failed:
        L += ["", "## Failed (nothing saved for these)", ""] + [f"- {t} {rel}: {err} ({url})" for t, rel, url, err in failed]
    out = "\n".join(L) + "\n"
    print(out)
    if not a.dry:
        Path("reports/cms-provider-data").mkdir(parents=True, exist_ok=True)
        Path("reports/cms-provider-data/README.md").write_text(out)
    if failed or left:
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
