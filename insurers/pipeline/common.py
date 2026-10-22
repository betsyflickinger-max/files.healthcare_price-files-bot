"""Shared paths and helpers for the Upfront DFW data pipeline (test copy)."""
import csv
import gzip
import io
import os
import sys
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


def download(url, out, log=print):
    """Save url to out. Returns the address that worked. Raises RuntimeError with every attempt's error."""
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
                    with open(out, "wb") as f:
                        for chunk in r.iter_content(8 << 20):
                            f.write(chunk)
                if not verify:
                    log(f"  note: {url.split('/')[2]} sends an incomplete certificate chain; read without verifying it")
                if who != "research":
                    log(f"  note: {url.split('/')[2]} only answers a browser user agent")
                return url
            except requests.exceptions.SSLError as e:
                errs.append(f"{who}: certificate ({str(e)[:80]})")
                continue    # same request without checking the chain
            except Exception as e:  # noqa: BLE001
                errs.append(f"{who}: {type(e).__name__}: {str(e)[:120]}")
                break
    try:
        from curl_cffi import requests as creq
        with creq.get(url, impersonate="chrome", stream=True, timeout=300, verify=False) as r:
            if r.status_code < 400 and "text/html" not in r.headers.get("Content-Type", "").lower():
                with open(out, "wb") as f:
                    for chunk in r.iter_content():
                        f.write(chunk)
                log(f"  note: {url.split('/')[2]} only answers a Chrome-like request")
                return url
            errs.append(f"chrome-like: HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        errs.append(f"chrome-like: {type(e).__name__}: {str(e)[:120]}")
    raise RuntimeError("; ".join(errs))
