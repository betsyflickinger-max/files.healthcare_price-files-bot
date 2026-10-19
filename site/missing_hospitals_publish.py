"""Publish the Price File Watch hospitals list (/price-file-watch/hospitals/) to the preview site. Oct 19, 2026 (Betsy).

  1. the page, from the newest reports/watch/missing-hospitals-<date>.csv (bot/missing_export.py runs first)
  2. a link to it under "Hospitals" on the Price File Watch page, with today's count (replaced on each run)
  3. deploy with wrangler (same steps as site/employers_publish.py), then save site/deploy/current.tgz

Needs R2_* and CLOUDFLARE_API_TOKEN. Run: python site/missing_hospitals_publish.py [--no-deploy] [--out DIR]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "bot")]
import store  # noqa: E402
import missing_hospitals_page as page  # noqa: E402

ANCHOR = "It must update the file at least once a year.</p>"
M1, M2 = "<!--pfw-missing-->", "<!--/pfw-missing-->"


def link_block(n):
    return (f'{M1}<p class="sub"><b>Beyond DFW:</b> <a href="/price-file-watch/hospitals/">{n:,} hospitals across the '
            f'country where we couldn\'t find a usable price file</a>, by state, with what we tried and when.</p>{M2}')


def patch_watch(html, n):
    if M1 in html:
        return re.sub(re.escape(M1) + ".*?" + re.escape(M2), lambda _: link_block(n), html, count=1, flags=re.S)
    if ANCHOR not in html:
        print("  WARNING: Watch page anchor not found; link not added")
        return html
    return html.replace(ANCHOR, ANCHOR + "\n" + link_block(n), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--out", default=os.environ.get("RUNNER_TEMP", "/tmp") + "/mhpub")
    a = ap.parse_args()
    src = sorted((ROOT / "reports" / "watch").glob("missing-hospitals-*.csv"))
    if not src:
        sys.exit("STOP: no reports/watch/missing-hospitals-*.csv; run bot/missing_export.py first")
    s3, B = store.r2()
    out = Path(a.out); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    s3.download_file(B, "site/deploy/current.tgz", str(out / "site.tgz"))
    etag = s3.head_object(Bucket=B, Key="site/deploy/current.tgz")["ETag"]
    d = out / "deploy"
    with tarfile.open(out / "site.tgz") as t:
        t.extractall(d)
    if not (d / "functions").is_dir() or not (d / "site/price-finder/index.html").is_file():
        sys.exit("STOP: site/deploy/current.tgz does not have the expected site/ and functions/ folders; nothing deployed")

    n = page.main(str(src[-1]), str(d / "site/price-file-watch/hospitals"))
    w = d / "site/price-file-watch/index.html"
    if w.is_file():
        w.write_text(patch_watch(w.read_text(encoding="utf-8"), n), encoding="utf-8")
    if a.no_deploy:
        print(f"built in {d}; not deployed"); return

    if s3.head_object(Bucket=B, Key="site/deploy/current.tgz")["ETag"] != etag:
        sys.exit("STOP: the live site changed while this ran (another build deployed); run again")
    E = dict(os.environ)
    for k in ("R2_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        E[k] = "".join(E.get(k, "").split())
    if not E.get("CLOUDFLARE_API_TOKEN"):
        sys.exit("CLOUDFLARE_API_TOKEN is not set; built but not deployed")
    subprocess.run([sys.executable, str(HERE / "sitewide.py"), str(d)], check=True)   # name, Units look, share image
    r = subprocess.run(["npx", "--yes", "wrangler@3.114.0", "pages", "deploy", "site", "--project-name", "upfront-dfw-preview",
                        "--branch", "main", "--commit-dirty=true"], cwd=d, env=dict(E, CLOUDFLARE_ACCOUNT_ID=E["R2_ACCOUNT_ID"]),
                       capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit("deploy failed; the preview site is unchanged")
    s3.copy_object(Bucket=B, Key="site/deploy/backups/current-before-missing-hospitals.tgz", CopySource={"Bucket": B, "Key": "site/deploy/current.tgz"})
    with tarfile.open(out / "site_new.tgz", "w:gz") as t:
        t.add(d, arcname=".")
    s3.upload_file(str(out / "site_new.tgz"), B, "site/deploy/current.tgz")
    print(f"live: https://files.healthcare/price-file-watch/hospitals/ ({n} hospitals)")


if __name__ == "__main__":
    main()
