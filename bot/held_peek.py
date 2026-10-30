"""First pass on hospital files held for a person to confirm (Oct 30, 2026).

For each row of data/web_search_held.csv, read only the start of the file (or, for a system's cms-hpt.txt index,
the entry the bot matched) and print what the file says about itself: hospital name, location names and address.
Nothing is downloaded whole and nothing is changed. One line per hospital, tab-separated, for review.

Run: python bot/held_peek.py [data/web_search_held.csv]
"""
import csv
import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def head(url, n=60000):
    r = requests.get(url, headers=dict(UA, Range=f"bytes=0-{n}"), timeout=60, stream=True)
    b = r.raw.read(n + 1, decode_content=True)
    return r.status_code, b


def from_bytes(b, url):
    if b[:2] == b"PK":
        try:
            import remotezip
            with remotezip.RemoteZip(url, headers=UA) as z:
                name = [i for i in z.namelist() if not i.endswith("/")][0]
                with z.open(name) as f:
                    b = f.read(60000)
        except Exception as e:
            return f"zip, couldn't peek ({str(e)[:60]})"
    t = b.decode("utf-8", "replace").lstrip("﻿")
    if t.lstrip().startswith("{"):
        out = []
        for k in ("hospital_name", "location_name", "hospital_address", "hospital_location"):
            m = re.search(rf'"{k}"\s*:\s*(\[[^\]]*\]|"[^"]*")', t)
            if m:
                out.append(f"{k}={m.group(1)[:160]}")
        return " | ".join(out) or "json, no name fields in the first 60 KB"
    rows = list(csv.reader(io.StringIO("\n".join(t.splitlines()[:3]))))
    if len(rows) >= 2:
        pairs = [f"{h.split('|')[0]}={v}" for h, v in zip(rows[0], rows[1])
                 if re.search(r"name|address|location|license", h, re.I)]
        return " | ".join(pairs)[:400] or ("csv: " + t[:200].replace("\n", " "))
    return "not a csv/json start: " + t[:120].replace("\n", " ")


def cms_hpt(domain, want):
    try:
        t = requests.get(f"{domain.rstrip('/')}/cms-hpt.txt", headers=UA, timeout=60).text
    except Exception as e:
        return f"cms-hpt.txt failed ({str(e)[:60]})"
    blocks = re.split(r"\n\s*\n", t)
    w = set(re.findall(r"[a-z]{3,}", want.lower())) - {"hospital", "medical", "center", "health", "the"}
    best = max(blocks, key=lambda b: len(w & set(re.findall(r"[a-z]{3,}", b.lower()))), default="")
    return "cms-hpt: " + " ; ".join(l.strip() for l in best.splitlines() if l.strip())[:400]


def one(r):
    u = r["mrf_url"] or r.get("domain", "")   # Oct 30: rows matched through a system's cms-hpt.txt have only the domain
    if u and not u.startswith("http"):
        u = "https://" + u
    try:
        if urlparse(u).path in ("", "/"):
            got = cms_hpt(u, r["name"])
        else:
            code, b = head(u)
            got = f"HTTP {code}: " + (from_bytes(b, u) if code < 400 else "")
    except Exception as e:
        got = f"failed: {type(e).__name__} {str(e)[:80]}"
    return "\t".join([r["state"], r["name"], r["city"], urlparse(u).netloc, got.replace("\t", " ")])


rows = list(csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "data/web_search_held.csv")))
if "--index-only" in sys.argv:
    rows = [r for r in rows if not r["mrf_url"]]
with ThreadPoolExecutor(12) as ex:
    for line in ex.map(one, rows):
        print(line, flush=True)
