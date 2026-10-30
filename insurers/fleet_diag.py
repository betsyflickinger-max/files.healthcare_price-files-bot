"""Fleet check (Oct 24, 2026): prints every rented queue machine with its claim, idle sighting and the end of its log,
so a machine that sits idle can be explained from one run (read-only; changes nothing)."""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "bot"))
import droplets, fleet, store  # noqa: E402

s3, b = store.r2()
# Oct 26, 2026: when R2 itself is down, still list every machine on the account with its CPU (is money being wasted?)
try:
    cl = fleet.claims(s3, b)
except Exception as e:
    print("R2 NOT REACHABLE:", repr(e)[:200])
    import time as _t, requests as _rq
    r = _rq.get(f"{droplets.API}/droplets", params={"per_page": 200}, headers=droplets._h(), timeout=60).json()["droplets"]
    print(f"=== ALL MACHINES: {len(r)}")
    for d in r:
        try:
            end = int(_t.time()); q = dict(host_id=str(d["id"]), start=str(end - 1800), end=str(end))
            res = _rq.get(f"{droplets.API}/monitoring/metrics/droplet/cpu", params=q, headers=droplets._h(), timeout=60).json()["data"]["result"]
            tot = {x["metric"].get("mode"): float(x["values"][-1][1]) - float(x["values"][0][1]) for x in res if len(x["values"]) >= 2}
            cpu = f"{100 * (1 - (tot.get('idle', 0) + tot.get('iowait', 0)) / sum(tot.values())):.0f}%" if sum(tot.values()) else "?"
        except Exception:
            cpu = "?"
        print(f"  {d['name']}  made {d['created_at']}  {d['size_slug']}  ${d['size']['price_hourly']}/h  CPU {cpu}")
    sys.exit(0)
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

for bid in [x for x in os.environ.get("BUILDS", "").split(",") if x and not x.startswith(("tables:", "logs:", "ctl:", "queue", "manifest:"))]:   # e.g. stn5-2026-10: a page build's saved state
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
# Every machine on the account that isn't a queue machine (site builds, the R2 -> B2 copy, ...)
import requests as _rq
_q = {n for _, n, _ in droplets.mine()}
for d in _rq.get(f"{droplets.API}/droplets", params={"per_page": 200}, headers=droplets._h(), timeout=60).json()["droplets"]:
    if d["name"] not in _q:
        print(f"other machine: {d['name']} ({d['size_slug']}, {d['status']}, made {d['created_at']})")

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
    # Oct 30: the newest 4 matching logs (was the first 4 by name, which showed week-old logs), plus every match's name and date
    objs = [o for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=f"site/builds/{bid}/logs/")
            for o in page.get("Contents", []) if part in o["Key"].rsplit("/", 1)[1]]
    objs.sort(key=lambda o: o["LastModified"])
    print(f"=== logs {bid} '{part}': " + ", ".join(f"{o['Key'].rsplit('/', 1)[1]} {o['LastModified']:%m-%d %H:%M}" for o in objs))
    if True:
        for o in objs[-4:]:
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

# Oct 24: "queue" prints every queued insurer file in the order the machines take them (fleet.order), one line each
if "queue" in os.environ.get("BUILDS", "").split(","):
    qj, qc = fleet.jobs(s3, b), fleet.claims(s3, b)
    rows = fleet.order(list(qj.values()))
    print(f"=== QUEUE {len(rows)} jobs, {len(qc)} claimed")
    for i, j in enumerate(rows, 1):
        c = qc.get(j["id"], {})
        print("Q\t" + "\t".join(str(x) for x in (i, "reading" if c else "waiting", j.get("scope"), j.get("network_label", "")[:90],
              j["id"].split("__", 1)[-1][:110], j.get("mem", 8), "re-read" if j.get("backfill") else "new",
              j.get("enqueued_at", ""), c.get("name", ""), c.get("claimed_at", ""))))

