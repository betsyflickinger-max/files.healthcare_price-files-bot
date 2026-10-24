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

for bid in [x for x in os.environ.get("BUILDS", "").split(",") if x and not x.startswith(("tables:", "logs:"))]:   # e.g. stn5-2026-10: a page build's saved state
    try:
        st = json.loads(s3.get_object(Bucket=b, Key=f"site/builds/{bid}/state.json")["Body"].read())
        print(f"=== build {bid}: stage {st.get('stage')}, machines {st.get('machines')}")
        print("  price check:", json.dumps(st.get("cost_check")))
        print("  last log:", *(st.get("log") or [])[-12:], sep="\n    ")
        print("  full state keys:", {k: (v if len(json.dumps(v)) < 300 else "...") for k, v in st.items() if k != "log"})
        # Oct 24: each build machine uploads its own log to site/builds/<bid>/logs/<role>.log when it ends
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=f"site/builds/{bid}/logs/"):
            for o in sorted(page.get("Contents", []), key=lambda o: o["LastModified"])[-8:]:
                txt = s3.get_object(Bucket=b, Key=o["Key"])["Body"].read().decode(errors="replace")
                print(f"  --- {o['Key']} ({o['LastModified']:%m-%d %H:%M}, {o['Size']} bytes)")
                print("    " + "\n    ".join(txt.strip().splitlines()[-15:]))
    except Exception as e:
        print(f"=== build {bid}: no state ({e})")
for d in droplets.names() if hasattr(droplets, "names") else []:
    if d.startswith("upfront-site-"):
        print("site machine:", d)

# Oct 24: insurer tables an area's page build reads (data/<scope>/rates/, the per-state split, split markers)
def _count(prefix):
    n = sz = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        for o in page.get("Contents", []): n += 1; sz += o["Size"]
    return n, round(sz / 1e9, 1)
for sc in [x[7:] for x in os.environ.get("BUILDS", "").split(",") if x.startswith("tables:")]:   # builds input "tables:n5"
    print(f"=== tables for {sc}: rates {_count(f'data/{sc}/rates/')} (files, GB); split markers {_count(f'data/{sc}/state/_done/')}")
    states = sorted({k.split('/')[3] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=f"data/{sc}/state/", Delimiter="/") for k in [c["Prefix"] + "x" for c in page.get("CommonPrefixes", [])]})
    for slug in states:
        print(f"  {slug}: rates {_count(f'data/{sc}/state/{slug}/rates/')}, npis {_count(f'data/{sc}/state/{slug}/npis.parquet')}")
    try:
        st = json.loads(s3.get_object(Bucket=b, Key=f"site/builds/st{sc}-2026-10/state.json")["Body"].read())
        print("  split_failed:", len(st.get("split_failed") or []), (st.get("split_failed") or [])[:10])
        print("  split_jobs:", [len(j) for j in st.get("split_jobs", [])], "back_jobs:", [len(j) for j in st.get("back_jobs", [])])
        print("  problems:", (st.get("problems") or [])[-8:])
    except Exception as e:
        print("  no build state:", e)

# Oct 24: "logs:<build id>:<part of machine role>" prints those machines' logs (first and last lines)
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("logs:")]:
    _, bid, part = x.split(":", 2)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=f"site/builds/{bid}/logs/"):
        for o in [o for o in page.get("Contents", []) if part in o["Key"].rsplit("/", 1)[1]][:4]:
            lines = s3.get_object(Bucket=b, Key=o["Key"])["Body"].read().decode(errors="replace").strip().splitlines()
            print(f"--- {o['Key']} ({o['LastModified']:%m-%d %H:%M}, {len(lines)} lines)")
            print("    " + "\n    ".join(lines[:12] + ["..."] + lines[-30:]))
