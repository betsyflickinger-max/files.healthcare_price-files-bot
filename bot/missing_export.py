"""Price File Watch: export every hospital without a working price file (Oct 19, 2026).

Reads the daily run's status for every state (R2 bot/manifest/hospitals/<ST>.csv), keeps hospitals whose status is
not a working file, and adds each one's type (data/hospitals.csv) and what the web search found (data/web_search_log.csv).
Writes reports/watch/missing-hospitals-<date>.csv. Read-only on R2.
"""
import csv
import io
from datetime import date
from pathlib import Path

import store

ROOT = Path(__file__).resolve().parent.parent
BAD = {"no price file found", "link broken", "not a price file", "wrong hospital's file"}


def main():
    s3, b = store.r2()
    H = {r["ccn"]: r for r in csv.DictReader(open(ROOT / "data/hospitals.csv"))}
    L = {r["ccn"]: r for r in csv.DictReader(open(ROOT / "data/web_search_log.csv"))}
    out = []
    for st in sorted({r["state"] for r in H.values()}):
        try:
            body = s3.get_object(Bucket=b, Key=f"{store.R2_PREFIX}manifest/hospitals/{st}.csv")["Body"].read().decode()
        except Exception:  # noqa: BLE001
            continue
        for m in csv.DictReader(io.StringIO(body)):
            if m.get("status", "") not in BAD:
                continue
            h, s = H.get(m["ccn"], {}), L.get(m["ccn"], {})
            out.append(dict(state=st, ccn=m["ccn"], name=h.get("name", m.get("name", "")), city=h.get("city", ""),
                            type=h.get("type", ""), status=m.get("status", ""), last_checked=m.get("last_checked", "")[:10],
                            website=h.get("index_domain", ""), link=m.get("mrf_url", "") or h.get("mrf_url", ""),
                            detail=(m.get("detail", "") or m.get("problem", ""))[:200],
                            search_result=s.get("result", ""), times_searched=s.get("times_searched", ""),
                            searched_at=s.get("searched_at", ""), search_why=s.get("why", "")[:200],
                            search_notes=s.get("notes", "")[:300]))
    d = ROOT / "reports" / "watch"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"missing-hospitals-{date.today().isoformat()}.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ["state"])
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} hospitals without a working price file -> {p.name}")


if __name__ == "__main__":
    main()
