"""Visitors tab for the private "Price Transparency Metrics" dashboard (Oct 17, 2026).

Reads the preview testers' page views that the site's password gate (functions/_middleware.js) saves to
R2 logs/preview-visits/<day>/*.json, plus the tester usernames from that same file in site/deploy/current.tgz
(only usernames; passwords are never stored there). Writes four files to out/board/ (private copy only):
  visitors_meta.json    one row of totals
  visitors_people.json  one row per tester, including testers who haven't visited yet
  visitors_pages.json   one row per page: views and how many people saw it
  visitors_log.json     every page view, newest first (last 3,000)
A "visit" = page views by one person with no gap over 30 minutes. Betsy's own password is never logged.
"""
import io
import json
import os
import re
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3

E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B = E["R2_BUCKET"]
OUT = "out/board"
GAP = 30 * 60

# Claude's own login checks on Oct 17, 2026 (before the gate stopped logging non-browser requests). Not real visits.
TEST_VIEWS = {("lance", "2026-10-18T00:43:49.389Z")} | {(w, t) for w, t in [
    ("lance", "2026-10-18T04:14:01.103Z"), ("lance", "2026-10-18T04:15:54.874Z"), ("lance", "2026-10-18T04:16:10.878Z"),
    ("lance", "2026-10-18T04:16:11.684Z"), ("lance", "2026-10-18T04:16:12.333Z"), ("lance", "2026-10-18T04:18:23.272Z")]}
TEST_WINDOW = ("2026-10-18T04:10:00Z", "2026-10-18T04:25:00Z", {"harry", "aaron"})


def testers():
    body = s3.get_object(Bucket=B, Key="site/deploy/current.tgz")["Body"].read()
    with tarfile.open(fileobj=io.BytesIO(body)) as t:
        m = next(x for x in t.getmembers() if x.name.endswith("functions/_middleware.js"))
        js = t.extractfile(m).read().decode()
    found = re.search(r"const TESTERS = (\{[^}]*\});", js)
    return sorted(set(json.loads(found.group(1)).values())) if found else []


def views():
    keys = []
    for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="logs/preview-visits/"):
        keys += [o["Key"] for o in pg.get("Contents", [])]
    get = lambda k: json.loads(s3.get_object(Bucket=B, Key=k)["Body"].read())
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(get, keys))
    lo, hi, who = TEST_WINDOW
    keep = [r for r in rows if (r.get("who"), r.get("t")) not in TEST_VIEWS
            and not (r.get("who") in who and r.get("device") == "computer" and lo <= r.get("t", "") <= hi)]
    return sorted(keep, key=lambda r: r["t"]), len(rows) - len(keep)


def label(path):
    if path in ("", "/"):
        return "Homepage"
    parts = [p for p in path.strip("/").split("/") if p]
    return " · ".join(p.replace("-", " ").capitalize() for p in parts)


def main():
    os.makedirs(OUT, exist_ok=True)
    names, (rows, skipped) = testers(), views()
    now = datetime.now(timezone.utc)
    ts = lambda r: datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
    by = defaultdict(list)
    for r in rows:
        by[r["who"]].append(r)

    people = []
    for w in sorted(set(names) | set(by)):
        rs = by.get(w, [])
        visits, prev = 0, None
        for r in rs:
            t = ts(r)
            if prev is None or (t - prev).total_seconds() > GAP:
                visits += 1
            prev = t
        top = Counter(label(r["path"]) for r in rs).most_common(1)
        dev = Counter(r.get("device", "") for r in rs)
        people.append({"id": w, "tester": w, "status": "Visited" if rs else "Not yet", "first": rs[0]["t"] if rs else None,
                       "last": rs[-1]["t"] if rs else None, "visits": visits, "page_views": len(rs),
                       "pages": len({r["path"] for r in rs}), "days": len({r["t"][:10] for r in rs}),
                       "phone": dev.get("phone", 0), "computer": dev.get("computer", 0), "top_page": top[0][0] if top else "",
                       "still_a_tester": w in names})

    pages = defaultdict(lambda: {"views": 0, "people": set(), "last": ""})
    for r in rows:
        p = pages[r["path"]]
        p["views"] += 1; p["people"].add(r["who"]); p["last"] = max(p["last"], r["t"])
    page_rows = [{"id": k, "page": label(k), "path": k, "views": v["views"], "people": len(v["people"]), "last": v["last"]}
                 for k, v in pages.items()]

    log = [{"id": f"{r['t']}-{r['who']}", "t": r["t"], "tester": r["who"], "page": label(r["path"]), "path": r["path"] + (r.get("q") or ""),
            "came_from": r.get("from") or "", "device": r.get("device", "")} for r in reversed(rows)][:3000]

    week = [r for r in rows if (now - ts(r)).total_seconds() <= 7 * 86400]
    meta = [{"id": "meta", "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "invited": len(names),
             "visited": sum(1 for p in people if p["page_views"] and p["still_a_tester"]),
             "page_views": len(rows), "visits": sum(p["visits"] for p in people),
             "views_7d": len(week), "people_7d": len({r["who"] for r in week}),
             "last_view_at": rows[-1]["t"] if rows else None, "last_view_by": rows[-1]["who"] if rows else None,
             "first_view_at": rows[0]["t"] if rows else None}]

    for name, data in (("visitors_meta", meta), ("visitors_people", people), ("visitors_pages", page_rows), ("visitors_log", log)):
        json.dump(data, open(f"{OUT}/{name}.json", "w"), separators=(",", ":"))
    print(f"visitors: {len(names)} testers, {meta[0]['visited']} visited, {len(rows)} page views ({skipped} test views left out)")


if __name__ == "__main__":
    main()
