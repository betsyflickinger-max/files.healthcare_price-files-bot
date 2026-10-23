"""Find this month's file for each insurer network.

Insurers re-post their rate files every month under a new dated name, e.g.
  .../2026-09-05/inNetworkRates/2026-09-05_pl-22z-hr23_Aetna-Health-Inc.---Texas.json.gz
networks.csv keeps each network's link as a template ({date}=YYYY-MM-DD, {dc}=YYYYMMDD, {ym}=YYYY-MM).
We try the dates from newest to oldest, from today back to the date we already have, and take the
first link that answers. Networks with no date in the link (Molina, Wellpoint) keep the same link.
A network whose new file can't be found keeps its current file and is flagged "no new file yet".
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
import check  # noqa: E402  (same header check as the hospital bot: HEAD, then a 1-byte GET)


def fill(template, d):
    return (template.replace("{date}", d.isoformat()).replace("{dc}", d.strftime("%Y%m%d"))
            .replace("{ymc}", d.strftime("%Y%m")).replace("{ym}", d.strftime("%Y-%m")))


def candidate_dates(since, today):
    d = today
    while d > since:
        yield d
        d -= timedelta(days=1)


_CACHE = {}


def _get(url, tries=3, **kw):
    """Fetch a file list, trying up to 3 times (waits 10s, then 30s) so one hiccup at the insurer
    doesn't fail every network that depends on that list."""
    import time
    import requests
    if url not in _CACHE:
        for i in range(tries):
            try:
                fixed = url.replace("://molinahealthcare.com/", "://www.molinahealthcare.com/")   # Oct 22: bare host -> home page
                try:
                    r = requests.get(fixed, headers={"User-Agent": check.UA}, timeout=600, **kw)
                except requests.exceptions.SSLError:   # Oct 22: BCBS Massachusetts sends an incomplete certificate chain
                    r = requests.get(fixed, headers={"User-Agent": check.UA}, timeout=600, verify=False, **kw)
                r.raise_for_status()
                _CACHE[url] = r.text
                break
            except requests.RequestException:
                if i == tries - 1:
                    raise
                time.sleep(10 * 3 ** i)
    return _CACHE[url]


def _why(e):
    """Short reason for a failed file-list read, with the HTTP code when there is one (403 = refused)."""
    code = getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__} {code}" if code else type(e).__name__


def cigna_toc(arg):
    """Cigna serves files only through signed links. Its public latest.json points to this month's
    table of contents, which lists a signed link for every rate file. arg = network part of the name."""
    import json
    latest = json.loads(_get("https://www.cigna.com/static/mrf/latest.json"))
    toc_url = next(f["url"] for m in latest["mrfs"] if m.get("kind") == "TOC" for f in m["files"])
    toc = _get(toc_url)
    for u in re.findall(r'"location"\s*:\s*"([^"]+)"', toc):
        if f"_{arg}_in-network-rates" in u.split("?")[0]:
            d = re.search(r"(\d{4}-\d{2}-\d{2})_cigna", u)
            return dict(url=u, how=f"from Cigna's table of contents ({d.group(1) if d else '?'})", http="200", error="", found=True)
    return dict(url="", how="not in Cigna's table of contents", http="", error="missing from table of contents", found=False)


def azure_list(arg):
    """Insurers that keep files in public Azure storage (BSW): list the folder, newest matching file.
    arg = '<container list URL>|<regex for the file name>'."""
    base, pat = arg.split("|", 1)
    names, marker = [], ""
    while True:
        x = _get(base + (f"&marker={marker}" if marker else ""))
        names += re.findall(r"<Name>([^<]+)</Name>", x)
        m = re.search(r"<NextMarker>([^<]+)</NextMarker>", x)
        if not m:
            break
        marker = m.group(1)
    hits = sorted(n for n in names if re.search(pat, n.rsplit("/", 1)[-1]))
    if not hits:
        return dict(url="", how="no matching file in the insurer's folder", http="", error="no match", found=False)
    root = base.split("?")[0]
    return dict(url=f"{root}/{hits[-1]}", how=f"newest in the insurer's folder ({hits[-1].rsplit('/', 1)[-1][:10]})",
                http="200", error="", found=True)


