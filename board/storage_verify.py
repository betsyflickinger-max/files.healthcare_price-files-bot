"""Independent R2 vs Backblaze comparison for the storage switch (Nov 9, 2026; reviewer's fix for a trustworthy gate).

Lists BOTH buckets in full with boto3 (raw keys, sizes, times), so the result never depends on rclone's own checks or
name encoding. Runs on the copy machine. Read-only on both sides.

  python3 storage_verify.py OUTDIR LABEL

Writes OUTDIR/LABEL-missing.txt   keys in R2 but not in Backblaze
       OUTDIR/LABEL-differ.txt    keys whose sizes differ
       OUTDIR/LABEL-extra-all.txt keys only in Backblaze
       OUTDIR/LABEL-extra.txt     the same, minus folders that are never moved (KEEP)
       OUTDIR/LABEL-r2.tsv        every R2 key<TAB>size<TAB>last-modified epoch (for the re-copy probe)
       OUTDIR/LABEL-summary.json  counts, R2 newest time, listing errors
Exit 0 = both listings complete; 2 = a listing failed (results must not be trusted).
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config

KEEP = ("history/", "raw/", "research/", "bot/migration/", "bot/cutover-test/", "migration/")
g = lambda k: "".join(os.environ.get(k, "").split())
CFG = Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=40)


def clients():
    r2 = boto3.client("s3", endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", region_name="auto",
                      aws_access_key_id=g("R2_ACCESS_KEY_ID"), aws_secret_access_key=g("R2_SECRET_ACCESS_KEY"), config=CFG)
    b2 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                      aws_access_key_id=g("B2K"), aws_secret_access_key=g("B2S"), config=CFG)
    return (r2, g("R2_BUCKET")), (b2, g("B2B"))


def prefixes(s3, b):
    """Root files plus every second-level folder, so the big folders are listed in parallel."""
    files, tops = {}, []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Delimiter="/"):
        for o in page.get("Contents", []):
            files[o["Key"]] = (o["Size"], o["LastModified"].timestamp())
        tops += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    subs = []
    for t in tops:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=t, Delimiter="/"):
            for o in page.get("Contents", []):
                files[o["Key"]] = (o["Size"], o["LastModified"].timestamp())
            subs += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    return files, subs


def listing(side):
    s3, b = side
    files, subs = prefixes(s3, b)
    lock, errs = threading.Lock(), []

    def one(p):
        out = {}
        try:
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=p):
                for o in page.get("Contents", []):
                    out[o["Key"]] = (o["Size"], o["LastModified"].timestamp())
        except Exception as e:
            with lock:
                errs.append(f"{p}: {e!r}"[:300])
            return
        with lock:
            files.update(out)

    with ThreadPoolExecutor(32) as ex:
        list(ex.map(one, subs))
    return files, errs


def main():
    out, label = sys.argv[1], sys.argv[2]
    r2, b2 = clients()
    with ThreadPoolExecutor(2) as ex:
        fr, fb = ex.submit(listing, r2), ex.submit(listing, b2)
        (R, er), (Bk, eb) = fr.result(), fb.result()
    missing = sorted(k for k in R if k not in Bk)
    differ = sorted(k for k in R if k in Bk and R[k][0] != Bk[k][0])
    extra_all = sorted(k for k in Bk if k not in R)
    extra = [k for k in extra_all if not k.startswith(KEEP)]
    for name, keys in (("missing", missing), ("differ", differ), ("extra-all", extra_all), ("extra", extra)):
        with open(f"{out}/{label}-{name}.txt", "w") as f:
            f.writelines(k + "\n" for k in keys)
    with open(f"{out}/{label}-r2.tsv", "w") as f:
        f.writelines(f"{k}\t{s}\t{t:.0f}\n" for k, (s, t) in R.items())
    summ = dict(r2_files=len(R), b2_files=len(Bk), missing=len(missing), differ=len(differ), extra=len(extra),
                extra_kept_in_protected_folders=len(extra_all) - len(extra), r2_newest=max((t for _, t in R.values()), default=0),
                errors=er + eb)
    json.dump(summ, open(f"{out}/{label}-summary.json", "w"), indent=1)
    print(f"{len(missing)} {len(differ)} {len(extra)} {len(extra_all) - len(extra)} {len(R)} {int(summ['r2_newest'])} {len(er) + len(eb)}")
    sys.exit(2 if er or eb else 0)


if __name__ == "__main__":
    main()
