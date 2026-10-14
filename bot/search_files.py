"""Search the web for the price files of hospitals the daily run marks "no price file found" (added Oct 14, 2026).

The weekly site finder (find_sites.py) only tries OpenStreetMap, chain sites, sister hospitals' indexes and guessed
domains; after Oct 10-14 about 1,500 hospitals were still missing. This bot asks Claude (Anthropic API, secret
ANTHROPIC_API_KEY) to search the web for each one: its own website, its health system's website, its price
transparency page, its cms-hpt.txt and direct links to its machine-readable file.

Layer 2 (bot/deep_find.py, free): before and after Claude's search, the bot also matches the hospital (by its
everyday, legal and doing-business-as names from Medicare's enrollment list) against every cms-hpt.txt we know
nationwide, crawls its sites (price pages, common paths, sitemaps) and searches the Wayback Machine / Common Crawl
and the big price-file vendors' sites for any file link ever posted. Hospitals searched recently and not found get
the free layers again without a new Claude search (--no-deep-again turns that off).

Nothing Claude or the crawl finds is trusted. A find is ACCEPTED only when the bot checks it itself:
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
import deep_find as deep  # noqa: E402
import discover  # noqa: E402
import find_sites as fs  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LIST, LOG = ROOT / "data" / "hospitals.csv", ROOT / "data" / "web_search_log.csv"
E = {k: v.strip() for k, v in os.environ.items()}
MODEL = E.get("MODEL") or "claude-haiku-5-5"
MAX_SEARCHES = int(E.get("MAX_SEARCHES") or 4)
LOG_FIELDS = ["ccn", "name", "city", "state", "type", "searched_at", "times_searched", "model", "result", "how",
              "domain", "mrf_url", "price_page", "why", "notes", "searches", "answer"]
NAMES, NAT, VENDORS = {}, None, []   # filled in main(): legal/DBA names, national index, vendor archive links

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
              {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3, "max_content_tokens": 10000}]
STATE = {"tools": TOOLS_FULL, "beta": "web-fetch-2025-09-10"}


def ask(h, extra):
    n = NAMES.get(h["ccn"], {})
    more = "".join(f"{k}: {v}\n" for k, v in (("Legal name", n.get("legal")), ("Doing business as", n.get("dba")),
                                               ("Address", n.get("address")), ("NPI", n.get("npi"))) if v)
    user = (f"Hospital: {h['name']}\nCity: {h['city'].title()}, {h['state']}\nMedicare CCN: {h['ccn']}\n"
            f"Type: {h['type']}\n{more}{extra}"
            "Price files are often named for the legal name, like <EIN>_<legal-name>_standardcharges.json, and are often "
            "hosted by a vendor (Panacea, Hospital Price Index, Craneware, Hyve, PARA...) rather than the hospital's site.")
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


def check_file(h, url, dup, names_=None, strict=False):
    text, info = head_text(url)
    if info == "zip file":
        return "held", "zipped file link (can't check the hospital name inside without downloading it)"
    if not text:
        return None, f"file link {info}" if info else "file link unreadable"
    names, addr = names_in_file(text)
    if names is None:
        return None, f"file link is not a CMS price file ({info[:40]})"
    ours = names_ or [h["name"]]
    scored = sorted(((discover.score(o, n), n) for n in names for o in ours), reverse=True) or [(0, "?")]
    best, bname = scored[0]
    words = any(fs.words_in(o, n) for n in names for o in ours)
    city_ok = h["city"].lower() in (addr or text[:5000]).lower()
    if (best >= 85 or words) and (city_ok or (not dup and not strict)):
        return "yes", f"file names '{bname[:60]}' ({round(best)})"
    if best >= 70 or words:
        return "held", f"file names '{bname[:60]}' ({round(best)}); city {'found' if city_ok else 'not found'}"
    return None, f"file is for '{bname[:60]}', not this hospital"


def check_index_url(h, url, dup, names_=None):
    """A cms-hpt.txt at an exact link (some sites keep it off the root)."""
    text, info = head_text(url, 2_000_000)
    ents = discover.parse(text) if text and not text.lstrip().startswith("<") else []
    if not ents:
        return None
    ours = names_ or [h["name"]]
    sc, e, o = max(((discover.score(o, x.get("location-name", "")), x, o) for x in ents for o in ours), key=lambda t: t[0])
    if sc >= 85:
        rough = not fs.words_in(o, e.get("location-name", ""))
        return dict(domain=discover.host(url), mrf=e["mrf-url"], score=round(sc), loc=e.get("location-name", ""),
                    accepted="held" if dup or rough else "yes")
    return None


def verify(h, ans, dup, names_=None):
    """Returns (result, how, domain, mrf_url, why)."""
    names_ = names_ or [h["name"]]
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
        res = None
        for nm in names_:
            try:
                r_ = fs.try_domain(dict(h, name=nm), d, "web", fs.DUP)
            except Exception:
                r_ = None
            if r_ and r_["accepted"] == "yes" and not fs.words_in(nm, r_["location"]):
                r_ = dict(r_, accepted="no - rough match")
            if r_ and (res is None or r_["accepted"] == "yes"):
                res = r_
            if res and res["accepted"] == "yes":
                break
        if res and res["accepted"] == "yes" and not any(fs.words_in(nm, res["location"]) for nm in names_):
            # a big system index ("CHI St. Vincent" for CHI St Vincent Infirmary) may list a sister hospital or the whole
            # system: every distinctive word of the name must be in the listed location, else a person checks it
            res = dict(res, accepted="no - rough match")
        if res and res["accepted"] == "yes":
            return "found", f"index {res['index_url']} lists '{res['location'][:60]}' ({res['score']})", d, "", ""
        if res:
            held = held or ("held", f"index {res['index_url']} lists '{res['location'][:60]}' ({res['score']}); "
                            + ("rough match" if "rough" in res["accepted"] else "same name in another state"), d, "", "")
        why.append(f"{d}: no matching cms-hpt.txt")
    if ans.get("cms_hpt_txt", "").startswith("http"):
        r = check_index_url(h, discover.clean(ans["cms_hpt_txt"]), dup, names_)
        if r and r["accepted"] == "yes":
            return "found", f"index {ans['cms_hpt_txt'][:100]} lists '{r['loc'][:60]}' ({r['score']})", "", r["mrf"], ""
        if r:
            held = held or ("held", f"index {ans['cms_hpt_txt'][:100]}; same name in another state", "", r["mrf"], "")
    for u in files:
        ok, msg = check_file(h, u, dup, names_)
        if ok == "yes":
            return "found", "file: " + msg, "", u, ""
        if ok == "held":
            held = held or ("held", "file: " + msg, "", u, "")
        why.append(msg)
    if held:
        return held
    return ("not found", "", "", "", "; ".join(why)[:300] or "nothing found")


def deep_layer(h, hosts, pages, names_, dup, done_hosts):
    """Layer 2 on the hospital's sites: crawl (price pages, common paths, sitemap), then archives (Wayback, Common
    Crawl, vendor sites). Returns (result, how, domain, mrf_url, why) or None; adds crawled hosts to done_hosts."""
    held, why = None, []
    for i, d in enumerate([x for x in hosts if x and x not in done_hosts][:3]):
        done_hosts.add(d)
        files, idx, n = deep.crawl(d, [p for p in pages if discover.host(p) == d])
        for u in idx:
            r = check_index_url(h, discover.clean(u), dup, names_)
            if r and r["accepted"] == "yes":
                return "found", f"crawl: index {u[:100]} lists '{r['loc'][:60]}' ({r['score']})", "", r["mrf"], ""
            if r:
                held = held or ("held", f"crawl: index {u[:100]} lists '{r['loc'][:60]}'", "", r["mrf"], "")
        for u in files[:12]:
            ok, msg = check_file(h, discover.clean(u), dup, names_)
            if ok == "yes":
                return "found", f"crawl ({n} pages on {d}): " + msg, "", discover.clean(u), ""
            if ok == "held":
                held = held or ("held", "crawl: " + msg, "", discover.clean(u), "")
        why.append(f"{d}: crawled {n} pages, {len(files)} file-like links")
        if E.get("NO_ARCHIVES") == "1":
            continue
        arch = deep.archives(d, names_, VENDORS if i == 0 else ())
        dead = []
        for u in arch[:14]:
            own = discover.host(u) == d
            if "cms-hpt" in u.lower():
                r = check_index_url(h, discover.clean(u), dup, names_)
                if r and r["accepted"] == "yes":
                    return "found", f"archive: index {u[:100]} lists '{r['loc'][:60]}' ({r['score']})", "", r["mrf"], ""
                continue
            ok, msg = check_file(h, discover.clean(u), dup, names_, strict=not own)
            if ok == "yes":
                return "found", "archive: " + msg, "", discover.clean(u), ""
            if ok == "held":
                held = held or ("held", "archive: " + msg, "", discover.clean(u), "")
            elif "HTTP 404" in msg or "HTTP 410" in msg:
                dead.append(u)
        why.append(f"archives: {len(arch)} links" + (f", {len(dead)} gone now (e.g. {dead[0][:90]})" if dead else ""))
    if held:
        return held
    return ("not found", "", "", "", "; ".join(why)) if why else None


def national_layer(h, names_, dup):
    held = None
    for idx, mrf, loc in NAT.candidates(h, names_) if NAT else []:
        ok, msg = check_file(h, mrf, dup, names_, strict=True)
        if ok == "yes":
            return "found", f"national: {idx[:80]} lists '{loc[:50]}'; " + msg, "", mrf, ""
        if ok == "held":
            held = held or ("held", f"national: {idx[:80]} lists '{loc[:50]}'; " + msg, "", mrf, "")
    return held


def logged_hosts(L):
    """Sites an earlier search found for this hospital (domain, price page, and those named in 'why')."""
    hs = [L.get("domain", ""), discover.host(L.get("price_page", ""))]
    hs += re.findall(r"([a-z0-9.-]+\.[a-z]{2,}): (?:no matching|crawled)", L.get("why", ""))
    try:
        a = json.loads(L.get("answer") or "{}")
        hs += [discover.host(a.get(k) or "") for k in ("website", "system_website", "price_page", "cms_hpt_txt")]
    except json.JSONDecodeError:
        pass
    return [x for x in dict.fromkeys(hs) if x and not x.endswith(discover.SHARED_HOSTS)]


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
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--no-deep-again", action="store_true",
                    help="don't run the free layers again on hospitals searched recently and not found")
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
    todo = []
    for r in targets(rows, a):
        L = log.get(r["ccn"], {})
        if L.get("searched_at", "") < cut:
            todo.append(r)
        elif not a.no_deep_again and L.get("result") in ("not found", "error") and "deep" not in L.get("model", ""):
            r["_deep_only"] = True   # searched recently: free layers only, no new Claude search
            todo.append(r)
    if a.limit:
        todo = todo[:a.limit]
    global NAMES, NAT, VENDORS
    NAMES = deep.enrollment_names()
    NAT = deep.National(rows)
    VENDORS = [] if E.get("NO_ARCHIVES") == "1" else deep.vendor_urls()
    print(f"{len(todo):,} hospitals to search (model {MODEL}, up to {MAX_SEARCHES} searches each)", flush=True)
    t0, stop = time.time(), float(E.get("STOP_AFTER_MIN") or 320) * 60
    today = date.today().isoformat()
    counts = {"found": 0, "held": 0, "not found": 0, "error": 0}
    held_rows = []

    def one(h):
        if time.time() - t0 > stop:
            return h, None
        dup, names_ = h["_norm"] in fs.DUP, deep.all_names(h, NAMES)
        L = log.get(h["ccn"], {})
        try:
            prev = json.loads(L.get("answer") or "{}")
        except json.JSONDecodeError:
            prev = {}
        prev.setdefault("price_page", L.get("price_page", ""))
        prev.setdefault("notes", L.get("notes", ""))
        held = None
        # layer 2a: every index we know, nationwide
        res = national_layer(h, names_, dup)
        if res and res[0] == "found":
            return h, res + (prev, 0)
        held = held or res
        # layer 2b: crawl + archives on the sites we already know
        done_hosts = set()
        known = [h.get("index_domain", "")] + logged_hosts(L)
        res = deep_layer(h, known, [prev.get("price_page", "")], names_, dup, done_hosts)
        if res and res[0] == "found":
            return h, res + (prev, 0)
        if res and res[0] == "held":
            held = held or res
        why0 = res[4] if res else ""
        if h.get("_deep_only"):
            return h, (held or ("not found", "", "", "", why0 or "free layers found nothing")) + (prev, 0)
        # layer 1: Claude searches the web
        extra = ""
        if h.get("index_domain"):
            extra = f"Note: {h['index_domain']}/cms-hpt.txt is missing or does not list this hospital.\n"
        ans, ns = ask(h, extra)
        if ans is None:
            return h, (held or ("error", "", "", "", "API error")) + (prev, 0)
        if not isinstance(ans, dict):
            ans = {"notes": str(ans)[:200]}
        res = verify(h, ans, dup, names_)
        if res[0] == "found":
            return h, res + (ans, ns)
        held = held or (res if res[0] == "held" else None)
        # layer 2c: crawl + archives on the sites Claude found
        hosts = [discover.host(ans.get(k) or "") for k in ("website", "system_website", "price_page", "cms_hpt_txt")]
        hosts += [discover.host(u) for u in (ans.get("file_urls") or []) if isinstance(u, str)]
        hosts = [x for x in dict.fromkeys(hosts) if x and not x.endswith(discover.SHARED_HOSTS)]
        res2 = deep_layer(h, hosts, [ans.get("price_page") or ""], names_, dup, done_hosts)
        if res2 and res2[0] == "found":
            return h, res2 + (ans, ns)
        if res2 and res2[0] == "held":
            held = held or res2
        why = "; ".join(x for x in (res[4], res2[4] if res2 else "", why0) if x)[:400]
        return h, (held or ("not found", "", "", "", why)) + (ans, ns)

    left = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (h, res) in enumerate(ex.map(one, todo), 1):
            if res is None:
                left += 1   # out of time: the workflow starts a fresh run for these
                continue
            result, how, dom, mrf, why, ans, ns = res
            counts[result] = counts.get(result, 0) + 1
            L = log.get(h["ccn"], {})
            log[h["ccn"]] = dict(ccn=h["ccn"], name=h["name"], city=h["city"], state=h["state"], type=h["type"],
                                 searched_at=today if not h.get("_deep_only") else L.get("searched_at", today),
                                 times_searched=str(int(L.get("times_searched") or 0) + 1),
                                 model=(MODEL if not h.get("_deep_only") else L.get("model", "")) + "+deep",
                                 result=result, how=how, domain=dom, mrf_url=mrf, price_page=(ans.get("price_page") or "")[:300],
                                 why=why, notes=" ".join(x for x in (ans.get("status_note") or "", ans.get("notes") or "") if x)[:300],
                                 searches=str(ns), answer=json.dumps(ans, ensure_ascii=False)[:1500])
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
        r.pop("_norm", None); r.pop("_status", None); r.pop("_deep_only", None)
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
               f"(${cost / max(n, 1):.3f} per hospital); left {left}")
    print(summary)


if __name__ == "__main__":
    main()
