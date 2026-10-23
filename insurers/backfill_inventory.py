"""Inventory + contract end dates for insurer tables already in R2 (read before Oct 13, 2026). No re-downloading:
DuckDB reads only the columns it needs straight from R2. Resumable: a table whose inventory and end-date table
already exist this month is skipped, and the run stops cleanly before its time budget so the next run continues.

Writes, per table (same places as new reads):
  bot/insurers/census/<yyyy-mm>/<scope>/<table>.json
  <out>/ends/<table>.parquet
Run: python insurers/backfill_inventory.py --scope dfw|tx|s7|nc|ct|il|n5 [--minutes 320] [--limit N]
"""
import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import boto3
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))
import inventory  # noqa: E402

OUTS = {"dfw": "data/full/", "tx": "data/tx/", "s7": "data/s7/", "nc": "data/nc/", "ct": "data/ct/", "il": "data/il/", "n5": "data/n5/", "ar": "data/ar/", "b1": "data/b1/", "la": "data/la/", "b4": "data/b4/", "az": "data/az/"}
E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"] or "upfrontdfwdata"
MONTH = date.today().strftime("%Y-%m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", required=True, choices=sorted(OUTS))
    ap.add_argument("--minutes", type=float, default=320)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    t0, out = time.time(), OUTS[a.scope]
    s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")

    def keys(prefix):
        got = {}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=prefix):
            for o in page.get("Contents", []):
                got[o["Key"]] = o["Size"]
        return got

    tables = {k.rsplit("/", 1)[1][:-8]: n for k, n in keys(f"{out}rates/").items() if k.endswith(".parquet")}
    def current(k):  # an inventory from an older version of inventory.py is redone
        try:
            return json.loads(s3.get_object(Bucket=B, Key=k)["Body"].read()).get("census_version", 1) >= inventory.VERSION
        except Exception:
            return False
    done_c = {k.rsplit("/", 1)[1][:-5] for k in keys(f"bot/insurers/census/{MONTH}/{out.strip('/').replace('/', '_')}/") if current(k)}
    done_e = {k.rsplit("/", 1)[1][:-8] for k in keys(f"{out}ends/")}
    todo = sorted((n, t) for t, n in tables.items() if not (t in done_c and t in done_e))
    print(f"{a.scope}: {len(tables)} tables, {len(tables) - len(todo)} already done, {len(todo)} to do "
          f"({sum(n for n, _ in todo) / 1e9:.1f} GB, smallest first)", flush=True)
    if a.limit:
        todo = todo[:a.limit]

    con = duckdb.connect()
    tmp = Path("/tmp/duck"); tmp.mkdir(exist_ok=True)
    con.execute(f"set temp_directory='{tmp}'; set preserve_insertion_order=false; set memory_limit='5GB'")
    con.execute(f"""create secret r2 (type r2, key_id '{E["R2_ACCESS_KEY_ID"]}', secret '{E["R2_SECRET_ACCESS_KEY"]}',
                    account_id '{E["R2_ACCOUNT_ID"]}')""")
    ok = failed = 0
    for size, tab in todo:
        if (time.time() - t0) / 60 > a.minutes:
            print(f"time budget reached; {len(todo) - ok - failed} tables left for the next run", flush=True)
            break
        t1 = time.time()
        t = f"read_parquet('r2://{B}/{out}rates/{tab}.parquet')"
        try:
            meta = con.execute(f"select any_value(reporting_entity_name), any_value(last_updated_on), any_value(file_label), "
                               f"any_value(source_file), any_value(source_url) from (select * from {t} limit 1)").fetchone()
            try:
                mem = con.execute(f"select count(*), count(distinct npi) from read_parquet('r2://{B}/{out}membership/{tab}.parquet')").fetchone()
            except Exception:
                mem = (None, None)
            base = {"source_file": meta[3] or tab, "source_url": meta[4] or "", "network": meta[2] or "", "checked_on": date.today().isoformat(),
                    "header": {"reporting_entity_name": meta[0] or "", "last_updated_on": meta[1] or ""},
                    "roster_rows_in_scope": mem[0], "roster_npis_in_scope": mem[1], "inventory_from": "existing table (backfill)"}
            cen = inventory.census(con, t, base)
            cen.update(inventory.roster(con, f"read_parquet('r2://{B}/{out}membership/{tab}.parquet')"))
            s3.put_object(Bucket=B, Key=f"bot/insurers/census/{MONTH}/{out.strip('/').replace('/', '_')}/{tab}.json",
                          Body=json.dumps(cen, indent=1, default=str).encode())
            local = tmp / f"{tab}.ends.parquet"
            if inventory.contract_ends(con, t, local):
                s3.upload_file(str(local), B, f"{out}ends/{tab}.parquet")
                local.unlink()
            ok += 1
            print(f"  [{ok + failed}/{len(todo)}] {tab[:90]}: {cen.get('rows', 0):,} rows, {size / 1e9:.2f} GB, {time.time() - t1:.0f} s", flush=True)
        except Exception as e:
            failed += 1
            print(f"  ! {tab[:90]}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    print(f"{a.scope}: {ok} done, {failed} failed this run", flush=True)


if __name__ == "__main__":
    main()
