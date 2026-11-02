"""Stop stuck queue machines (Nov 2, 2026, Betsy OK'd stopping the one the stall watch flagged).

The stall watch (stall_watch.py) only reports. This stops the machines named in the STOP input, and only if,
checked again right now:
  - the name is a queue machine (upfront-fleet-*). Website-build machines (upfront-site-*) are never stopped here:
    they can sit quiet while they wait for other machines' tables.
  - it is still under the stall watch's CPU line (5%) over the last 30 minutes, and
  - it is not still downloading (under 1 Mbps in), the same test the stall watch uses.
The machine's file is not lost: its claim stops getting a heartbeat, the fill clears it after ~20 minutes and the
file goes back in line for a fresh machine (fleet.py, GONE_MINS / MAX_ATTEMPTS).
"""
import os

import requests

import droplets
from stall_watch import CPU_UNDER, MBPS_OVER, _safe_cpu, _safe_mbps


def main():
    want = [n.strip() for n in os.environ.get("STOP", "").split(",") if n.strip()]
    if not want:
        print("Nothing named. Put machine names (or unique parts of them) in the input.")
        return
    r = requests.get(f"{droplets.API}/droplets", params={"per_page": 200}, headers=droplets._h(), timeout=60)
    r.raise_for_status()
    ds = r.json()["droplets"]
    for w in want:
        hits = [d for d in ds if w in d["name"]]
        if len(hits) != 1:
            print(f"{w}: {len(hits)} machines match, need exactly one. Nothing stopped.")
            continue
        d = hits[0]
        n = d["name"]
        if not n.startswith("upfront-fleet-"):
            print(f"{n}: not a queue machine. Left running.")
            continue
        cpu, mb = _safe_cpu(d["id"]), _safe_mbps(d["id"])
        if cpu is None or cpu >= CPU_UNDER or mb > MBPS_OVER:
            print(f"{n}: working again ({cpu}% CPU, {mb:.1f} Mbps in). Left running.")
            continue
        ok = droplets.delete(d["id"])
        print(f"{n}: {cpu}% CPU, {mb:.1f} Mbps in -> " + ("STOPPED. Its file goes back in line in ~20 minutes."
                                                         if ok else "stop FAILED, try again"))


if __name__ == "__main__":
    main()
