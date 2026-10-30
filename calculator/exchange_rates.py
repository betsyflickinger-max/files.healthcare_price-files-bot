"""Add marketplace networks to the Plan Calculator's exchange rate file from the bot's DFW insurer tables.

Oct 30, 2026: the 2027 plans came out with Wellpoint and Molina networks whose rates were never in the exchange rate
file (it was built by hand on Sept 29 from August files). The bot now reads both for DFW (data/full/rates/), so this
takes the current exchange rate file, keeps every row in it as is, and adds the rows of the networks below from the
newest bot table of each source file. Same codes (the calculator's procedures = the codes already in the file) and
DFW facilities (calculator/data/dfw_facilities_npi.csv). Nothing is estimated or averaged; every added row keeps its
source URL and file date.

Run (needs the R2_* or STORAGE_* settings): python calculator/exchange_rates.py [--dry-run]
Writes data/<today>/payer_rates_dfw_exchange_<today>.csv.gz to storage; the Plan Calculator build uses the newest one.
"""
import argparse
import io
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bot"))
import store  # noqa: E402

# network label the calculator matches (calculator/oop.py LINK, third column) -> bot table name pattern (data/full/rates/)
ADD = {
    "Wellpoint Texas Essential (TX_JBLXMED0001)": r"^TX_JBLXMED0001",
    "Molina Marketplace TX": r"^innetwork-G-(GMZ|MPT|QMX)CT\d+",
}
KEEP = ["negotiated_type", "negotiated_rate", "billing_code_type", "billing_code", "billing_class", "service_code",
        "npi", "last_updated_on", "source_url", "expiration_date"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s3, b = store.r2()
    objs = [o for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix="data/")
            for o in pg.get("Contents", []) if "payer_rates_dfw_exchange" in o["Key"]]
    cur = max(objs, key=lambda o: o["LastModified"])["Key"]
    raw = s3.get_object(Bucket=b, Key=cur)["Body"].read()
    old = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, compression="gzip" if cur.endswith(".gz") else None)
    print(f"current file {cur}: {len(old):,} rows; networks:", old.network_name.value_counts().to_dict())
    codes = set(old.billing_code)
    names = old.drop_duplicates("billing_code").set_index("billing_code").plain_name.to_dict()
    fac = pd.read_csv(HERE / "data" / "dfw_facilities_npi.csv", dtype=str).drop_duplicates("npi").set_index("npi")

    tables = [o for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix="data/full/rates/")
              for o in pg.get("Contents", []) if o["Key"].endswith(".parquet")]
    added = []
    for label, pat in ADD.items():
        n_add = len(added)
        newest = {}
        for o in tables:
            name = o["Key"].rsplit("/", 1)[1][:-8]
            m = re.search(pat, name)
            if m and (m.group(0) not in newest or o["LastModified"] > newest[m.group(0)]["LastModified"]):
                newest[m.group(0)] = o
        print(f"{label}: {len(newest)} source files, {sum(o['Size'] for o in newest.values()) / 1e9:.2f} GB")
        for stem, o in sorted(newest.items()):
            import pyarrow.parquet as pq, tempfile
            with tempfile.NamedTemporaryFile(suffix=".parquet") as tf:
                s3.download_file(b, o["Key"], tf.name)   # read only the columns and codes needed (Wellpoint's table is big)
                have = set(pq.read_schema(tf.name).names)
                miss = [c for c in KEEP if c not in have and c != "expiration_date"]
                if miss:
                    print(f"  ! {o['Key']}: missing columns {miss}; skipped"); continue
                pf = pq.ParquetFile(tf.name)
                n_all = pf.metadata.num_rows
                smp = pf.read_row_group(0, columns=["billing_code", "npi"]).to_pandas().head(3) if pf.num_row_groups else None
                t = pd.read_parquet(tf.name, columns=[c for c in KEEP if c in have], filters=[("billing_code", "in", sorted(codes))])
            t["billing_code"] = t.billing_code.astype(str).str.strip()
            t["npi"] = t.npi.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            n_code = len(t)
            n_npi = int(t.npi.isin(fac.index).sum())
            if not n_npi:   # Oct 30: say why a table adds nothing (the first run added no rows and gave no reason)
                print(f"  {stem}: {n_all:,} rows, {n_code:,} with the calculator's codes, {n_npi:,} of those at DFW facilities;"
                      f" sample rows {None if smp is None else smp.values.tolist()}; sample NPIs with codes {t.npi.head(3).tolist()}")
            t = t[t.npi.isin(fac.index)].copy()
            if not len(t):
                continue
            t = t[[c for c in KEEP if c in t.columns]].astype(str)
            t["network_name"] = label
            t["plain_name"] = t.billing_code.map(names)
            t["provider_name"] = t.npi.map(fac["name"])
            t["facility_type"] = t.npi.map(fac["facility_type"])
            t["reporting_entity_name"] = label.split(" ")[0]
            added.append(t)
            print(f"  {stem}: {len(t):,} rows (file date {t.last_updated_on.iloc[0]})")
        if len(added) > n_add:   # replace this network's old rows only when the bot's tables gave new ones
            old = old[old.network_name != label]
        else:
            print(f"  {label}: nothing new; its {int((old.network_name == label).sum()):,} existing rows are kept")
    new = pd.concat([old] + added, ignore_index=True).fillna("")
    for c in old.columns:
        if c not in new.columns:
            new[c] = ""
    print(f"new file: {len(new):,} rows; networks:", new.network_name.value_counts().to_dict())
    key = f"data/{date.today().isoformat()}/payer_rates_dfw_exchange_{date.today().isoformat()}.csv.gz"
    if a.dry_run:
        print("dry run: not saved", key); return
    buf = io.BytesIO()
    new.to_csv(buf, index=False, compression={"method": "gzip"})
    s3.put_object(Bucket=b, Key=key, Body=buf.getvalue())
    print("saved", key, f"({len(buf.getvalue()) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
