"""Texas step 1: shrink one insurer table before the every-code build.

Insurer files repeat each rate once per clinician (NPI) in a group (Aetna: 5-8.5B rows per network; the npi and tin
columns are 96% of the file). This keeps every distinct rate line once, with the list of NPIs it applies to stored
separately (identical lists stored once). Nothing is averaged or dropped: every (rate line, NPI) pair can be rebuilt.
Same filters as every_code.py (CPT/HCPCS/MS-DRG; negotiated/fee schedule/derived/percentage; rate >= 0).
Output R2 data/tx/shrunk/<table>/{lines,npisets}.parquet + stats.json.
Env: R2_*; TABLE (file name in data/tx/rates/ without .parquet) or ALL=1; MEM; THREADS."""
import json, os, time, duckdb, boto3, shutil
E = os.environ
B = E.get('R2_BUCKET', 'upfrontdfwdata')
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
W = E.get('WORK', '/d'); os.makedirs(f'{W}/tmp', exist_ok=True)
def ls(p): return [(o['Key'], o['Size']) for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])]
tables = [k.rsplit('/', 1)[1][:-8] for k, _ in sorted(ls('data/tx/rates/'), key=lambda x: -x[1])] if E.get('ALL') else [E['TABLE']]
done = {k.split('/')[3] for k, _ in ls('data/tx/shrunk/') if k.endswith('stats.json')}
for t in tables:
    if t in done: print('skip', t, flush=True); continue
    if s3.head_object(Bucket=B, Key=f'data/tx/rates/{t}.parquet').get('Metadata', {}).get('layout') == 'lines':
        print('skip', t, '(already stored once per provider group by the insurer bot, Oct 12, 2026 layout)', flush=True); continue
    t0 = time.time(); src = f'{W}/in.parquet'
    s3.download_file(B, f'data/tx/rates/{t}.parquet', src)
    try: s3.download_file(B, f'data/tx/membership/{t}.parquet', f'{W}/m.parquet'); mj = True
    except Exception: mj = False
    td = time.time() - t0
    n_in = duckdb.sql(f"select sum(row_group_num_rows) from (select distinct row_group_id, row_group_num_rows from parquet_metadata('{src}'))").fetchone()[0]
    gb_in = round(os.path.getsize(src) / 1e9, 2)
    c = duckdb.connect()
    c.execute(f"set memory_limit='{E.get('MEM', '12GB')}'; set threads={E.get('THREADS', '8')}; set preserve_insertion_order=false; set temp_directory='{W}/tmp'; set enable_progress_bar=false")
    c.execute(f"""create view r as select * from read_parquet('{src}')
      where (billing_code_type ilike 'cpt%' or billing_code_type ilike 'hcpcs%' or billing_code_type ilike 'ms-drg%' or billing_code_type ilike 'drg%')
        and lower(negotiated_type) in ('negotiated','fee schedule','derived','percentage') and try_cast(negotiated_rate as double) >= 0""")
    cols = "reporting_entity_name, file_label, last_updated_on, billing_code_type, billing_code, name, tin, negotiated_type, negotiated_rate, billing_class, setting, billing_code_modifier, source_url"
    # step 0: split by provider group (tin) so each piece fits in memory; a rate line never spans pieces (tin is part of it)
    K = max(1, int(os.path.getsize(src) / 1.5e9) + 1)
    c.execute(f"copy (select {cols}, npi, hash(tin) % {K} p from r) to '{W}/parts' (format parquet, partition_by (p), overwrite_or_ignore)")
    os.remove(src)
    os.makedirs(f'{W}/g', exist_ok=True)
    for p_ in range(K):
        pd = f'{W}/parts/p={p_}'
        if not os.path.isdir(pd): continue
        # step 1: one row per distinct rate line, with its sorted NPI list
        c.execute(f"copy (select {cols}, list_sort(list(distinct npi)) npis from read_parquet('{pd}/*.parquet') group by all) to '{W}/g/{p_}.parquet' (format parquet, compression zstd)")
        shutil.rmtree(pd)
        print(f'  piece {p_ + 1}/{K}', round((time.time() - t0) / 60, 1), 'min', flush=True)
    # step 2: store each distinct NPI list once
    c.execute(f"""copy (select {cols}, hash(npis) npiset, len(npis) n_npi from read_parquet('{W}/g/*.parquet')) to '{W}/lines.parquet' (format parquet, compression zstd)""")
    c.execute(f"""copy (select hash(npis) npiset, any_value(npis) npis from read_parquet('{W}/g/*.parquet') group by 1) to '{W}/npisets.parquet' (format parquet, compression zstd)""")
    n_lines, n_pairs = c.execute(f"select count(*), sum(n_npi) from read_parquet('{W}/lines.parquet')").fetchone()
    n_sets = c.execute(f"select count(*) from read_parquet('{W}/npisets.parquet')").fetchone()[0]
    c.close()
    for f in ('lines', 'npisets'): s3.upload_file(f'{W}/{f}.parquet', B, f'data/tx/shrunk/{t}/{f}.parquet')
    if mj: s3.upload_file(f'{W}/m.parquet', B, f'data/tx/shrunk/{t}/membership.parquet')
    st = dict(table=t, rows_in=n_in, rate_lines=n_lines, line_npi_pairs=int(n_pairs or 0), npi_sets=n_sets,
              gb_in=gb_in, gb_out=round(sum(os.path.getsize(f'{W}/{f}.parquet') for f in ('lines', 'npisets')) / 1e9, 2),
              download_min=round(td / 60, 1), total_min=round((time.time() - t0) / 60, 1))
    s3.put_object(Bucket=B, Key=f'data/tx/shrunk/{t}/stats.json', Body=json.dumps(st).encode())
    print(json.dumps(st), flush=True)
    shutil.rmtree(f'{W}/g', ignore_errors=True); shutil.rmtree(f'{W}/parts', ignore_errors=True)
    for f in ('in', 'm', 'lines', 'npisets'):
        if os.path.exists(f'{W}/{f}.parquet'): os.remove(f'{W}/{f}.parquet')
    shutil.rmtree(f'{W}/tmp', ignore_errors=True); os.makedirs(f'{W}/tmp', exist_ok=True)
print('ALL DONE', flush=True)
