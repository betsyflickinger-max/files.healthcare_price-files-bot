"""Plan -> network crosswalk, one snapshot per table-of-contents date (Nov 7, 2026). Prep for the 2027 file change.

Why: today insurers post one in-network rate file per plan (or per group of plans) and name the files in a table of
contents (TOC) that lists every plan. Under the Transparency in Coverage final rule (CMS-9882-F, Oct 2026), starting
about five months after publication (about March 2027) they post one in-network file per provider NETWORK, updated
quarterly, and the file names its network (name and identifier). To follow one plan's rates across that change we need,
from every TOC we read now, the plan -> network link keyed by the TOC's own date. See docs/plan-network-crosswalk.md.

What already exists and is reused (not duplicated):
  insurers/catalog.py      reads the whole TOC of anthem, cigna, uhc, aetna, hcsc each month and writes
                           R2 bot/catalog/<insurer>/<toc month>/employers.csv.gz (one row per plan: sponsor, plan id,
                           id type, plan name, market, issuer, network_set) + network_sets.csv.gz (network_set -> network
                           keys) + catalog.json (each network's description, state, files and file dates). The month
                           folder is the TOC's own last_updated_on.
  dashboard/build_xwalk_us.py  network-vs-network shared providers (no plans); not what this needs.
This module turns those monthly catalog files into one long table, one row per plan x network x TOC date:
  R2 bot/xwalk/plan_network/<insurer>/<toc month>.parquet
    insurer, toc_month, toc_last_updated_on, plan_id, plan_id_type, plan_market_type, plan_name, plan_sponsor_name,
    issuer_name, network_key, network_description, network_state, network_id, network_name_in_file, source_key
network_key is the catalog's file name without its date, so it stays the same month to month. network_id and
network_name_in_file are blank today; they are filled from the catalog when insurers start writing them (the 2027 files),
so a plan seen under a per-plan file key before and a network id after can be followed by its plan_id.
Existing snapshots are never overwritten (use --force to rebuild one month); nothing is deleted.

Run:  python insurers/plan_network_xwalk.py build [--month YYYY-MM] [--insurers anthem,cigna,...] [--local DIR] [--force]
      python insurers/plan_network_xwalk.py follow --plan-id 123456789 [--local DIR]   (a plan's networks month by month)
--local DIR reads and writes DIR/<same keys> instead of R2 (tests, or catalog --out folders).
"""
import argparse
import csv
import gzip
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSURERS = ["anthem", "cigna", "uhc", "aetna", "hcsc"]
OUT = "bot/xwalk/plan_network/{ins}/{month}.parquet"
COLS = ["insurer", "toc_month", "toc_last_updated_on", "plan_id", "plan_id_type", "plan_market_type", "plan_name",
        "plan_sponsor_name", "issuer_name", "network_key", "network_description", "network_state", "network_id",
        "network_name_in_file", "source_key"]


class Files:
    """R2, or a local folder laid out with the same keys."""
    def __init__(self, local):
        self.local = Path(local) if local else None
        if not self.local:
            sys.path.insert(0, str(HERE.parent / "bot"))
            import store
            self.s3, self.b = store.r2()

    def list(self, prefix):
        if self.local:
            root = self.local / prefix
            return sorted(str(p.relative_to(self.local)) for p in root.rglob("*") if p.is_file()) if root.exists() else []
        return sorted(o["Key"] for pg in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.b, Prefix=prefix)
                      for o in pg.get("Contents", []))

    def get(self, key):
        if self.local:
            p = self.local / key
            return p.read_bytes() if p.exists() else None
        try:
            return self.s3.get_object(Bucket=self.b, Key=key)["Body"].read()
        except Exception:
            return None

    def put_file(self, key, path):
        if self.local:
            dst = self.local / key
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(Path(path).read_bytes())
        else:
            self.s3.upload_file(str(path), self.b, key)

    def exists(self, key):
        return (self.local / key).exists() if self.local else self.get_head(key)

    def get_head(self, key):
        try:
            self.s3.head_object(Bucket=self.b, Key=key)
            return True
        except Exception:
            return False


def months_for(fs, ins):
    return sorted({k.split("/")[3] for k in fs.list(f"bot/catalog/{ins}/") if k.endswith("/employers.csv.gz")})


