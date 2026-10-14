"""Second layer for search_files.py (Oct 14, 2026): free, code-only ways to find a hospital's price file.

Runs before Claude's web search (on what we already know) and after it (on the sites Claude found). Nothing here
costs per search. Every candidate still has to pass search_files' own checks (the hospital's index lists it, or the
file's first bytes are a CMS standard-charges file that names the hospital).

  names     Medicare's enrollment list gives each hospital's LEGAL name and doing-business-as name (files are often
            named for the legal entity: "Health Care Authority for Baptist Health" for Baptist Medical Center South).
  national  every cms-hpt.txt we know of, in every state (a national system's index lists hospitals far from its HQ).
  crawl     the hospital's site: its price page, common price-transparency paths, links that mention standard
            charges / machine-readable / price transparency (two clicks deep), and its sitemap.
  archives  the Wayback Machine and Common Crawl URL indexes: any file ever posted on the hospital's site whose link
            looks like a price file (standardcharges, machine-readable, cms-hpt...), and the big price-file vendors'
            sites (Panacea, Hospital Price Index, Craneware, Hyve, PARA...) searched for the hospital's name.
"""
import csv
import io
import json
import re
import threading
import time
import urllib.parse

import requests

import discover
import fetch_plus

UA = {"User-Agent": discover.UA}
FILE_RX = re.compile(r"standard[-_ ]?charges?|machine[-_ ]?readable|cms-hpt|chargemaster|charge[-_ ]?master|"
                     r"price[-_ ]?transparency|pricetransparency|\bmrf\b|mrfdownload|_standardcharges", re.I)
FILE_EXT = re.compile(r"\.(json|csv|zip|gz|txt|xlsx?)(\?|$)", re.I)
PAGE_RX = re.compile(r"price[-_ ]?transparen|standard[-_ ]?charge|machine[-_ ]?readable|chargemaster|"
                     r"pricing|price[-_ ]?estimat|patient[-_ ]?financial|billing", re.I)
PATHS = ["price-transparency", "pricetransparency", "pricing-transparency", "price-transparency/",
         "patients-visitors/price-transparency", "patients/price-transparency", "billing/price-transparency",
         "patients-and-visitors/billing/price-transparency", "standard-charges", "hospital-price-transparency",
         "financial-information/price-transparency", "about-us/price-transparency", "chargemaster", "pricing",
         "billing-and-insurance/price-transparency", "patient-resources/price-transparency"]
VENDORS = ["pt.panaceainc.com/MRFDownload/", "hospitalpriceindex.com/", "apim.services.craneware.com/",
           "mrfs.hyvehealthcare.com/", "apps.para-hcfs.com/", "uhsfilecdn.eskycity.net/", "pricetransparency.blob.core.windows.net/",
           "www.hospitalpricedisclosure.com/", "cdn.mdxcloud.com/", "rm.121cms.com/"]
DROP = {"llc", "inc", "the", "of", "and", "at", "a", "hospital", "hospitals", "medical", "center", "centre", "health",
        "healthcare", "regional", "memorial", "community", "general", "system", "dba", "ii", "iii", "lp", "corp"}


def get(url, timeout=25, stream=False):
    try:
        r = requests.get(url, headers=UA, timeout=(6, min(timeout, 12)), verify=False, allow_redirects=True, stream=stream)
    except requests.RequestException:
        r = None
    if r is None or r.status_code in fetch_plus.BLOCKED:   # Oct 14: bot wall? ask the way Chrome would
        r2 = fetch_plus.cffi_get(url, timeout=min(timeout, 20), stream=stream)
        if r2 is not None and r2.status_code < 400:
            return r2
    return r


