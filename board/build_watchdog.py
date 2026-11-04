"""Stuck-build watchdog (Nov 3, 2026, Betsy OK'd: "I don't want any of these to get stuck").

Why: Washington's page build ran up to 14 rented machines from Oct 31 to Nov 3 and finished 0 of 256 batches. Every
worker ran out of memory and was killed without leaving an error, and nothing noticed until Betsy asked. The November
hold also sat on a build that could never finish. This job looks at every state page build once an hour, from outside:

  1. No progress   machines have been billing for 3+ hours and nothing new was saved in 3 hours (stage-B results, or
                   stage-A tables finishing). -> ONE GitHub issue (an email to Betsy) and the build is cut to 2 machines
                   (R2 bot/watchdog/cap/<build>.json, read by machine_shares.build_cap) so a stuck build can't burn money.
  2. Out of memory when (1) fires and at least half of the build's machines had under 1 GB free for the last 30
                   minutes (DigitalOcean monitoring), the issue names memory as the likely cause. Low memory alone, with
                   results still landing, is only logged (a busy healthy build can run near full).
  3. Waiting long  a current build has sat at 'wait' or 'split' with no machines for 12+ hours. -> one issue saying so.
  4. Daily summary once a day (~7 AM CT) a comment on the "Daily build summary" issue: every build with machines, its
                   stage, results saved and saved in the last 24 h, and the price check's hours / dollars left.

When a stuck build moves again (new results in the last hour) its issue closes and the cap is removed by itself.
Read-only apart from: GitHub issues/comments, and the cap/state files under bot/watchdog/ in R2. Never deletes data.
Run with DRY=1 to print what it would do.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bot"))
import store  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "betsyflickinger-max/files.healthcare_price-files-bot")
GH = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{REPO}"
DO = "https://api.digitalocean.com/v2"
DRY = bool(os.environ.get("DRY"))
STUCK_H, WAIT_H, MEM_FREE_GB, CAP = 3, 12, 1.0, 2
W = "bot/watchdog/"
DIGEST_HOUR_UTC = 13          # ~7 AM CT (8 AM during daylight time)
DIGEST_TITLE = "Daily build summary"
s3, B = store.r2()
NOW = time.time()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def gh(method, path, **kw):
    if DRY and method != "GET":
        log("DRY", method, path, json.dumps(kw.get("json", {}))[:300]); return None
    r = requests.request(method, path if path.startswith("http") else API + path, headers=GH, timeout=60, **kw)
    if r.status_code >= 300:
        log(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
    return r


def getj(key, default=None):
    try:
        return json.loads(s3.get_object(Bucket=B, Key=key)["Body"].read())
    except Exception:
        return default


def putj(key, obj):
    if DRY:
        log("DRY put", key, json.dumps(obj)[:200]); return
    s3.put_object(Bucket=B, Key=key, Body=json.dumps(obj).encode())


def delete(key):
    if DRY:
        log("DRY delete", key); return
    try:
        s3.delete_object(Bucket=B, Key=key)
    except Exception as e:
        log("delete failed", key, repr(e)[:120])


def ls(prefix, delim=None):
    kw = dict(Bucket=B, Prefix=prefix)
    if delim:
        kw["Delimiter"] = delim
    for page in s3.get_paginator("list_objects_v2").paginate(**kw):
        yield from page.get("Contents", [])


def do_h():
    return {"Authorization": f"Bearer {''.join(os.environ.get('DIGITALOCEAN_TOKEN', '').split())}"}


def droplets():
    out, url = [], f"{DO}/droplets?per_page=200"
    while url:
        r = requests.get(url, headers=do_h(), timeout=60).json()
        out += r.get("droplets", [])
        url = (r.get("links", {}).get("pages") or {}).get("next")
    return out


BID_RE = re.compile(r"^upfront-site-(st[a-z0-9]*-\d{4}-\d{2}[a-z]?)-")


def machines_by_build():
    """{build id: [droplet, ...]} for state page builds (not their hospital-step machines)."""
    out = {}
    for d in droplets():
        m = BID_RE.match(d["name"])
        if m:
            out.setdefault(m.group(1), []).append(d)
    return out


def ts(iso):
    return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


def saved_since(bid, st, since):
    """(results saved after `since`, all results) for this build's states: stage-B results (B/, P/) and stage-A tables
    finishing (Acache/<table>.done, top level only, so the per-bucket files aren't listed)."""
    ym = "v" + bid.split("-", 1)[1].replace("-", "")   # st-2026-11 -> v202611, st-2026-10b -> v202610b (orchestrate_states.wk)
    new = total = 0
    for slug in (st.get("machines") or {}):
        for pre, delim in ((f"work/every-st/{slug}/{ym}/B/", None), (f"work/every-st/{slug}/{ym}/P/", None),
                           (f"work/every-st/{slug}/Acache/", "/")):
            for o in ls(pre, delim):
                if pre.endswith("Acache/") and not o["Key"].endswith(".done"):
                    continue
                if not pre.endswith("Acache/"):
                    total += 1
                if o["LastModified"].timestamp() > since:
                    new += 1
    return new, total


def memory_pinned(ds):
    """machines whose free memory stayed under MEM_FREE_GB for the last 30 minutes (None = monitoring unreadable)"""
    pinned, read = [], 0
    for d in ds:
        q = dict(host_id=str(d["id"]), start=str(int(NOW) - 1800), end=str(int(NOW)))
        try:
            res = requests.get(f"{DO}/monitoring/metrics/droplet/memory_available", params=q, headers=do_h(),
                               timeout=60).json()["data"]["result"]
            pts = [float(v) / 1e9 for _, v in res[0]["values"]] if res else []
        except Exception:
            continue
        if len(pts) >= 5:
            read += 1
            if max(pts) < MEM_FREE_GB:
                pinned.append(d["name"])
    return pinned if read else None


_OPEN = []


def open_issues():
    if not _OPEN:
        r = gh("GET", "/issues", params={"state": "open", "per_page": 100})
        _OPEN.append([i for i in (r.json() or []) if isinstance(i, dict)])
    return _OPEN[0]


def find_issue(title):
    for i in open_issues():
        if isinstance(i, dict) and i.get("title", "").startswith(title):
            return i
    return None


def states_of(st):
    return ", ".join(s.replace("-", " ").title() for s in (st.get("machines") or {})) or "?"


def ct(t):
    """a time in Central (CST from Nov 1, 2026)"""
    return time.strftime("%b %d %I:%M %p CT", time.gmtime(t - 6 * 3600)).replace(" 0", " ")


def stuck(bid, st, ds, why, detail):
    title = f"Build stuck: {bid}"
    cap_key = f"{W}cap/{bid}.json"
    if not getj(cap_key):
        putj(cap_key, {"most": CAP, "at": NOW, "why": why})
        log(bid, "capped at", CAP, "machines:", why)
    if find_issue(title):
        log(bid, "already reported"); return
    body = (f"**{states_of(st)}** ({bid}) looks stuck: **{why}**.\n\n{detail}\n\n"
            f"**What I did:** cut this build to at most {CAP} machines (it had {len(ds)}), so it can't keep billing "
            f"for nothing. Nothing was deleted; finished work stays saved.\n\n"
            f"**What to do:** ask Claude to look at it (Fleet check workflow, `mon:` and `tail:` modes show memory and "
            f"live machine logs). This issue closes itself, and the cap comes off, once the build saves new results again.")
    gh("POST", "/issues", json={"title": f"{title} ({states_of(st)})", "body": body})


def unstick(bid):
    cap_key = f"{W}cap/{bid}.json"
    if getj(cap_key):
        delete(cap_key); log(bid, "moving again: cap removed")
    i = find_issue(f"Build stuck: {bid}")
    if i:
        gh("POST", f"/issues/{i['number']}/comments", json={"body": f"Moving again: new results saved ({ct(NOW)}). "
                                                                       "The machine cap is off. Closing."})
        gh("PATCH", f"/issues/{i['number']}", json={"state": "closed"})


def builds():
    """{build id: (state, LastModified)} for every state page build"""
    out = {}
    for o in ls("site/builds/"):
        k = o["Key"]
        if k.endswith("/state.json") and k.count("/") == 3:
            bid = k.split("/")[2]
            if bid.startswith("st"):
                out[bid] = (getj(k, {}), o["LastModified"].timestamp())
    return out


def main():
    mine = machines_by_build()
    allb = builds()
    seen = getj(W + "seen.json", {})          # {bid: first time seen waiting}
    month = time.strftime("%Y-%m", time.gmtime(NOW))
    rows = []
    for bid, (st, _) in sorted(allb.items()):
        ds = mine.get(bid, [])
        stage = st.get("stage", "?")
        ck = (st.get("cost_check") or {}).get("last") or {}
        if ds:
            oldest = min(ts(d["created_at"]) for d in ds)
            new2, total = saved_since(bid, st, NOW - STUCK_H * 3600)
            new24, _ = saved_since(bid, st, NOW - 24 * 3600)
            pinned = memory_pinned(ds)
            rows.append((bid, states_of(st), stage, len(ds), total, new24, ck))
            log(bid, stage, f"{len(ds)} machines, oldest {round((NOW - oldest) / 3600, 1)} h;",
                f"{new2} saved in {STUCK_H} h, {total} results; memory pinned: {pinned}")
            if NOW - oldest > STUCK_H * 3600 and new2 == 0 and stage == "build":
                mem = pinned and len(pinned) * 2 >= len(ds)
                stuck(bid, st, ds, f"nothing saved in {STUCK_H} hours" + ("; its machines are out of memory" if mem else ""),
                      f"{len(ds)} machines have been running (the oldest since {ct(oldest)}); {total} results saved in "
                      f"all, none in the last {STUCK_H} hours. Stage: {stage}."
                      + (f"\n\n**Likely cause: memory.** {len(pinned)} of {len(ds)} machines had under {MEM_FREE_GB:.0f} GB "
                         f"free for the last 30 minutes ({', '.join(pinned[:8])}). Workers killed for memory leave no "
                         f"error message (Washington, Nov 2-3)." if mem else ""))
            else:
                new1, _ = saved_since(bid, st, NOW - 3600)
                if new1:
                    unstick(bid)
            seen.pop(bid, None)
        elif month in bid and stage in ("wait", "split"):
            first = seen.setdefault(bid, NOW)
            if NOW - first > WAIT_H * 3600 and not find_issue(f"Build waiting: {bid}"):
                gh("POST", "/issues", json={"title": f"Build waiting: {bid} ({states_of(st)})", "body":
                    f"**{states_of(st)}** ({bid}) has been at '{stage}' with no machines since about {ct(first)} "
                    f"({round((NOW - first) / 3600)} hours). It may be waiting on insurer files, a hold "
                    f"(site/month_hold.json) or a price-check OK; the hourly 'State Price Finder pages' run log says which. "
                    f"Ask Claude to check. This issue closes itself when the build starts."})
        else:
            seen.pop(bid, None)
            if stage not in ("wait", "split"):
                i = find_issue(f"Build waiting: {bid}")
                if i:
                    gh("PATCH", f"/issues/{i['number']}", json={"state": "closed"})
    # a waiting build that got machines: close its waiting issue
    for bid in mine:
        i = find_issue(f"Build waiting: {bid}")
        if i:
            gh("PATCH", f"/issues/{i['number']}", json={"state": "closed"})
    putj(W + "seen.json", seen)
    digest(rows)


def digest(rows):
    if time.gmtime(NOW).tm_hour != DIGEST_HOUR_UTC and not os.environ.get("DIGEST_NOW"):
        return
    day = time.strftime("%Y-%m-%d", time.gmtime(NOW))
    if getj(W + "digest_day.json") == day and not os.environ.get("DIGEST_NOW"):
        return
    lines = [f"**Builds with machines, {ct(NOW)}**", "",
             "| Build | States | Stage | Machines | Results saved | Saved last 24 h | Price check |",
             "|---|---|---|---|---|---|---|"]
    for bid, states, stage, n, total, new24, ck in rows:
        pc = (f"~{ck.get('hours_left')} h, ${ck.get('usd_left')} left" if ck.get("hours_left") is not None else "measuring")
        flag = " **(stuck?)**" if new24 == 0 else ""
        lines.append(f"| {bid} | {states} | {stage} | {n} | {total:,} | {new24:,}{flag} | {pc} |")
    if not rows:
        lines.append("| none | | | | | | |")
    stuck_open = [i["title"] for i in open_issues() if i.get("title", "").startswith(("Build stuck", "Build waiting"))]
    lines += ["", "Open stuck/waiting issues: " + ("; ".join(stuck_open) if stuck_open else "none") + ".",
              "", "(The price check's hours left uses the build's average speed since it started, so it runs high "
                  "after a slow start.)"]
    i = find_issue(DIGEST_TITLE)
    if not i:
        r = gh("POST", "/issues", json={"title": DIGEST_TITLE, "body": "One comment a day (about 7 AM CT) from "
                                        "board/build_watchdog.py: every page build with machines and how it's moving."})
        i = r.json() if r is not None else None
    if i:
        gh("POST", f"/issues/{i['number']}/comments", json={"body": "\n".join(lines)})
    putj(W + "digest_day.json", day)


if __name__ == "__main__":
    main()
