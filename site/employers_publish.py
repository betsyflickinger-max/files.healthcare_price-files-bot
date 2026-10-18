"""Publish the Employer Plans page (/employer-plans/) and the Insurers page (/insurers/) to the preview site.

  1. the page + its search list (site/employers_page.py), from R2 bot/employers/<newest>/site_employers.json
  2. "Employer Plans" in the nav of every page, and of the pages the monthly builds start from
     (R2 site/deploy/price-finder.html and site/deploy/cities/<slug>/price-finder.html)
  3. deploy with wrangler (same steps as nsa/arb_publish.py), then save site/deploy/current.tgz

Needs R2_* and CLOUDFLARE_API_TOKEN. Run: python site/employers_publish.py [--no-deploy] [--out DIR]
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
sys.path.insert(0, str(HERE.parent / "bot"))
import store  # noqa: E402

# links added to the site nav, in order, each after the one before it (or after Surprise Bills / Price File Watch)
NAV = [("/employer-plans/", "Employer Plans"), ("/insurers/", "Insurers"), ("/hospitals/", "Hospitals")]


def add_nav(html):
    """Adds the Employer Plans and Insurers links to the site's nav bars, after Surprise Bills (or Price File Watch).
    Idempotent: a link already in a nav bar is left alone."""
    for href, label in NAV:
        out, pos = [], 0
        for m in re.finditer(r'<(span|nav)[^>]*class="(sn-links|toplinks|nav)"[^>]*>', html):
            end = html.find("</" + m.group(1) + ">", m.end())
            block = html[m.end():end]
            if end < 0 or f'href="{href}"' in block:
                continue
            anchor = next((f'<a href="{h}"' for h in [x for x, _ in NAV if x != href][::-1] + ["/surprise-bills/", "/price-file-watch/"]
                           if f'<a href="{h}"' in block and [x for x, _ in NAV].index(href) > ([x for x, _ in NAV].index(h) if h in [x for x, _ in NAV] else -1)), None)
            if not anchor:
                continue
            j = m.end() + block.index(anchor)
            k = html.index("</a>", j) + 4
            out.append(html[pos:k] + f'<a href="{href}">{label}</a>'); pos = k
        html = "".join(out) + html[pos:]
    return html


NET_ANCHOR = "const qc = new URLSearchParams(location.search).get('code');"
NET_PATCH = ("/*netparam*/ { const qn = new URLSearchParams(location.search).get('net'); "
             "const lab = x => String(x).split('|').slice(1).join('|').toLowerCase() || String(x).toLowerCase(); "
             "let ni = qn && Array.isArray(D.nets) ? D.nets.indexOf(qn) : -1; "
             "if (qn && ni < 0 && Array.isArray(D.nets)) ni = D.nets.findIndex(n => lab(n) === lab(qn)); "
             "if (ni >= 0) { S.pay = String(ni); S.showAll = {}; const ps = document.getElementById('pay'); if (ps) ps.value = S.pay; } }\n  ")


def add_net_param(html):
    """Price Finder pages: ?net=<insurer|network> opens the page with that network chosen under "How are you paying?"
    (Employer Plans links here). Idempotent; pages without the ?code= handler are left alone."""
    if "/*netparam*/" in html or NET_ANCHOR not in html:
        return html
    return html.replace(NET_ANCHOR, NET_PATCH + NET_ANCHOR, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--out", default=os.environ.get("RUNNER_TEMP", "/tmp") + "/emppub")
    a = ap.parse_args()
    s3, B = store.r2()
    out = Path(a.out); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    latest = json.loads(s3.get_object(Bucket=B, Key="bot/employers/latest.json")["Body"].read())
    s3.download_file(B, f"bot/employers/{latest['date']}/site_employers.json", str(out / "site_employers.json"))
    s3.download_file(B, "site/deploy/current.tgz", str(out / "site.tgz"))
    etag = s3.head_object(Bucket=B, Key="site/deploy/current.tgz")["ETag"]
    d = out / "deploy"
    with tarfile.open(out / "site.tgz") as t:
        t.extractall(d)
    if not (d / "functions/price-finder").is_dir() or not (d / "site/price-finder/index.html").is_file():
        sys.exit("STOP: site/deploy/current.tgz does not have the expected site/ and functions/ folders; nothing deployed")

    # 1. the page
    r = subprocess.run([sys.executable, str(HERE / "employers_page.py"), str(out / "site_employers.json"), str(d / "site/employer-plans")],
                       capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode:
        sys.exit("STOP: the Employer Plans page failed; nothing deployed")

    # 1b. the Insurers page (data committed in insurers/mlr/, CMS MLR 2024)
    r = subprocess.run([sys.executable, str(HERE / "insurers_page.py"), str(HERE.parent / "insurers/mlr/site_insurers.json"), str(d / "site/insurers")],
                       capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode:
        sys.exit("STOP: the Insurers page failed; nothing deployed")

    # 2. nav on every page and on the build templates
    n = 0
    for f in (d / "site").rglob("*.html"):
        s = f.read_text(encoding="utf-8")
        s2 = add_nav(s)
        if f.name == "index.html" and f.parent.name == "price-finder":
            s2 = add_net_param(s2)
        if s2 != s:
            f.write_text(s2, encoding="utf-8"); n += 1
    print(f"  nav link added to {n} pages")
    tmpl = []
    keys = ["site/deploy/price-finder.html"] + [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="site/deploy/cities/")
                                                 for o in pg.get("Contents", []) if o["Key"].endswith("/price-finder.html")]
    for i, key in enumerate(keys):
        try:
            html = s3.get_object(Bucket=B, Key=key)["Body"].read().decode("utf-8")
        except Exception:
            continue
        h2 = add_net_param(add_nav(html))
        if h2 != html:
            (out / f"tmpl_{i}.html").write_text(h2, encoding="utf-8"); tmpl.append((key, out / f"tmpl_{i}.html"))
    print(f"  nav link added to {len(tmpl)} build templates")
    if a.no_deploy:
        print(f"built in {d}; not deployed"); return

    # 3. deploy, then save the new site and templates
    if s3.head_object(Bucket=B, Key="site/deploy/current.tgz")["ETag"] != etag:
        sys.exit("STOP: the live site changed while this ran (another build deployed); run again")
    E = dict(os.environ)
    for k in ("R2_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        E[k] = "".join(E.get(k, "").split())
    if not E.get("CLOUDFLARE_API_TOKEN"):
        sys.exit("CLOUDFLARE_API_TOKEN is not set; built but not deployed")
    r = subprocess.run(["npx", "--yes", "wrangler@3.114.0", "pages", "deploy", "site", "--project-name", "upfront-dfw-preview",
                        "--branch", "main", "--commit-dirty=true"], cwd=d, env=dict(E, CLOUDFLARE_ACCOUNT_ID=E["R2_ACCOUNT_ID"]),
                       capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit("deploy failed; the preview site is unchanged")
    s3.copy_object(Bucket=B, Key="site/deploy/backups/current-before-employers-publish.tgz", CopySource={"Bucket": B, "Key": "site/deploy/current.tgz"})
    with tarfile.open(out / "site_new.tgz", "w:gz") as t:
        t.add(d, arcname=".")
    s3.upload_file(str(out / "site_new.tgz"), B, "site/deploy/current.tgz")
    for key, f in tmpl:
        s3.upload_file(str(f), B, key)
    print("live: https://files.healthcare/employer-plans/ and https://files.healthcare/insurers/")


if __name__ == "__main__":
    main()
