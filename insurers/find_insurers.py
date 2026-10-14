"""Find every insurer's price files (Transparency in Coverage), state by state (added Oct 14, 2026).

Who: every health insurer selling marketplace plans in the HealthCare.gov states (CMS plan-attributes file, latest
year posted), plus, for states that run their own marketplace (not in CMS's file), the insurers Claude lists for that
state. Insurers the bot already reads (insurers/networks*.csv) are marked "already reading" and not searched.

How, for each one not yet found:
  1. Claude searches the web (Anthropic API, web search + page fetch) for its table-of-contents (index) file, its
     in-network rate files, or its transparency page.
  2. Free layer: the bot crawls those pages for file links and searches the Wayback Machine / Common Crawl for index
     and in-network files ever posted on the insurer's site.
  3. Nothing is trusted until the bot opens the first bytes itself: a table of contents has "reporting_entity_name" and
     "reporting_structure"; a rate file has "reporting_entity_name" and "in_network"/"provider_references". The
     reporting entity has to match the insurer's name, or the find goes to a hand check.
  Sites that only offer a JavaScript search tool (HealthSparq, Sapphire...) are recorded as "portal only": that's a
  Price File Watch finding, and the link is kept so a person (or a browser bot) can pull the index from it.

Writes data/insurer_sources.csv (one row per state + insurer; the evidence for the Price File Watch). Finding a file
does not read it: adding an insurer to the reading list (insurers/networks*.csv) costs machine time, so that stays a
separate decision, state by state.
Usage: python insurers/find_insurers.py [--states TX,OK] [--limit N] [--workers 8]
env: ANTHROPIC_API_KEY, MODEL (default claude-haiku-5-5), RESEARCH_DAYS (default 30), PUF_YEAR (default: newest posted),
     SBE_STATES (states with their own marketplace to ask Claude about; default below)
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
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bot"))
import deep_find as deep  # noqa: E402
import discover  # noqa: E402

E = {k: v.strip() for k, v in os.environ.items()}
MODEL = E.get("MODEL") or "claude-haiku-5-5"
OUT = ROOT / "data" / "insurer_sources.csv"
FIELDS = ["state", "issuer_id", "issuer", "source", "result", "url", "reporting_entity", "how", "price_page", "notes",
          "searched_at", "times_searched", "searches", "answer"]
SBE = (E.get("SBE_STATES") or "CA,CO,CT,DC,GA,ID,IL,KY,MA,MD,ME,MN,NJ,NM,NV,NY,PA,RI,VA,VT,WA").split(",")
PORTALS = ("healthsparq.com", "sapphiremrfhub.com", "transparency-in-coverage.uhc.com", "anthem.com/machine-readable",
           "cms-machine-readable", "mrfhub", "kyruus")
TIC_RX = r"(?i)index\.json|table.of.contents|_index|/toc|in.network|innetwork|transparency|machine.readable|mrf"
USE = {"in": 0, "out": 0, "searches": 0, "fetches": 0}
LOCK = threading.Lock()
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4,
          "user_location": {"type": "approximate", "country": "US"}},
         {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3, "max_content_tokens": 10000}]
STATE = {"tools": TOOLS, "beta": "web-fetch-2025-09-10"}

PROMPT = """You help a public healthcare price-transparency project find US health insurers' federally required
Transparency in Coverage machine-readable files. Since 2022 every health insurer and group health plan must post, on a
public website, monthly JSON files of its negotiated rates ("in-network rates"), usually listed in a
"table of contents" / index JSON file. Search the web for the insurer given (in the state given). Find, if they exist:
- toc_urls: direct links to its table-of-contents / index JSON file(s) (often ..._index.json)
- file_urls: direct links to in-network rate JSON files (often .json.gz), only if no index was found
- page: the page where it posts these files ("transparency in coverage", "machine-readable files")
- portal_only: true if the files are only reachable through a search tool that needs JavaScript or a login
- status_note: if it left the market, merged, or is part of a bigger company whose files cover it, say so
Use web_fetch on the page when that helps you find exact file links. Never invent or guess links: only give links you
saw in search results or fetched pages. Make sure the files are THIS insurer's (same company / state).
Reply with ONLY a JSON object: {"toc_urls": [], "file_urls": [], "page": "", "portal_only": false,
"status_note": "", "notes": ""} (notes: one short sentence)."""

LIST_PROMPT = """List every health insurance company selling individual-market (marketplace) medical plans in the given
US state for the current or coming plan year, using web search (the state marketplace's insurer list is best).
Reply with ONLY a JSON object: {"insurers": ["Company name", ...]}"""


def call(system, user, tools=True, max_tokens=2500):
    for attempt in range(6):
        h = {"x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
        if STATE["beta"] and tools:
            h["anthropic-beta"] = STATE["beta"]
        body = {"model": MODEL, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]}
        if tools:
            body["tools"] = STATE["tools"]
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", headers=h, json=body, timeout=300)
        except requests.RequestException:
            time.sleep(10 * (attempt + 1)); continue
        if r.status_code == 400 and "web_fetch" in r.text and STATE["beta"]:
            STATE.update(tools=TOOLS[:1], beta=""); continue
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(min(float(r.headers.get("retry-after") or 15 * (attempt + 1)), 120)); continue
        if r.status_code != 200:
            print("  API error", r.status_code, r.text[:200], flush=True)
            return None, 0
        out = r.json(); u = out.get("usage", {}); st = u.get("server_tool_use", {})
        with LOCK:
            USE["in"] += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            USE["out"] += u.get("output_tokens", 0)
            USE["searches"] += st.get("web_search_requests", 0); USE["fetches"] += st.get("web_fetch_requests", 0)
        txt = "".join(c.get("text", "") for c in out.get("content", []) if c.get("type") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            return (json.loads(m.group(0)) if m else {"notes": txt[:200]}), st.get("web_search_requests", 0)
        except json.JSONDecodeError:
            return {"notes": txt[:200]}, st.get("web_search_requests", 0)
    return None, 0


# ---------- who: the insurers ----------
def puf_issuers():
    year = int(E.get("PUF_YEAR") or date.today().year + 1)
    for y in (year, year - 1):
        url = f"https://download.cms.gov/marketplace-puf/{y}/plan-attributes-puf.zip"
        try:
            r = requests.get(url, timeout=300)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            src = z.read([n for n in z.namelist() if n.endswith(".csv")][0]).decode("utf-8-sig", "replace")
            out = {}
            for row in csv.DictReader(io.StringIO(src)):
                if row.get("DentalOnlyPlan") == "Yes":
                    continue
                k = (row["StateCode"], row["IssuerId"])
                out.setdefault(k, row.get("IssuerMarketPlaceMarketingName", "").strip())
            print(f"  CMS {y} marketplace file: {len(out):,} insurer-state pairs", flush=True)
            return [dict(state=s, issuer_id=i, issuer=n, source=f"CMS {y} marketplace") for (s, i), n in out.items()]
        except Exception as e:
            print("  ! PUF", y, str(e)[:120], flush=True)
    return []


def sbe_issuers(states):
    out = []
    for st in states:
        ans, _ = call(LIST_PROMPT, f"State: {st}", max_tokens=1500)
        for n in (ans or {}).get("insurers", [])[:25]:
            if isinstance(n, str) and n.strip():
                out.append(dict(state=st, issuer_id="", issuer=n.strip(), source="state marketplace (Claude's list)"))
    print(f"  state-run marketplaces: {len(out)} insurer-state pairs from {len(states)} states", flush=True)
    return out


# reading-list name -> pattern for CMS / state marketplace names. Molina is left out on purpose: it is on the list but its
# files are not posted (Price File Watch), so it gets searched like any other missing insurer.
ALIASES = {"Aetna": r"aetna", "Alliant": r"alliant", "Ambetter": r"ambetter", "Anthem Colorado": r"anthem",
           "Anthem Georgia": r"anthem", "BCBS Alabama": r"blue ?cross.*alabama", "BCBS Mississippi": r"blue ?cross.*mississippi",
           "BCBSOK": r"blue ?cross.*oklahoma", "BCBST": r"blue ?cross.*tennessee", "BCBSTX": r"blue ?cross.*texas",
           "BSW Health Plan": r"baylor scott", "Blue KC": r"blue ?cross.*kansas city|blue ?kc", "Cigna": r"cigna",
           "Curative": r"curative", "Oscar": r"oscar", "UnitedHealthcare": r"united ?health", "Wellpoint": r"wellpoint"}
# companies whose files we already know how to find nationally (one company-wide listing covers every state)
NATIONAL = {"UnitedHealthcare": r"united ?health", "Cigna": r"cigna", "Aetna": r"aetna", "Oscar": r"oscar",
            "Ambetter (Centene)": r"ambetter", "Anthem / Wellpoint (Elevance)": r"anthem|wellpoint|empire blue"}


def known_networks():
    """(scope states, reading-list insurer) the bot already reads."""
    known = []
    for f, states in (("networks.csv", {"TX"}), ("networks_s7.csv", {"TN", "CO", "OK", "AL", "MS", "MO", "GA"})):
        p = ROOT / "insurers" / f
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                if r.get("enabled", "yes") != "no" and r.get("insurer") in ALIASES:
                    known.append((states, r["insurer"]))
    return known


def already(t, known):
    for states, name in known:
        if t["state"] in states and re.search(ALIASES[name], t["issuer"], re.I):
            return name
    return ""


def national(t):
    return next((k for k, rx in NATIONAL.items() if re.search(rx, t["issuer"], re.I)), "")


# ---------- verify ----------
def head_json(url, limit=600_000):
    """First bytes of a link as text, un-gzipped if needed (.json.gz). ('', reason) if not readable."""
    try:
        with requests.get(url, headers={"User-Agent": discover.UA}, timeout=(8, 40), stream=True, verify=False,
                          allow_redirects=True) as r:
            if r.status_code != 200:
                return "", f"HTTP {r.status_code}", r.url
            buf = b""
            for chunk in r.raw.stream(65536, decode_content=True):
                buf += chunk
                if len(buf) >= limit:
                    break
            if buf[:2] == b"\x1f\x8b":
                buf = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(buf, limit * 4)
            return buf.decode("utf-8", "replace"), r.headers.get("content-type", ""), r.url
    except Exception as e:
        return "", type(e).__name__, url


def kind_of(text):
    t = text[:400000]
    if '"reporting_entity_name"' not in t:
        return "", ""
    ent = re.search(r'"reporting_entity_name"\s*:\s*"([^"]*)"', t)
    ent = ent.group(1) if ent else ""
    if '"reporting_structure"' in t:
        return "toc", ent
    if '"in_network"' in t or '"provider_references"' in t:
        return "in-network file", ent
    if '"out_of_network"' in t:
        return "allowed-amounts file", ent
    return "", ent


def entity_ok(issuer, ent):
    a, b = issuer.lower(), ent.lower()
    return bool(ent) and (fuzz.token_set_ratio(a, b) >= 80 or fuzz.partial_ratio(a, b) >= 85)


def check(t, url):
    text, info, final = head_json(url)
    if not text:
        return None, f"{url[:80]}: {info}"
    if text.lstrip()[:1] == "<":
        return None, f"{url[:80]}: a web page, not a file"
    k, ent = kind_of(text)
    if not k:
        return None, f"{url[:80]}: not a price-transparency file"
    if entity_ok(t["issuer"], ent):
        return ("found " + ("toc" if k == "toc" else "file")), f"{k} for '{ent[:60]}'"
    return "held", f"{k} for '{ent[:60]}' (doesn't clearly match {t['issuer'][:40]})"


def page_links(url):
    r = deep.get(url, timeout=20)
    if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
        return []
    return [u for u, text in deep.links(r.url, r.text[:800000])
            if re.search(r"(?i)\.json(\.gz)?(\?|$)|index|toc|table.of.contents|in.network", u)][:20]


def search_one(t):
    ans, ns = call(PROMPT, f"Insurer: {t['issuer']}\nState: {t['state']}\n"
                   + (f"CMS issuer ID: {t['issuer_id']}\n" if t["issuer_id"] else ""))
    if ans is None:
        return t, ("error", "", "", "API error", {}, 0)
    if not isinstance(ans, dict):
        ans = {"notes": str(ans)[:200]}
    urls = [u for u in (ans.get("toc_urls") or []) + (ans.get("file_urls") or []) if isinstance(u, str) and u.startswith("http")]
    page = ans.get("page") or ""
    why, held = [], None
    for u in urls[:6]:
        res, msg = check(t, u)
        if res and res.startswith("found"):
            return t, (res, u, msg, "", ans, ns)
        if res == "held":
            held = held or ("held", u, msg, "", ans, ns)
        why.append(msg)
    # free layer: file links on the page, then the archives for the insurer's site
    cands = page_links(page) if page.startswith("http") else []
    host = discover.host(page) if page else ""
    if host and E.get("NO_ARCHIVES") != "1":
        cands += [u for u, ts in sorted(deep.wayback(host, TIC_RX.replace("(?i)", "")), key=lambda x: x[1], reverse=True)
                  if re.search(r"(?i)\.json(\.gz)?(\?|$)", u)][:10]
    for u in list(dict.fromkeys(cands))[:12]:
        res, msg = check(t, u)
        if res and res.startswith("found"):
            return t, (res, u, "free layer: " + msg, "", ans, ns)
        if res == "held":
            held = held or ("held", u, "free layer: " + msg, "", ans, ns)
    if held:
        return t, held
    portal = ans.get("portal_only") or any(p in (page + " ".join(urls)).lower() for p in PORTALS)
    if portal:
        return t, ("portal only", page or (urls[0] if urls else ""), "files only reachable through a search tool", "", ans, ns)
    return t, ("not found", page, "", "; ".join(why)[:300] or "nothing found", ans, ns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-sbe", action="store_true")
    a = ap.parse_args()
    if not E.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    want = {s.strip().upper() for s in a.states.split(",") if s.strip()}
    prev = {(r["state"], r["issuer"].lower()): r for r in csv.DictReader(open(OUT, encoding="utf-8"))} if OUT.exists() else {}
    targets = puf_issuers()
    sbe = [s for s in SBE if not want or s in want]
    if not a.no_sbe:
        targets += sbe_issuers(sbe)
    if want:
        targets = [t for t in targets if t["state"] in want]
    seen, uniq = set(), []
    for t in targets:   # one row per state + insurer name
        k = (t["state"], re.sub(r"[^a-z0-9]", "", t["issuer"].lower()))
        if k not in seen:
            seen.add(k); uniq.append(t)
    known = known_networks()
    cut = (date.today() - timedelta(days=int(E.get("RESEARCH_DAYS") or 30))).isoformat()
    today, todo, rows = date.today().isoformat(), [], dict(prev)
    for t in uniq:
        k = (t["state"], t["issuer"].lower())
        name = already(t, known)
        if name:
            rows[k] = dict(t, result="already reading", how=f"on the reading list as '{name[:60]}'", searched_at=today)
            continue
        nat = national(t)
        if nat:
            rows[k] = dict(t, result="known (national insurer)",
                           how=f"{nat}: one company-wide file listing covers this state; read when this state is added",
                           searched_at=today)
            continue
        p = prev.get(k, {})
        if p.get("result", "").startswith("found") or p.get("searched_at", "") >= cut:
            continue
        todo.append(t)
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(uniq):,} insurer-state pairs; {len(todo):,} to search", flush=True)
    counts = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (t, (result, url, how, why, ans, ns)) in enumerate(ex.map(search_one, todo), 1):
            counts[result] = counts.get(result, 0) + 1
            k = (t["state"], t["issuer"].lower())
            ent = re.search(r"for '([^']*)'", how)
            rows[k] = dict(t, result=result, url=url, reporting_entity=ent.group(1) if ent else "", how=how or why,
                           price_page=(ans.get("page") or "")[:300],
                           notes=" ".join(x for x in (ans.get("status_note") or "", ans.get("notes") or "") if x)[:300],
                           searched_at=today, times_searched=str(int(prev.get(k, {}).get("times_searched") or 0) + 1),
                           searches=str(ns), answer=json.dumps(ans, ensure_ascii=False)[:1500])
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}: {counts}", flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore"); w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["state"], r["issuer"].lower())))
    cost = USE["in"] / 1e6 * float(E.get("PRICE_IN") or 1) + USE["out"] / 1e6 * float(E.get("PRICE_OUT") or 5) \
        + USE["searches"] / 1000 * float(E.get("PRICE_SEARCH") or 10)
    allc = {}
    for r in rows.values():
        allc[r["result"]] = allc.get(r["result"], 0) + 1
    print(f"done: searched {len(todo):,} insurer-state pairs: {counts}. All pairs on file: {allc}. "
          f"{USE['searches']:,} web searches, about ${cost:,.2f}")


if __name__ == "__main__":
    main()
