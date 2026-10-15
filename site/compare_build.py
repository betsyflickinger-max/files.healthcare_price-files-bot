"""Compare two every_code.py outputs code file by code file (Oct 15, 2026; written to check the LINES=1 build against the
live flat build). Every provider row is compared field by field. The "unusually low" flag (bit 2 of the flags field) is
counted on its own: it depends on an approximate market middle that can move slightly between runs.

  python site/compare_build.py OLD_PREFIX NEW_PREFIX [REPORT_KEY]      (prefixes are TOUT folders in R2, ending in /)
Env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET. Exit code 0 = no differences other than that flag."""
import base64, gzip, json, os, sys
from concurrent.futures import ThreadPoolExecutor
import boto3

E = os.environ
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
B = E['R2_BUCKET']
OLD, NEW = sys.argv[1], sys.argv[2]
REPORT = sys.argv[3] if len(sys.argv) > 3 else None
def ls(p): return {o['Key'][len(p):]: o['Size'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])}
def load(key): return json.loads(gzip.decompress(base64.b64decode(s3.get_object(Bucket=B, Key=key)['Body'].read())))['f']
FIELDS = ['network', 'fee', 'type', 'rate', 'flags', 'date', 'source', 'other_count', 'others', 'zeros', 'label']

old, new = ls(OLD + 't/'), ls(NEW + 't/')
rep = {'old_codes': len(old), 'new_codes': len(new), 'only_old': sorted(set(old) - set(new))[:50], 'only_new': sorted(set(new) - set(old))[:50],
       'codes_compared': 0, 'providers_compared': 0, 'rows_compared': 0, 'rows_identical': 0, 'rows_low_flag_only': 0,
       'providers_missing': 0, 'providers_extra': 0, 'rows_differ': 0, 'by_field': {}, 'examples': []}
def one(name):
    a, b = load(OLD + 't/' + name), load(NEW + 't/' + name)
    out = {'p': 0, 'r': 0, 'same': 0, 'low': 0, 'miss': 0, 'extra': 0, 'diff': 0, 'by': {}, 'ex': []}
    for pk in set(a) | set(b):
        if pk not in b: out['miss'] += 1; out['ex'].append([name, pk, 'provider missing in new']); continue
        if pk not in a: out['extra'] += 1; out['ex'].append([name, pk, 'provider only in new']); continue
        out['p'] += 1; ra, rb = a[pk], b[pk]
        if len(ra) != len(rb): out['diff'] += max(len(ra), len(rb)); out['by']['row_count'] = out['by'].get('row_count', 0) + 1; out['ex'].append([name, pk, 'row count', ra, rb]); continue
        for x, y in zip(ra, rb):
            out['r'] += 1
            if x == y: out['same'] += 1; continue
            fx = [i for i in range(len(x)) if x[i] != y[i]]
            if fx == [4] and (x[4] ^ y[4]) == 2: out['low'] += 1; continue
            out['diff'] += 1
            for i in fx: out['by'][FIELDS[i]] = out['by'].get(FIELDS[i], 0) + 1
            if len(out['ex']) < 5: out['ex'].append([name, pk, x, y])
    return out
both = sorted(set(old) & set(new))
with ThreadPoolExecutor(16) as ex:
    for o in ex.map(one, both):
        rep['codes_compared'] += 1; rep['providers_compared'] += o['p']; rep['rows_compared'] += o['r']; rep['rows_identical'] += o['same']
        rep['rows_low_flag_only'] += o['low']; rep['providers_missing'] += o['miss']; rep['providers_extra'] += o['extra']; rep['rows_differ'] += o['diff']
        for k, v in o['by'].items(): rep['by_field'][k] = rep['by_field'].get(k, 0) + v
        if len(rep['examples']) < 20: rep['examples'] += o['ex'][:20 - len(rep['examples'])]
for name in ('embed.json', 'npis.json'):
    try:
        ea = json.loads(s3.get_object(Bucket=B, Key=OLD + name)['Body'].read()); eb = json.loads(s3.get_object(Bucket=B, Key=NEW + name)['Body'].read())
        rep[name] = 'identical' if ea == eb else ('differs: ' + ', '.join(k for k in ea if ea.get(k) != eb.get(k)) if isinstance(ea, dict) else 'differs')
    except Exception as e: rep[name] = f'not compared ({type(e).__name__})'
ok = not rep['only_old'] and not rep['only_new'] and rep['rows_differ'] == 0 and rep['providers_missing'] == 0 and rep['providers_extra'] == 0
rep['result'] = 'PASS' if ok else 'FAIL'
print(json.dumps({k: v for k, v in rep.items() if k != 'examples'}, indent=1)); print('examples:', json.dumps(rep['examples'][:8])[:3000])
if REPORT: s3.put_object(Bucket=B, Key=REPORT, Body=json.dumps(rep, indent=1).encode())
sys.exit(0 if ok else 1)
