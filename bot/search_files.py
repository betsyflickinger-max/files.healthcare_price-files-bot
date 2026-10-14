"""Search the web for the price files of hospitals the daily run marks "no price file found" (added Oct 14, 2026).

The weekly site finder (find_sites.py) only tries OpenStreetMap, chain sites, sister hospitals' indexes and guessed
domains; after Oct 10-14 about 1,500 hospitals were still missing. This bot asks Claude (Anthropic API, secret
ANTHROPIC_API_KEY) to search the web for each one: its own website, its health system's website, its price
transparency page, its cms-hpt.txt and direct links to its machine-readable file.

Nothing Claude says is trusted. A find is ACCEPTED only when the bot checks it itself:
  index  https://<domain>/cms-hpt.txt (or the exact cms-hpt.txt link found) lists a location whose name matches the
         hospital (same rule as find_sites.py: score >= 85)            -> index_domain in data/hospitals.csv
  file   a file link whose first bytes are a CMS standard-charges file (hospital_name / standard_charge fields) and
         whose hospital or location name matches the hospital         -> mrf_url in data/hospitals.csv
A name shared by hospitals in other states, a name that only roughly matches, or a zip file is HELD for a hand check
(an issue is opened). The daily run (run.py) then downloads and checks the file like any other.

Every hospital searched gets a row in data/web_search_log.csv (what was found, where, why it was or wasn't accepted,
the price page and Claude's notes such as "closed in 2024"): evidence for the Price File Watch that we looked.
Hospitals searched in the last RESEARCH_DAYS days are skipped, so re-runs only pay for new or old searches.

Targets: every hospital whose latest status in R2 bot/manifest/hospitals/<state>.csv is "no price file found"
(--also-broken adds "link broken" and "not a price file"), plus hospitals the daily run has never checked that have
no website or file link.
Usage: python bot/search_files.py [--limit N] [--states TX,OK] [--also-broken] [--workers 8]
env: ANTHROPIC_API_KEY, R2_* ; MODEL (default claude-haiku-5-5), MAX_SEARCHES (per hospital, default 4),
     RESEARCH_DAYS (default 30), STOP_AFTER_MIN (default 320), PRICE_IN / PRICE_OUT ($ per million tokens, for the
     cost estimate only) and PRICE_SEARCH ($ per 1,000 searches).
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover  # noqa: E402
import find_sites as fs  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LIST, LOG = ROOT / "data" / "hospitals.csv", ROOT / "data" / "web_search_log.csv"
E = {k: v.strip() for k, v in os.environ.items()}
MODEL = E.get("MODEL") or "claude-haiku-5-5"
MAX_SEARCHES = int(E.get("MAX_SEARCHES") or 4)
LOG_FIELDS = ["ccn", "name", "city", "state", "type", "searched_at", "times_searched", "model", "result", "how",
              "domain", "mrf_url", "price_page", "why", "notes", "searches"]

PROMPT = """You help a public healthcare price-transparency project find US hospitals' federally required price files.
Since 2021 every US hospital must post a machine-readable file of its standard charges (JSON or CSV, sometimes zipped)
and, since 2024, a text file at https://<its website>/cms-hpt.txt that lists its locations and file links.
Search the web for the hospital given. Find, if they exist:
- website: the hospital's own website (domain), or the site of the health system that runs it
- price_page: the page where it posts its standard charges / price transparency / "price estimator" files
- cms_hpt_txt: the full link to the cms-hpt.txt that lists this hospital
- file_urls: direct links to this hospital's machine-readable standard charges file(s) (not the shoppable-services
  estimator tool, not a PDF chargemaster summary)
