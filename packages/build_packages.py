"""Procedure packages: the facility fee and the doctor's fee for one procedure, side by side, from the insurers' own files.

A patient pays the facility AND the doctor (and usually anesthesia). Insurer files price each part separately and
never say which doctor works at which facility, so a package here is:
  facility fee  = that facility's own listed price for the code (billing class institutional)
  doctor's fee  = the lowest, middle and highest fee the same network lists for that code across DFW doctors
                  (billing class professional); every one is a real listed price, nothing averaged
  total         = facility fee + lowest doctor's fee ... facility fee + highest doctor's fee
  anesthesia, pathology: shown separately with their own lowest-highest, never added (anesthesia is billed by time)
Only dollar prices (negotiated, fee schedule, derived), above $0, with no modifier. Each row keeps the source file link
and the file's date. Definitions: packages/packages.csv.

Outputs: R2 data/packages/<yyyy-mm>/dfw.parquet (one row per package x network x facility),
         reports/packages/<yyyy-mm>.md (summary for review; not on the site yet).
Run: python packages/build_packages.py [--rates data/full/rates/] [--npis data/2026-09-29/dfw_npis_all.parquet]
"""
import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import boto3
import duckdb

HERE = Path(__file__).resolve().parent
E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"] or "upfrontdfwdata"
MONTH = date.today().strftime("%Y-%m")
# Medicare "Physician & Other Practitioners - by Provider and Service", data year 2024 (CMS hides rows under 11 patients)
MEDICARE_API = "https://data.cms.gov/data-api/v1/dataset/335e5f35-eca6-482d-87b3-f99883e213e3/data"


