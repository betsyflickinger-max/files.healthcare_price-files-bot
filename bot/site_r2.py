"""Keep the live website's files on Cloudflare R2 after the bot moves to Backblaze (Nov 9, 2026; Betsy chose option 1).

Why: the website's Pages Functions read Price Finder data straight from R2 at request time (binding PF), and Pages can
only bind to R2. After the switch the bot writes to Backblaze, so every file the website reads has to be copied to R2
before the site points at it. R2 keeps only those files (~1.3 TB); everything else lives in Backblaze.

What gets copied (Backblaze -> R2, copy only, never deletes):
  - every folder or file the site's Functions name: any 'site/...' or 'control/...' text in functions/**/*.js, e.g.
    const PREFIX = "site/every-st/alabama/2026-11/". A pointer file such as site/every/CURRENT is read and the folder it
    names is copied too, BEFORE the pointer itself, so the site never points at a folder R2 doesn't have yet.
  - always: control/data/ (the control center) and site/more/ (procedure pages).
A file is copied when R2 lacks it, its size differs, or Backblaze's copy is newer than R2's.

Used by:
  - site/pages_spill.py offload(): right before every website deploy (all deploys go through it). If the copy fails,
    nothing is deployed.
  - .github/workflows/site-mirror.yml: every 30 minutes, for the site's current deploy (site/deploy/current.tgz), so
    data the bot updates between deploys (control center, procedure pages) reaches the site.
While STORAGE_ENDPOINT is empty the bot still writes to R2 itself and this does nothing.

  python bot/site_r2.py publish DIR [--dry]   copy what DIR/functions reads
  python bot/site_r2.py mirror [--dry]        the same for the live deploy (current.tgz), plus control/data and site/more
Env: STORAGE_ENDPOINT/STORAGE_REGION + R2_* (the bot's storage), R2_ACCOUNT_ID, SITE_R2_ACCESS_KEY_ID,
     SITE_R2_SECRET_ACCESS_KEY, SITE_R2_BUCKET (R2 itself). SITE_R2_FORCE=1 runs even with STORAGE_ENDPOINT empty (tests).
"""
import io
import os
import re
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ALWAYS = ("control/data/", "site/more/")
TOPS = ("site/", "control/")
NAME = re.compile(r"""['"`]((?:site|control)/[A-Za-z0-9_./=-]*)""")
CFG = Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=64)
g = lambda k: "".join(os.environ.get(k, "").split())


def enabled():
    return bool(g("STORAGE_ENDPOINT")) or g("SITE_R2_FORCE") == "1"


def src():
    """The bot's storage (Backblaze after the switch)."""
    ep = g("STORAGE_ENDPOINT") or g("SITE_SRC_ENDPOINT")
    if ep and "://" not in ep:
        ep = "https://" + ep
    return (boto3.client("s3", endpoint_url=ep or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                         region_name=g("STORAGE_REGION") or g("SITE_SRC_REGION") or "auto", config=CFG,
                         aws_access_key_id=g("R2_ACCESS_KEY_ID"), aws_secret_access_key=g("R2_SECRET_ACCESS_KEY")),
            g("R2_BUCKET"))


def dst():
    """R2 itself, which the website reads."""
    k, s, b = g("SITE_R2_ACCESS_KEY_ID"), g("SITE_R2_SECRET_ACCESS_KEY"), g("SITE_R2_BUCKET")
    if not (k and s and b and g("R2_ACCOUNT_ID")):
        raise RuntimeError("SITE_R2_* secrets missing: can't copy the website's files to R2, so not deploying")
    return (boto3.client("s3", endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", region_name="auto",
                         aws_access_key_id=k, aws_secret_access_key=s, config=CFG), b)


def refs(functions_dir):
    """(folders, files) the site's Functions name.

    A name that is completed at run time (followed by + or ${...}) is a stem. The only stem this can follow is the
    folder of a pointer file (site/every/ with site/every/CURRENT) or one copied whole (ALWAYS); any other refuses, so
    the site is never left reading files R2 doesn't have."""
    folders, files, stems = set(ALWAYS), set(), set()
    for f in Path(functions_dir).rglob("*"):
        if f.suffix not in (".js", ".mjs", ".ts") or not f.is_file():
            continue
        text = f.read_text(errors="replace")
        for m in NAME.finditer(text):
            s, rest = m.group(1), text[m.end(1):m.end(1) + 20]
            closed = rest[:1] == m.group(0)[0] and not re.match(r"['\"`]\s*\+", rest)
            if not closed or rest.startswith("${"):
                stems.add(s)
            else:
                (folders if s.endswith("/") else files).add(s)
    pointer_dirs = {k.rsplit("/", 1)[0] + "/" for k in files if k.rsplit("/", 1)[-1].isupper()}
    unknown = sorted(st for st in stems if st not in pointer_dirs and not st.startswith(ALWAYS))
    if unknown:
        raise RuntimeError(f"the website builds file names from {unknown} at run time; site_r2 can't tell which files "
                           "that means, so it must be taught before the site can be served from R2 copies")
    fl = sorted(folders)
    folders = [p for p in fl if not any(p != q and p.startswith(q) for q in fl)]
    files = sorted(k for k in files if not any(k.startswith(q) for q in folders))
    return folders, files


