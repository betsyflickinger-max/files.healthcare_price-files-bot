#!/usr/bin/env python3
"""Read an insurer's Transparency in Coverage index (table of contents) as a stream and summarize it.

Usage:
  python3 toc.py URL [URL ...] [--out FILE.json] [--max-mb 4000] [--head-cap 400] [--grep TEXT]
  python3 toc.py --file URL          # a single in-network rate file: check it answers, size, reporting entity

What it prints / writes, per index:
  - reporting entity, index size read, number of plan entries
  - every distinct in-network network (files grouped by description, or by file name without the part suffix):
      parts, total size of the parts that answered, how many parts are missing (HTTP 4xx), plan count,
      market types, plan id types, sample plan names
  - problems: links that don't answer, empty files
--grep keeps only networks whose description/file name/plan names contain TEXT (case-insensitive), e.g. a state.
"""
import argparse, gzip, io, json, re, sys, time, zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import requests, ijson

UA = "Mozilla/5.0 (compatible; price-transparency-research; +https://github.com/betsyflickinger-max/price-files-bot)"
S = requests.Session(); S.headers["User-Agent"] = UA


class Capped(io.RawIOBase):
    """Raw stream over an HTTP response that stops after max_bytes and counts bytes read."""
    def __init__(self, resp, max_bytes):
        self.it = resp.iter_content(1 << 20); self.buf = b""; self.n = 0; self.max = max_bytes; self.capped = False
    def readable(self): return True
    def readinto(self, b):
        while not self.buf:
            if self.n >= self.max: self.capped = True; return 0
            try: self.buf = next(self.it)
            except StopIteration: return 0
            self.n += len(self.buf)
        k = min(len(b), len(self.buf)); b[:k] = self.buf[:k]; self.buf = self.buf[k:]; return k


def open_stream(url, max_mb):
    r = S.get(url, stream=True, timeout=120, allow_redirects=True)
    if r.status_code >= 400:
        return None, r.status_code, None
    raw = Capped(r, max_mb * 1e6)
    br = io.BufferedReader(raw, 1 << 20)
    head = br.peek(2)[:2]
    f = gzip.GzipFile(fileobj=br) if head == b"\x1f\x8b" or url.split("?")[0].endswith(".gz") and head == b"\x1f\x8b" else br
    return f, r.status_code, raw


PART = re.compile(r"(?i)([_\-. ]?(part)?[_\-. ]?\d{1,3}[_\- ]of[_\- ]\d{1,3}|[_\-]part[_\-]?\d{1,3}|_\d{2,3}(?=\.json))")


def netkey(desc, loc):
    name = loc.split("?")[0].rsplit("/", 1)[-1]
    name = re.sub(r"\.json(\.gz)?$", "", name)
    base = PART.sub("", name)
    base = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", base)
    d = (desc or "").strip()
    return (d + " | " + base) if d and d.lower() not in ("in-network file", "in network file", "in-network", "") else base


def probe(url):
    """Size and status without downloading: HEAD, then a 1-byte range GET if HEAD gives nothing."""
    for m in ("head", "get"):
        try:
            if m == "head":
                r = S.head(url, timeout=40, allow_redirects=True)
            else:
                r = S.get(url, timeout=40, allow_redirects=True, stream=True, headers={"Range": "bytes=0-0"}); r.close()
            size = None
            cr = r.headers.get("Content-Range", "")
            if "/" in cr and cr.rsplit("/", 1)[1].isdigit(): size = int(cr.rsplit("/", 1)[1])
            elif r.headers.get("Content-Length", "").isdigit() and m == "head": size = int(r.headers["Content-Length"])
            if m == "head" and r.status_code in (403, 405) : continue   # some hosts refuse HEAD
            if m == "head" and r.status_code < 400 and size is None: continue
            return {"status": r.status_code, "size": size, "modified": r.headers.get("Last-Modified", "")}
        except Exception as e:
            err = str(e)[:80]
    return {"status": "error", "size": None, "modified": "", "err": err}


