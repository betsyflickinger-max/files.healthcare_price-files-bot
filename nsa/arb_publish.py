"""Publish the No Surprises Act arbitration features to the preview site.

  1. /surprise-bills/ page + its search lists (nsa/surprise_page.py), from R2 data/idr/site/ (nsa/arb_build.py)
  2. every Price Finder page in the site (DFW and each area page): the arbitration code and that area's figures
     (nsa/arb_page.py); area pages with no CMS metro area (small towns, other states) get the code but no figures.
     The same is done to the pages the monthly builds start from: R2 site/deploy/price-finder.html (DFW) and
     site/deploy/cities/<slug>/price-finder.html.
  3. "Surprise Bills" in the nav of every page
  4. deploy with wrangler (same steps as site/orchestrate.py publish), then save site/deploy/current.tgz

Needs R2_* and CLOUDFLARE_API_TOKEN. Run: python nsa/arb_publish.py [--no-deploy] [--out DIR]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "bot"))
import arb_page  # noqa: E402
import store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--out", default=os.environ.get("RUNNER_TEMP", "/tmp") + "/arbpub")
    a = ap.parse_args()
    s3, B = store.r2()
    out = Path(a.out); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    get = lambda k, f: s3.download_file(B, k, str(out / f))
    for k, f in [("data/idr/site/arb_tx.json", "arb_tx.json"), ("data/idr/site/texas.json", "texas.json"),
                 ("data/idr/site/plans.json", "plans.json"), ("bot/idr/manifest.csv", "manifest.csv"), ("site/deploy/current.tgz", "site.tgz")]:
        get(k, f)
    A = json.load(open(out / "arb_tx.json"))
    d = out / "deploy"
    with tarfile.open(out / "site.tgz") as t:
        t.extractall(d)
    if not (d / "functions/price-finder").is_dir() or not (d / "site/price-finder/index.html").is_file():
        sys.exit("STOP: site/deploy/current.tgz does not have the expected site/ and functions/ folders; nothing deployed")

    def npis_for(prefix):
        try:
            return json.loads(s3.get_object(Bucket=B, Key=prefix + "npis.json")["Body"].read())
        except Exception:
            return None

    cur = s3.get_object(Bucket=B, Key="site/every/CURRENT")["Body"].read().decode().strip()

    def patch(html, slug, prefix):
        _, D, _ = arb_page.split(html)
        arb = arb_page.page_arb(A, slug, npis_for(prefix) if prefix else None, set(D["codes"]))
        return arb_page.patch_page(html, arb), arb

    # 1. Price Finder pages in the site
    pages = [("dfw", d / "site/price-finder/index.html", f"site/every/{cur}/")]
    for f in sorted((d / "site").glob("*/price-finder/index.html")):
        slug = f.parent.parent.name
        fn = d / "functions" / slug / "price-finder/pf/t/[code].js"
        m = re.search(r'PREFIX = ("[^"]+")', fn.read_text()) if fn.exists() else None
        pages.append((slug, f, json.loads(m.group(1)) if m else None))
    for slug, f, prefix in pages:
        html, arb = patch(f.read_text(encoding="utf-8"), slug, prefix)
        f.write_text(html, encoding="utf-8")
        print(f"  {slug}: " + (f"{arb['region']}: {len(arb['c']):,} codes, {len(arb['p']):,} providers" if arb else "code only (no CMS metro area)"))
    # the pages the monthly builds start from
    tmpl = [("dfw", "site/deploy/price-finder.html", f"site/every/{cur}/")] + [
        (slug, f"site/deploy/cities/{slug}/price-finder.html", prefix) for slug, _, prefix in pages[1:]]
    patched_tmpl = []
    for slug, key, prefix in tmpl:
        try:
            html = s3.get_object(Bucket=B, Key=key)["Body"].read().decode("utf-8")
        except Exception:
            continue
        html, _ = patch(html, slug, prefix)
        (out / f"tmpl_{slug}.html").write_text(html, encoding="utf-8")
        patched_tmpl.append((key, out / f"tmpl_{slug}.html"))

    # 2. the Surprise Bills page
    r = subprocess.run([sys.executable, str(HERE / "surprise_page.py"), str(out / "texas.json"), str(out / "arb_tx.json"),
                        str(out / "plans.json"), str(out / "manifest.csv"), str(d / "site/surprise-bills")], capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode:
        sys.exit("STOP: the Surprise Bills page failed; nothing deployed")

    # 3. nav on every page
    n = 0
    for f in (d / "site").rglob("*.html"):
        s = f.read_text(encoding="utf-8")
        s2 = arb_page.add_nav(s)
        if s2 != s:
            f.write_text(s2, encoding="utf-8"); n += 1
    print(f"  nav link added to {n} pages")
    if a.no_deploy:
        print(f"built in {d}; not deployed"); return

    # 4. deploy, then save the new site and templates
    E = dict(os.environ)
    for k in ("R2_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        E[k] = "".join(E.get(k, "").split())
    if not E.get("CLOUDFLARE_API_TOKEN"):
        sys.exit("CLOUDFLARE_API_TOKEN is not set; built but not deployed")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site', 'sitewide.py'), d], check=True)   # name, Units look, share image (Oct 18)
    r = subprocess.run(["npx", "--yes", "wrangler@3.114.0", "pages", "deploy", "site", "--project-name", "upfront-dfw-preview",
                        "--branch", "main", "--commit-dirty=true"], cwd=d, env=dict(E, CLOUDFLARE_ACCOUNT_ID=E["R2_ACCOUNT_ID"]),
                       capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit("deploy failed; the preview site is unchanged")
    s3.copy_object(Bucket=B, Key="site/deploy/backups/current-before-arb-publish.tgz", CopySource={"Bucket": B, "Key": "site/deploy/current.tgz"})
    with tarfile.open(out / "site_new.tgz", "w:gz") as t:
        t.add(d, arcname=".")
    s3.upload_file(str(out / "site_new.tgz"), B, "site/deploy/current.tgz")
    for key, f in patched_tmpl:
        s3.upload_file(str(f), B, key)
    print("live: https://files.healthcare/surprise-bills/")


if __name__ == "__main__":
    main()