def _list(side, prefix):
    s3, b = (src() if side == "src" else dst())
    out = {}
    for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        for o in pg.get("Contents", []):
            out[o["Key"]] = (o["Size"], o["LastModified"].timestamp())
    return out


_tl = threading.local()


def _copy(k):
    """Stream one file Backblaze -> R2 (no temp file: the map tiles file alone is 18.8 GB). One client pair per thread."""
    if not hasattr(_tl, "c"):
        _tl.c = (src(), dst())
    (s, sb), (d, db) = _tl.c
    body = s.get_object(Bucket=sb, Key=k)["Body"]
    d.upload_fileobj(body, db, k)
    return k


def _head(c, b, k):
    try:
        o = c.head_object(Bucket=b, Key=k)
        return o["ContentLength"], o["LastModified"].timestamp()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def switched_at(s, sb):
    """When the bot moved to Backblaze. Until then R2 was the original, so a Backblaze file from before it (its time is
    when it was copied over) is not "newer" than R2's. The final copy pass writes it; SITE_R2_SINCE overrides (tests)."""
    if g("SITE_R2_SINCE"):
        return float(g("SITE_R2_SINCE"))
    try:
        return float(s.get_object(Bucket=sb, Key="bot/migration/switched-at.txt")["Body"].read().decode().strip())
    except ClientError as e:
        raise RuntimeError("bot/migration/switched-at.txt is missing (the final copy pass writes it): can't tell which "
                           "website files changed after the switch, so not deploying") from e


def publish(functions_dir, dry=False, log=print):
    """Copy everything the Functions in functions_dir read. Raises on any failure (callers must not deploy)."""
    if not enabled():
        log("site_r2: the bot still uses R2 directly; nothing to copy")
        return {"skipped": True}
    t0 = time.time()
    folders, files = refs(functions_dir)
    (s, sb), (d, db) = src(), dst()
    # pointer files (e.g. site/every/CURRENT): copy the folder they name first, then the pointer
    pointers = {}
    for k in files:
        if k.rsplit("/", 1)[-1].isupper():
            v = s.get_object(Bucket=sb, Key=k)["Body"].read().decode().strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]+", v):
                raise RuntimeError(f"{k} holds an unexpected value: {v[:60]!r}")
            folders.append(k.rsplit("/", 1)[0] + "/" + v + "/")
            pointers[k] = v
    plain = [k for k in files if k not in pointers]
    since = switched_at(s, sb)
    todo, errs = [], []
    with ProcessPoolExecutor(min(32, 2 * len(folders) + 2)) as ex:
        futs = {}
        for p in folders:
            futs[ex.submit(_list, "src", p)] = ("src", p)
            futs[ex.submit(_list, "dst", p)] = ("dst", p)
        got = {}
        for f in as_completed(futs):
            side, p = futs[f]
            got[(side, p)] = f.result()          # a listing error raises: never copy from a partial picture
    for p in folders:
        a, b = got[("src", p)], got[("dst", p)]
        todo += [k for k, (sz, t) in a.items() if k not in b or b[k][0] != sz or (t > since and t > b[k][1])]
    for k in plain:
        a, b = _head(s, sb, k), _head(d, db, k)
        if not a:
            raise RuntimeError(f"the website reads {k}, but the bot's storage doesn't have it")
        if (not b or b[0] != a[0] or (a[1] > since and a[1] > b[1])):
            todo.append(k)
    stats = {"folders": len(folders), "files_named": len(files), "to_copy": len(todo), "pointers": sorted(pointers),
             "src_files": sum(len(got[("src", p)]) for p in folders)}
    if dry:
        stats["sample"] = todo[:10]
        stats["seconds"] = round(time.time() - t0)
        log(f"site_r2 (dry run): {stats}")
        return stats
    with ThreadPoolExecutor(32) as ex:
        for f in as_completed([ex.submit(_copy, k) for k in todo]):
            try:
                f.result()
            except Exception as e:
                errs.append(repr(e)[:200])
    if errs:
        raise RuntimeError(f"site_r2: {len(errs)} of {len(todo)} copies failed, e.g. {errs[0]}")
    for k, v in pointers.items():      # last, and exactly the value read above: never a newer build not copied yet
        d.put_object(Bucket=db, Key=k, Body=v.encode())
    stats["seconds"] = round(time.time() - t0)
    log(f"site_r2: copied {len(todo)} files to R2 for the website ({stats['folders']} folders, {stats['seconds']} s)")
    return stats


def mirror(dry=False):
    """publish() for the live deploy: the Functions inside site/deploy/current.tgz."""
    if not enabled():
        print("site_r2: the bot still uses R2 directly; nothing to copy")
        return
    s, b = src()
    data = s.get_object(Bucket=b, Key="site/deploy/current.tgz")["Body"].read()
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                n = m.name.lstrip("./")
                if m.isfile() and "functions/" in n and n.endswith((".js", ".mjs", ".ts")) and ".." not in n:
                    out = Path(tmp) / n
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(t.extractfile(m).read())
        return publish(tmp, dry=dry)


if __name__ == "__main__":
    a = sys.argv[1:]
    dry = "--dry" in a
    if a and a[0] == "publish":
        publish(a[1], dry=dry)
    elif a and a[0] == "mirror":
        mirror(dry=dry)
    else:
        sys.exit(__doc__)
