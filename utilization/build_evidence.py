"""Proof a provider actually does a procedure: Medicare and Medicaid volume counts for Texas (card #2, Betsy OK'd Oct 30, 2026).

Used only to confirm ("yes, they do this"), never to exclude, never to rank by size, never as a price (Betsy, Oct 30):
  * Medicare is mostly people 65+; Medicaid's public file is professional bills only, with managed-care gaps. A provider with
    no record here still shows; it just needs other proof. Payment columns in these files are averages or unreliable and are
    never read into the output.
  * CMS hides Medicare rows under 11 patients/services; HHS hides Medicaid rows under 12 claims.
  * Medicare's hospital outpatient file counts only "comprehensive" procedure groups (most surgeries: knee scope, cataract,
    laparoscopic gallbladder, carpal tunnel). Smaller ones such as colonoscopy have no hospital volume record.

Sources (newest version found in each catalog at run time; every original is saved untouched, nothing replaced or deleted):
  medicare_physician    CMS Medicare Physician & Other Practitioners - by Provider and Service (NPI x HCPCS x place of service)
  medicare_outpatient   CMS Medicare Outpatient Hospitals - by Provider and Service (CCN x APC procedure group)
  medicare_inpatient    CMS Medicare Inpatient Hospitals - by Provider and Service (CCN x DRG hospital-stay group)
  medicaid_professional HHS Medicaid Provider Spending by HCPCS (billing + servicing NPI x HCPCS x month)
  hospital_enrollments  CMS Hospital Enrollments (CCN -> NPI)
  code_to_apc           HCPCS -> APC from the site's Medicare benchmark file (storage reference/site/med_all.json, OPPS Addendum B)

Storage outputs:
  raw/utilization/<source>/<label>/<sha12>_<file>.zst   originals (parquet saved as-is)
  data/utilization/<data_year>/evidence_tx.parquet       one row per provider x code/group x evidence_source (counts only)
  data/utilization/<data_year>/code_to_apc.parquet       HCPCS -> APC map used
  bot/utilization/manifest.csv                           one row per original saved (url, sha256, bytes, checked_on)
Repo output: reports/utilization/<data_year>/summary.md, sources.json

Run: python utilization/build_evidence.py [--work /mnt/u]
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
from pathlib import Path

import boto3
import duckdb
import requests
import zstandard

ROOT = Path(__file__).resolve().parent.parent
E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"] or "upfrontdfwdata"
TODAY = dt.date.today().isoformat()
CMS_CATALOG = "https://data.cms.gov/data.json"
CMS_TITLES = {
    "medicare_physician": "Medicare Physician & Other Practitioners - by Provider and Service",
    "medicare_outpatient": "Medicare Outpatient Hospitals - by Provider and Service",
    "medicare_inpatient": "Medicare Inpatient Hospitals - by Provider and Service",
    "hospital_enrollments": "Hospital Enrollments",
}
MEDICAID_PAGE = "https://opendata.hhs.gov/datasets/medicaid-provider-spending/"
MEDICAID_FALLBACK = ("https://stopendataprod.blob.core.windows.net/datasets/medicaid-provider-spending/2026-02-09/dataset/"
                     "medicaid-provider-spending.parquet")
MEDICAID_YEARS = ("2023", "2024")   # 2024 is marked preliminary (Nov-Dec look incomplete); 2023 is the last full year
APC_KEY = "reference/site/med_all.json"   # site Medicare benchmarks; opps = [rate, status, APC]


def s3():
    return boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                        aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"],
                        region_name=os.environ.get("STORAGE_REGION") or "auto")


def exists(c, key):
    try:
        c.head_object(Bucket=B, Key=key)
        return True
    except Exception:
        return False


def newest_cms(cat, key):
    """(title, csv url) of the newest version of a CMS dataset, by the date in its title."""
    c = [(x.get("title", ""), x["downloadURL"]) for d in cat["dataset"] for x in d.get("distribution", [])
         if x.get("title", "").startswith(key + " :") and str(x.get("downloadURL", "")).lower().endswith(".csv")]
    if not c:
        raise SystemExit(f"CMS catalog has no CSV for {key}")
    return max(c)


def medicaid_url():
    try:
        t = requests.get(MEDICAID_PAGE, timeout=60).text
        u = sorted(set(re.findall(r"https://[^\"'\\ <>]+medicaid-provider-spending\.parquet", t)))
        return u[-1] if u else MEDICAID_FALLBACK
    except Exception:
        return MEDICAID_FALLBACK


def download(url, path):
    h, n = hashlib.sha256(), 0
    with requests.get(url, stream=True, timeout=600) as r, open(path, "wb") as f:
        r.raise_for_status()
        for b in r.iter_content(8 << 20):
            f.write(b)
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def archive(c, src, label, url, path, sha, n, manifest):
    """Save the original once (zstd unless already compressed). Never overwrites: the key carries the file's fingerprint."""
    name = url.rsplit("/", 1)[-1]
    packed = name.endswith((".parquet", ".zip", ".gz", ".zst"))
    key = f"raw/utilization/{src}/{label}/{sha[:12]}_{name}" + ("" if packed else ".zst")
    if not exists(c, key):
        if packed:
            c.upload_file(str(path), B, key)
        else:
            z = path.with_suffix(path.suffix + ".zst")
            with open(path, "rb") as fi, open(z, "wb") as fo:
                zstandard.ZstdCompressor(level=10, threads=-1).copy_stream(fi, fo)
            c.upload_file(str(z), B, key)
            z.unlink()
    manifest.append(dict(source=src, label=label, url=url, key=key, sha256=sha, bytes=n, checked_on=TODAY))
    return key


