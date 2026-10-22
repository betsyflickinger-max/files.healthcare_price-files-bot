"""Provider list for a state from the CMS NPI Registry API, for when the monthly NPPES file can't be downloaded.

Added Oct 22, 2026: download.cms.gov/nppes was "down for maintenance until further notice" and its files returned 404,
so no new state's provider list could be built. The NPI Registry API (npiregistry.cms.hhs.gov/api, same registry,
active NPIs only) answers at most 1,200 results per search (6 pages of 200; later pages repeat), so a state is split
until every search fits: 3-digit ZIP prefix -> 4-digit -> 5-digit ZIP -> person / organization -> first two letters of
the name. A search that still fills up at the deepest level is reported (count printed), never silently dropped.

Same columns as build_scope.py: npi, entity_type, name, credential, taxonomy_1, address, city, zip5, phone,
deactivated (always empty: the API lists active NPIs only), state. Practice-location address only.

  python insurers/npi_api.py MT out.parquet        # local test; build_scope.py calls build(states) when NPPES is down
"""
import string
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
from zip_state import _RANGES  # noqa: E402  (3-digit ZIP prefixes of each state)

API = "https://npiregistry.cms.hhs.gov/api/"
CAP = 1200          # the API's real limit per search (skip above 1,000 repeats the last page)
_local = threading.local()
_stats = {"requests": 0, "full": []}
_lock = threading.Lock()


def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers["User-Agent"] = "price-files-bot (+https://github.com/betsyflickinger-max/price-files-bot)"
    return _local.s


def _page(params, skip):
    for i in range(6):
        try:
            r = _session().get(API, params=dict(params, version="2.1", limit=200, skip=skip, address_purpose="LOCATION"),
                               timeout=90)
            if r.status_code == 200:
                with _lock:
                    _stats["requests"] += 1
                return r.json().get("results", []) or []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"NPI API kept failing for {params}")


def _search(params):
    """All results of one search, up to CAP. Returns (results by NPI, filled_up)."""
    out = {}
    for skip in range(0, CAP, 200):
        res = _page(params, skip)
        new = {r["number"]: r for r in res if r["number"] not in out}
        out.update(new)
        if len(res) < 200 or not new:
            return out, False
    return out, True


def _letters():
    a = string.ascii_uppercase
    return [x + y for x in a for y in a]


def _split(params, level):
    """Children of a search that filled up."""
    z = params.get("postal_code", "").rstrip("*")
    if level == "zip3":
        return [dict(params, postal_code=f"{z}{d}*") for d in range(10)], "zip4"
    if level == "zip4":
        return [dict(params, postal_code=f"{z}{d}") for d in range(10)], "zip5"
    if level == "zip5":
        return [dict(params, enumeration_type=t) for t in ("NPI-1", "NPI-2")], "type"
    if level == "type":
        key = "last_name" if params["enumeration_type"] == "NPI-1" else "organization_name"
        pre = _letters() + ([f"{d}*" for d in range(10, 100)] if key == "organization_name" else [])
        return [dict(params, **{key: p if p.endswith("*") else p + "*"}) for p in pre], "name"
    return [], None


def _run(params, level, found, pool_depth=0):
    res, full = _search(params)
    found.update(res)
    if not full:
        return
    kids, nxt = _split(params, level)
    if not kids:
        with _lock:
            _stats["full"].append(dict(params))
        print(f"  still {CAP}+ at the deepest split: {params}", flush=True)
        return
    for k in kids:
        _run(k, nxt, found, pool_depth + 1)


def _row(r, st):
    b = r.get("basic", {})
    loc = next((a for a in r.get("addresses", []) if a.get("address_purpose") == "LOCATION"), {})
    tax = next((t for t in r.get("taxonomies", []) if t.get("primary")), (r.get("taxonomies") or [{}])[0])
    if r.get("enumeration_type") == "NPI-2":
        name = b.get("organization_name", "")
    else:
        name = f"{b.get('first_name', '')} {b.get('last_name', '')}".strip()
    return dict(npi=str(r["number"]), entity_type="2" if r.get("enumeration_type") == "NPI-2" else "1", name=name,
                credential=(b.get("credential") or "").replace(".", "").strip() or None, taxonomy_1=tax.get("code") or None,
                address=loc.get("address_1", ""), city=loc.get("city", ""), zip5=(loc.get("postal_code") or "")[:5],
                phone=loc.get("telephone_number") or None, deactivated=None, state=(loc.get("state") or st).upper())


def build(states, workers=8):
    """{column: [values]} for every active NPI whose practice location is in one of the states."""
    rows = {k: [] for k in ("npi", "entity_type", "name", "credential", "taxonomy_1", "address", "city", "zip5", "phone",
                            "deactivated", "state")}
    t0 = time.time()
    for st in sorted(states):
        prefixes = [p for a, b, s in _RANGES if s == st for p in range(a, b + 1)]
        found = {}
        jobs = [dict(state=st, postal_code=f"{p:03d}*") for p in prefixes]
        with ThreadPoolExecutor(workers) as ex:
            parts = list(ex.map(lambda q: (lambda f: (_run(q, "zip3", f), f)[1])({}), jobs))
        for f in parts:
            found.update(f)
        kept = 0
        for r in found.values():
            row = _row(r, st)
            if row["state"] != st:
                continue
            kept += 1
            for k, v in row.items():
                rows[k].append(v)
        print(f"{st}: {kept:,} providers ({len(found):,} found, {_stats['requests']:,} API requests so far, "
              f"{time.time() - t0:.0f}s)", flush=True)
    return rows, dict(requests=_stats["requests"], still_full=_stats["full"])


if __name__ == "__main__":
    import pyarrow as pa
    import pyarrow.parquet as pq
    rows, info = build({x.strip().upper() for x in sys.argv[1].split(",")})
    pq.write_table(pa.table({k: pa.array(v, pa.string()) for k, v in rows.items()}), sys.argv[2], compression="zstd")
    print(info["requests"], "requests;", len(info["still_full"]), "searches still full at the deepest split")
