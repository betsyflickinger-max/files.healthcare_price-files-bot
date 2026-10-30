"""Find text in a huge insurer index without parsing it (Oct 30, 2026).

Streams the (gzipped) index, and for each pattern prints the first hits with the bytes around them, plus every
in-network file link ("location") within the same reporting_structure entry, so one can see which rate files an
insurer's plans point to (e.g. Harbor Health's plans inside Anthem's 11 GB index).

Run: python insurers/index_grep.py URL PATTERN [PATTERN ...] [--max-hits 20]
"""
import argparse
import re
import urllib.request
import zlib

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("patterns", nargs="+")
ap.add_argument("--max-hits", type=int, default=20)
a = ap.parse_args()
pats = [re.compile(p.encode(), re.I) for p in a.patterns]
hits = {p.pattern: 0 for p in pats}
files = {p.pattern: set() for p in pats}
r = urllib.request.urlopen(urllib.request.Request(a.url, headers={"User-Agent": "Mozilla/5.0"}), timeout=600)
d = zlib.decompressobj(16 + zlib.MAX_WBITS) if a.url.split("?")[0].endswith(".gz") else None
tail, total = b"", 0
LOC = re.compile(rb'"location"\s*:\s*"([^"]+)"')
while True:
    c = r.read(1 << 24)
    if not c:
        break
    c = d.decompress(c) if d else c
    total += len(c)
    buf = tail + c
    for p in pats:
        for m in p.finditer(buf):
            hits[p.pattern] += 1
            # the reporting_structure entry around the hit: back to the last "reporting_plans", forward to its files
            s = buf.rfind(b'"reporting_plans"', 0, m.start())
            e = buf.find(b'"reporting_plans"', m.end())
            seg = buf[s if s >= 0 else max(0, m.start() - 20000): e if e > 0 else m.end() + 200000]
            for u in LOC.findall(seg):
                files[p.pattern].add(u.split(b"?")[0].decode(errors="replace"))
            if hits[p.pattern] <= a.max_hits:
                print(f"--- {p.pattern.decode()} hit {hits[p.pattern]} at ~{total / 1e9:.1f} GB:",
                      buf[max(0, m.start() - 300): m.end() + 300].decode(errors="replace").replace("\n", " "), flush=True)
    tail = buf[-300000:]
    if total and total % (20 * 1 << 30) < (1 << 24):
        print(f"... {total / 1e9:.0f} GB read", flush=True)
print(f"=== done: {total / 1e9:.1f} GB uncompressed")
for p in pats:
    k = p.pattern.decode()
    print(f"=== {k}: {hits[p.pattern]} hits; {len(files[p.pattern])} rate files in the matching entries")
    for u in sorted(files[p.pattern])[:200]:
        print("   ", u)
