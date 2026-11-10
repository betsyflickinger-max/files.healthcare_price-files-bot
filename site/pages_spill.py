"""Keep the website under Cloudflare Pages' 20,000-file limit (Nov 2, 2026; Betsy OK'd).

On Nov 2 the site reached 19,618 files and the procedure-pages update for the new states went over the limit, so
Cloudflare refused every whole-site deploy. The fix uses what the "more procedures" pages already use (since Oct 19):
pages kept in R2 under site/more/ and served by the Pages Function functions/costs/[[path]].js
(more_pages.FUNCTION_JS), which looks in R2 first and falls back to the static site.

Right before each deploy, offload(DIR):
  1. writes the current Function into DIR/functions/costs/ (it also sends /costs/a/b to /costs/a/b/ when the page is in R2)
  2. uploads every featured procedure page and its price list (site/costs/<place>/<procedure>/index.html, prices.csv;
     ~3,400 files) to R2 site/more/<place>/<procedure>/ -- only files whose content changed (compared with R2's ETag)
  3. moves them out of DIR/site while wrangler uploads, and puts them back afterwards
The live site's master copy (R2 site/deploy/current.tgz) keeps every file, so the bots that edit those pages work as
before. If an upload fails, nothing is deployed (better than a site missing its procedure pages).

Use:  with pages_spill.offload(d): subprocess.run([... 'wrangler', 'pages', 'deploy', 'site', ...], cwd=d)
      python site/pages_spill.py DIR -- npx wrangler pages deploy site ...      (for shell steps, e.g. names.yml)
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
PFX = "site/more/"
PAGE = re.compile(r"^costs/[a-z0-9-]+/(?!all/)[a-z0-9-]+/(?:index\.html|prices\.csv)$")   # <place>/all/ is R2's own page
LIMIT = 20000
TYPES = {"html": "text/html; charset=utf-8", "csv": "text/csv; charset=utf-8"}


def _s3():
    import boto3
    E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                      aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                      region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    return s3, E["R2_BUCKET"]


def _etags(s3, b):
    out, tok = {}, None
    while True:
        kw = dict(Bucket=b, Prefix=PFX, MaxKeys=1000)
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = o.get("ETag", "").strip('"')
        if not r.get("IsTruncated"):
            return out
        tok = r["NextContinuationToken"]


def count(site):
    return sum(len(fs) for _, _, fs in os.walk(site))


@contextmanager
def offload(d):
    site, hold = os.path.join(d, "site"), os.path.join(d, ".spilled")
    if os.path.isdir(os.path.join(d, "functions")):
        sys.path.insert(0, HERE)
        import more_pages
        fdir = os.path.join(d, "functions", "costs")
        os.makedirs(fdir, exist_ok=True)
        open(os.path.join(fdir, "[[path]].js"), "w").write(more_pages.FUNCTION_JS)
    files = []
    for root, _, fs in os.walk(site):
        for f in fs:
            rel = os.path.relpath(os.path.join(root, f), site).replace(os.sep, "/")
            if PAGE.match(rel):
                files.append(rel)
    s3, b = _s3()
    have = _etags(s3, b)
    todo = []
    for rel in files:
        body = open(os.path.join(site, rel), "rb").read()
        key = PFX + rel[len("costs/"):]
        if have.get(key) != hashlib.md5(body).hexdigest():
            todo.append((key, body, TYPES[rel.rsplit(".", 1)[1]]))
    with ThreadPoolExecutor(32) as ex:   # an error here stops the deploy: nothing goes out without its procedure pages
        list(ex.map(lambda t: s3.put_object(Bucket=b, Key=t[0], Body=t[1], ContentType=t[2]), todo))
    # Nov 9, 2026 (storage move, Betsy chose "keep the website's files on R2"): once the bot writes to Backblaze, copy
    # every file this deploy's Functions read to R2 first. Does nothing while the bot still writes to R2. A failure
    # stops the deploy (better than a live site pointing at files R2 doesn't have).
    subprocess.run([sys.executable, os.path.join(HERE, "..", "bot", "site_r2.py"), "publish", os.path.join(d, "functions")],
                   check=True)
    moved = []
    try:
        for rel in files:
            dst = os.path.join(hold, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(os.path.join(site, rel), dst)
            moved.append(rel)
        n = count(site)
        print(f"pages_spill: {len(files):,} procedure files served from storage ({len(todo):,} uploaded, the rest "
              f"unchanged); the deploy has {n:,} files (Cloudflare's limit is {LIMIT:,})", flush=True)
        if n > LIMIT:
            print(f"pages_spill: STILL OVER THE LIMIT by {n - LIMIT:,} files; move more pages to storage", flush=True)
        yield
    finally:
        for rel in moved:   # put every file back, so the saved copy of the site keeps them
            src = os.path.join(site, rel)
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(os.path.join(hold, rel), src)
        shutil.rmtree(hold, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        sys.exit(__doc__)
    with offload(sys.argv[1]):
        rc = subprocess.run(sys.argv[3:], cwd=sys.argv[1]).returncode
    sys.exit(rc)