- status_note: if it closed, merged, was renamed, or is part of another hospital's license, say so with the year
Use web_fetch on the price page or cms-hpt.txt when that helps you find the exact file link.
Never invent or guess links: only give links you saw in search results or fetched pages; leave a field empty
otherwise. Make sure it is THIS hospital (same city and state), not a same-named hospital elsewhere.
Reply with ONLY a JSON object: {"website": "", "system_website": "", "price_page": "", "cms_hpt_txt": "",
"file_urls": [], "status_note": "", "notes": ""} (notes: one short sentence on what you found or why nothing)."""

USE = {"in": 0, "out": 0, "searches": 0, "fetches": 0, "calls": 0}
LOCK = threading.Lock()
TOOLS_FULL = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES,
               "user_location": {"type": "approximate", "country": "US"}},
              {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3, "max_content_tokens": 20000}]
STATE = {"tools": TOOLS_FULL, "beta": "web-fetch-2025-09-10"}


def ask(h, extra):
    user = (f"Hospital: {h['name']}\nCity: {h['city'].title()}, {h['state']}\nMedicare CCN: {h['ccn']}\n"
            f"Type: {h['type']}\n{extra}")
    for attempt in range(6):
        headers = {"x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
        if STATE["beta"]:
            headers["anthropic-beta"] = STATE["beta"]
        body = {"model": MODEL, "max_tokens": 2500, "system": PROMPT, "tools": STATE["tools"],
                "messages": [{"role": "user", "content": user}]}
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=300)
        except requests.RequestException as e:
            time.sleep(10 * (attempt + 1)); continue
        if r.status_code == 400 and "web_fetch" in r.text and STATE["beta"]:
            print("  web_fetch not available on this key/model; continuing with web search only", flush=True)
            STATE.update(tools=TOOLS_FULL[:1], beta=""); continue
        if r.status_code in (429, 529, 500, 502, 503):
            time.sleep(min(float(r.headers.get("retry-after") or 15 * (attempt + 1)), 120)); continue
        if r.status_code != 200:
            print("  API error", r.status_code, r.text[:300], flush=True)
            return None, 0
        out = r.json()
        u = out.get("usage", {}); st = u.get("server_tool_use", {})
        with LOCK:
            USE["in"] += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            USE["out"] += u.get("output_tokens", 0); USE["calls"] += 1
            USE["searches"] += st.get("web_search_requests", 0); USE["fetches"] += st.get("web_fetch_requests", 0)
        txt = "".join(c.get("text", "") for c in out.get("content", []) if c.get("type") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        n = st.get("web_search_requests", 0)
        try:
            return (json.loads(m.group(0)) if m else {"notes": txt[:200]}), n
        except json.JSONDecodeError:
            return {"notes": txt[:200]}, n
    return None, 0


def head_text(url, limit=1_000_000):
    """First ~1 MB of a link as text (requests un-gzips transfer encoding). '' if unreachable or binary."""
    try:
        with requests.get(url, headers={"User-Agent": discover.UA}, timeout=40, stream=True, verify=False,
                          allow_redirects=True) as r:
            if r.status_code != 200:
                return "", f"HTTP {r.status_code}"
            ct = r.headers.get("content-type", "").lower()
            buf = b""
            for chunk in r.iter_content(65536):
                buf += chunk
                if len(buf) >= limit:
                    break
            if buf[:2] == b"PK" or "zip" in ct:
                return "", "zip file"
            return buf.decode("utf-8", "replace"), ct
    except requests.RequestException as e:
        return "", type(e).__name__


def names_in_file(text):
    """Hospital / location names from the head of a CMS standard-charges file (CSV or JSON)."""
    low = text[:200000].lower()
    if "hospital_name" not in low and "standard_charge" not in low:
        return None, ""
    out = []
    if text.lstrip()[:1] in "{[":
        for k in ("hospital_name", "location_name", "hospital_location"):
            for m in re.finditer(rf'"{k}"\s*:\s*(\[[^\]]*\]|"[^"]*")', text[:200000]):
                try:
                    v = json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
                out += v if isinstance(v, list) else [v]
        addr = " ".join(re.findall(r'"hospital_address"\s*:\s*(\[[^\]]*\]|"[^"]*")', text[:200000]))
    else:
        rows = list(csv.reader(io.StringIO("\n".join(text.splitlines()[:3]))))
        addr = ""
        if len(rows) >= 2:
            hdr = [c.strip().lower() for c in rows[0]]
            for i, c in enumerate(hdr):
                if i < len(rows[1]) and (c.startswith("hospital_name") or c.startswith("location_name")):
                    out += rows[1][i].split("|")
                if i < len(rows[1]) and c.startswith("hospital_address"):
                    addr += rows[1][i]
    return [str(x) for x in out if x], addr


def check_file(h, url, dup):
    text, info = head_text(url)
    if not text:
        return None, f"file link {info}" if info else "file link unreadable"
    names, addr = names_in_file(text)
    if names is None:
        return None, f"file link is not a CMS price file ({info[:40]})"
    best = max([discover.score(h["name"], n) for n in names] + [0])
    words = any(fs.words_in(h["name"], n) for n in names)
    city_ok = h["city"].lower() in (addr or text[:5000]).lower()
    if (best >= 85 or words) and (city_ok or not dup):
        return "yes", f"file names '{(names or [''])[0][:60]}' ({round(best)})"
    if best >= 70 or words:
        return "held", f"file names '{(names or [''])[0][:60]}' ({round(best)}); city {'found' if city_ok else 'not found'}"
    return None, f"file is for '{(names or ['?'])[0][:60]}', not this hospital"


def check_index_url(h, url, dup):
    """A cms-hpt.txt at an exact link (some sites keep it off the root)."""
    text, info = head_text(url, 2_000_000)
    ents = discover.parse(text) if text and not text.lstrip().startswith("<") else []
    if not ents:
        return None
    sc, e = max(((discover.score(h["name"], x.get("location-name", "")), x) for x in ents), key=lambda t: t[0])
    if sc >= 85:
        return dict(domain=discover.host(url), mrf=e["mrf-url"], score=round(sc), loc=e.get("location-name", ""),
                    accepted="held" if dup else "yes")
    return None


def verify(h, ans, dup):
    """Returns (result, how, domain, mrf_url, why)."""
    hosts, why = [], []
    for k in ("website", "system_website", "price_page", "cms_hpt_txt"):
        d = discover.host(ans.get(k) or "")
        if d and not d.endswith(discover.SHARED_HOSTS) and d not in hosts:
            hosts.append(d)
    files = [discover.clean(u) for u in (ans.get("file_urls") or []) if isinstance(u, str) and u.startswith("http")][:4]
    for u in files:
        d = discover.host(u)
        if d and not d.endswith(discover.SHARED_HOSTS) and d not in hosts:
            hosts.append(d)
    held = None
    for d in hosts[:5]:
        try:
            res = fs.try_domain(h, d, "web", fs.DUP)
        except Exception:
            res = None
        if res and res["accepted"] == "yes":
            return "found", f"index {res['index_url']} lists '{res['location'][:60]}' ({res['score']})", d, "", ""
        if res:
            held = held or ("held", f"index {res['index_url']} lists '{res['location'][:60]}'; same name in another state", d, "", "")
        why.append(f"{d}: no matching cms-hpt.txt")
    if ans.get("cms_hpt_txt", "").startswith("http"):
        r = check_index_url(h, discover.clean(ans["cms_hpt_txt"]), dup)
        if r and r["accepted"] == "yes":
            return "found", f"index {ans['cms_hpt_txt'][:100]} lists '{r['loc'][:60]}' ({r['score']})", "", r["mrf"], ""
        if r:
            held = held or ("held", f"index {ans['cms_hpt_txt'][:100]}; same name in another state", "", r["mrf"], "")
    for u in files:
        ok, msg = check_file(h, u, dup)
        if ok == "yes":
            return "found", "file: " + msg, "", u, ""
        if ok == "held":
            held = held or ("held", "file: " + msg, "", u, "")
        why.append(msg)
    if held:
        return held
    return ("not found", "", "", "", "; ".join(why)[:300] or "nothing found")


def targets(rows, a):
    want = {s.strip().upper() for s in (a.states or "").split(",") if s.strip()}
    bad = {"no price file found"} | ({"link broken", "not a price file"} if a.also_broken else set())
    s3, bucket = store.r2()
    status = {}
    for st in sorted({r["state"] for r in rows}):
        if want and st not in want:
            continue
        try:
            body = s3.get_object(Bucket=bucket, Key=f"{store.R2_PREFIX}manifest/hospitals/{st}.csv")["Body"].read().decode()
            for m in csv.DictReader(io.StringIO(body)):
                status[m["ccn"]] = m.get("status", "")
        except Exception:
            pass
    out = []
    for r in rows:
        if want and r["state"] not in want:
            continue
        s = status.get(r["ccn"])
        if s in bad or (s is None and not r.get("index_domain") and not r.get("mrf_url")):
            r["_status"] = s or "never checked"
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--states", default="")
    ap.add_argument("--also-broken", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if not E.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    rows = list(csv.DictReader(open(LIST, encoding="utf-8")))
    fields = list(rows[0].keys()) + (["found_by"] if "found_by" not in rows[0] else [])
    states_by = {}
    for r in rows:
        r["_norm"] = " ".join(discover._toks(r["name"]))
        states_by.setdefault(r["_norm"], set()).add(r["state"])
    fs.DUP = {n for n, s in states_by.items() if len(s) > 1}
    log = {r["ccn"]: r for r in csv.DictReader(open(LOG, encoding="utf-8"))} if LOG.exists() else {}
    cut = (date.today() - timedelta(days=int(E.get("RESEARCH_DAYS") or 30))).isoformat()
    todo = [r for r in targets(rows, a) if log.get(r["ccn"], {}).get("searched_at", "") < cut]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo):,} hospitals to search (model {MODEL}, up to {MAX_SEARCHES} searches each)", flush=True)
    t0, stop = time.time(), float(E.get("STOP_AFTER_MIN") or 320) * 60
    today = date.today().isoformat()
    counts = {"found": 0, "held": 0, "not found": 0, "error": 0}
    held_rows = []

    def one(h):
        if time.time() - t0 > stop:
            return h, None
        extra = ""
        if h.get("index_domain"):
            extra = f"Note: {h['index_domain']}/cms-hpt.txt is missing or does not list this hospital.\n"
        ans, ns = ask(h, extra)
        if ans is None:
            return h, ("error", "", "", "", "API error", {}, 0)
        if not isinstance(ans, dict):
            ans = {"notes": str(ans)[:200]}
        res = verify(h, ans, h["_norm"] in fs.DUP)
        return h, res + (ans, ns)

    with ThreadPoolExecutor(a.workers) as ex:
        for i, (h, res) in enumerate(ex.map(one, todo), 1):
            if res is None:
                continue
            result, how, dom, mrf, why, ans, ns = res
            counts[result] = counts.get(result, 0) + 1
            L = log.get(h["ccn"], {})
            log[h["ccn"]] = dict(ccn=h["ccn"], name=h["name"], city=h["city"], state=h["state"], type=h["type"],
                                 searched_at=today, times_searched=str(int(L.get("times_searched") or 0) + 1), model=MODEL,
                                 result=result, how=how, domain=dom, mrf_url=mrf, price_page=(ans.get("price_page") or "")[:300],
                                 why=why, notes=" ".join(x for x in (ans.get("status_note") or "", ans.get("notes") or "") if x)[:300],
                                 searches=str(ns))
            if result == "found":
                if dom:
                    h["index_domain"] = dom
                if mrf and not dom:
                    h["mrf_url"] = mrf
                h["found_by"] = f"web {today}"
            elif result == "held":
                held_rows.append(log[h["ccn"]])
            if i % 25 == 0:
                print(f"  {i:,}/{len(todo):,}: {counts} · {USE['searches']} searches", flush=True)
    for r in rows:
        r.pop("_norm", None); r.pop("_status", None)
    with open(LIST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields); w.writeheader(); w.writerows(rows)
    with open(LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, LOG_FIELDS, extrasaction="ignore"); w.writeheader()
        w.writerows(sorted(log.values(), key=lambda r: (r["state"], r["ccn"])))
    pin, pout, ps = float(E.get("PRICE_IN") or 1), float(E.get("PRICE_OUT") or 5), float(E.get("PRICE_SEARCH") or 10)
    cost = USE["in"] / 1e6 * pin + USE["out"] / 1e6 * pout + USE["searches"] / 1000 * ps
    n = sum(counts.values())
    held_rows = [r for r in log.values() if r.get("result") == "held"]   # every open hand check, not just this run's
    with open(ROOT / "held_web.md", "w") as f:
        if held_rows:
            f.write("The web-search bot found these, but the match isn't certain enough to add automatically "
                    "(same name in another state, a rough name match, or a zip file). If one is right, put the domain "
                    "in `index_domain` or the file link in `mrf_url` in data/hospitals.csv.\n\n"
                    "| State | Hospital | City | Website | File link | Why held |\n|---|---|---|---|---|---|\n")
            for r in held_rows:
                f.write(f"| {r['state']} | {r['name']} | {r['city']} | {r['domain']} | {r['mrf_url'][:90]} | {r['how'][:120]} |\n")
    summary = (f"done: searched {n:,} hospitals; found {counts['found']:,}, held {counts['held']:,} for a hand check, "
               f"not found {counts['not found']:,}, errors {counts.get('error', 0):,}. {USE['searches']:,} web searches, "
               f"{USE['fetches']:,} page fetches, {USE['in']:,} tokens in / {USE['out']:,} out: about ${cost:,.2f} "
               f"(${cost / max(n, 1):.3f} per hospital)")
    print(summary)


if __name__ == "__main__":
    main()
