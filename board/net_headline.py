"""Network access tab: the six headline boxes, worked out here instead of in the browser (Oct 31, 2026, Betsy).

Usage: python board/net_headline.py <folder>   (reads net_access.json, net_parts.json, markets.json; writes net_headline.json)
Same figures the control page's net_summary calc made, row for row, so the page only has to read one small file:
networks compared, providers and facilities in any network, the broadest and lowest/highest-priced networks, and the
middle overlap. Run by .github/workflows/dashboard.yml (publish) and net-headline.yml. Never stops the workflow.
"""
import json
import os
import sys


def rows(folder, name):
    p = os.path.join(folder, name + ".json")
    if not os.path.isfile(p):
        return None
    j = json.load(open(p, encoding="utf-8"))
    return j.get("rows", j.get("data", j)) if isinstance(j, dict) else j


def main(folder):
    acc = rows(folder, "net_access")   # Nov 3, 2026: net_access comes in parts (net_access.json, _2 ... _6)
    for j in range(2, 7):
        acc = (acc or []) + (rows(folder, f"net_access_{j}") or []) if acc is not None else acc
    parts, mk = rows(folder, "net_parts") or [], rows(folder, "markets") or []
    if not acc:
        print("net_headline: no net_access.json; nothing written")
        return
    P = {r["market"]: r for r in parts}
    M = {r["market"]: r for r in mk}
    out = []
    for m in dict.fromkeys(r["market"] for r in acc):
        n = [r for r in acc if r["market"] == m and r["level"] == "network"]
        g = n or [r for r in acc if r["market"] == m and r["level"] == "insurer"]   # Nov 3: National has insurer rows only
        broad = sorted(g, key=lambda r: -(r.get("providers") or 0))[0] if g else None
        priced = sorted([r for r in n if r.get("typical_vs_market") is not None], key=lambda r: r["typical_vs_market"])
        k, np = M.get(m), P.get(m)
        if not k and np and np.get("rollup"): k = np   # Nov 3: roll-ups (Texas, National) carry their own hospital counts
        out.append({
            "market": m, "networks": len(n) or (np or {}).get("networks") or 0, "providers": g[0].get("market_providers") if g else None,
            "hospitals": k.get("hospitals") if k else None, "surgery_centers": k.get("surgery_centers") if k else None,
            "facilities": (k.get("hospitals") or 0) + (k.get("surgery_centers") or 0) if k else None,
            "broadest": broad["label"] if broad else None, "broadest_share": broad.get("share_of_market") if broad else None,
            "cheapest": priced[0]["label"] if priced else None, "cheapest_vs": priced[0]["typical_vs_market"] if priced else None,
            "priciest": priced[-1]["label"] if priced else None, "priciest_vs": priced[-1]["typical_vs_market"] if priced else None,
            "overlap_mid": np.get("overlap_mid") if np else None,
        })
    with open(os.path.join(folder, "net_headline.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"net_headline: {len(out)} areas written")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as e:  # a convenience file; never fail the bot over it
        print(f"::warning::net_headline failed: {e}")
