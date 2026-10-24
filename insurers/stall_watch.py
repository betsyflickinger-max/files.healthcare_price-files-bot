"""Stalled-machine alert (Oct 24, 2026, Betsy asked for it).

A rented machine that should be working but has sat under 5% CPU for 30 minutes is probably stuck: it keeps billing
and its file never finishes. Run from the insurer fill (every 10 minutes), at most once per 9 minutes:
  - every machine on the account is checked: queue machines that hold a file, and website-build machines
    (upfront-site-*, which exist only while they work), once they are over an hour old
  - CPU = DigitalOcean monitoring, last 30 minutes (the same reading as the control center's "CPU (30 min)" column)
  - a machine must look stalled on two checks in a row (at least ~10 minutes apart) before anyone is told
  - one open GitHub issue, label machine-stalled, assigned to Betsy so GitHub emails her; new stalled machines are
    added as a comment; the issue closes itself when nothing is stalled any more
Read-only towards the machines: it never stops or deletes one. Never raises (an alert must not stop the fill).
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

import droplets

STATE = "bot/alerts/stalled.json"   # {"at": last check, "seen": {machine name: first time it looked stalled}}
LABEL = "machine-stalled"
TITLE = "Machine stalled: needs a look"
OWNER = "betsyflickinger-max"
REPO = os.environ.get("GITHUB_REPOSITORY", "betsyflickinger-max/price-files-bot")
MIN_GAP = 9 * 60
CPU_UNDER = 5


def cpu_pct(did):
    end = int(time.time())
    r = requests.get(f"{droplets.API}/monitoring/metrics/droplet/cpu", headers=droplets._h(), timeout=60,
                     params=dict(host_id=str(did), start=str(end - 1800), end=str(end)))
    tot = {}
    for x in r.json()["data"]["result"]:
        v = x["values"]
        if len(v) >= 2:
            tot[x["metric"].get("mode")] = float(v[-1][1]) - float(v[0][1])
    allt = sum(tot.values())
    return round(100 * (1 - (tot.get("idle", 0) + tot.get("iowait", 0)) / allt)) if allt > 0 else None


def _gh(method, path, **kw):
    tok = "".join(os.environ.get("GH_TOKEN", "").split())
    if not tok:
        raise RuntimeError("no GH_TOKEN")
    r = requests.request(method, f"https://api.github.com/repos/{REPO}{path}", timeout=60,
                         headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def check(s3, b, claims):
    try:
        _check(s3, b, claims)
    except Exception as e:
        print("stall watch:", repr(e)[:200])


def _check(s3, b, claims):
    try:
        st = json.loads(s3.get_object(Bucket=b, Key=STATE)["Body"].read())
    except Exception:
        st = {"at": 0, "seen": {}}
    if time.time() - st.get("at", 0) < MIN_GAP:
        return
    r = requests.get(f"{droplets.API}/droplets", params={"per_page": 200}, headers=droplets._h(), timeout=60)
    r.raise_for_status()
    now = datetime.now(timezone.utc)
    busy_names = {c.get("name") for c in claims.values()}
    todo = []
    for d in r.json()["droplets"]:
        n = d["name"]
        age_h = (now - datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))).total_seconds() / 3600
        should_work = (n.startswith("upfront-fleet-") and n in busy_names) or n.startswith("upfront-site-")
        if should_work and age_h > 1:
            todo.append((d["id"], n, round(age_h, 1)))
    with ThreadPoolExecutor(8) as P:
        cpus = list(P.map(lambda t: _safe_cpu(t[0]), todo))
    stalled = {n: (h, c) for (_, n, h), c in zip(todo, cpus) if c is not None and c < CPU_UNDER}
    seen = {n: t for n, t in st.get("seen", {}).items() if n in stalled}
    for n in stalled:
        seen.setdefault(n, now.isoformat(timespec="seconds"))
    confirmed = {n: v for n, v in stalled.items() if (now - datetime.fromisoformat(seen[n])).total_seconds() >= MIN_GAP}
    print(f"stall watch: {len(todo)} working machines checked; {len(stalled)} under {CPU_UNDER}% CPU; "
          f"{len(confirmed)} on two checks in a row" + (f": {', '.join(confirmed)}" if confirmed else ""))
    told = set(st.get("told", []))
    open_issues = _gh("GET", f"/issues?state=open&labels={LABEL}&per_page=5")
    if confirmed:
        work = {c.get("name"): jid.split("__", 1)[-1] for jid, c in claims.items()}
        lines = [f"- **{n}**: {c}% CPU over the last 30 minutes, up {h} hours"
                 + (f", on `{work[n]}`" if n in work else "") for n, (h, c) in sorted(confirmed.items())]
        new = [n for n in confirmed if n not in told]
        body = ("These machines should be working but have used almost no CPU for 30 minutes on two checks in a row, "
                "so they are probably stuck (still billing, file not finishing):\n\n" + "\n".join(lines) +
                "\n\nA website-build machine (upfront-site-*) can also sit quiet while it waits for other machines' tables, "
                "so treat those as a maybe. Nothing was stopped. Ask Claude to look at them (the Fleet check workflow shows their logs). "
                "This issue closes itself once no machine looks stalled.")
        if not open_issues:
            try:
                _gh("POST", "/labels", json={"name": LABEL, "color": "B22222", "description": "A rented machine looks stuck"})
            except Exception:
                pass
            _gh("POST", "/issues", json={"title": TITLE, "body": body, "labels": [LABEL], "assignees": [OWNER]})
            print("stall watch: opened an issue")
        elif new:
            _gh("POST", f"/issues/{open_issues[0]['number']}/comments", json={"body": body})
            print("stall watch: added to the open issue")
        told |= set(confirmed)
    elif open_issues:
        for i in open_issues:
            _gh("POST", f"/issues/{i['number']}/comments", json={"body": "No machine looks stalled any more. Closing."})
            _gh("PATCH", f"/issues/{i['number']}", json={"state": "closed"})
        print("stall watch: closed the issue")
        told = set()
    s3.put_object(Bucket=b, Key=STATE, Body=json.dumps({"at": time.time(), "seen": seen, "told": sorted(told & set(stalled))}).encode())


def _safe_cpu(did):
    try:
        return cpu_pct(did)
    except Exception:
        return None
