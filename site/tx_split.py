"""Texas step 1: split each Texas insurer table by metro area, so each metro can be built like DFW.

Metro = the provider's practice ZIP (NPPES, data/scope/tx_npis_all.parquet) by 3-digit ZIP area:
  houston 770-775 · san-antonio 780-782 · austin 786-787 · el-paso 798-799. Every other Texas ZIP (Oct 12, 2026; was one
  "rest" metro) goes to its metro-area page by reference/geo/tx_zip_metro.csv (Census ZIP -> county -> metro area: mcallen,
  lubbock, ...), and a ZIP in no listed metro area to small-towns.
DFW (750-753, 760-762) is skipped: the DFW site is built from the DFW files.
Rows are copied unchanged (no averaging, nothing dropped inside a metro); same code/rate filters as every_code.py.
Output R2 data/tx/metro/<metro>/rates/<table>.parquet (+ membership/), and data/tx/metro/_done/<table>.json.
SRC=rest: re-split the tables already split into the old "rest" metro (data/tx/metro/rest/, October 2026) into the metro-area
pages the same way; done markers data/tx/metro/_done_rest/<table>.json. The rest/ copies are left in place.
SCOPE=s7 (Oct 13, 2026): split the first national batch (data/s7/) by the provider's practice state instead, into
data/s7/state/<state slug>/rates|membership/<table>.parquet, done markers data/s7/state/_done/<table>.json. Same filters.
Env: R2_*; TABLES (comma list of table names without .parquet) or ALL=1; [SRC=rest]; [SCOPE=s7]; MEM; THREADS; WORK."""
import json, os, time, glob, shutil, duckdb, boto3
E = os.environ
B = E.get('R2_BUCKET', 'upfrontdfwdata')
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
W = E.get('WORK', '/d'); os.makedirs(f'{W}/tmp', exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
GEO = next((p for p in (f'{HERE}/tx_zip_metro.csv', f'{HERE}/../reference/geo/tx_zip_metro.csv') if os.path.exists(p)), None)   # bundled next to this file on machines
if not GEO: raise SystemExit('STOP: tx_zip_metro.csv not found')
def ls(p): return [(o['Key'], o['Size']) for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])]
REST = E.get('SRC') == 'rest'
ST = E.get('SCOPE') == 's7'
STATES = {'TN': 'tennessee', 'CO': 'colorado', 'OK': 'oklahoma', 'AL': 'alabama', 'MS': 'mississippi', 'MO': 'missouri', 'GA': 'georgia'}
RIN, MIN, DONE = (('data/tx/metro/rest/rates/', 'data/tx/metro/rest/membership/', 'data/tx/metro/_done_rest/') if REST else
                  ('data/s7/rates/', 'data/s7/membership/', 'data/s7/state/_done/') if ST else
                  ('data/tx/rates/', 'data/tx/membership/', 'data/tx/metro/_done/'))
OUTD = 'data/s7/state/' if ST else 'data/tx/metro/'
# z = 3-digit ZIP area, g.slug = metro area page of the 5-digit ZIP. A rest/ table holds only rest-of-Texas providers, so SRC=rest
# uses the metro-area table alone (a provider can't land in a city folder and overwrite that city's split of the same table).
AREA = "coalesce(g.slug, 'small-towns')"
METRO = AREA if REST else f"""case when z between '770' and '775' then 'houston' when z between '780' and '782' then 'san-antonio'
  when z between '786' and '787' then 'austin' when z between '798' and '799' then 'el-paso'
  when (z between '750' and '753') or (z between '760' and '762') then 'dfw' else {AREA} end"""
