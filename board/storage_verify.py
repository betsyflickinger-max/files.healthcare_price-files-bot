"""Independent R2 vs Backblaze comparison for the storage switch (Nov 9, 2026; reviewer's fix for a trustworthy gate).

Lists BOTH buckets in full with boto3 (raw keys, sizes, times), so the result never depends on rclone's own checks or
name encoding. Runs on the copy machine. Read-only on both sides.

  python3 storage_verify.py OUTDIR LABEL

Writes OUTDIR/LABEL-missing.txt   keys in R2 but not in Backblaze
       OUTDIR/LABEL-differ.txt    keys whose sizes differ
       OUTDIR/LABEL-extra-all.txt keys only in Backblaze
       OUTDIR/LABEL-extra.txt     the same, minus folders that are never moved (KEEP)
       OUTDIR/LABEL-r2.tsv        every R2 key<TAB>size<TAB>last-modified epoch (for the re-copy probe)
       OUTDIR/LABEL-summary.json  counts, R2 newest time, listing errors, seconds taken
Exit 0 = both listings complete; 2 = a listing failed (results must not be trusted).

Nov 9 (later): the first version listed with threads in one process, so XML parsing ran on one core and ~20 million
keys (10.2M in R2 plus Backblaze) took hours. Now the buckets are split into folders DEPTH levels deep and each folder is
listed in its own process. Every key is still listed exactly once: keys sitting directly in a folder above DEPTH are
collected while splitting, and everything below a DEPTH-level folder is listed in full without a delimiter.
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config

KEEP = ("history/", "raw/", "research/", "bot/migration/", "bot/cutover-test/", "migration/")
DEPTH = int(os.environ.get("VERIFY_DEPTH", "3"))
PROCS = int(os.environ.get("VERIFY_PROCS", str(max(4, (os.cpu_count() or 4) * 3))))
g = lambda k: "".join(os.environ.get(k, "").split())
CFG = Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=40)


def client(side):
    """side is 'r2' or 'b2'; returns (s3 client, bucket). Built inside each process (clients can't be shared)."""
    if side == "r2":
        return (boto3.client("s3", endpoint_url=g("VERIFY_R2_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                             region_name="auto", aws_access_key_id=g("R2_ACCESS_KEY_ID"),
                             aws_secret_access_key=g("R2_SECRET_ACCESS_KEY"), config=CFG), g("R2_BUCKET"))
    return (boto3.client("s3", endpoint_url=g("VERIFY_B2_ENDPOINT") or "https://s3.us-east-005.backblazeb2.com",
                         region_name="us-east-005", aws_access_key_id=g("B2K"), aws_secret_access_key=g("B2S"), config=CFG),
            g("B2B"))


def _rows(page):
    return [(o["Key"], o["Size"], int(o["LastModified"].timestamp())) for o in page.get("Contents", [])]


def split(side, prefix):
    """One delimiter listing: (keys directly in this folder, its subfolders)."""
    s3, b = client(side)
    rows, subs = [], []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix, Delimiter="/"):
        rows += _rows(page)
        subs += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    return rows, subs


def full(side, prefix):
    """Everything under a folder, no delimiter."""
    s3, b = client(side)
    rows = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        rows += _rows(page)
    return rows


def main():
    out, label = sys.argv[1], sys.argv[2]
    t0 = time.time()
    files = {"r2": {}, "b2": {}}
    errs = []

    def add(side, rows):
        d = files[side]
        for k, s, t in rows:
            d[k] = (s, t)

    with ProcessPoolExecutor(PROCS) as ex:
        # 1. split both buckets into folders, level by level (keys found directly at each level are kept)
        level = [("r2", ""), ("b2", "")]
        for _ in range(DEPTH):
            nxt = []
            futs = {ex.submit(split, side, p): (side, p) for side, p in level}
            for f in as_completed(futs):
                side, p = futs[f]
                try:
                    rows, subs = f.result()
                except Exception as e:
                    errs.append(f"{side}:{p}: {e!r}"[:300])
                    continue
                add(side, rows)
                nxt += [(side, s) for s in subs]
            level = nxt
        # 2. list every remaining folder in full, each in its own process
        futs = {ex.submit(full, side, p): (side, p) for side, p in level}
        for f in as_completed(futs):
            side, p = futs[f]
            try:
                add(side, f.result())
            except Exception as e:
                errs.append(f"{side}:{p}: {e!r}"[:300])
    R, Bk = files["r2"], files["b2"]
    missing = sorted(k for k in R if k not in Bk)
    differ = sorted(k for k in R if k in Bk and R[k][0] != Bk[k][0])
    extra_all = sorted(k for k in Bk if k not in R)
    extra = [k for k in extra_all if not k.startswith(KEEP)]
    for name, keys in (("missing", missing), ("differ", differ), ("extra-all", extra_all), ("extra", extra)):
        with open(f"{out}/{label}-{name}.txt", "w") as f:
            f.writelines(k + "\n" for k in keys)
    with open(f"{out}/{label}-r2.tsv", "w") as f:
        f.writelines(f"{k}\t{s}\t{t}\n" for k, (s, t) in R.items())
    summ = dict(r2_files=len(R), b2_files=len(Bk), missing=len(missing), differ=len(differ), extra=len(extra),
                extra_kept_in_protected_folders=len(extra_all) - len(extra), r2_newest=max((t for _, t in R.values()), default=0),
                errors=errs, folders_listed=len(level), seconds=round(time.time() - t0))
    with open(f"{out}/{label}-summary.json", "w") as f:
        json.dump(summ, f, indent=1)
    print(f"{len(missing)} {len(differ)} {len(extra)} {len(extra_all) - len(extra)} {len(R)} {int(summ['r2_newest'])} {len(errs)}")
    sys.exit(2 if errs else 0)


if __name__ == "__main__":
    main()
