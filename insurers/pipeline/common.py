"""Shared paths and helpers for the Upfront DFW data pipeline (test copy)."""
import csv
import gzip
import io
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "raw"
CODES_FILE = Path(__file__).resolve().parent / "codes.csv"
csv.field_size_limit(sys.maxsize)
USER_AGENT = "UpfrontDFW-research/0.1 (price transparency research)"


def load_codes():
    with open(CODES_FILE, newline="", encoding="utf-8") as f:
        return {r["code"].strip(): r["plain_name"].strip() for r in csv.DictReader(f)}


def open_binary(path):
    path = str(path)
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    if path.endswith(".zip"):
        z = zipfile.ZipFile(path)
        inner = [n for n in z.namelist() if not n.endswith("/")][0]
        return z.open(inner)
    return open(path, "rb")


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    if s == "" or s.lower() in ("n/a", "na", "null", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---- downloading a price file (Oct 22, 2026) ----
# Problems found building the pick lists for the 33 remaining states (claude/pick-lists-oct21.md):
#  - Molina: links on the bare host molinahealthcare.com redirect to the home page; the same paths on www. work.
#  - BCBS Kansas, BCBS South Carolina (CloudFront) and Molina refuse research user agents (403) but serve a browser.
#  - BCBS Massachusetts' server sends an incomplete certificate chain, so a verified download fails.
# download() tries the plain research request first, then a browser user agent, then a Chrome-like request (curl_cffi,
# as the hospital bots do), and drops certificate checking only when the chain itself is the problem (and says so).
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0.0.0 Safari/537.36")
HOST_SWAP = {"molinahealthcare.com": "www.molinahealthcare.com"}
_BLOCKED = {401, 403, 406, 409, 429}


def fix_url(url):
    from urllib.parse import urlsplit, urlunsplit
    p = urlsplit(url)
    h = HOST_SWAP.get(p.hostname or "")
    return urlunsplit(p._replace(netloc=h)) if h else url


def _web_page(r, url):
    """A web page instead of the file (a home page after a redirect, a bot wall)."""
    ct = r.headers.get("Content-Type", "").lower()
    return "text/html" in ct and not url.split("?")[0].lower().endswith((".html", ".htm"))


class SlowDownload(RuntimeError):
    """Nov 2, 2026: the host sends too little to be worth a rented machine's time (see _Speed)."""


class _Speed:
    """Nov 2, 2026: Geisinger's server (mrf.thehealthplan.com) trickled files at ~0.1 Mbps: a machine sat 12 hours on one
    file at 0% CPU, billing and holding one of the host's 2 slots. A dead connection already fails (300 s read timeout);
    a trickle never did. Now a download that has received less than MIN_MB in the last WINDOW_MIN minutes stops with
    SlowDownload ("download too slow"). Normal hosts send hundreds of MB a minute; 64 MB per 30 min is ~0.3 Mbps."""
    MIN_MB = float(os.environ.get("DL_MIN_MB", "64"))
    WINDOW_MIN = float(os.environ.get("DL_WINDOW_MIN", "30"))

    def __init__(self, url):
        self.url, self.t0, self.marks, self.n = url, time.time(), [(time.time(), 0)], 0

    def add(self, k):
        self.n += k
        now = time.time()
        if now - self.marks[-1][0] >= 60:
            self.marks.append((now, self.n))
        w = self.WINDOW_MIN * 60
        if now - self.t0 < w:
            return
        while len(self.marks) > 1 and now - self.marks[1][0] >= w:
            self.marks.pop(0)
        got = (self.n - self.marks[0][1]) / 1e6
        if got < self.MIN_MB:
            raise SlowDownload(f"download too slow: {got:.0f} MB in the last {self.WINDOW_MIN:.0f} min "
                               f"({self.n / 1e6:.0f} MB in {(now - self.t0) / 60:.0f} min) from {self.url.split('/')[2]}")


def download(url, out, log=print):
    """Save url to out. Returns the address that worked. Raises RuntimeError with every attempt's error
    (SlowDownload at once, without the other ways of asking, when the host trickles)."""
    import requests
    url = fix_url(url)
    errs = []
    for who, ua in (("research", USER_AGENT), ("browser", BROWSER_UA)):
        for verify in (True, False):
            try:
                with requests.get(url, stream=True, timeout=300, verify=verify,
                                  headers={"User-Agent": ua, "Accept": "*/*"}) as r:
                    if r.status_code in _BLOCKED or _web_page(r, url):
                        errs.append(f"{who}: HTTP {r.status_code}{' (web page)' if _web_page(r, url) else ''}")
                        break
                    r.raise_for_status()
                    sp = _Speed(url)
                    with open(out, "wb") as f:
                        for chunk in r.iter_content(1 << 20):   # 1 MB pieces so the speed check runs on a slow host
                            f.write(chunk)
                            sp.add(len(chunk))
                if not verify:
                    log(f"  note: {url.split('/')[2]} sends an incomplete certificate chain; read without verifying it")
                if who != "research":
                    log(f"  note: {url.split('/')[2]} only answers a browser user agent")
                return url
            except SlowDownload:
                Path(out).unlink(missing_ok=True)
                raise
            except requests.exceptions.SSLError as e:
                errs.append(f"{who}: certificate ({str(e)[:80]})")
                continue    # same request without checking the chain
            except Exception as e:  # noqa: BLE001
                errs.append(f"{who}: {type(e).__name__}: {str(e)[:120]}")
                break
    try:
        from curl_cffi import requests as creq
        # Oct 29, 2026: curl_cffi's streamed response is not a context manager ("'Response' object does not support
        # the context manager protocol"), so this fallback never ran (Molina WA files); close it by hand instead.
        r = creq.get(url, impersonate="chrome", stream=True, timeout=300, verify=False)
        try:
            if r.status_code < 400 and "text/html" not in r.headers.get("Content-Type", "").lower():
                sp = _Speed(url)
                with open(out, "wb") as f:
                    for chunk in r.iter_content():
                        f.write(chunk)
                        sp.add(len(chunk))
                log(f"  note: {url.split('/')[2]} only answers a Chrome-like request")
                return url
            errs.append(f"chrome-like: HTTP {r.status_code}")
        finally:
            r.close()
    except SlowDownload:
        Path(out).unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        errs.append(f"chrome-like: {type(e).__name__}: {str(e)[:120]}")
    raise RuntimeError("; ".join(errs))