if ST: METRO = 'case st ' + ' '.join(f"when '{k}' then '{v}'" for k, v in STATES.items()) + " else 'dfw' end"   # 'dfw' = dropped
s3.download_file(B, 'data/scope/s7_npis_all.parquet' if ST else 'data/scope/tx_npis_all.parquet', f'{W}/npis.parquet')
allt = [k.rsplit('/', 1)[1][:-8] for k, _ in sorted(ls(RIN), key=lambda x: -x[1]) if k.endswith('.parquet')]
tables = allt if E.get('ALL') else [t for t in E['TABLES'].split(',') if t]
for t in tables:
    try: s3.head_object(Bucket=B, Key=f'{DONE}{t}.json'); print('skip', t, flush=True); continue
    except Exception: pass
    t0 = time.time(); src = f'{W}/in.parquet'
    s3.download_file(B, f'{RIN}{t}.parquet', src)
    c = duckdb.connect()
    c.execute(f"set memory_limit='{E.get('MEM', '12GB')}'; set threads={E.get('THREADS', '8')}; set preserve_insertion_order=false; set temp_directory='{W}/tmp'; set enable_progress_bar=false")
    c.execute(f"create table g as select zip5, slug from read_csv('{GEO}', all_varchar=true)")
    if c.execute("select count(*) - count(distinct zip5) from g").fetchone()[0]: raise SystemExit('STOP: a ZIP is listed twice in tx_zip_metro.csv')
    c.execute(f"""create table m as select distinct n.npi, {METRO} metro
      from (select npi, left(zip5, 3) z, left(zip5, 5) z5{', upper(state) st' if ST else ''} from read_parquet('{W}/npis.parquet')) n left join g on g.zip5 = n.z5""")
    out = f'{W}/out'; shutil.rmtree(out, ignore_errors=True)
    c.execute(f"""copy (select r.*, m.metro from read_parquet('{src}') r join m using (npi)
      where m.metro <> 'dfw'
        and (billing_code_type ilike 'cpt%' or billing_code_type ilike 'hcpcs%' or billing_code_type ilike 'ms-drg%' or billing_code_type ilike 'drg%')
        and lower(negotiated_type) in ('negotiated','fee schedule','derived','percentage') and try_cast(negotiated_rate as double) >= 0)
      to '{out}' (format parquet, compression zstd, partition_by (metro), overwrite_or_ignore)""")
    n_in = c.execute(f"select sum(row_group_num_rows) from (select distinct row_group_id, row_group_num_rows from parquet_metadata('{src}'))").fetchone()[0]
    os.remove(src)
    have_m = True
    try: s3.download_file(B, f'{MIN}{t}.parquet', f'{W}/mem.parquet')
    except Exception: have_m = False
    stats = dict(table=t, rows_in=n_in, metros={})
    for d in sorted(glob.glob(f'{out}/metro=*')):
        mt = d.rsplit('=', 1)[1]
        c.execute(f"copy (select * exclude (metro) from read_parquet('{d}/*.parquet')) to '{W}/one.parquet' (format parquet, compression zstd)")
        n = c.execute(f"select count(*) from read_parquet('{W}/one.parquet')").fetchone()[0]
        s3.upload_file(f'{W}/one.parquet', B, f'{OUTD}{mt}/rates/{t}.parquet')
        if have_m:
            c.execute(f"copy (select x.* from read_parquet('{W}/mem.parquet') x join m using (npi) where m.metro = '{mt}') to '{W}/onem.parquet' (format parquet, compression zstd)")
            s3.upload_file(f'{W}/onem.parquet', B, f'{OUTD}{mt}/membership/{t}.parquet')
        stats['metros'][mt] = n
    c.close(); shutil.rmtree(out, ignore_errors=True)
    for f in ('one', 'onem', 'mem'):
        if os.path.exists(f'{W}/{f}.parquet'): os.remove(f'{W}/{f}.parquet')
    stats['minutes'] = round((time.time() - t0) / 60, 1)
    if REST and sum(stats['metros'].values()) != n_in: stats['note'] = 'rows out differ from rows in (a provider with ZIPs in two areas is in both)'
    s3.put_object(Bucket=B, Key=f'{DONE}{t}.json', Body=json.dumps(stats).encode())
    print(json.dumps(stats), flush=True)
print('ALL DONE', flush=True)
