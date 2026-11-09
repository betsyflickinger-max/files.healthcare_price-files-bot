"""One-off (Nov 9, 2026): are any per-code hospital files older than the hospital index they're read with?
h2_build.py numbers hospital files 0..n per run and never clears old per-code files, so a code missing from a later run
keeps an older file whose numbers point at different hospitals."""
import collections, os, boto3
E_ = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
EP = os.environ.get('STORAGE_ENDPOINT') or f"https://{E_['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
s3 = boto3.client('s3', endpoint_url=EP, aws_access_key_id=E_['R2_ACCESS_KEY_ID'], aws_secret_access_key=E_['R2_SECRET_ACCESS_KEY'], region_name=os.environ.get('STORAGE_REGION') or 'auto')
B = E_['R2_BUCKET']
idx, h = {}, collections.defaultdict(list)
for root in ('site/every-tx/', 'site/every-st/', 'site/every/'):
    for p in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=root):
        for o in p.get('Contents', []):
            k = o['Key']
            if k.endswith('/hosp/hosp_index.json'):
                idx[k[:-len('hosp_index.json')]] = o['LastModified']
            elif '/hosp/h/' in k:
                h[k.split('/hosp/h/')[0] + '/hosp/'].append((k.rsplit('/', 1)[1], o['LastModified']))
print(len(idx), 'hospital indexes')
tot_old = 0
for pre, t in sorted(idx.items()):
    fs = h.get(pre, [])
    old = [(n, m) for n, m in fs if (t - m).total_seconds() > 6 * 3600]
    tot_old += len(old)
    if old or 'odessa' in pre:
        print(f'{pre}  index {t:%Y-%m-%d %H:%M}  per-code files {len(fs)}  older than index by 6h+: {len(old)}  '
              f'oldest {min(m for _, m in old):%Y-%m-%d} ' if old else f'{pre}  index {t:%Y-%m-%d %H:%M}  per-code files {len(fs)}  none older',
              ' '.join(n for n, _ in old if n[:-4] in ('77066', '76805', '70450', '43239'))[:200])
print('total stale per-code files:', tot_old)