# ---------- names: Medicare enrollment list (legal + DBA names, NPI, ZIP) ----------
def enrollment_names():
    """ccn -> {"legal", "dba", "npi", "zip", "address"} from data.cms.gov "Hospital Enrollments" (found via the catalog)."""
    out = {}
    try:
        cat = requests.get("https://data.cms.gov/data.json", timeout=120).json()
        ds = next(d for d in cat.get("dataset", []) if "hospital enrollments" in d.get("title", "").lower())
        dists = [x for x in ds.get("distribution", []) if (x.get("mediaType") or x.get("format") or "").lower().endswith("csv")
                 and x.get("downloadURL")]
        url = sorted(dists, key=lambda x: x.get("modified") or x.get("temporal") or "", reverse=True)[0]["downloadURL"]
        r = requests.get(url, timeout=300)
        for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace"))):
            k = {c.lower().strip(): v for c, v in row.items() if c}
            ccn = k.get("ccn") or k.get("cms certification number (ccn)") or ""
            if not ccn:
                continue
            out[ccn.zfill(6)] = dict(legal=k.get("organization name", ""), dba=k.get("doing business as name", ""),
                                     npi=k.get("npi", ""), zip=(k.get("zip code") or "")[:5],
                                     address=" ".join(x for x in (k.get("address line 1", ""), k.get("city", "")) if x))
        print(f"  enrollment list: legal names for {len(out):,} hospitals", flush=True)
    except Exception as e:
        print("  ! enrollment list unavailable:", str(e)[:150], flush=True)
    return out


def all_names(h, names):
    n = names.get(h["ccn"], {})
    return [x for x in dict.fromkeys([h["name"], n.get("dba", ""), n.get("legal", "")]) if x]


def core(name):
    return [w for w in discover._toks(name) if w not in DROP and len(w) > 1]


# ---------- national: every known cms-hpt.txt ----------
class National:
    """Every location in every index we know, for matching missing hospitals anywhere in the country."""

    def __init__(self, rows, workers=48):
        doms = sorted({d for d in (discover.index_domain(r) for r in rows) if d})
        self.entries = []
        lock = threading.Lock()

        def one(d):
            idx, ents = discover.fetch_index(d)
            if ents:
                with lock:
                    self.entries += [(idx, e) for e in ents]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, doms))
        self.by_word = {}
        for i, (_, e) in enumerate(self.entries):
            for w in set(core(e.get("location-name", ""))):
                self.by_word.setdefault(w, []).append(i)
        print(f"  national: {len(self.entries):,} locations in {len(doms):,} indexes", flush=True)

    def candidates(self, h, names):
        """(index_url, mrf_url, location) for locations whose name matches one of the hospital's names closely."""
        out = []
        for nm in names:
            ws = core(nm)
            if not ws:
                continue
            pool = set(self.by_word.get(ws[0], []))
            for w in ws[1:2]:
                pool &= set(self.by_word.get(w, []))
            for i in pool:
                idx, e = self.entries[i]
                loc = e.get("location-name", "")
                if discover.score(nm, loc) >= 88:
                    out.append((idx, e["mrf-url"], loc))
        return list(dict.fromkeys(out))[:6]


# ---------- crawl: the hospital's own site ----------
HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["'][^>]*>(.{0,200}?)</a""", re.I | re.S)


def links(base, html):
    for m in HREF.finditer(html or ""):
        u = urllib.parse.urljoin(base, m.group(1).strip())
        if u.startswith("http"):
            yield u, re.sub(r"<[^>]+>", " ", m.group(2))


def crawl(domain, start_pages=(), max_pages=25, budget=75):
    """Price-file-looking links on the hospital's site. Returns (file_links, index_links, pages_seen)."""
    seen, files, idx = set(), [], []
    end = time.time() + budget
    host = discover.host(domain)
    queue = [(p, 0) for p in start_pages if p] + [(f"https://{host}/", 0)] + [(f"https://{host}/{p}", 1) for p in PATHS]
    while queue and len(seen) < max_pages and time.time() < end:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        r = get(url, timeout=20)
        if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
            continue
        for u, text in links(r.url, r.text[:800000]):
            blob = u + " " + text
            if "cms-hpt.txt" in u.lower():
                idx.append(u)
            elif FILE_RX.search(blob) and (FILE_EXT.search(u) or "download" in u.lower() or "mrf" in u.lower()):
                files.append(u)
            elif depth < 2 and PAGE_RX.search(blob) and (discover.host(u) == host or FILE_RX.search(blob)):
                queue.append((u, depth + 1))
    # sitemap: pages and files whose address mentions price transparency
    for sm in [f"https://{host}/sitemap.xml", f"https://{host}/sitemap_index.xml"]:
        if time.time() > end + 30:
            break
        r = get(sm, timeout=20)
        if r is None or r.status_code != 200:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text[:3000000])
        subs = [u for u in locs if u.endswith(".xml")][:8]
        for s in subs:
            if time.time() > end + 45:
                break
            r2 = get(s, timeout=20)
            if r2 is not None and r2.status_code == 200:
                locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r2.text[:3000000])
        for u in locs:
            if FILE_RX.search(u):
                (files if FILE_EXT.search(u) else []).append(u)
                if not FILE_EXT.search(u) and u not in seen and len(seen) < max_pages + 10 and time.time() < end + 60:
                    seen.add(u)
                    r3 = get(u, timeout=20)
                    if r3 is not None and r3.status_code == 200:
                        for v, text in links(r3.url, r3.text[:800000]):
                            if "cms-hpt.txt" in v.lower():
                                idx.append(v)
                            elif FILE_RX.search(v + " " + text) and (FILE_EXT.search(v) or "download" in v.lower()):
                                files.append(v)
        break
    return list(dict.fromkeys(files))[:30], list(dict.fromkeys(idx))[:5], len(seen)


