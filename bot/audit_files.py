"""Check every saved hospital price file against the hospital it is filed under (Oct 15, 2026). See bot/identity.py.

Usage: python bot/audit_files.py [--states TX,GA] [--workers 16]
Reads, for each hospital, the file it is on now (R2 bot/manifest/hospitals + files) and the October file in
data/hospitals.csv (last_key), only the first ~2 MB of each saved original, and compares the address the file gives with
Medicare's address for the hospital. Writes the wrong ones to R2 bot/manifest/wrong_files.csv (merged; hand verdicts in
data/wrong_files.csv always win) and every result to reports/file_identity.csv.
"""
import argparse
import csv
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identity  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = {}


def head(s3, bucket, key, nbytes=2_000_000):
    """First part of a saved original (.zst), decompressed as far as the bytes go."""
    raw = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{nbytes - 1}")["Body"].read()
    if not key.endswith(".zst"):
        return raw.decode("utf-8", "replace")
    out = io.BytesIO()
    try:
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as r:
            while out.tell() < 1_500_000:
                b = r.read(65536)
                if not b:
                    break
                out.write(b)
    except zstandard.ZstdError:
        pass
    data = out.getvalue()
    if data[:4] == b"PK\x03\x04":   # a zipped price file: unzip the start of its first file (deflate)
        import struct, zlib
        n, x = struct.unpack("<HH", data[26:30])
        method = struct.unpack("<H", data[8:10])[0]
        body = data[30 + n + x:]
        if method == 8:
            try:
                data = zlib.decompressobj(-15).decompress(body, 600_000)
            except zlib.error:
                data = b""
        elif method == 0:
            data = body
    return data.decode("utf-8-sig", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default="")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    want = {s.strip().upper() for s in a.states.split(",") if s.strip()}
    s3, bucket = store.r2()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hospitals = [r for r in csv.DictReader(open(ROOT / "data" / "hospitals.csv")) if not want or r["state"] in want]
    NAME.update({h["ccn"]: h["name"] for h in hospitals})
    pairs = {}   # (ccn, url) -> r2 key of the saved original
    for st in sorted({h["state"] for h in hospitals}):
        cur = {r["ccn"]: r for r in store.read_csv(s3, bucket, f"{store.R2_PREFIX}manifest/hospitals/{st}.csv")}
        files = {r["url"]: r for r in store.read_csv(s3, bucket, f"{store.R2_PREFIX}manifest/files/{st}.csv")}
        for h in (x for x in hospitals if x["state"] == st):
            u = (cur.get(h["ccn"]) or {}).get("mrf_url", "")
            if u and (files.get(u) or {}).get("r2_key"):
                pairs[(h["ccn"], u)] = files[u]["r2_key"]
            if h.get("mrf_url") and h.get("last_key"):
                pairs.setdefault((h["ccn"], h["mrf_url"]), h["last_key"])
    print(f"{len(pairs)} hospital/file pairs to check", flush=True)
    by_key = {}
    for (c, u), k in pairs.items():
        by_key.setdefault(k, []).append((c, u))

    def one(k):
        try:
            t = head(s3, bucket, k)
            return k, identity.address_text(t), identity.names_text(t), ""
        except Exception as e:
            return k, "", [], f"{type(e).__name__}: {str(e)[:120]}"

    rows, wrong = [], []
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (k, addr, nm, err) in enumerate(ex.map(one, by_key), 1):
            for c, u in by_key[k]:
                v, why = identity.check(c, addr, nm, [NAME.get(c, "")])
                rows.append(dict(ccn=c, mrf_url=u, r2_key=k, file_address=addr[:300], file_names=" | ".join(nm)[:200],
                                 verdict=v or ("ok" if identity.places(addr) else "unknown"), reason=why or err))
                if v:
                    wrong.append(dict(ccn=c, mrf_url=u, verdict=v, reason=why, file_address=addr[:300], checked_at=now, by="audit"))
            if i % 500 == 0:
                print(f"  {i}/{len(by_key)} files read, {len(wrong)} wrong so far", flush=True)
    identity.save(s3, bucket, wrong, checked=set(pairs))
    (ROOT / "reports").mkdir(exist_ok=True)
    with open(ROOT / "reports" / "file_identity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["ccn", "mrf_url", "r2_key", "verdict", "reason", "file_address", "file_names"])
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: ({"wrong": 0, "check": 1}.get(r["verdict"], 2), r["ccn"])))
    n = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("ok", "wrong", "check", "unknown")}
    print(f"done: {n['ok']} match, {n['wrong']} wrong hospital's file, {n['check']} to check by hand, {n['unknown']} no address to judge; "
          "reports/file_identity.csv", flush=True)


if __name__ == "__main__":
    main()
