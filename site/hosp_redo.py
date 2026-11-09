"""Nov 9, 2026: rebuild some areas' hospital price files and republish their pages (.github/workflows/hosp-redo.yml).

Why: until Nov 9 every hospital rebuild of an area wrote into the same hosp/h/ folder and never cleared it, so after a
rebuild with fewer hospitals the page read older per-code files whose hospital numbers pointed at the wrong hospitals.
hosp_area.py now writes each run to its own folder; this rebuilds the affected areas that way.

  python site/hosp_redo.py find AREA          prints the hospital build folder (site/builds/hosp-*/) the area's page uses
  python site/hosp_redo.py marks AREA [...]    clears the areas' "published" marks (keeping the fresh h2 marks), so the
                                              next page run (pages_loop.py / hosp-areas.yml) republishes them through the audit gate
"""
import collections, json, os, subprocess, sys, boto3

HERE = os.path.dirname(os.path.abspath(__file__))
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                  region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = E['R2_BUCKET']


def builds_with(area):
    out = []
    for p in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix='site/builds/hosp-', Delimiter='/'):
        for c in p.get('CommonPrefixes', []):
            try:
                plan = json.loads(s3.get_object(Bucket=B, Key=c['Prefix'] + 'areas.json')['Body'].read())
            except Exception:
                continue
            if area in plan:
                out.append((plan[area].get('prefix', ''), c['Prefix']))
    return sorted(out)   # by the insurer build folder the hospital files sit next to; the newest last


if __name__ == '__main__':
    cmd, areas = sys.argv[1], sys.argv[2:]
    if cmd == 'find':
        b = builds_with(areas[0])
        if not b:
            sys.exit(f'{areas[0]}: no hospital build lists it')
        print(b[-1][1])
    elif cmd == 'marks':
        by = collections.defaultdict(list)
        for a in areas:
            b = builds_with(a)
            if not b:
                print(a, ': no hospital build lists it', flush=True); continue
            try:
                H = json.loads(s3.get_object(Bucket=B, Key=b[-1][0] + 'hosp/hosp_index.json')['Body'].read())
            except Exception:
                H = {}
            if H.get('h'):   # rebuilt into a fresh folder: republish it
                by[b[-1][1]].append(a)
            else:
                print(a, ': not rebuilt into a fresh folder, left as it is', flush=True)
        for sp, xs in by.items():
            build = sp.rstrip('/').rsplit('/', 1)[1]
            print('republish', build, xs, flush=True)
            subprocess.run([sys.executable, f'{HERE}/hosp_area.py', 'redo', *xs], check=True,
                           env={**os.environ, 'BUILD': build, 'KEEP_H2': '1'})
