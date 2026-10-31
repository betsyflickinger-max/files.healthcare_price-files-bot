"""Proof a provider actually does a procedure: Medicare and Medicaid volume counts for every state we cover (card #2).

Betsy OK'd Texas Oct 30, 2026 and every state Oct 31, 2026 ("reuse the files already saved, no new download").

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

Every state we cover = every state in the provider lists the bot already keeps (storage data/scope/*_npis_all.parquet, NPPES
practice state). Medicare rows carry the state CMS lists for the provider; Medicaid rows (no state in the HHS file) take the
practice state of the NPI from those provider lists.

Storage outputs:
  raw/utilization/<source>/<label>/<sha12>_<file>.zst      originals (parquet saved as-is)
  data/utilization/<data_year>/by_state/evidence_<st>.parquet  one row per provider x code/group x evidence_source (counts only)
  data/utilization/<data_year>/by_state/npi_tax_<st>.parquet   npi -> primary taxonomy + credential (anesthesia check in proof.py)
  data/utilization/<data_year>/evidence_tx.parquet          the first (Oct 30) Texas table: kept as is, never rewritten here
  data/utilization/<data_year>/code_to_apc.parquet          HCPCS -> APC map used
  bot/utilization/manifest.csv                              one row per original saved (url, sha256, bytes, checked_on)
Repo output: reports/utilization/<data_year>/summary.md, sources.json

Run: python utilization/build_evidence.py [--work /mnt/u]            reuse the originals already saved in raw/utilization/
     python utilization/build_evidence.py --fresh [--work /mnt/u]    download the newest CMS/HHS versions first (yearly run)
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


def saved_originals(c):
    """source -> newest manifest row (the original already saved in raw/utilization/)."""
    rows = list(csv.DictReader(io.StringIO(c.get_object(Bucket=B, Key="bot/utilization/manifest.csv")["Body"].read().decode())))
    out = {}
    for r in sorted(rows, key=lambda r: (r["label"], r["checked_on"])):
        out[r["source"]] = r
    missing = set(CMS_TITLES) | {"medicaid_professional"}
    missing -= set(out)
    if missing:
        raise SystemExit(f"no saved original for {sorted(missing)}; run with --fresh")
    return out


def from_storage(c, r, W):
    """Copy a saved original from storage to the work folder (unpacking .zst); check it is the file the manifest names."""
    key = r["key"]
    p = W / key.rsplit("/", 1)[-1]
    c.download_file(B, key, str(p))
    if key.endswith(".zst"):
        q = p.with_suffix("")
        with open(p, "rb") as fi, open(q, "wb") as fo:
            zstandard.ZstdDecompressor().copy_stream(fi, fo)
        p.unlink()
        p = q
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    if h.hexdigest() != r["sha256"]:
        raise SystemExit(f"{key}: fingerprint differs from the manifest; stopping")
    return p


def load_scope(c, con, W):
    """npi -> practice state (+ taxonomy, credential) from every provider list in data/scope/; returns the covered states."""
    keys = [o["Key"] for pg in c.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="data/scope/")
            for o in pg.get("Contents", []) if o["Key"].endswith("_npis_all.parquet")]
    parts = []
    for k in keys:
        name = k.rsplit("/", 1)[-1]
        label = name[:-len("_npis_all.parquet")]
        p = W / f"scope_{name}"
        c.download_file(B, k, str(p))
        cols = [x[0] for x in con.execute(f"describe select * from read_parquet('{p}')").fetchall()]
        one = label.upper() if len(label) == 2 else {"nyhf": "NY", "skipil": "IL"}.get(label)
        if "state" in cols:
            st = f"coalesce(nullif(upper(state), ''), {repr(one) if one else 'null'})"
        elif one:
            st = repr(one)
        else:
            print(f"  {k}: no state column and not a one-state list; skipped", flush=True)
            continue
        tax = "taxonomy_1" if "taxonomy_1" in cols else "null"
        cred = "credential" if "credential" in cols else "null"
        parts.append(f"select npi::varchar npi, {st} state, {tax}::varchar taxonomy_1, {cred}::varchar credential from read_parquet('{p}')")
    con.execute("create or replace table npi_st as select npi, state, any_value(taxonomy_1) taxonomy_1, any_value(credential) credential "
                f"from ({' union all '.join(parts)}) where state is not null and npi is not null group by npi, state")
    covered = [r[0] for r in con.execute("select distinct state from npi_st where length(state) = 2 order by 1").fetchall()]
    con.execute("create or replace table covered as select unnest(?::varchar[]) st", [covered])
    print(f"provider lists: {len(keys)} files, {len(covered)} states: {', '.join(covered)}", flush=True)
    return covered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/utilization")
    ap.add_argument("--fresh", action="store_true", help="download the newest versions instead of reusing saved originals")
    a = ap.parse_args()
    W = Path(a.work)
    W.mkdir(parents=True, exist_ok=True)
    c = s3()
    con = duckdb.connect(str(W / "u.duckdb"))
    con.execute("set memory_limit='5GB'; set preserve_insertion_order=false")
    covered = load_scope(c, con, W)   # tables npi_st (npi, state, taxonomy_1, credential) and covered (st)
    man, meta = [], {}
    saved = {} if a.fresh else saved_originals(c)
    cat = requests.get(CMS_CATALOG, timeout=300).json() if a.fresh else None

    # ---- CMS files: the saved original (or a fresh download), every state, counts only ----
    for src, title in CMS_TITLES.items():
        if a.fresh:
            t, url = newest_cms(cat, title)
            label = t.split(" : ")[-1]
            p = W / url.rsplit("/", 1)[-1]
            sha, n = download(url, p)
            archive(c, src, label, url, p, sha, n, man)
        else:
            r = saved[src]
            t, url, label, n = f"{title} : {r['label']}", r["url"], r["label"], int(r["bytes"])
            p = from_storage(c, r, W)
        meta[src] = dict(title=t, url=url, label=label, bytes=n)
        q = f"read_csv('{p}', header=true, all_varchar=true, quote='\"', ignore_errors=true)"
        if src == "medicare_physician":
            con.execute(f"""create or replace table phy as select Rndrng_NPI npi, HCPCS_Cd code, any_value(HCPCS_Desc) code_name,
                              sum(try_cast(Tot_Srvcs as double))::bigint services, sum(try_cast(Tot_Benes as bigint)) patients,
                              string_agg(distinct Place_Of_Srvc, '') places,
                              Rndrng_Prvdr_State_Abrvtn state
                            from {q} where Rndrng_Prvdr_State_Abrvtn in (select st from covered) group by all""")
        elif src == "medicare_outpatient":
            con.execute(f"""create or replace table opd as select Rndrng_Prvdr_CCN ccn, any_value(Rndrng_Prvdr_Org_Name) org, APC_Cd apc,
                              any_value(APC_Desc) apc_name, sum(try_cast(CAPC_Srvcs as bigint)) services, sum(try_cast(Bene_Cnt as bigint)) patients,
                              Rndrng_Prvdr_State_Abrvtn state
                            from {q} where Rndrng_Prvdr_State_Abrvtn in (select st from covered) group by all""")
        elif src == "medicare_inpatient":
            con.execute(f"""create or replace table ipd as select Rndrng_Prvdr_CCN ccn, any_value(Rndrng_Prvdr_Org_Name) org, DRG_Cd drg,
                              any_value(DRG_Desc) drg_name, sum(try_cast(Tot_Dschrgs as bigint)) discharges,
                              Rndrng_Prvdr_State_Abrvtn state
                            from {q} where Rndrng_Prvdr_State_Abrvtn in (select st from covered) group by all""")
        else:
            con.execute(f"""create or replace table enr as select distinct CCN ccn, NPI npi, "ORGANIZATION NAME" org
                            from {q} where CCN <> '' and NPI <> ''""")
        p.unlink()   # temporary copy only; the original is kept in storage

    # ---- Medicaid (HHS): the saved original (or a fresh download); NPIs in the states we cover, by practice state ----
    if a.fresh:
        mu = medicaid_url()
        mp = W / "medicaid-provider-spending.parquet"
        sha, n = download(mu, mp)
        mlabel = (re.search(r"/(\d{4}-\d{2}-\d{2})/", mu) or [None, "current"])[1]
        archive(c, "medicaid_professional", mlabel, mu, mp, sha, n, man)
    else:
        r = saved["medicaid_professional"]
        mu, mlabel, n = r["url"], r["label"], int(r["bytes"])
        mp = from_storage(c, r, W)
    meta["medicaid_professional"] = dict(title="Medicaid Provider Spending by HCPCS", url=mu, label=mlabel, bytes=n, page=MEDICAID_PAGE)
    yrs = ",".join(f"'{y}'" for y in MEDICAID_YEARS)
    con.execute(f"""create or replace table mcd as
        select m.npi, m.code, s.state, sum(m.lines)::bigint claim_lines, max(m.pts) most_patients_in_a_month,
               min(m.mo) first_month, max(m.mo) last_month
        from (select coalesce(nullif(SERVICING_PROVIDER_NPI_NUM, ''), BILLING_PROVIDER_NPI_NUM) npi, HCPCS_CODE code,
                     TOTAL_CLAIM_LINES lines, TOTAL_PATIENTS pts, CLAIM_FROM_MONTH mo
              from read_parquet('{mp}') where left(CLAIM_FROM_MONTH, 4) in ({yrs})) m
        join npi_st s on s.npi = m.npi
        group by m.npi, m.code, s.state""")
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
               '{meta['medicare_physician']['url']}' file_url, '{TODAY}' checked_on, state from phy
        union all
        select e.npi, o.ccn, 'hospital', 'medicare_outpatient', 'apc', ltrim(o.apc, '0'), o.apc_name, o.services, 'services', o.patients, null,
               '{dy['medicare_outpatient']}', '{meta['medicare_outpatient']['url']}', '{TODAY}', o.state
        from opd o left join enr e using (ccn)
        union all
        select e.npi, i.ccn, 'hospital', 'medicare_inpatient', 'drg', i.drg, i.drg_name, i.discharges, 'discharges', null, null,
               '{dy['medicare_inpatient']}', '{meta['medicare_inpatient']['url']}', '{TODAY}', i.state
        from ipd i left join enr e using (ccn)
        union all
        select npi, null, 'clinician_or_group', 'medicaid_professional', 'hcpcs', code, null, claim_lines, 'claim lines',
               most_patients_in_a_month, null, '{'-'.join(MEDICAID_YEARS)}', '{mu}', '{TODAY}', state from mcd""")
    year = dy["medicare_physician"]
    pre = f"data/utilization/{year}/by_state/"
    for st in covered:
        out = W / f"evidence_{st.lower()}.parquet"
        con.execute(f"copy (select * from ev where state = '{st}') to '{out}' (format parquet, compression zstd)")
        c.upload_file(str(out), B, pre + out.name)
        out.unlink()
        tx = W / f"npi_tax_{st.lower()}.parquet"
        con.execute(f"""copy (select npi, any_value(taxonomy_1) taxonomy_1, any_value(credential) credential from npi_st
                         where state = '{st}' group by npi) to '{tx}' (format parquet, compression zstd)""")
        c.upload_file(str(tx), B, pre + tx.name)
        tx.unlink()
    con.execute(f"copy c2a to '{W / 'c2a.parquet'}' (format parquet)")
    c.upload_file(str(W / "c2a.parquet"), B, f"data/utilization/{year}/code_to_apc.parquet")
    if man:
        save_manifest(c, man)

    # ---- summary for review ----
    q = lambda s: con.execute(s).fetchall()
    by_src = q("select evidence_source, count(*), count(distinct coalesce(npi, ccn)), sum(volume) from ev where state = 'TX' group by 1 order by 1")
    by_st = q("""select state, count(*) filter (where evidence_source = 'medicare_physician'),
                        count(*) filter (where evidence_source = 'medicare_outpatient'),
                        count(*) filter (where evidence_source = 'medicare_inpatient'),
                        count(*) filter (where evidence_source = 'medicaid_professional'),
                        count(distinct coalesce(npi, ccn)) from ev group by 1 order by 1""")
    no_npi = q("select state, count(distinct ccn) from ev where provider_kind = 'hospital' and npi is null group by 1 order by 2 desc limit 10")
    L = [f"# Proof a provider does the procedure: every state we cover, data year {year}", "",
         f"Built {TODAY} by utilization/build_evidence.py (card #2). Counts only; used to confirm, never to exclude or rank by size.",
         "Originals " + ("downloaded fresh" if a.fresh else "reused from storage (raw/utilization/, no new download)") + ".", "",
         "## Files used (originals saved in storage, raw/utilization/)", "", "| Source | Version | Size | Link |", "|---|---|---|---|"]
    L += [f"| {s} | {m['label']} | {m['bytes'] / 1e6:,.0f} MB | {m['url']} |" for s, m in meta.items()]
    L += ["", f"Medicaid years kept: {', '.join(MEDICAID_YEARS)} (2024 is preliminary). Medicaid rows are placed by the NPI's practice state.",
          f"{apc_note}.", "", f"States covered ({len(covered)}): {', '.join(covered)}", "",
          "## Texas check (should match the Oct 30 Texas-only build: 666,881 / 9,614 / 9,955 / 442,625 rows)", "",
          "| Source | Rows | Providers | Total count |", "|---|---|---|---|"]
    L += [f"| {s} | {r:,} | {p:,} | {t:,} |" for s, r, p, t in by_src]
    L += ["", "## Rows by state", "", "| State | Medicare clinician | Medicare hospital outpatient | Medicare hospital stay | Medicaid | Providers |",
          "|---|---|---|---|---|---|"]
    L += [f"| {s} | {a_:,} | {b_:,} | {c_:,} | {d_:,} | {e_:,} |" for s, a_, b_, c_, d_, e_ in by_st]
    L += ["", "Hospitals with a Medicare record but no NPI in CMS Hospital Enrollments (matched by CCN only), top 10 states: "
          + (", ".join(f"{s} {n}" for s, n in no_npi) or "none"), ""]
    rp = ROOT / "reports" / "utilization" / year
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "summary_all_states.md").write_text("\n".join(L))   # the Oct 30 Texas summary.md is kept as is
    (rp / "sources_all_states.json").write_text(json.dumps(meta, indent=1))
    print("\n".join(L))
    shutil.rmtree(W, ignore_errors=True)


if __name__ == "__main__":
    main()
