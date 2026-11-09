"""One-off look at archived hospital originals (Nov 9, 2026): python audit/peek_raw.py <sha-prefix> [...]"""
import io, os, sys, zstandard, boto3
E_ = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=os.environ.get('STORAGE_ENDPOINT') or f"https://{E_['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E_['R2_ACCESS_KEY_ID'], aws_secret_access_key=E_['R2_SECRET_ACCESS_KEY'], region_name=os.environ.get('STORAGE_REGION') or 'auto')
B = E_['R2_BUCKET']
keys = []
for p in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix='raw/hospitals/'):
    keys += [(o['Key'], o['Size']) for o in p.get('Contents', [])]
print(len(keys), 'raw hospital objects')
for want in sys.argv[1:]:
    hits = [k for k in keys if os.path.basename(k[0]).startswith(want[:12]) or want[:12] in k[0]]
    print('\n==', want, len(hits), 'objects')
    for k, size in hits[:6]:
        print('  ', k, size)
    for k, size in hits[:2]:
        body = s3.get_object(Bucket=B, Key=k)['Body']
        rd = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(body, read_across_frames=True)
        tot, nl, cr, chunks, first = 0, 0, 0, 0, b''
        while True:
            b = rd.read(1 << 22)
            if not b:
                break
            if not first:
                first = b[:400]
            tot += len(b); nl += b.count(b'\n'); cr += b.count(b'\r'); chunks += 1
        print('   zstd stream_reader:', tot, 'bytes,', nl, '\\n,', cr, '\\r,', chunks, 'reads; head', first[:300])
        body = s3.get_object(Bucket=B, Key=k)['Body']
        out = io.BytesIO() if size < 3e8 else None
        if out is not None:
            zstandard.ZstdDecompressor(max_window_size=2 ** 31).copy_stream(body, out)
            v = out.getvalue()
            print('   copy_stream:', len(v), 'bytes,', v.count(b'\n'), '\\n')
