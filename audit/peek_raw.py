"""One-off look at Odessa Regional's archived originals and the extracted rows that cite them (Nov 9, 2026)."""
import io, os, sys, zstandard, boto3, duckdb
E_ = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
EP = os.environ.get('STORAGE_ENDPOINT') or f"https://{E_['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
s3 = boto3.client('s3', endpoint_url=EP, aws_access_key_id=E_['R2_ACCESS_KEY_ID'], aws_secret_access_key=E_['R2_SECRET_ACCESS_KEY'], region_name=os.environ.get('STORAGE_REGION') or 'auto')
B = E_['R2_BUCKET']
def ls(pfx):
    out = []
    for p in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pfx):
        out += [(o['Key'], o['Size'], str(o['LastModified'])[:10]) for o in p.get('Contents', [])]
    return out
raw = [k for k in ls('raw/hospitals/') if 'odessa' in k[0].lower()]
for k in raw:
    print(k)
for k, size, _ in raw:
    if 'OdessaTexasHospital' not in k:
        continue
    rd = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(s3.get_object(Bucket=B, Key=k)['Body'], read_across_frames=True)
    t = io.TextIOWrapper(rd, encoding='utf-8', errors='replace', newline='')
    lines = [t.readline() for _ in range(5)]
    print('\n', k)
    for l in lines:
        print('   ', l[:400].rstrip())
host = EP.replace('https://', '').rstrip('/')
con = duckdb.connect()
con.execute(f"""INSTALL httpfs; LOAD httpfs; CREATE SECRET s (TYPE S3, KEY_ID '{E_['R2_ACCESS_KEY_ID']}', SECRET '{E_['R2_SECRET_ACCESS_KEY']}',
                ENDPOINT '{host}', URL_STYLE 'path', REGION '{os.environ.get('STORAGE_REGION') or 'auto'}')""")
for pfx in ('data/hosp_every/rows/', ):
    keys = [k for k, s, _ in ls(pfx) if k.endswith('.parquet')]
    print('\n', pfx, len(keys), 'parquet files')
    hit = []
    for i in range(0, len(keys), 200):
        lst = '[' + ','.join(f"'s3://{B}/{k}'" for k in keys[i:i + 200]) + ']'
        try:
            hit += con.execute(f"""select filename, left(sha256,16), raw_key, count(*), min(try_cast(source_row as bigint)), max(try_cast(source_row as bigint))
                                   from read_parquet({lst}, union_by_name=true, filename=true)
                                   where lower(raw_key) like '%odessatexashospital%' or sha256 like '2651d8c5%' group by all""").fetchall()
        except Exception as e:
            print('  batch', i, type(e).__name__, str(e)[:200])
    for h in hit:
        print('  ', h)