def snapshot(fs, ins, month):
    """Rows for one insurer's catalog month (generator, so a 26,000-plan TOC never sits in memory twice)."""
    base = f"bot/catalog/{ins}/{month}/"
    cat = json.loads(fs.get(base + "catalog.json") or b"{}")
    toc_date = cat.get("last_updated_on", "")
    nets = {n.get("network"): n for n in cat.get("networks", [])}
    sets = {}
    for r in csv.DictReader(io.TextIOWrapper(gzip.open(io.BytesIO(fs.get(base + "network_sets.csv.gz"))), encoding="utf-8")):
        sets[r["network_set"]] = [x for x in r["networks"].split("|") if x]
    emp = csv.DictReader(io.TextIOWrapper(gzip.open(io.BytesIO(fs.get(base + "employers.csv.gz"))), encoding="utf-8"))
    for p in emp:
        for nk in sets.get(p.get("network_set", ""), []):
            n = nets.get(nk, {})
            yield dict(insurer=ins, toc_month=month, toc_last_updated_on=toc_date, plan_id=p.get("plan_id", ""),
                       plan_id_type=p.get("plan_id_type", ""), plan_market_type=p.get("plan_market_type", ""),
                       plan_name=p.get("plan_name", ""), plan_sponsor_name=p.get("plan_sponsor_name", ""),
                       issuer_name=p.get("issuer_name", ""), network_key=nk, network_description=n.get("description", ""),
                       network_state=n.get("state", ""),
                       # filled once insurers write a network identifier / name (2027 per-network files); blank today
                       network_id=str(n.get("network_id") or n.get("provider_network_id") or ""),
                       network_name_in_file=str(n.get("network_name") or n.get("provider_network_name") or ""),
                       source_key=base + "employers.csv.gz")


def build(fs, insurers, month=None, force=False, work="/tmp/xwalk"):
    import pyarrow as pa
    import pyarrow.parquet as pq
    Path(work).mkdir(parents=True, exist_ok=True)
    done = []
    for ins in insurers:
        for m in ([month] if month else months_for(fs, ins)):
            key = OUT.format(ins=ins, month=m)
            if not force and fs.exists(key):
                continue
            if not fs.get(f"bot/catalog/{ins}/{m}/employers.csv.gz"):
                print(f"  {ins} {m}: no catalog employers file")
                continue
            path = Path(work) / f"{ins}_{m}.parquet"
            schema = pa.schema([(c, pa.string()) for c in COLS])
            n, buf = 0, []
            with pq.ParquetWriter(path, schema, compression="zstd") as w:
                for r in snapshot(fs, ins, m):
                    buf.append(r)
                    if len(buf) >= 200_000:
                        w.write_table(pa.Table.from_pylist(buf, schema)); n += len(buf); buf = []
                if buf:
                    w.write_table(pa.Table.from_pylist(buf, schema)); n += len(buf)
            fs.put_file(key, path)
            path.unlink()
            print(f"  {ins} {m}: {n:,} plan x network rows -> {key}", flush=True)
            done.append((ins, m, n))
    return done


def follow(fs, plan_id, work="/tmp/xwalk"):
    """A plan's networks in every snapshot: [(insurer, toc_month, network_key, network_id, network_description)]."""
    import duckdb
    con = duckdb.connect()
    out = []
    for ins in INSURERS:
        for k in fs.list(f"bot/xwalk/plan_network/{ins}/"):
            p = Path(work) / "f.parquet"
            Path(work).mkdir(parents=True, exist_ok=True)
            p.write_bytes(fs.get(k))
            out += con.execute(f"""select insurer, toc_month, network_key, network_id, network_description from read_parquet('{p}')
                                   where plan_id = ? order by network_key""", [plan_id]).fetchall()
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "follow"])
    ap.add_argument("--month", default="")
    ap.add_argument("--insurers", default=",".join(INSURERS))
    ap.add_argument("--plan-id", default="")
    ap.add_argument("--local", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    fs = Files(a.local)
    if a.cmd == "build":
        done = build(fs, [i for i in a.insurers.split(",") if i], a.month or None, a.force)
        print(f"{len(done)} snapshot(s) written")
    else:
        for r in follow(fs, a.plan_id):
            print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
