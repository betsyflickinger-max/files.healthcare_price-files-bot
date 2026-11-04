"""National network crosswalk for the control center (Nov 4, 2026, Betsy: lifted the freeze and asked for it).

The Network access tab's "Download crosswalk (CSV)" gave every network-vs-network pair inside one area. Nationally the
tab shows insurers only (thousands of networks are not one grid), so this builds the network-level pairs for the whole
country as a download: for every two networks that share at least one provider, how many providers (by NPI, counted once
across areas) and hospitals they share. Counts only, no prices (prices are compared inside one area).

Input: the folder dashboard/build_network.py --kept-out wrote (kept.npz + kept.json: each area's providers, their kind and
which networks list them). A network is (insurer, network name); the same name in two areas is one network.
Output: net_xwalk_us.json (+ _2, _3 ...), each under 7 MB, for R2 control/data/ (board/to_r2_control.py):
  first part: {made, areas, providers, min_shared, parts, networks: [[insurer, network, providers, hospitals], ...],
               cols: ["a", "b", "shared", "shared_hospitals"], rows: [[a, b, shared, shared_hospitals], ...]}
  later parts: {rows: [...]}
Each pair is listed once (a < b); the page writes the CSV with both shares. If the pairs would need more than MAX_PARTS
files, only pairs sharing at least min_shared providers are kept, and the file and CSV say so.
usage: build_xwalk_us.py KEPT_DIR OUT_DIR
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

PART_BYTES, MAX_PARTS = 7_000_000, 20


def main(kdir, out):
    t0 = time.time()
    kdir, out = Path(kdir), Path(out); out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((kdir / "kept.json").read_text()); Z = np.load(kdir / "kept.npz")
    areas = meta["areas"]
    nets = sorted({tuple(n) for ns in meta["nets"] for n in ns}); nid = {n: i for i, n in enumerate(nets)}
    allnpi = np.unique(np.concatenate([Z[f"{i}_npi"] for i in range(len(areas))]))
    U, N = len(allnpi), len(nets)
    hosp = np.zeros(U, dtype=bool)
    rows, cols = [], []
    for i in range(len(areas)):
        npi, kind, bits = Z[f"{i}_npi"], Z[f"{i}_kind"], Z[f"{i}_bits"]
        r = np.searchsorted(allnpi, npi); hosp[r[kind == "H"]] = True
        mem = np.unpackbits(bits, axis=1, count=len(meta["nets"][i])).astype(bool)
        rr, cc = np.nonzero(mem)
        rows.append(r[rr]); cols.append(np.array([nid[tuple(meta["nets"][i][c])] for c in range(mem.shape[1])], dtype=np.int64)[cc])
        del mem
    S = sp.csr_matrix((np.ones(sum(len(x) for x in rows), dtype=np.float32), (np.concatenate(rows), np.concatenate(cols))), shape=(U, N))
    S.sum_duplicates(); S.data[:] = 1          # a provider listed by one network in two areas counts once
    del rows, cols
    G = (S.T @ S).toarray().astype(np.int64)   # shared providers, every pair (diagonal = network size)
    Sh = S[hosp]; GH = (Sh.T @ Sh).toarray().astype(np.int64)
    size, hsize = np.diag(G).copy(), np.diag(GH).copy()
    a, b = np.nonzero(np.triu(G, 1))
    sh, shh = G[a, b], GH[a, b]
    print(f"{U:,} providers, {N:,} networks, {len(a):,} pairs sharing a provider ({round(time.time() - t0)} s)", flush=True)
    order = np.lexsort((-sh,))
    min_shared = 1
    def parts_needed(keep): return int(keep.sum()) * 24 // PART_BYTES + 1   # ~24 bytes per row in JSON
    keep = sh >= min_shared
    while parts_needed(keep) > MAX_PARTS:
        min_shared *= 2; keep = sh >= min_shared
    if min_shared > 1: print(f"too many pairs for {MAX_PARTS} files: keeping pairs that share at least {min_shared} providers", flush=True)
    idx = order[keep[order]]
    R = np.stack([a[idx], b[idx], sh[idx], shh[idx]], axis=1).tolist()
    head = {"made": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "areas": len(areas), "providers": U, "min_shared": min_shared,
            "networks": [[n[0], n[1], int(size[i]), int(hsize[i])] for i, n in enumerate(nets)],
            "cols": ["a", "b", "shared", "shared_hospitals"]}
    first_room = PART_BYTES - len(json.dumps(head))
    chunks, cur, room = [], [], first_room
    for r in R:
        t = len(json.dumps(r)) + 1
        if cur and t > room:
            chunks.append(cur); cur, room = [], PART_BYTES - 20
        cur.append(r); room -= t
    chunks.append(cur)
    if len(chunks) > MAX_PARTS: sys.exit(f"STOP: {len(chunks)} parts")
    for j, ch in enumerate(chunks):
        body = dict(head, parts=len(chunks), rows=ch) if j == 0 else {"rows": ch}
        f = out / ("net_xwalk_us.json" if j == 0 else f"net_xwalk_us_{j + 1}.json")
        f.write_text(json.dumps(body, separators=(",", ":")))
        assert f.stat().st_size < 8_000_000, f
    print(f"national crosswalk: {len(R):,} pairs in {len(chunks)} file(s), {round(time.time() - t0)} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