# ---------- archives: Wayback Machine and Common Crawl ----------
_CC = {}
ARCH_LOCK = threading.Semaphore(4)   # be polite to the archive APIs


def _cc_index():
    if "id" not in _CC:
        try:
            _CC["id"] = requests.get("https://index.commoncrawl.org/collinfo.json", timeout=60).json()[0]["cdx-api"]
        except Exception:
            _CC["id"] = ""
    return _CC["id"]


def wayback(prefix, rx, match="domain", limit=150):
    with ARCH_LOCK:
        for attempt in range(2):
            try:
                r = requests.get("https://web.archive.org/cdx/search/cdx", params={
                    "url": prefix, "matchType": match, "output": "json", "fl": "original,timestamp,statuscode",
                    "filter": f"original:(?i).*({rx.replace('(?i)', '')}).*", "collapse": "urlkey", "limit": str(limit)}, timeout=90)
                if r.status_code == 200:
                    rows = r.json()[1:] if r.text.strip() else []
                    return [(x[0], x[1]) for x in rows]
                time.sleep(5)
            except Exception:
                time.sleep(5)
    return []


def commoncrawl(domain, rx, limit=150):
    api = _cc_index()
    if not api:
        return []
    with ARCH_LOCK:
        try:
            r = requests.get(api, params={"url": f"*.{domain}", "output": "json", "filter": f"~url:.*({rx}).*",
                                          "limit": str(limit)}, timeout=90)
            return [json.loads(l)["url"] for l in r.text.splitlines() if l.startswith("{")]
        except Exception:
            return []


FILE_WORDS = r"standardcharges|standard-charges|standard_charges|machine-readable|machinereadable|cms-hpt|chargemaster|mrf"
_DOM = {}
_DOM_LOCK = threading.Lock()


def vendor_urls():
    """Every file link the archives have seen on the big price-file vendors' sites (fetched once per run)."""
    out = []
    for v in VENDORS:
        got = [u for u, ts in sorted(wayback(v, r"(?i)\.json|\.csv|\.zip|download|mrf", match="prefix", limit=60000),
                                     key=lambda x: x[1], reverse=True)]
        out += got
        print(f"  vendor archive {v.split('/')[0]}: {len(got):,} file links", flush=True)
    return list(dict.fromkeys(out))


def archives(domain, names, vendors=()):
    """Price-file-looking links ever seen on the hospital's site (newest first), and vendor files named for it."""
    out = []
    if domain:
        with _DOM_LOCK:
            cached = _DOM.get(domain)
        if cached is None:
            cached = [u for u, ts in sorted(wayback(domain, FILE_WORDS), key=lambda x: x[1], reverse=True)]
            cached += commoncrawl(domain, FILE_WORDS)
            with _DOM_LOCK:
                _DOM[domain] = cached
        out += cached
    for nm in names[:3]:
        ws = core(nm)[:2]
        if len(ws) < 1 or (len(ws) == 1 and len(ws[0]) < 6):
            continue   # one short word ("st", "baptist") would match too many vendor files
        rx = re.compile(r"[^/]{0,3}".join(re.escape(w) for w in ws), re.I)
        out += [u for u in vendors if rx.search(urllib.parse.unquote(u).replace("_", " ").replace("-", " ").lower()
                                                 .replace(" ", "")) or rx.search(urllib.parse.unquote(u))]
    out = [u for u in dict.fromkeys(out) if FILE_EXT.search(u) or "download" in u.lower() or "cms-hpt" in u.lower()]
    return out[:40]