# Oct 25: "manifest:<area>" prints that area's insurer manifest rows that are not processed (what a page build waits on)
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("manifest:")]:
    import csv as _csv, io as _io
    sc = x.split(":", 1)[1]
    m = list(_csv.DictReader(_io.StringIO(s3.get_object(Bucket=b, Key=f"bot/insurers/{sc}/manifest.csv")["Body"].read().decode())))
    from collections import Counter as _C
    print(f"=== manifest {sc}: {len(m)} rows", dict(_C(r.get("status") for r in m)))
    for r in m:
        if r.get("status") in ("running", "queued"):
            print("  ", {k: (v[:120] if isinstance(v, str) else v) for k, v in r.items() if v})

# Oct 29, 2026: "fleetlogs:<start of machine name>" prints the logs of queue machines that are already gone (newest 4),
# plus any page build below its machine floor (queue machines step aside for those), so a machine that deleted itself
# without reading a file can be explained after the fact.
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("fleetlogs:")]:
    pre = fleet.L + x.split(":", 1)[1]
    print("=== page builds below their machine floor:", fleet.build_shortfall(s3, b) or "none")
    objs = [o for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=pre) for o in page.get("Contents", [])]
    print(f"=== {len(objs)} machine logs starting {pre}")
    for o in sorted(objs, key=lambda o: o["LastModified"])[-4:]:
        lines = s3.get_object(Bucket=b, Key=o["Key"])["Body"].read().decode(errors="replace").strip().splitlines()
        print(f"--- {o['Key']} ({o['LastModified']:%m-%d %H:%M}, {len(lines)} lines)")
        print("    " + "\n    ".join(lines[-20:]))

# Oct 29, 2026: "joblog:<part of a file id>" finds that file's reads in queue machine logs from the last 3 days and prints
# the end of each read (from its "claimed" line to the next file), so a file that failed after reading can be explained.
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("joblog:")]:
    import datetime as _dt
    want = x.split(":", 1)[1]
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=3)
    objs = [o for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=fleet.L)
            for o in page.get("Contents", []) if o["LastModified"] >= since]
    print(f"=== joblog {want}: searching {len(objs)} machine logs from the last 3 days")
    for o in sorted(objs, key=lambda o: o["LastModified"]):
        lines = s3.get_object(Bucket=b, Key=o["Key"])["Body"].read().decode(errors="replace").splitlines()
        starts = [i for i, l in enumerate(lines) if want in l and "claimed" in l]
        for s in starts:
            e = next((i for i in range(s + 1, len(lines)) if "] claimed (" in lines[i]), len(lines))
            seg = lines[s:e]
            print(f"--- {o['Key']} lines {s + 1}-{e} ({len(seg)} lines)")
            print("    " + "\n    ".join(l[:300] for l in (seg[:3] + ["    ..."] + seg[-30:] if len(seg) > 34 else seg)))

# Oct 29, 2026: "result:<area>:<part of slot>" prints the saved result of that file's last read (the full error, not
# the 300-character cut the status board shows).
for x in [x for x in os.environ.get("BUILDS", "").split(",") if x.startswith("result:")]:
    import csv as _csv, io as _io
    _, sc, part = x.split(":", 2)
    m = list(_csv.DictReader(_io.StringIO(s3.get_object(Bucket=b, Key=f"bot/insurers/{sc}/manifest.csv")["Body"].read().decode())))
    for r in [r for r in m if part in r.get("slot", "")]:
        print(f"=== result {sc} {r['slot']}: status {r.get('status')}, fails {r.get('fails')}, run {r.get('run_id')}, launched {r.get('launched_at')}")
        k = f"bot/insurers/{sc}/runs/{r.get('run_id')}/done/{r['slot']}.json"
        try:
            print("   ", json.dumps(json.loads(s3.get_object(Bucket=b, Key=k)["Body"].read()), indent=1)[:4000])
        except Exception as e:
            print(f"    no saved result at {k}: {type(e).__name__}")