def read_index(url, max_mb, head_cap, grep):
    t0 = time.time()
    f, code, raw = open_stream(url, max_mb)
    out = {"index": url, "http": code}
    if f is None:
        out["error"] = f"HTTP {code}"; return out
    files = {}; plans_by = defaultdict(set); entity = None; n_items = 0
    try:
        for prefix, event, value in ijson.parse(f, use_float=True):
            if prefix == "reporting_entity_name": entity = value
            if prefix == "reporting_structure.item" and event == "start_map":
                cur = {"plans": [], "files": []}
            elif prefix == "reporting_structure.item.reporting_plans.item" and event == "start_map":
                p = {}
            elif prefix.startswith("reporting_structure.item.reporting_plans.item.") and event in ("string", "number"):
                p[prefix.rsplit(".", 1)[1]] = value
            elif prefix == "reporting_structure.item.reporting_plans.item" and event == "end_map":
                cur["plans"].append(p)
            elif prefix == "reporting_structure.item.in_network_files.item" and event == "start_map":
                fl = {}
            elif prefix.startswith("reporting_structure.item.in_network_files.item.") and event == "string":
                fl[prefix.rsplit(".", 1)[1]] = value
            elif prefix == "reporting_structure.item.in_network_files.item" and event == "end_map":
                cur["files"].append(fl)
            elif prefix == "reporting_structure.item" and event == "end_map":
                n_items += 1
                for fl in cur["files"]:
                    loc = fl.get("location", "")
                    if not loc: continue
                    e = files.setdefault(loc, {"desc": fl.get("description", ""), "plans": 0, "names": [], "markets": set(), "idtypes": set()})
                    e["plans"] += len(cur["plans"])
                    for p in cur["plans"]:
                        e["markets"].add(p.get("plan_market_type", "")); e["idtypes"].add(p.get("plan_id_type", ""))
                        if len(e["names"]) < 6 and p.get("plan_name") and p["plan_name"] not in e["names"]: e["names"].append(p["plan_name"])
                        plans_by[loc].add(str(p.get("plan_id", "")))
    except Exception as ex:
        out["parse_error"] = str(ex)[:200]
    out.update(entity=entity, plan_entries=n_items, read_mb=round(raw.n / 1e6, 1), capped=raw.capped, distinct_files=len(files))
    nets = defaultdict(lambda: {"parts": [], "plans": 0, "plan_ids": set(), "markets": set(), "idtypes": set(), "names": []})
    for loc, e in files.items():
        k = netkey(e["desc"], loc); n = nets[k]
        n["parts"].append(loc); n["plans"] = max(n["plans"], e["plans"]); n["plan_ids"] |= plans_by[loc]
        n["markets"] |= e["markets"]; n["idtypes"] |= e["idtypes"]
        for nm in e["names"]:
            if len(n["names"]) < 6 and nm not in n["names"]: n["names"].append(nm)
    if grep:
        g = grep.lower()
        nets = {k: v for k, v in nets.items() if g in k.lower() or any(g in x.lower() for x in v["names"]) or any(g in p.lower() for p in v["parts"])}
    allparts = [p for v in nets.values() for p in v["parts"]][:head_cap]
    with ThreadPoolExecutor(16) as ex:
        pr = dict(zip(allparts, ex.map(probe, allparts)))
    res = []
    for k, v in sorted(nets.items(), key=lambda kv: -len(kv[1]["plan_ids"])):
        ps = [pr.get(p) for p in v["parts"]]
        checked = [x for x in ps if x]
        ok = [x for x in checked if isinstance(x["status"], int) and x["status"] < 400]
        miss = [p for p, x in zip(v["parts"], ps) if x and not (isinstance(x["status"], int) and x["status"] < 400)]
        res.append({"network": k, "parts": len(v["parts"]), "checked": len(checked), "ok": len(ok), "missing": len(miss),
                    "missing_sample": miss[:3], "gb": round(sum((x["size"] or 0) for x in ok) / 1e9, 3),
                    "unknown_size": sum(1 for x in ok if not x["size"]), "plan_ids": len(v["plan_ids"]),
                    "markets": sorted(x for x in v["markets"] if x), "idtypes": sorted(x for x in v["idtypes"] if x),
                    "names": v["names"], "modified": next((x["modified"] for x in ok if x["modified"]), ""),
                    "sample_url": v["parts"][0]})
    out["networks"] = res; out["secs"] = round(time.time() - t0)
    return out


def check_file(url):
    pr = probe(url); out = {"file": url, **pr}
    try:
        f, code, raw = open_stream(url, 5)
        if f is not None:
            head = f.read(4000).decode("utf-8", "replace")
            m = re.search(r'"reporting_entity_name"\s*:\s*"([^"]*)"', head); out["entity"] = m.group(1) if m else None
            out["has_in_network"] = '"in_network"' in head or '"provider_references"' in head
            m = re.search(r'"last_updated_on"\s*:\s*"([^"]*)"', head); out["last_updated_on"] = m.group(1) if m else None
    except Exception as e:
        out["read_error"] = str(e)[:120]
    return out


def show(o):
    if "file" in o:
        print(json.dumps(o)); return
    print(f"\n=== {o['index']}\n entity={o.get('entity')} http={o.get('http')} plans={o.get('plan_entries')} read={o.get('read_mb')}MB"
          f"{' CAPPED' if o.get('capped') else ''} files={o.get('distinct_files')} {o.get('error','')} {o.get('parse_error','')}")
    for n in o.get("networks", [])[:60]:
        print(f" - {n['network'][:110]} | parts {n['ok']}/{n['parts']} ok, {n['missing']} missing | {n['gb']} GB"
              f"{' (+' + str(n['unknown_size']) + ' no size)' if n['unknown_size'] else ''} | {n['plan_ids']} plan ids | {','.join(n['markets'])} {','.join(n['idtypes'])} | {n['modified'][:16]} | {'; '.join(n['names'][:3])[:120]}")


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("urls", nargs="+"); a.add_argument("--out"); a.add_argument("--max-mb", type=float, default=4000)
    a.add_argument("--head-cap", type=int, default=400); a.add_argument("--grep"); a.add_argument("--file", action="store_true")
    x = a.parse_args(); results = []
    for u in x.urls:
        o = check_file(u) if x.file else read_index(u, x.max_mb, x.head_cap, x.grep)
        show(o); results.append(o)
    if x.out: json.dump(results, open(x.out, "w"), indent=1, default=list)