_TOC = {}


def real(h):
    """The link answered with the file itself (not a refusal that only might open in a browser)."""
    return h["ok"] and not h.get("needs_browser")


def _toc_url(loc, today):
    """A table of contents link: fixed, or a dated template ({date}/{ym}/{ymc}) tried newest first over 60 days.
    A directory file that lists TOC_Files (BCBS Tennessee) is followed to its first table of contents."""
    import json
    if loc not in _TOC:
        url = loc
        if "{" in loc:
            url = next((fill(loc, today - timedelta(days=i)) for i in range(60)
                        if real(check.headers(fill(loc, today - timedelta(days=i))))), "")
            if not url:
                raise ValueError("no table of contents in the last 60 days")
        head = _get(url)[:3000]
        if '"TOC_Files"' in head:
            url = json.loads(_get(url))["TOC_Files"][0]
        _TOC[loc] = url
    return _TOC[loc]


def toc_match(arg, today):
    """Insurers whose file names change in ways a template can't follow (two different dates in one link, signed
    links, multi-part files): read the insurer's table of contents and take the newest file whose link (without
    the ?signature) matches a pattern. arg = '<table of contents link or template>|<regex>'."""
    loc, pat = arg.split("|", 1)
    toc = _toc_url(loc, today)
    hits = {}
    for u in re.findall(r'"location"\s*:\s*"([^"]+)"', _get(toc)):
        u = u.replace("\\u0026", "&").replace("\\/", "/")
        if re.search(pat, u.split("?")[0]):
            hits[u.split("?")[0]] = u
    if not hits:
        return dict(url="", how="not in the insurer's table of contents", http="", error="no match", found=False)
    key = sorted(hits)[-1]
    return dict(url=hits[key], how=f"from the insurer's table of contents ({toc.rsplit('/', 1)[-1][:60]})",
                http="200", error="", found=True)


def find(row, today, since):
    """Returns dict(url, how, http, error). since = date of the file we already have."""
    finder = row.get("finder", "")
    try:
        if finder == "cigna_toc":
            return cigna_toc(row["finder_arg"])
        if finder == "azure_list":
            return azure_list(row["finder_arg"])
        if finder == "toc_match":
            return toc_match(row["finder_arg"], today)
        if finder == "catalog":   # Oct 16, 2026: link from the newest insurer catalog (insurers/catalog.py), arg insurer|network|part
            import catalog
            ins, net, part = row["finder_arg"].split("|")
            c = catalog.current_link(ins, net, part)
            if not c:
                return dict(url=row["current_url"], how="not in the newest catalog", http="", error="not in catalog", found=False)
            return dict(url=c["url"], how=f"from the {c['month']} {ins} catalog", http=str(c.get("http") or ""), error="", found=True)
    except Exception as e:
        return dict(url=row["current_url"], how=f"could not read the file list: {_why(e)}", http="",
                    error=str(e)[:200], found=False)
    t = row["url_template"] or row.get("current_url", "")   # Oct 23, 2026: rows with only a fixed link (Molina KY/OH, PacificSource MT,
    # Presbyterian NM) have no template; checking "" gave "Invalid URL ''" and the file was never read
    if "{" not in t:
        h = check.headers(t)
        if h["ok"] and h.get("html"):
            return dict(url=t, how="link now opens a web page, not a file", http=h["http"], error="web page", found=False)
        return dict(url=t, how="same link every month" if h["ok"] else f"link broken ({h['error']})",
                    http=h["http"], error=h["error"], found=h["ok"])
    cands = {}
    for d in candidate_dates(since, today):  # newest first; {ym}-only templates repeat, keep the newest day
        cands.setdefault(fill(t, d), d)
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda u: (u, check.headers(u)), cands))
    for u, h in results:  # still newest first. A guessed dated link must really answer: "403, may open in a browser"
        # counts for hospital sites, but on insurer file storage a 403 means no such file (Oct 15, 2026: Curative 2026-10-15)
        if h["ok"] and not h.get("html") and not h.get("needs_browser"):
            return dict(url=u, how=f"new file dated {cands[u].isoformat()}", http=h["http"], error="", found=True)
    return dict(url=row["current_url"], how="no new file yet", http="", error="", found=False)
