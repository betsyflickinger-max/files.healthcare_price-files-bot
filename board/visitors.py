"""Visitors tab for the private "Price Transparency Metrics" dashboard (Oct 17, 2026).

Reads the preview testers' page views that the site's password gate (functions/_middleware.js) saves to
R2 logs/preview-visits/<day>/*.json, plus the tester usernames from that same file in site/deploy/current.tgz
(only usernames; passwords are never stored there). Writes four files to out/board/ (private copy only):
  visitors_meta.json    one row of totals
  visitors_people.json  one row per tester, including testers who haven't visited yet
  visitors_pages.json   one row per page: views and how many people saw it
  visitors_log.json     every page view, newest first (last 3,000)
  visitors_events.json  what testers did on a page, newest first (last 3,000): taps, searches, guesses, how long they stayed and
                        how far they scrolled, and their answer to the homepage's one question (Oct 18: site/home_v2.py tracker)
In-page views the server never sees (a receipt or the Chargemaster opened on the homepage) come from the tracker and are
counted as page views, so a visit that never left the homepage no longer looks like it did nothing.
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


def events():
    """Tester actions from the tracker (R2 logs/preview-events/), oldest first."""
    keys = []
    for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="logs/preview-events/"):
        keys += [o["Key"] for o in pg.get("Contents", [])]
    get = lambda k: json.loads(s3.get_object(Bucket=B, Key=k)["Body"].read())
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(get, keys))
    return sorted(rows, key=lambda r: r["t"])


HASH = {"r": "Receipt", "chargemaster": "The Chargemaster", "rules": "House rules"}


def label(path):
    base, _, frag = path.partition("#")
    if frag:
        bits = [b for b in frag.strip("/").split("/") if b]
        name = HASH.get(bits[0], bits[0].capitalize()) if bits else ""
        return label(base) + " · " + name + (f" ({bits[1]})" if len(bits) > 1 else "")
    if path in ("", "/"):
        return "Homepage"
    if path.strip("/") == "v2":
        return "Homepage v2"
    parts = [p for p in path.strip("/").split("/") if p]
    return " · ".join(p.replace("-", " ").capitalize() for p in parts)


def main():
    os.makedirs(OUT, exist_ok=True)
    names, (rows, skipped) = testers(), views()
    evs = events()
    # in-page views (homepage receipts, the Chargemaster) count as page views
    rows = sorted(rows + [{"t": e["t"], "who": e["who"], "path": e.get("page", ""), "q": "", "from": "(opened on the page)", "device": e.get("device", ""), "in_page": True}
                          for e in evs if e.get("ev") == "view"], key=lambda r: r["t"])
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

    what = {"tap": "Tapped", "search": "Searched", "guess": "Guess game", "guess-skip": "Skipped the guess game", "answer": "Answered the question",
            "leave": "Left the page"}
    ev_rows = []
    for e in reversed([e for e in evs if e.get("ev") != "view"]):
        d = e.get("detail") or ""
        if e.get("ev") == "leave":
            d = f"after {e.get('secs', 0)} s, scrolled {e.get('depth', 0)}% of the page"
        elif e.get("ev") == "tap" and e.get("to"):
            d = f"{d} → {e['to']}"
        ev_rows.append({"id": f"{e['t']}-{e['who']}", "t": e["t"], "tester": e["who"], "page": label(e.get("page", "")),
                        "event": what.get(e.get("ev"), e.get("ev", "")), "detail": d, "device": e.get("device", "")})
    for name, data in (("visitors_events", ev_rows[:3000]), ("visitors_meta", meta), ("visitors_people", people), ("visitors_pages", page_rows), ("visitors_log", log)):
        json.dump(data, open(f"{OUT}/{name}.json", "w"), separators=(",", ":"))
    print(f"visitors: {len(names)} testers, {meta[0]['visited']} visited, {len(rows)} page views ({skipped} test views left out)")


if __name__ == "__main__":
    main()
