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
    # Oct 24: is it working? CPU busy share and download speed over the last 30 minutes (DigitalOcean monitoring agent)
    try:
        import time as _t, requests as _rq
        end = int(_t.time()); q = dict(host_id=str(did), start=str(end - 1800), end=str(end))
        cpu = _rq.get(f"{droplets.API}/monitoring/metrics/droplet/cpu", params=q, headers=droplets._h(), timeout=60).json()
        tot = {}
        for r in cpu["data"]["result"]:
            v = r["values"]; tot[r["metric"].get("mode")] = float(v[-1][1]) - float(v[0][1])
        busy = 1 - (tot.get("idle", 0) + tot.get("iowait", 0)) / max(sum(tot.values()), 1e-9)
        bw = _rq.get(f"{droplets.API}/monitoring/metrics/droplet/bandwidth", params=dict(q, interface="public", direction="inbound"),
                     headers=droplets._h(), timeout=60).json()["data"]["result"]
        pts = [float(x[1]) for x in bw[0]["values"]] if bw else []
        print(f"  last 30 min: CPU busy {busy:.0%}, iowait {tot.get('iowait', 0) / max(sum(tot.values()), 1e-9):.0%}; "
              f"download avg {sum(pts) / max(len(pts), 1):.1f} Mbps, last {pts[-1] if pts else 0:.1f} Mbps")
    except Exception as e:
        print("  activity: could not read monitoring:", repr(e)[:200])
    try:
        log = s3.get_object(Bucket=b, Key=fleet.L + f"{name}.txt")["Body"].read().decode(errors="replace")
        print("  log tail:\n    " + "\n    ".join(log.strip().splitlines()[-25:]))
    except Exception as e:
        print("  no log:", e)

for bid in [x for x in os.environ.get("BUILDS", "").split(",") if x and not x.startswith(("tables:", "logs:", "ctl:"))]:   # e.g. stn5-2026-10: a page build's saved state
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

# Oct 24: "ctl:<text>" prints the lines of the live control center page (site/control/index.html in the deployed site)
# around each place that text appears, so a change to the page can be written against what is really there
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("ctl:")]:
    import tarfile
    s3.download_file(b, "site/deploy/current.tgz", "/tmp/current.tgz")
    with tarfile.open("/tmp/current.tgz") as t:
        m = next(m for m in t.getmembers() if m.name.lstrip("./").endswith("control/index.html"))
        page = t.extractfile(m).read().decode("utf-8", errors="replace")
    lines = page.splitlines(); hit = x[4:]
    print(f"=== control page {m.name}: {len(page)} chars, {len(lines)} lines; '{hit}':")
    for i, l in enumerate(lines):
        if hit in l:
            for j in range(max(0, i - 3), min(len(lines), i + 4)): print(f"  {j + 1}: {lines[j][:400]}")
            print("  ...")
