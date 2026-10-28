"""Save every file in an insurer's open web folder to R2, compressed, with a manifest. For insurers we don't read yet
(Cox HealthPlans, Oct 2026) so the data is kept and can be used later.

  python insurers/archive_folder.py https://www.coxhealthplans.com/MRF/ cox

Reads the folder listing (and one level of subfolders), then for each file: stream download -> zstd -> R2
raw/insurers/<name>/<YYYY-MM-DD>/<path>.zst. Files already saved under that day are skipped, so a rerun resumes.
Writes raw/insurers/<name>/<YYYY-MM-DD>/manifest.csv (url, bytes, sha256 of the original, R2 key, saved_at).
"""
import csv
import hashlib
import io
import os
import re
import sys
import tempfile
import time
from datetime import date
from urllib.parse import quote, urljoin

import boto3
import requests
import zstandard

E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
B = E["R2_BUCKET"]
UA = {"User-Agent": "Mozilla/5.0 (price-transparency research; archive of public machine-readable files)"}


def listing(url):
    html = requests.get(url, headers=UA, timeout=120).text
    out = []
    for h in re.findall(r'href="([^"]+)"', html, flags=re.I):
        u = urljoin(url, h)
        if u.startswith(url) and u.rstrip("/") != url.rstrip("/"):
            out.append(u)
    return list(dict.fromkeys(out))


def files_in(root):
    files = []
    for u in listing(root):
        if "." in u.rstrip("/").rsplit("/", 1)[-1]:
            files.append(u)
        else:  # a subfolder: one level down
            files += [x for x in listing(u.rstrip("/") + "/") if "." in x.rsplit("/", 1)[-1]]
    return files


def save(url, key):
    h, n = hashlib.sha256(), 0
    with tempfile.TemporaryFile() as tmp:
        for attempt in range(4):
            try:
                tmp.seek(0); tmp.truncate(); h, n = hashlib.sha256(), 0
                with requests.get(quote(url, safe=":/?=&%"), headers=UA, stream=True, timeout=600) as r:
                    r.raise_for_status()
                    w = zstandard.ZstdCompressor(level=6, threads=-1).stream_writer(tmp, closefd=False)
                    for ch in r.iter_content(8 << 20):
                        h.update(ch); n += len(ch); w.write(ch)
                    w.close()
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  retry {attempt + 1}: {e}", flush=True)
                time.sleep(15 * (attempt + 1))
        tmp.seek(0)
        s3.upload_fileobj(tmp, B, key)
    return n, h.hexdigest()


def main(root, name):
    day = date.today().isoformat()
    pre = f"raw/insurers/{name}/{day}/"
    have = set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=pre):
        have |= {o["Key"] for o in page.get("Contents", [])}
    rows = []
    try:
        rows = list(csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key=pre + "manifest.csv")["Body"].read().decode())))
    except Exception:
        pass
    done = {r["url"] for r in rows}
    files = files_in(root)
    print(f"{len(files)} files in {root}; {len(done)} already saved today", flush=True)
    for i, u in enumerate(files, 1):
        key = pre + u[len(root):].lstrip("/") + ".zst"
        if u in done and key in have:
            continue
        t0 = time.time()
        try:
            n, sha = save(u, key)
        except Exception as e:
            print(f"[{i}/{len(files)}] FAILED {u}: {e}", flush=True)
            continue
        rows.append(dict(url=u, bytes=n, sha256=sha, r2_key=key, saved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        print(f"[{i}/{len(files)}] {n / 1e6:,.0f} MB in {time.time() - t0:,.0f}s  {u.rsplit('/', 1)[-1]}", flush=True)
        if i % 10 == 0 or i == len(files):
            buf = io.StringIO(); wr = csv.DictWriter(buf, ["url", "bytes", "sha256", "r2_key", "saved_at"])
            wr.writeheader(); wr.writerows(rows)
            s3.put_object(Bucket=B, Key=pre + "manifest.csv", Body=buf.getvalue().encode())
    buf = io.StringIO(); wr = csv.DictWriter(buf, ["url", "bytes", "sha256", "r2_key", "saved_at"])
    wr.writeheader(); wr.writerows(rows)
    s3.put_object(Bucket=B, Key=pre + "manifest.csv", Body=buf.getvalue().encode())
    print(f"saved {len(rows)} of {len(files)} files, {sum(int(r['bytes']) for r in rows) / 1e9:,.1f} GB before compression")
    if len(rows) < len(files):
        sys.exit(f"{len(files) - len(rows)} files failed; run again to retry them")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
