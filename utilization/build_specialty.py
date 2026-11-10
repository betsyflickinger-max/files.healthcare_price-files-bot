"""Who bills each code, by specialty: the reference for rate label d, "specialty mismatch" (Nov 9, 2026, Betsy OK'd).

Insurer files list a rate for many clinician-and-code pairs that will never be billed (an eye doctor with a knee-replacement
rate). This builds, from the Medicare and Medicaid volume tables the bot already keeps (utilization/build_evidence.py, data
year 2024), how often clinicians of each specialty (NPPES primary taxonomy) actually billed each code. A label only: it never
removes, hides or re-ranks a rate, and is never shown as a finding about an insurer or a provider.

Rule (insurers/pipeline/rate_labels.py, label d): a professional (doctor-fee) rate at an individual clinician's NPI whose
specialty has at least MIN_TAX clinicians in these tables, for a code at least MIN_CODE clinicians billed, where at most
MAX_SHARE of that specialty's clinicians billed the code (fewer than 1 in 500). Organizations (entity type 2: hospitals,
groups) are never labeled: one NPI covers many specialties.

Inputs (storage):  data/scope/*_npis_all.parquet                       npi, entity_type, taxonomy_1 (NPPES)
                   data/utilization/<year>/by_state/evidence_*.parquet  npi x code, Medicare physician + Medicaid professional
Outputs (storage): reference/specialty/code_taxonomy.parquet   code, taxonomy_1, billers (pairs with at least one biller)
                   reference/specialty/taxonomy_n.parquet      taxonomy_1, clinicians (with any Medicare/Medicaid record)
                   reference/specialty/code_n.parquet          code, billers (individual clinicians)
                   reference/specialty/npi_taxonomy.parquet    npi, taxonomy_1 (individual clinicians in the provider lists)
                   reference/specialty/meta.json               thresholds, year, counts, built date
Run: python utilization/build_specialty.py [--work /tmp/spec] [--year 2024]
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

import boto3
import duckdb

MIN_TAX, MIN_CODE, MAX_SHARE = 200, 100, 0.002
OUT = "reference/specialty/"
E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"]


def client():
    return boto3.client("s3", endpoint_url=os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                        region_name=os.environ.get("STORAGE_REGION") or "auto")


def keys(c, prefix, suffix):
    return [o["Key"] for pg in c.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=prefix)
            for o in pg.get("Contents", []) if o["Key"].endswith(suffix)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/spec")
    ap.add_argument("--year", default="2024")
    a = ap.parse_args()
    W = Path(a.work)
    W.mkdir(parents=True, exist_ok=True)
    c = client()
    con = duckdb.connect(str(W / "spec.duckdb"))
    con.execute("set preserve_insertion_order = false")

    parts = []
    for k in keys(c, "data/scope/", "_npis_all.parquet"):
        p = W / k.rsplit("/", 1)[-1]
        c.download_file(B, k, str(p))
        cols = {x[0] for x in con.execute(f"describe select * from read_parquet('{p}')").fetchall()}
        if {"npi", "entity_type", "taxonomy_1"} <= cols:
            parts.append(f"select npi::varchar npi, entity_type::varchar et, taxonomy_1::varchar taxonomy_1 from read_parquet('{p}')")
        else:
            print(f"  {k}: lacks entity_type/taxonomy_1; skipped", flush=True)
    con.execute(f"""create table npi_tax as select npi, any_value(taxonomy_1) taxonomy_1
                    from ({' union all '.join(parts)}) where et = '1' and npi is not null and nullif(taxonomy_1, '') is not null
                    group by npi""")

    ev = keys(c, f"data/utilization/{a.year}/by_state/", ".parquet")
    ev = [k for k in ev if k.rsplit("/", 1)[-1].startswith("evidence_")]
    for k in ev:
        c.download_file(B, k, str(W / k.rsplit("/", 1)[-1]))
    con.execute(f"""create table bill as select distinct npi::varchar npi, upper(code::varchar) code
                    from read_parquet('{W}/evidence_*.parquet', union_by_name = true)
                    where evidence_source in ('medicare_physician', 'medicaid_professional') and code_level = 'hcpcs'
                      and npi is not null and code is not null""")
    con.execute("create table b as select bill.npi, code, taxonomy_1 from bill join npi_tax using (npi)")
    con.execute("create table taxonomy_n as select taxonomy_1, count(distinct npi) clinicians from b group by 1")
    con.execute("create table code_n as select code, count(distinct npi) billers from b group by 1")
    con.execute("create table code_taxonomy as select code, taxonomy_1, count(distinct npi) billers from b group by 1, 2")

    for t in ("code_taxonomy", "taxonomy_n", "code_n", "npi_tax"):
        f = W / f"{t}.parquet"
        con.execute(f"copy {t} to '{f}' (format parquet, compression zstd)")
        c.upload_file(str(f), B, OUT + ("npi_taxonomy.parquet" if t == "npi_tax" else f.name))
    n = lambda q: con.execute(q).fetchone()[0]
    meta = dict(built=dt.date.today().isoformat(), data_year=a.year, min_tax=MIN_TAX, min_code=MIN_CODE, max_share=MAX_SHARE,
                evidence_files=len(ev), clinicians_in_lists=n("select count(*) from npi_tax"),
                clinicians_with_records=n("select count(distinct npi) from b"),
                specialties_used=n(f"select count(*) from taxonomy_n where clinicians >= {MIN_TAX}"),
                codes_used=n(f"select count(*) from code_n where billers >= {MIN_CODE}"))
    c.put_object(Bucket=B, Key=OUT + "meta.json", Body=json.dumps(meta, indent=1).encode(), ContentType="application/json")
    print(json.dumps(meta, indent=1), flush=True)


if __name__ == "__main__":
    main()