def save_manifest(c, rows):
    key = "bot/utilization/manifest.csv"
    old = []
    if exists(c, key):
        old = list(csv.DictReader(io.StringIO(c.get_object(Bucket=B, Key=key)["Body"].read().decode())))
    seen = {(r["key"], r["checked_on"]) for r in old}
    allr = old + [r for r in rows if (r["key"], r["checked_on"]) not in seen]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(allr)
    c.put_object(Bucket=B, Key=key, Body=buf.getvalue().encode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/utilization")
    a = ap.parse_args()
    W = Path(a.work)
    W.mkdir(parents=True, exist_ok=True)
    c = s3()
    con = duckdb.connect(str(W / "u.duckdb"))
    con.execute("set memory_limit='5GB'; set preserve_insertion_order=false")
    cat = requests.get(CMS_CATALOG, timeout=300).json()
    man, meta = [], {}

    # ---- CMS files: download, save original, keep Texas rows (counts only) ----
    for src, title in CMS_TITLES.items():
        t, url = newest_cms(cat, title)
        label = t.split(" : ")[-1]
        p = W / url.rsplit("/", 1)[-1]
        sha, n = download(url, p)
        archive(c, src, label, url, p, sha, n, man)
        meta[src] = dict(title=t, url=url, label=label, bytes=n)
        q = f"read_csv('{p}', header=true, all_varchar=true, quote='\"', ignore_errors=true)"
        if src == "medicare_physician":
            con.execute(f"""create or replace table phy as select Rndrng_NPI npi, HCPCS_Cd code, any_value(HCPCS_Desc) code_name,
                              sum(try_cast(Tot_Srvcs as double))::bigint services, sum(try_cast(Tot_Benes as bigint)) patients,
                              string_agg(distinct Place_Of_Srvc, '') places
                            from {q} where Rndrng_Prvdr_State_Abrvtn = 'TX' group by all""")
        elif src == "medicare_outpatient":
            con.execute(f"""create or replace table opd as select Rndrng_Prvdr_CCN ccn, any_value(Rndrng_Prvdr_Org_Name) org, APC_Cd apc,
                              any_value(APC_Desc) apc_name, sum(try_cast(CAPC_Srvcs as bigint)) services, sum(try_cast(Bene_Cnt as bigint)) patients
                            from {q} where Rndrng_Prvdr_State_Abrvtn = 'TX' group by all""")
        elif src == "medicare_inpatient":
            con.execute(f"""create or replace table ipd as select Rndrng_Prvdr_CCN ccn, any_value(Rndrng_Prvdr_Org_Name) org, DRG_Cd drg,
                              any_value(DRG_Desc) drg_name, sum(try_cast(Tot_Dschrgs as bigint)) discharges
                            from {q} where Rndrng_Prvdr_State_Abrvtn = 'TX' group by all""")
        else:
            con.execute(f"""create or replace table enr as select distinct CCN ccn, NPI npi, "ORGANIZATION NAME" org
                            from {q} where STATE = 'TX' and CCN <> '' and NPI <> ''""")
        p.unlink()   # temporary download only; the original is kept in storage

    # ---- Medicaid (HHS): save the original, keep Texas NPIs ----
    mu = medicaid_url()
    mp = W / "medicaid-provider-spending.parquet"
    sha, n = download(mu, mp)
    mlabel = (re.search(r"/(\d{4}-\d{2}-\d{2})/", mu) or [None, "current"])[1]
    archive(c, "medicaid_professional", mlabel, mu, mp, sha, n, man)
    meta["medicaid_professional"] = dict(title="Medicaid Provider Spending by HCPCS", url=mu, label=mlabel, bytes=n, page=MEDICAID_PAGE)
    c.download_file(B, "data/scope/tx_npis_all.parquet", str(W / "tx_npis.parquet"))
    con.execute(f"create or replace table txn as select distinct npi::varchar npi from read_parquet('{W / 'tx_npis.parquet'}')")
    yrs = ",".join(f"'{y}'" for y in MEDICAID_YEARS)
    con.execute(f"""create or replace table mcd as
        select coalesce(nullif(SERVICING_PROVIDER_NPI_NUM, ''), BILLING_PROVIDER_NPI_NUM) npi, HCPCS_CODE code,
               sum(TOTAL_CLAIM_LINES)::bigint claim_lines, max(TOTAL_PATIENTS) most_patients_in_a_month,
               min(CLAIM_FROM_MONTH) first_month, max(CLAIM_FROM_MONTH) last_month
        from read_parquet('{mp}') m
        where left(CLAIM_FROM_MONTH, 4) in ({yrs})
          and coalesce(nullif(SERVICING_PROVIDER_NPI_NUM, ''), BILLING_PROVIDER_NPI_NUM) in (select npi from txn)
        group by all""")
    mp.unlink()

    # ---- HCPCS -> APC: the site's Medicare benchmark file (site/build_med_all.py: CMS OPPS Addendum B, July 2026) ----
    con.execute("create or replace table c2a (code varchar, apc varchar)")
    apc_note = f"no {APC_KEY} in storage; hospital outpatient proof can't be tied to codes yet"
    if exists(c, APC_KEY):
        med = json.loads(c.get_object(Bucket=B, Key=APC_KEY)["Body"].read())
        med = med.get("med", med)   # build_med_all.py writes {"med": {code: {...}}, "hcpcs_names": {...}}
        pairs = [(k, str(v["opps"][2]).strip().lstrip("0")) for k, v in med.items()
                 if isinstance(v, dict) and isinstance(v.get("opps"), list) and len(v["opps"]) > 2 and str(v["opps"][2]).strip()]
        if pairs:
            con.executemany("insert into c2a values (?, ?)", pairs)
        apc_note = f"HCPCS -> APC for {len(pairs):,} codes from {APC_KEY} (CMS OPPS Addendum B, July 2026; 2024 volume matched to 2026 groups)"

    # ---- one evidence table ----
    dy = {s: m["label"][:4] for s, m in meta.items()}
    con.execute(f"""create or replace table ev as
        select npi, null::varchar ccn, 'clinician' provider_kind, 'medicare_physician' evidence_source, 'hcpcs' code_level, code, code_name group_name,
               services volume, 'services' unit, patients, places place_of_service, '{dy['medicare_physician']}' data_year,
               '{meta['medicare_physician']['url']}' file_url, '{TODAY}' checked_on from phy
        union all
        select e.npi, o.ccn, 'hospital', 'medicare_outpatient', 'apc', ltrim(o.apc, '0'), o.apc_name, o.services, 'services', o.patients, null,
               '{dy['medicare_outpatient']}', '{meta['medicare_outpatient']['url']}', '{TODAY}'
        from opd o left join enr e using (ccn)
        union all
        select e.npi, i.ccn, 'hospital', 'medicare_inpatient', 'drg', i.drg, i.drg_name, i.discharges, 'discharges', null, null,
               '{dy['medicare_inpatient']}', '{meta['medicare_inpatient']['url']}', '{TODAY}'
        from ipd i left join enr e using (ccn)
        union all
        select npi, null, 'clinician_or_group', 'medicaid_professional', 'hcpcs', code, null, claim_lines, 'claim lines',
               most_patients_in_a_month, null, '{'-'.join(MEDICAID_YEARS)}', '{mu}', '{TODAY}' from mcd""")
    year = dy["medicare_physician"]
    out = W / "evidence_tx.parquet"
    con.execute(f"copy ev to '{out}' (format parquet, compression zstd)")
    c.upload_file(str(out), B, f"data/utilization/{year}/evidence_tx.parquet")
    con.execute(f"copy c2a to '{W / 'c2a.parquet'}' (format parquet)")
    c.upload_file(str(W / "c2a.parquet"), B, f"data/utilization/{year}/code_to_apc.parquet")
    save_manifest(c, man)

    # ---- summary for review ----
    q = lambda s: con.execute(s).fetchall()
    by_src = q("select evidence_source, count(*), count(distinct coalesce(npi, ccn)), sum(volume) from ev group by 1 order by 1")
    no_npi = q("select evidence_source, count(distinct ccn) from ev where provider_kind = 'hospital' and npi is null group by 1")
    ob = q("""select evidence_source, count(distinct npi) from ev where code in ('59400','59409','59410','59510','59514','59515') group by 1""")
    pk = q("""select c2a.code, ev.code apc, any_value(ev.group_name), count(distinct ev.ccn), sum(ev.volume)
              from c2a join ev on ev.evidence_source = 'medicare_outpatient' and ev.code = c2a.apc
              where c2a.code in ('45378','29881','66984','64721','47562') group by all order by 1""")
    L = [f"# Proof a provider does the procedure: Texas, data year {year}", "",
         f"Built {TODAY} by utilization/build_evidence.py (card #2). Counts only; used to confirm, never to exclude or rank by size.", "",
         "## Files used (originals saved in storage, raw/utilization/)", "", "| Source | Version | Size | Link |", "|---|---|---|---|"]
    L += [f"| {s} | {m['label']} | {m['bytes'] / 1e6:,.0f} MB | {m['url']} |" for s, m in meta.items()]
    L += ["", f"Medicaid years kept: {', '.join(MEDICAID_YEARS)} (2024 is preliminary).", f"{apc_note}.", "",
          "## Texas rows", "", "| Source | Rows | Providers | Total count |", "|---|---|---|---|"]
    L += [f"| {s} | {r:,} | {p:,} | {t:,} |" for s, r, p, t in by_src]
    L += ["", "Hospitals with a Medicare record but no NPI in CMS Hospital Enrollments (matched by CCN only): "
          + (", ".join(f"{s} {n}" for s, n in no_npi) or "none"),
          "", "Texas clinicians with delivery codes (59400-59515), by source: " + (", ".join(f"{s} {n:,}" for s, n in ob) or "none"),
          "", "## Packaged procedures: Texas hospitals with Medicare outpatient volume in the code's procedure group", "",
          "| Code | Group (APC) | Group name | Hospitals | Services |", "|---|---|---|---|---|"]
    L += [f"| {a_} | {b_} | {c_} | {d_} | {e_:,} |" for a_, b_, c_, d_, e_ in pk]
    L += ["", "Codes missing from this table have no hospital outpatient volume record (not a comprehensive procedure group).", ""]
    rp = ROOT / "reports" / "utilization" / year
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "summary.md").write_text("\n".join(L))
    (rp / "sources.json").write_text(json.dumps(meta, indent=1))
    print("\n".join(L))
    shutil.rmtree(W, ignore_errors=True)


if __name__ == "__main__":
    main()
