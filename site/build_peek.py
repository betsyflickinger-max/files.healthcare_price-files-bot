"""Oct 30, 2026: read-only look at one state build in R2: which files it has and what each kind holds (shapes and a sample),
for planning the California regional split. Changes nothing. Usage: python site/build_peek.py california"""
import base64, gzip, json, os, sys, collections
import boto3
slug = sys.argv[1]
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = E['R2_BUCKET']
def ls(p):
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p):
        yield from pg.get('Contents', [])
def get(k): return s3.get_object(Bucket=B, Key=k)['Body'].read()
def shape(v, d=0):
    if isinstance(v, dict):
        ks = list(v)[:6]; return '{' + ', '.join(f'{k!r}: {shape(v[k], d+1)}' for k in ks) + (f', …{len(v)} keys' if len(v) > 6 else '') + '}' if d < 3 else f'dict({len(v)})'
    if isinstance(v, list): return f'[{len(v)}: ' + (shape(v[0], d+1) if v else '') + ']' if d < 4 else f'list({len(v)})'
    return repr(v)[:60]
root = f'site/every-st/{slug}/'
months = sorted({o['Key'][len(root):].split('/')[0] for o in ls(root)})
print('builds:', months)
pre = root + months[-1] + '/'
groups = collections.Counter(); sizes = collections.Counter()
for o in ls(pre):
    rel = o['Key'][len(pre):]; g = rel.split('/')[0] + ('/' if '/' in rel else '') + ('/'.join(rel.split('/')[1:2]) + '/' if rel.count('/') > 1 else '')
    groups[g] += 1; sizes[g] += o['Size']
for g, n in sorted(groups.items()): print(f'  {g:40} {n:7,} files {sizes[g]/1e6:10.1f} MB')
emb = json.loads(get(pre + 'embed.json'))
print('embed keys:', {k: len(json.dumps(v)) for k, v in emb.items()})
for k, v in emb.items():
    if isinstance(v, dict) and v: kk = next(iter(v)); print(f'  embed.{k}[{kk!r}] =', json.dumps(v[kk])[:400])
    elif isinstance(v, list) and v: print(f'  embed.{k}[0] =', json.dumps(v[0])[:400], f'(len {len(v)})')
    else: print(f'  embed.{k} =', json.dumps(v)[:200])
np_ = json.loads(get(pre + 'npis.json')); print('npis.json:', shape(np_))
def dec(k): return json.loads(gzip.decompress(base64.b64decode(get(k))))
t = dec(pre + 't/27447.txt'); print('t/27447 f keys', len(t.get('f', {})), 'p keys', len(t.get('p', {})))
for k in ('f', 'p'):
    if t.get(k): kk = next(iter(t[k])); print(f'  t.{k}[{kk}] =', json.dumps(t[k][kk])[:500])
for o in ls(pre + 'hosp/'):
    print('hosp file:', o['Key'][len(pre):], o['Size']); break
try:
    H = json.loads(get(pre + 'hosp/hosp_index.json')); print('hosp_index:', shape(H))
    for k, v in H.items():
        if isinstance(v, list) and v: print(f'  hosp.{k}[0] =', json.dumps(v[0])[:400], len(v))
        elif isinstance(v, dict) and v: kk = next(iter(v)); print(f'  hosp.{k}[{kk}] =', json.dumps(v[kk])[:400], len(v))
    hk = [o['Key'] for o in ls(pre + 'hosp/h/')][:1]
    if hk:
        raw = get(hk[0])
        try: h = json.loads(gzip.decompress(base64.b64decode(raw)))
        except Exception: h = json.loads(raw)
        print(hk[0][len(pre):], shape(h)); print('  sample', json.dumps(h)[:600])
except Exception as e: print('hosp:', e)
for k in ('site/builds/hosp-stn5-' + months[-1] + '/areas.json',):
    try:
        A = json.loads(get(k)); a = A.get(slug); print('areas.json', slug, shape(a))
        if a and a.get('jobs'): print('  job sample', json.dumps(a['jobs'][0])[:500])
    except Exception as e: print(k, e)
