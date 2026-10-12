"""Texas step 1: split each Texas insurer table by metro area, so each metro can be built like DFW.

Metro = the provider's practice ZIP (NPPES, data/scope/tx_npis_all.parquet) by 3-digit ZIP area:
  houston 770-775 · san-antonio 780-782 · austin 786-787 · el-paso 798-799 · rest = every other Texas ZIP.
DFW (750-753, 760-762) is skipped: the DFW site is built from the DFW files.
Rows are copied unchanged (no averaging, nothing dropped inside a metro); same code/rate filters as every_code.py.
Output R2 data/tx/metro/<metro>/rates/<table>.parquet (+ membership/), and data/tx/metro/_done/<table>.json.
Env: R2_*; TABLES (comma list of names in data/tx/rates/ without .parquet) or ALL=1; MEM; THREADS; WORK."""
import json, os, time, glob, shutil, duckdb, boto3
E = os.environ
B = E.get('R2_BUCKET', 'upfrontdfwdata')
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
W = E.get('WORK', '/d'); os.makedirs(f'{W}/tmp', exist_ok=True)
FLAT_COLS = ["reporting_entity_name", "file_label", "last_updated_on", "billing_code_type", "billing_code", "name",
             "negotiation_arrangement", "npi", "tin", "tin_type", "negotiated_type", "negotiated_rate", "billing_class",
             "setting", "service_code", "billing_code_modifier", "expiration_date", "source_file", "source_url", "checked_on"]
def ls(p): return [(o['Key'], o['Size']) for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])]
METRO = """case when z between '770' and '775' then 'houston' when z between '780' and '782' then 'san-antonio'
  when z between '786' and '787' then 'austin' when z between '798' and '799' then 'el-paso'
  when (z between '750' and '753') or (z between '760' and '762') then 'dfw' else 'rest' end"""
s3.download_file(B, 'data/scope/tx_npis_all.parquet', f'{W}/npis.parquet')
allt = [k.rsplit('/', 1)[1][:-8] for k, _ in sorted(ls('data/tx/rates/'), key=lambda x: -x[1])]
tables = allt if E.get('ALL') else [t for t in E['TABLES'].split(',') if t]
for t in tables:
    try: s3.head_object(Bucket=B, Key=f'data/tx/metro/_done/{t}.json'); print('skip', t, flush=True); continue
    except Exception: pass
    t0 = time.time(); src = f'{W}/in.parquet'
    s3.download_file(B, f'data/tx/rates/{t}.parquet', src)
    c = duckdb.connect()
    # Oct 12, 2026: "lines" tables (npiset column) are expanded back to one row per NPI with their npisets/ file,
    # so the metro tables written below stay in the flat layout.
    rsrc = f"read_parquet('{src}')"
    if 'npiset' in {r[0] for r in c.execute(f"describe select * from read_parquet('{src}')").fetchall()}:
        s3.download_file(B, f'data/tx/npisets/{t}.parquet', f'{W}/sets.parquet')
        cols = ", ".join("s.npi" if x == "npi" else f"l.{x}" for x in FLAT_COLS)
        rsrc = f"(select {cols} from read_parquet('{src}') l join (select npiset, unnest(npis) npi from read_parquet('{W}/sets.parquet')) s using (npiset))"
    c.execute(f"set memory_limit='{E.get('MEM', '12GB')}'; set threads={E.get('THREADS', '8')}; set preserve_insertion_order=false; set temp_directory='{W}/tmp'; set enable_progress_bar=false")
    c.execute(f"create table m as select npi, {METRO.replace('z', 'left(zip5, 3)')} metro from read_parquet('{W}/npis.parquet')")
    out = f'{W}/out'; shutil.rmtree(out, ignore_errors=True)
    c.execute(f"""copy (select r.*, m.metro from {rsrc} r join m using (npi)
      where m.metro <> 'dfw'
        and (billing_code_type ilike 'cpt%' or billing_code_type ilike 'hcpcs%' or billing_code_type ilike 'ms-drg%' or billing_code_type ilike 'drg%')
        and lower(negotiated_type) in ('negotiated','fee schedule','derived','percentage') and try_cast(negotiated_rate as double) >= 0)
      to '{out}' (format parquet, compression zstd, partition_by (metro), overwrite_or_ignore)""")
    n_in = c.execute(f"select count(*) from {rsrc}").fetchone()[0]   # flat rows, either layout
    os.remove(src)
    have_m = True
    try: s3.download_file(B, f'data/tx/membership/{t}.parquet', f'{W}/mem.parquet')
    except Exception: have_m = False
    stats = dict(table=t, rows_in=n_in, metros={})
    for d in sorted(glob.glob(f'{out}/metro=*')):
        mt = d.rsplit('=', 1)[1]
        c.execute(f"copy (select * exclude (metro) from read_parquet('{d}/*.parquet')) to '{W}/one.parquet' (format parquet, compression zstd)")
        n = c.execute(f"select count(*) from read_parquet('{W}/one.parquet')").fetchone()[0]
        s3.upload_file(f'{W}/one.parquet', B, f'data/tx/metro/{mt}/rates/{t}.parquet')
        if have_m:
            c.execute(f"copy (select x.* from read_parquet('{W}/mem.parquet') x join m using (npi) where m.metro = '{mt}') to '{W}/onem.parquet' (format parquet, compression zstd)")
            s3.upload_file(f'{W}/onem.parquet', B, f'data/tx/metro/{mt}/membership/{t}.parquet')
        stats['metros'][mt] = n
    c.close(); shutil.rmtree(out, ignore_errors=True)
    for f in ('one', 'onem', 'mem', 'sets'):
        if os.path.exists(f'{W}/{f}.parquet'): os.remove(f'{W}/{f}.parquet')
    stats['minutes'] = round((time.time() - t0) / 60, 1)
    s3.put_object(Bucket=B, Key=f'data/tx/metro/_done/{t}.json', Body=json.dumps(stats).encode())
    print(json.dumps(stats), flush=True)
print('ALL DONE', flush=True)
