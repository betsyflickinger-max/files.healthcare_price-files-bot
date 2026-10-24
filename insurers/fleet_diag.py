"""Fleet check (Oct 24, 2026): prints every rented queue machine with its claim, idle sighting and the end of its log,
so a machine that sits idle can be explained from one run (read-only; changes nothing)."""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "bot"))
import droplets, fleet, store  # noqa: E402

s3, b = store.r2()
cl = fleet.claims(s3, b)
by_did = {}
for jid, c in cl.items():
    by_did.setdefault(str(c.get("droplet_id")), []).append((jid, c.get("name"), c.get("heartbeat") or c.get("at")))
only = [x for x in os.environ.get("ONLY", "").split(",") if x]
for did, name, created in droplets.mine():
    if only and not any(o in name for o in only):
        continue
    seen = fleet._get(s3, b, f"bot/fleet/idle_seen/{did}.json")
    print(f"=== {name} (id {did}, made {created})")
    print("  claims by droplet id:", by_did.get(str(did), "none"))
    print("  claims by name:", [jid for jid, c in cl.items() if c.get("name") == name] or "none")
    print("  idle first seen:", seen or "never")
    try:
        log = s3.get_object(Bucket=b, Key=fleet.L + f"{name}.txt")["Body"].read().decode(errors="replace")
        print("  log tail:\n    " + "\n    ".join(log.strip().splitlines()[-25:]))
    except Exception as e:
        print("  no log:", e)
