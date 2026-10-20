"""Insurer index watch (Oct 20, 2026; Betsy: "every hospital and insurer file get checked once a day").

The insurer bot (bot.py) reads the rate files of the insurers on the pick lists and checks them every 6 hours. This job
watches every OTHER insurer file source we know of, too: each insurer's table-of-contents (index) file and price-file
page, from data/insurer_sources.csv (state marketplace insurers), insurers/mlr/parents.csv (the ~200 parent companies),
the insurer catalog (catalog.py) and insurers/index_watch_extra.csv (added by hand).

  daily  every source: does it still answer, did its size/date change, is it a file or a web page?
         -> R2 bot/watch/indexes/<date>.csv and latest.csv; new problems -> out/index_alerts.md (issue)
  deep   (monthly, the 3rd; or --deep) every index up to DEEP_MAX_MB: read it, list every rate file it names, and
         check that each one answers (up to LINK_CAP per index). This is the check that would have caught Arkansas Blue
         Cross on Oct 1 (its indexes named only part-1 files that don't exist).
         -> R2 bot/watch/indexes/deep/<YYYY-MM>.csv and deep/<YYYY-MM>/<slug>.missing.csv
  archive (with deep) the index file itself goes to archive.org (item upfront-insurer-index-files-<YYYY-MM>), and
         every price-file page goes to the Wayback Machine (Save Page Now), so there is a public record of what each
         insurer said it published and when.
  evidence (Oct 20, 2026; Betsy: "what about the fact that they could delete or change it?") rows in
         index_watch_extra.csv with kind "evidence" are files we cite on the Price File Watch (e.g. UnitedHealthcare
         of Texas's index that names no in-network file). Each is saved to archive.org and the Wayback Machine when
         it is added (--evidence; the push that adds it runs this) and again with every deep check, and is checked
         daily like an index, so an alert opens if the insurer removes or changes it.

Run:  python insurers/index_watch.py [--deep] [--evidence] [--limit N] [--dry-run]
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bot"))
import check  # noqa: E402
import store  # noqa: E402

W = "bot/watch/indexes/"
DEEP_MAX_MB = 400      # indexes bigger than this (Anthem 11 GB, UHC's 68,000 small ones) are left to catalog.py
LINK_CAP = 3000        # rate-file links checked per index in the deep check (evenly sampled when there are more)
THREADS = 16
FIELDS = ["checked_on", "insurer", "state", "kind", "url", "http", "status", "size", "last_modified", "etag",
          "changed", "error", "source"]
DEEP_FIELDS = ["checked_on", "insurer", "state", "url", "index_bytes", "links", "checked", "missing", "hosts",
               "missing_examples", "archived", "error"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80] or hashlib.md5(s.encode()).hexdigest()[:10]


def sources():
    """Every index file or price-file page we know of, one row per distinct link."""
    out = {}

    def add(url, insurer, state, kind, src):
        url = (url or "").strip()
        if url.startswith("http") and "{" not in url and url not in out:
            out[url] = dict(url=url, insurer=insurer, state=state, kind=kind, source=src)
    for r in csv.DictReader(open(HERE.parent / "data" / "insurer_sources.csv")):
        if r["result"] in ("found toc", "found file"):
            add(r["url"], r["issuer"], r["state"], "index", "insurer_sources")
        if r.get("price_page"):
            add(r["price_page"], r["issuer"], r["state"], "page", "insurer_sources")
        if r["result"] == "portal only":
            add(r["url"], r["issuer"], r["state"], "page", "insurer_sources")
    for r in csv.DictReader(open(HERE / "mlr" / "parents.csv")):
        add(r.get("tic_landing_page"), r["parent_group"], "", "page", "parents")
    try:
        import catalog
        for k, v in catalog.INSURERS.items():
            for u in [v.get("latest"), *(v.get("metas") or [])]:
                add(u, v.get("name", k), "national", "index", "catalog")
    except Exception as e:
        print("catalog list not read:", e)
    extra = HERE / "index_watch_extra.csv"
    if extra.exists():
        for r in csv.DictReader(open(extra)):
            add(r["url"], r["insurer"], r.get("state", ""), r.get("kind", "index"), "extra")
    return list(out.values())


def daily_check(src, prev):
    h = check.headers(src["url"])
    if not h["ok"]:
        status = "broken"
    elif src["kind"] in ("index", "evidence") and h.get("html"):
        status = "web page, not a file"
    else:
        status = "ok"
    p = prev.get(src["url"]) or {}
    changed = ""
    if p and status == "ok" and p.get("status") == "ok":
        if (h["size"] and h["size"] != p.get("size")) or (h["last_modified"] and h["last_modified"] != p.get("last_modified")):
            changed = "yes"
    return dict(src, checked_on=date.today().isoformat(), http=h["http"], status=status, size=h["size"],
                last_modified=h["last_modified"], etag=h["etag"], changed=changed, error=h["error"][:200])


def index_links(path):
    """Every rate-file link an index names (in-network and allowed-amount), streamed with ijson."""
    import ijson
    op = gzip.open if open(path, "rb").read(2) == b"\x1f\x8b" else open
    links = []
    with op(path, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if event == "string" and prefix.endswith(".location"):
                links.append(value)
    return list(dict.fromkeys(links))


def ia_upload_index(path, name, month):
    if not store.ia_enabled():
        return "archive.org keys not set"
    from internetarchive import upload
    md = dict(title=f"Health insurer price-transparency index files, {month}", mediatype="data",
              collection="opensource_media",
              description=("Table-of-contents (index) files that U.S. health insurers post under the Transparency in "
                           "Coverage rule (45 CFR 147.212), saved as posted, so there is a record of which rate files "
                           "each insurer said it published that month. Collected for public price-transparency research."),
              subject="healthcare; price transparency; transparency in coverage; insurer prices")
    try:
        rs = upload(f"upfront-insurer-index-files-{month}", files={name: path}, metadata=md,
                    access_key=store.env("IA_ACCESS_KEY"), secret_key=store.env("IA_SECRET_KEY"),
                    retries=5, retries_sleep=30)
        bad = [r for r in rs if getattr(r, "status_code", 200) >= 300]
        return f"archive.org HTTP {bad[0].status_code}" if bad else "archive.org"
    except Exception as e:  # never let archive.org stop the run
        return f"archive.org: {type(e).__name__}: {str(e)[:150]}"


def wayback_save(url):
    """Ask the Wayback Machine to save a page now (needs the archive.org keys)."""
    if not store.ia_enabled():
        return "archive.org keys not set"
    try:
        r = requests.post("https://web.archive.org/save", data={"url": url, "skip_first_archive": "1"}, timeout=60,
                          headers={"Accept": "application/json",
                                   "Authorization": f"LOW {store.env('IA_ACCESS_KEY')}:{store.env('IA_SECRET_KEY')}"})
        return "wayback" if r.status_code < 300 else f"wayback HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"wayback: {type(e).__name__}"


def deep_check(src, month, archive):
    row = dict(checked_on=date.today().isoformat(), insurer=src["insurer"], state=src["state"], url=src["url"],
               index_bytes="", links=0, checked=0, missing=0, hosts="", missing_examples="", archived="", error="")
    h = check.headers(src["url"])
    if h["size"].isdigit() and int(h["size"]) > DEEP_MAX_MB * 2**20:
        row["error"] = f"index over {DEEP_MAX_MB} MB, left to the catalog"
        return row, []
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "index")
        ok, err, _ = check.download(src["url"], path, max_time=1800)
        if not ok:
            row["error"] = f"index did not download: {err[:150]}"
            return row, []
        row["index_bytes"] = os.path.getsize(path)
        try:
            links = index_links(path)
        except Exception as e:
            row["error"] = f"index unreadable: {type(e).__name__}: {str(e)[:120]}"
            links = []
        if archive:
            name = f"{month}_{slug(src['insurer'])}_{hashlib.sha256(src['url'].encode()).hexdigest()[:8]}" + \
                   os.path.splitext(urlparse(src["url"]).path)[1]
            row["archived"] = ia_upload_index(path, name, month)
    row["links"] = len(links)
    row["hosts"] = "; ".join(sorted({urlparse(u).netloc for u in links}))[:300]
    sample = links if len(links) <= LINK_CAP else [links[int(i * len(links) / LINK_CAP)] for i in range(LINK_CAP)]
    with ThreadPoolExecutor(THREADS) as ex:
        res = list(ex.map(lambda u: (u, check.headers(u)), sample))
    missing = [(u, r["http"] or r["error"][:60]) for u, r in res if not r["ok"]]
    row.update(checked=len(sample), missing=len(missing),
               missing_examples=" | ".join(u.split("?")[0].rsplit("/", 1)[-1] for u, _ in missing[:3]))
    return row, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="also read each index and check every rate file it names")
    ap.add_argument("--evidence", action="store_true",
                    help="save every 'evidence' row (index_watch_extra.csv) to archive.org and the Wayback Machine now")
    ap.add_argument("--no-archive", action="store_true", help="deep check without saving to archive.org/Wayback")
    ap.add_argument("--limit", type=int, default=0, help="only the first N sources (testing)")
    ap.add_argument("--dry-run", action="store_true", help="check and print; write nothing to R2")
    a = ap.parse_args()
    today, month = date.today().isoformat(), date.today().strftime("%Y-%m")
    s3 = b = None
    if not a.dry_run:
        s3, b = store.r2()
    srcs = sources()[: a.limit or None]
    print(f"{len(srcs)} sources: {sum(1 for s in srcs if s['kind'] == 'index')} index files, "
          f"{sum(1 for s in srcs if s['kind'] == 'page')} price-file pages", flush=True)
    prev = {r["url"]: r for r in store.read_csv(s3, b, W + "latest.csv")} if s3 else {}
    with ThreadPoolExecutor(THREADS) as ex:
        rows = list(ex.map(lambda s: daily_check(s, prev), srcs))
    bad = [r for r in rows if r["status"] != "ok"]
    new_bad = [r for r in bad if (prev.get(r["url"]) or {}).get("status", "ok") == "ok"]
    print(f"daily: {len(rows)} checked, {len(bad)} with problems ({len(new_bad)} new), "
          f"{sum(1 for r in rows if r['changed'])} changed since the last check", flush=True)
    alerts = [f"- **{r['insurer']}** ({r['state'] or 'all states'}, {r['kind']}): {r['status']} "
              f"(HTTP {r['http'] or '-'}) {r['url']}" for r in new_bad]
    if s3:
        store.write_csv(s3, b, f"{W}{today}.csv", rows, FIELDS)
        store.write_csv(s3, b, W + "latest.csv", rows, FIELDS)

    if a.evidence and not a.deep and not a.dry_run:
        ev = [x for x in srcs if x["kind"] == "evidence"]
        for s in ev:
            row, _ = deep_check(s, month, archive=True)
            wb = wayback_save(s["url"])
            print(f"evidence: {s['insurer']}: {row['archived'] or row['error']}; {wb}", flush=True)
            time.sleep(8)
        print(f"evidence: {len(ev)} files saved", flush=True)

    if a.deep:
        deep_rows = []
        for s in [x for x in srcs if x["kind"] in ("index", "evidence")]:
            row, missing = deep_check(s, month, archive=not a.no_archive and not a.dry_run)
            deep_rows.append(row)
            print(f"deep: {s['insurer']}: {row['links']} links, {row['missing']} of {row['checked']} checked missing "
                  f"{row['error']}", flush=True)
            if missing:
                alerts.append(f"- **{s['insurer']}** ({s['state'] or 'all states'}): {row['missing']} of "
                              f"{row['checked']} rate files its index names don't answer, e.g. {row['missing_examples']} "
                              f"({s['url']})")
                if s3:
                    buf = io.StringIO()
                    w = csv.writer(buf)
                    w.writerow(["url", "http_or_error"])
                    w.writerows(missing)
                    s3.put_object(Bucket=b, Key=f"{W}deep/{month}/{slug(s['insurer'])}.missing.csv",
                                  Body=buf.getvalue().encode())
        if s3:
            store.write_csv(s3, b, f"{W}deep/{month}.csv", deep_rows, DEEP_FIELDS)
        if not a.no_archive and not a.dry_run:
            pages = [x for x in srcs if x["kind"] in ("page", "evidence")]
            saved = 0
            for p in pages:
                saved += wayback_save(p["url"]) == "wayback"
                time.sleep(8)   # Save Page Now asks for a gentle pace
            print(f"wayback: {saved} of {len(pages)} price-file pages saved", flush=True)

    os.makedirs("out", exist_ok=True)
    with open("out/index_summary.md", "w") as f:
        f.write(f"## Insurer index watch {today}\n\n{len(rows)} sources checked, {len(bad)} with problems, "
                f"{len(new_bad)} new.\n")
    if alerts:
        with open("out/index_alerts.md", "w") as f:
            f.write(f"Insurer price-file problems found {today} (insurers/index_watch.py). Each is for the Price File "
                    f"Watch / failed-files list.\n\n" + "\n".join(alerts) + "\n")


if __name__ == "__main__":
    main()
