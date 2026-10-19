"""Fetching past bot walls (added Oct 14, 2026). Used by the daily hospital run, the hospital search and the insurer search.

Of the 902 hospitals still "not found" on Oct 14, 237 had answered the bot with "403 Forbidden": the file is there,
but the site's bot protection turned the script away. Three ways to fetch, tried in order:
  1. plain requests / curl (what the bots always did)
  2. curl_cffi: the same request made the way Chrome makes it (Chrome's TLS fingerprint and headers). Gets past most
     "403" walls (tested: St. Bernards, Baxter Health).
  3. a real headless Chrome (Playwright): for JavaScript challenges ("Just a moment...", Cloudflare), it loads the
     link like a person's browser and saves the download (tested: Select Medical's ~100 hospitals).
Also: browser_links() opens a page in Chrome and collects every file-like link the page shows or loads, for price
pages and insurer portals that are built with JavaScript (a plain fetch sees an empty page).
Chrome is installed on first use (python -m playwright install --with-deps chromium), so runs that never need it
don't pay for it. FETCH_BROWSER=0 turns layer 3 off.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

BLOCKED = {401, 403, 406, 409, 429, 503}
CHALLENGE = ("just a moment", "cf-chl", "attention required", "captcha", "are you a robot", "incapsula",
             "perimeterx", "access denied", "request unsuccessful", "checking your browser")
UA_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0.0.0 Safari/537.36")
LINK_HINT = re.compile(r"standard[-_ ]?charges?|machine[-_ ]?readable|price[-_ ]?transparen|chargemaster|cms-hpt|"
                       r"in[-_ ]?network|table[-_ ]?of[-_ ]?contents|_index\.json|\bmrf\b|mrfdownload|"
                       r"\.json(\.gz)?(\?|$)|\.csv(\?|$)|\.zip(\?|$)", re.I)
try:
    from curl_cffi import requests as creq
except Exception:  # noqa: BLE001
    creq = None

_LOCK = threading.BoundedSemaphore(int(os.environ.get("BROWSER_SLOTS") or 3))   # browsers at once
_INSTALL = threading.Lock()
_STATE = {"installed": False, "uses": 0}


def challenged(status, body):
    """A bot wall rather than the file: a blocked status, or an HTML page with challenge words."""
    head = (body or b"")[:6000]
    if isinstance(head, bytes):
        head = head.decode("utf-8", "replace")
    low = head.lower()
    return (status in BLOCKED) or (low.lstrip().startswith("<") and any(c in low for c in CHALLENGE))


# ---------- layer 2: Chrome-like requests ----------
def cffi_get(url, timeout=40, stream=False, headers=None):
    if creq is None:
        return None
    try:
        return creq.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True, verify=False,
                        stream=stream, headers=headers or {})
    except Exception:  # noqa: BLE001
        return None


def cffi_head(url, limit=1_000_000, timeout=40):
    """(status, content_type, first bytes, final_url); status None if it couldn't connect."""
    r = cffi_get(url, timeout=timeout, stream=True)
    if r is None:
        return None, "", b"", url
    buf = b""
    try:
        for ch in r.iter_content():
            buf += ch
            if len(buf) >= limit:
                break
    except Exception:  # noqa: BLE001
        pass
    st, ct, fu = r.status_code, r.headers.get("content-type", ""), str(r.url)
    try:
        r.close()
    except Exception:  # noqa: BLE001
        pass
    return st, ct, buf, fu


def cffi_download(url, out, max_time=5400):
    r = cffi_get(url, timeout=120, stream=True)
    if r is None:
        return False, "curl_cffi: could not connect"
    if r.status_code >= 400:
        st = r.status_code
        r.close()
        return False, f"curl_cffi: HTTP {st}"
    t0 = time.time()
    try:
        with open(out, "wb") as f:
            for ch in r.iter_content():
                f.write(ch)
                if time.time() - t0 > max_time:
                    return False, "curl_cffi: time limit"
    except Exception as e:  # noqa: BLE001
        return False, f"curl_cffi: {type(e).__name__}"
    finally:
        r.close()
    with open(out, "rb") as f:
        if challenged(200, f.read(6000)):
            return False, "curl_cffi: got a bot-check page"
    return True, ""


