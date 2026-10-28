"""Progress of a state build, read from R2 (Oct 16, 2026: to see why North Carolina showed 0 of 256 batches done for hours).
Prints the build's state.json summary, stage A (tables done / claimed of the state's tables), stage B batches done, and the
last lines of every machine's log.txt. Changes nothing.
Usage: python site/build_check.py stnc-2026-10 north-carolina [lines]   (run by .github/workflows/build-check.yml)"""
import json, os, sys, time
import boto3

E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = E['R2_BUCKET']
bid, slug = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 15
scope = bid.split('-', 1)[0][2:] or 's7'
month = bid.split('-', 1)[1]


def ls(p):
    out = []
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p): out += pg.get('Contents', [])
    return out


def get(k):
    try: return s3.get_object(Bucket=B, Key=k)['Body'].read().decode(errors='replace')
    except Exception: return None


now = time.time()
st = json.loads(get(f'site/builds/{bid}/state.json') or '{}')
print('state:', json.dumps({k: v for k, v in st.items() if k in ('stage', 'started', 'machines', 'launches', 'problems', 'split_failed', 'providers')})[:3000])
print('state log (last 10):', *st.get('log', [])[-10:], sep='\n  ')
rates = [o for o in ls(f'data/{scope}/state/{slug}/rates/') if o['Key'].endswith('.parquet')]
print(f'\nrates: {len(rates)} tables, {sum(o["Size"] for o in rates) / 1e9:.1f} GB; biggest:',
      ', '.join(f"{o['Key'].rsplit('/', 1)[1]} {o['Size'] / 1e9:.1f} GB" for o in sorted(rates, key=lambda o: -o['Size'])[:6]))
allr = {o['Key'].rsplit('/', 1)[1]: o['Size'] for o in ls(f'data/{scope}/rates/') if o['Key'].endswith('.parquet')}
mine = {o['Key'].rsplit('/', 1)[1] for o in rates}
none = sorted((t for t in allr if t not in mine), key=lambda t: -allr[t])
print(f'{len(allr)} {scope} insurer tables; {len(none)} have no rows for {slug}:',
      ', '.join(f'{t} {allr[t] / 1e9:.2f} GB' for t in none[:30]))
ac = f'work/every-st/{slug}/Acache/'
A = [o for o in ls(ac) if o['Key'].endswith(('.done', '.claim'))]
done = [o for o in A if o['Key'].endswith('.done')]
claims = [o for o in A if o['Key'].endswith('.claim')]
print(f'stage A cache {ac}: {len(done)} .done marks, {len(claims)} claims; newest done',
      max((o['LastModified'] for o in done), default='none'))
for o in sorted(claims, key=lambda o: o['LastModified'])[-25:]:
    tag = o['Key'].rsplit('/', 1)[1][:-6]
    if not any(d['Key'].endswith(f'/{tag}.done') for d in done):
        print(f"  open claim {tag} by {get(o['Key'])} for {(now - o['LastModified'].timestamp()) / 60:.0f} min")
wk = f"work/every-st/{slug}/v{month.replace('-', '')}/"
Bj = [o for o in ls(wk + 'B/') if o['Key'].endswith('.json')]
print(f'stage B {wk}: {len(Bj)} batch results; newest', max((o['LastModified'] for o in Bj), default='none'))
logs = [o for o in ls(f'site/builds/{bid}/') if o['Key'].endswith('/log.txt')]
for o in sorted(logs, key=lambda o: o['Key']):
    lines = (get(o['Key']) or '').splitlines()
    print(f"\n== {o['Key']} (updated {(now - o['LastModified'].timestamp()) / 60:.0f} min ago, {len(lines)} lines)")
    print('\n'.join(lines[-n:]))