def medicare_billers(codes, state="TX"):
    """NPIs that billed Medicare for each code in the state (one API query per code, paged)."""
    out = []
    for c in codes:
        off = 0
        while True:
            q = urllib.parse.urlencode({"filter[HCPCS_Cd]": c, "filter[Rndrng_Prvdr_State_Abrvtn]": state, "size": 5000, "offset": off})
            for attempt in range(4):
                try:
                    rows = json.loads(urllib.request.urlopen(f"{MEDICARE_API}?{q}", timeout=120).read())
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(5 * (attempt + 1))
            out += [(r["Rndrng_NPI"], c, int(float(r.get("Tot_Srvcs") or 0))) for r in rows]
            if len(rows) < 5000:
                break
            off += 5000
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rates", default="data/full/rates/")
    ap.add_argument("--npis", default="data/2026-09-29/dfw_npis_all.parquet")
    ap.add_argument("--area", default="dfw")
    ap.add_argument("--reuse", action="store_true", help="use this month's saved price rows instead of re-reading every table")
    a = ap.parse_args()
    defs = list(csv.DictReader(open(HERE / "packages.csv")))
    codes = sorted({c for d in defs for k in ("codes", "family") for c in d[k].split("|") if c})
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    tables = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=a.rates):
        tables += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".parquet")]
    con = duckdb.connect()
    Path("/tmp/duck").mkdir(exist_ok=True)
    con.execute("set temp_directory='/tmp/duck'; set preserve_insertion_order=false; set memory_limit='10GB'")
    con.execute(f"""create secret r2 (type r2, key_id '{E["R2_ACCESS_KEY_ID"]}', secret '{E["R2_SECRET_ACCESS_KEY"]}', account_id '{E["R2_ACCOUNT_ID"]}')""")
    lst = ", ".join(f"'{c}'" for c in codes)
    raw = f"data/packages/{MONTH}/{a.area}_rows.parquet"   # the matching price rows, saved so a re-run needn't re-read every table
    con.execute("""create table r (billing_code varchar, billing_class varchar, npi varchar, rate double, network varchar, insurer varchar,
                   source_url varchar, file_date varchar)""")
    t0 = time.time()
    if a.reuse:
        try:
            s3.download_file(B, raw, "/tmp/rows.parquet")
            con.execute("insert into r select * from read_parquet('/tmp/rows.parquet')")
            tables = []
            print("reusing saved price rows", flush=True)
        except Exception as e:
            print(f"no saved rows ({e}); reading every table", flush=True)
    for i, k in enumerate(sorted(tables), 1):
        t = f"read_parquet('r2://{B}/{k}')"
        m = f"read_parquet('r2://{B}/{k.replace('/rates/', '/membership/')}')"
        try:  # same network naming as the Price Finder: the roster's network name, else the file's label
            con.execute(f"""insert into r select x.billing_code, lower(x.billing_class), x.npi, try_cast(x.negotiated_rate as double),
                              coalesce(mm.network_name, x.file_label), x.reporting_entity_name, x.source_url, x.last_updated_on
                            from (select * from {t} where billing_code in ({lst})
                                    and lower(negotiated_type) in ('negotiated', 'fee schedule', 'derived')
                                    and coalesce(billing_code_modifier, '') = '' and try_cast(negotiated_rate as double) > 0) x
                            left join (select npi, tin, any_value(network_name) network_name from {m} group by all) mm using (npi, tin)""")
        except Exception as e:
            print(f"  ! {k}: {str(e)[:160]}", flush=True)
        if i % 10 == 0:
            print(f"  {i}/{len(tables)} tables, {con.execute('select count(*) from r').fetchone()[0]:,} rows, {time.time() - t0:.0f} s", flush=True)
    n_rows = con.execute("select count(*) from r").fetchone()[0]
    print(f"{len(tables)} tables read, {n_rows:,} matching price rows, {time.time() - t0:.0f} s", flush=True)
    if tables:
        con.execute("copy r to '/tmp/rows.parquet' (format parquet, compression zstd)")
        s3.upload_file("/tmp/rows.parquet", B, raw)

    s3.download_file(B, a.npis, "/tmp/npis.parquet")
    con.execute("create table d as select * from read_csv(?, header=true, all_varchar=true)", [str(HERE / "packages.csv")])
    con.execute("""create table dc as select package, "name", role, unnest(string_split(codes, '|')) code, billing_class, in_total, note, taxonomy from d""")
    con.execute("""create table fam as select package, role, unnest(string_split(family, '|')) code, billing_class from d""")
    # Evidence the provider really does the procedure:
    #  facilities: lists its own (institutional) price for at least 2 codes in the procedure's family (packages.csv 'family')
    #  clinicians: billed Medicare in Texas for a code in the family (2024 Medicare data)
    con.execute("""create table fac_ev as
                   with need as (select package, least(2, count(*)) k from fam where role = 'facility' group by package),
                        got as (select f.package, r.network, r.npi, count(distinct r.billing_code) n_codes
                                from r join fam f on f.code = r.billing_code and r.billing_class = 'institutional' and f.role = 'facility'
                                group by f.package, r.network, r.npi)
                   select got.* from got join need using (package) where got.n_codes >= need.k""")
    med_codes = sorted({c for d in defs if d["role"] != "facility" for c in d["family"].split("|")})
    try:
        med = medicare_billers(med_codes)
        print(f"Medicare 2024: {len(med):,} Texas clinician-code rows for {len(med_codes)} codes", flush=True)
    except Exception as e:
        med = []
        print(f"! Medicare data unavailable ({e}); doctor fees use every listed specialist this run", flush=True)
    con.execute("create table med (npi varchar, code varchar, services int)")
    if med:
        con.executemany("insert into med values (?, ?, ?)", med)
    con.execute("""create table cl_ev as select distinct f.package, f.role, m.npi from med m join fam f on f.code = m.code and f.role <> 'facility'""")
    # every listed price per package part (one row per provider: if a provider has several prices, its lowest and highest stay visible)
    con.execute("""create table nt as select npi, any_value("name") as fname, any_value(city) as city, any_value(entity_type) as et,
                   any_value(taxonomy_1) as tax from read_parquet('/tmp/npis.parquet') group by npi""")
    # Insurers list prices for providers who never do the procedure ("ghost rates"). Keep only facilities that are hospitals or
    # surgery centers, and individual clinicians whose listed specialty matches the part (packages.csv 'taxonomy' prefixes).
    con.execute("""create table parts as select dc.package, dc."name", dc.role, dc.in_total, r.network, r.insurer, r.npi, r.billing_code,
                     min(r.rate) lo, max(r.rate) hi, any_value(r.source_url) source_url, max(r.file_date) file_date
                   from r join dc on dc.code = r.billing_code and r.billing_class = dc.billing_class
                   join nt on nt.npi = r.npi
                   where len([prefix for prefix in string_split(dc.taxonomy, '|') if starts_with(coalesce(nt.tax, ''), prefix)]) > 0
                     and ((dc.role = 'facility' and nt.et = '2') or (dc.role <> 'facility' and nt.et = '1'))
                   group by all""")
    # doctor/anesthesia/pathology fees: only clinicians with Medicare evidence; a network with none falls back to all listed specialists
    con.execute("""create table doc_ev as select p.package, p.network, p.role, count(distinct p.npi) n, min(p.lo) lo, quantile_disc(p.lo, 0.5) mid,
                     max(p.hi) hi, 'billed Medicare for it' basis
                   from parts p join cl_ev e on e.package = p.package and e.role = p.role and e.npi = p.npi
                   where p.role <> 'facility' group by all""")
    con.execute("""create table doc as select * from doc_ev union all
                   select package, network, role, count(distinct npi) n, min(lo) lo, quantile_disc(lo, 0.5) mid, max(hi) hi,
                          'listed specialists (no Medicare evidence in this network)' basis
                   from parts p where role <> 'facility'
                     and not exists (select 1 from doc_ev e where e.package = p.package and e.network = p.network and e.role = p.role)
                   group by all""")
    con.execute(f"""create table pk as
        select f.package, f."name", f.network, f.insurer, f.npi facility_npi, coalesce(n.fname, 'NPI ' || f.npi) as facility, n.city,
               f.lo facility_fee, f.hi facility_fee_high,
               dr.n doctors, dr.lo doctor_low, dr.mid doctor_middle, dr.hi doctor_high, dr.basis doctor_basis,
               (fe.npi is not null) does_procedure,
               f.lo + dr.lo total_low, f.lo + dr.mid total_middle, f.lo + dr.hi total_high,
               an.lo anesthesia_low, an.hi anesthesia_high, pa.lo pathology_low, pa.hi pathology_high,
               f.source_url, f.file_date, '{date.today().isoformat()}' checked_on
        from parts f
        join doc dr on dr.package = f.package and dr.network = f.network and dr.role = 'doctor'
        left join doc an on an.package = f.package and an.network = f.network and an.role = 'anesthesia'
        left join doc pa on pa.package = f.package and pa.network = f.network and pa.role = 'pathology'
        left join nt n on n.npi = f.npi
        left join fac_ev fe on fe.package = f.package and fe.network = f.network and fe.npi = f.npi
        where f.role = 'facility'""")  # a facility fee belongs to an organization, not one doctor
    # Flat-price networks: one facility fee for every facility in the network (e.g. a default rate). Kept and labeled,
    # but left out of lowest/highest rankings (Betsy, Oct 14, 2026).
    con.execute("""alter table pk add column same_price_everywhere boolean""")
    con.execute("""update pk set same_price_everywhere = (select count(distinct facility_fee) = 1 and count(*) >= 10 from pk p2
                   where p2.package = pk.package and p2.network = pk.network)""")
    con.execute("copy pk to '/tmp/pk.parquet' (format parquet, compression zstd)")
    s3.upload_file("/tmp/pk.parquet", B, f"data/packages/{MONTH}/{a.area}.parquet")

    money = lambda v: "—" if v is None else f"${v:,.0f}"
    L = [f"# Procedure packages ({a.area.upper()}): {MONTH}", "",
         "Facility fee plus the doctor's fee for the same procedure, in the same network, from the insurers' own files. Insurer files don't say "
         "which doctor works where, so the doctor's part is the lowest, middle and highest fee the network lists for DFW doctors who billed "
         "Medicare for this procedure in 2024. Ranked facilities also list prices for related codes in the same procedure family. "
         "Anesthesia (billed by time) and pathology are shown separately, never added. For review; not on the site yet.", ""]
    for pkg, name in con.execute('select distinct package, "name" from pk order by 1').fetchall():
        s = con.execute(f"""select count(*), count(distinct facility_npi), count(distinct network), min(total_low), max(total_high),
                                   quantile_disc(total_middle, 0.5) from pk where package = '{pkg}' and not same_price_everywhere and does_procedure""").fetchone()
        L += [f"## {name}", "", f"{s[0]:,} facility-and-network prices: {s[1]:,} facilities in {s[2]} networks. "
              f"Totals run from {money(s[3])} to {money(s[4])}.", "",
              "Lowest five, using each network's middle doctor's fee:", "",
              "| Facility | City | Network | Facility fee | Doctor (low / middle / high) | Total with middle doctor | Anesthesia (separate) |",
              "|---|---|---|---|---|---|---|"]
        for r in con.execute(f"""select facility, city, network, facility_fee, doctor_low, doctor_middle, doctor_high, total_middle,
                                        anesthesia_low, anesthesia_high from pk where package = '{pkg}' and not same_price_everywhere and does_procedure order by total_middle limit 5""").fetchall():
            L.append(f"| {r[0]} | {(r[1] or '').title()} | {r[2]} | {money(r[3])} | {money(r[4])} / {money(r[5])} / {money(r[6])} | "
                     f"{money(r[7])} | {money(r[8])}–{money(r[9])} |")
        L += ["", "Highest five:", "", "| Facility | City | Network | Facility fee | Total with middle doctor |", "|---|---|---|---|---|"]
        for r in con.execute(f"""select facility, city, network, facility_fee, total_middle from pk where package = '{pkg}' and not same_price_everywhere and does_procedure
                                 order by total_middle desc limit 5""").fetchall():
            L.append(f"| {r[0]} | {(r[1] or '').title()} | {r[2]} | {money(r[3])} | {money(r[4])} |")
        al = con.execute(f"""select count(*), count(distinct facility_npi) from pk where package = '{pkg}' and not does_procedure""").fetchone()
        L += ["", f"Also listed in the insurers' files, may not offer this procedure (shown last on the site, not ranked): "
              f"{al[0]:,} prices at {al[1]:,} facilities."]
        flat = con.execute(f"""select network, any_value(facility_fee), count(*) from pk where package = '{pkg}' and same_price_everywhere
                               group by network order by 1""").fetchall()
        if flat:
            L += ["", "Same facility price at every facility in the network (labeled on the site, left out of rankings):", ""]
            L += [f"- {n}: {money(v)} at {c:,} facilities" for n, v, c in flat]
        L.append("")
    out = HERE.parent / "reports" / "packages" / f"{MONTH}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"{con.execute('select count(*) from pk').fetchone()[0]:,} package rows -> data/packages/{MONTH}/{a.area}.parquet and {out.name}")


if __name__ == "__main__":
    main()