# ---------- layer 3: headless Chrome ----------
def _ensure_browser():
    with _INSTALL:
        return _install()


def _install():
    if _STATE["installed"]:
        return True
    try:
        import playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright==1.56.0"], check=False)
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
                       capture_output=True, text=True)
    if r.returncode != 0:  # no sudo for system packages: the browser alone often still runs
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, text=True)
    _STATE["installed"] = True
    return True


def _launch(p):
    exe = os.environ.get("CHROME_PATH") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
    return p.chromium.launch(headless=True, executable_path=exe,
                             args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])


def browser_download(url, out, timeout=900):
    """Save the link's file with headless Chrome. (ok, error)."""
    if os.environ.get("FETCH_BROWSER") == "0":
        return False, "browser off"
    _ensure_browser()
    with _LOCK:
        _STATE["uses"] += 1
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = _launch(p)
                try:
                    ctx = b.new_context(user_agent=UA_CHROME, accept_downloads=True)
                    pg = ctx.new_page()
                    try:
                        with pg.expect_download(timeout=90_000) as dl:
                            try:
                                pg.goto(url, timeout=90_000)
                            except Exception:  # noqa: BLE001  ("Download is starting" is reported as an error)
                                pass
                        d = dl.value
                        d.save_as(out)
                    except Exception:  # noqa: BLE001
                        # not a download: the file opened in the tab (JSON/CSV shown as text); read it in the page
                        pg.wait_for_timeout(3000)
                        txt = pg.evaluate("""async (u) => { const r = await fetch(u, {credentials: 'include'});
                                             return r.ok ? await r.text() : '__HTTP__' + r.status; }""", url)
                        if txt.startswith("__HTTP__"):
                            return False, "browser: HTTP " + txt[8:]
                        with open(out, "w", encoding="utf-8") as f:
                            f.write(txt)
                finally:
                    b.close()
        except Exception as e:  # noqa: BLE001
            return False, f"browser: {type(e).__name__}: {str(e)[:120]}"
    with open(out, "rb") as f:
        if challenged(200, f.read(6000)):
            return False, "browser: still a bot-check page"
    return True, ""


def browser_head(url, limit=1_000_000):
    """First bytes of a file fetched with headless Chrome (unzipped if it's a zip). (text, info)."""
    tmp = tempfile.mkdtemp(prefix="bh_")
    out = os.path.join(tmp, "f")
    try:
        ok, err = browser_download(url, out)
        if not ok:
            return "", err
        with open(out, "rb") as f:
            start = f.read(4)
        if start[:2] == b"PK":
            if not zipfile.is_zipfile(out):   # Oct 19: a damaged zip crashed a whole search run
                return "", "zip file (damaged; can't be opened)"
            with zipfile.ZipFile(out) as z:
                ms = [i for i in z.infolist() if re.search(r"\.(json|csv)$", i.filename, re.I)]
                if not ms:
                    return "", "zip file (no JSON or CSV inside)"
                with z.open(max(ms, key=lambda i: i.file_size)) as f:
                    return f.read(limit).decode("utf-8", "replace"), "browser zip"
        if start[:2] == b"\x1f\x8b":
            import gzip
            with gzip.open(out) as f:
                return f.read(limit).decode("utf-8", "replace"), "browser gz"
        with open(out, "rb") as f:
            return f.read(limit).decode("utf-8", "replace"), "browser"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def browser_links(urls, wait_ms=5000, follow=2):
    """Open each page in headless Chrome; return every file-like link it shows or loads (incl. links one or two clicks
    away whose text mentions price transparency). For JavaScript-built price pages and insurer portals."""
    if os.environ.get("FETCH_BROWSER") == "0" or not urls:
        return []
    _ensure_browser()
    found, pages = [], [u for u in urls if u][:3]
    with _LOCK:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = _launch(p)
                try:
                    ctx = b.new_context(user_agent=UA_CHROME)
                    seen = set()
                    while pages and len(seen) < 3 + follow:
                        u = pages.pop(0)
                        if u in seen:
                            continue
                        seen.add(u)
                        pg = ctx.new_page()
                        pg.on("response", lambda r: found.append(r.url) if LINK_HINT.search(r.url) else None)
                        try:
                            pg.goto(u, timeout=45_000, wait_until="domcontentloaded")
                            pg.wait_for_timeout(wait_ms)
                            links = pg.eval_on_selector_all(
                                "a[href]", "els => els.map(e => [e.href, (e.innerText || '').slice(0, 150)])")
                        except Exception:  # noqa: BLE001
                            links = []
                        for href, text in links:
                            if LINK_HINT.search(href):
                                found.append(href)
                            elif follow and re.search(r"price|transparen|standard charge|machine.readable", text, re.I):
                                pages.append(href)
                        pg.close()
                finally:
                    b.close()
        except Exception:  # noqa: BLE001
            return []
    return [x for x in dict.fromkeys(found) if x.startswith("http")][:40]


