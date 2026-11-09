"""One-off (Nov 9, 2026): Odessa's hospital index vs one of its Oct 13 per-code files."""
import base64, gzip, json, os, boto3
E_ = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
EP = os.environ.get('STORAGE_ENDPOINT') or f"https://{E_['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
s3 = boto3.client('s3', endpoint_url=EP, aws_access_key_id=E_['R2_ACCESS_KEY_ID'], aws_secret_access_key=E_['R2_SECRET_ACCESS_KEY'], region_name=os.environ.get('STORAGE_REGION') or 'auto')
B = E_['R2_BUCKET']
get = lambda k: s3.get_object(Bucket=B, Key=k)['Body'].read()
for area, codes in (('odessa', ['77066', '43239']), ('houston', ['77066'])):
    pre = f'site/every-tx/{area}/2026-10/hosp/'
    H = json.loads(get(pre + 'hosp_index.json'))
    print('\n==', area, 'index src', len(H['src']))
    for i, x in enumerate(H['src']):
        print('  ', i, x[0][:45], x[3], x[5], x[6] if len(x) > 6 else '')
    for c in codes:
        b = get(pre + f'h/{c}.txt')
        d = json.loads(gzip.decompress(base64.b64decode(b)))
        slots = sorted({r[0] for r in d.get('r', [])} | {r[0] for r in d.get('c', [])})
        print('  code', c, 'slots used', slots, 'max row', max([r[7] for r in d.get('r', [])] + [0]))
        for r in d.get('r', [])[:3]:
            print('     ', r)
for k in ('site/builds/hosp-tx-2026-10/state.json', 'site/builds/hosp-tx-2026-11/state.json'):
    try:
        st = json.loads(get(k)); print('\n', k, 'stage', st.get('stage'), 'published odessa:', st.get('published', {}).get('odessa'), 'houston:', st.get('published', {}).get('houston'))
    except Exception as e:
        print(k, e)