CLICK_TEXT = re.compile(r"standard[-_ ]?charges?|machine[-_ ]?readable|chargemaster|charge description master|"
                        r"price[-_ ]?transparen|\bmrf\b|download", re.I)
SKIP_TEXT = re.compile(r"shoppable|estimat|average charges|unavailable|\bpdf\b|good faith|financial assistance", re.I)


def browser_click_links(urls, max_clicks=8, wait_ms=4000):
    """Oct 19, 2026: price pages whose download buttons are JavaScript (href="#"), e.g. PARA's
    apps.para-hcfs.com/PTT/FinalLinks/*.aspx (25 hospitals the Oct 14 search left "not found"). Opens each page in
    headless Chrome, clicks the buttons and links whose text mentions standard charges / machine-readable / download
    (skipping shoppable-services, estimator and average-charge lists), and returns the link each click downloads or
    opens. The link is usually a plain GET (PARA: Reports.aspx?dbName=...&type=CDMWithoutLabel) that the daily run can
    fetch like any other. Every link still has to pass search_files.check_file."""
    if os.environ.get("FETCH_BROWSER") == "0" or not urls:
        return []
    _ensure_browser()
    found = []
    with _LOCK:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = _launch(p)
                try:
                    ctx = b.new_context(user_agent=UA_CHROME, accept_downloads=True)
                    for u in [x for x in urls if x][:3]:
                        pg = ctx.new_page()
                        try:
                            pg.goto(u, timeout=45_000, wait_until="domcontentloaded")
                            pg.wait_for_timeout(wait_ms)
                        except Exception:  # noqa: BLE001
                            pg.close()
                            continue
                        els = pg.locator("a, button, input[type=submit], input[type=button]")
                        clicks = 0
                        for i in range(min(els.count(), 400)):
                            if clicks >= max_clicks:
                                break
                            el = els.nth(i)
                            try:
                                text = " ".join(((el.inner_text(timeout=1000) or el.get_attribute("value") or "")).split())[:150]
                                href = el.get_attribute("href") or ""
                            except Exception:  # noqa: BLE001
                                continue
                            # plain links are browser_links' job; this is for buttons a fetch can't follow
                            if href and not href.startswith(("#", "javascript")):
                                continue
                            if not CLICK_TEXT.search(text) or SKIP_TEXT.search(text):
                                continue
                            clicks += 1
                            before = len(ctx.pages)
                            try:
                                with pg.expect_download(timeout=20_000) as d:
                                    el.click(timeout=5000)
                                found.append(d.value.url)
                                d.value.cancel()
                            except Exception:  # noqa: BLE001
                                for q in ctx.pages[before:]:   # opened in a new tab instead
                                    found.append(q.url)
                                    q.close()
                        pg.close()
                finally:
                    b.close()
        except Exception:  # noqa: BLE001
            return []
    return [x for x in dict.fromkeys(found) if x.startswith("http")][:20]
