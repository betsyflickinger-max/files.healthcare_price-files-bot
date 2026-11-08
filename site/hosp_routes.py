"""Hospital-price routes on every area's Price Finder (Nov 7, 2026). Usage: called by sitewide.apply(d) on every deploy.

San Angelo's page asks for its hospital lines (…/price-finder/pf/h/<code>.txt) but its deploy had no pf/h function, so no
hospital price ever loaded there (the robot tester found it; R2 had 3,350 hospital code files for the area). For each area
whose insurer route (functions/<area>/price-finder/pf/t/[code].js) points at an R2 build folder that also holds hospital
files (<build>/hosp/h/), this writes the matching pf/h function if it's missing, the same way city_page.py
does. Needs R2 credentials in the environment; without them it does nothing.
"""
import glob
import json
import os
import re


def repair(d):
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    if not (E['R2_ACCESS_KEY_ID'] and E['R2_SECRET_ACCESS_KEY']):
        return []
    import boto3
    s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                      aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                      region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
    B = E['R2_BUCKET'] or 'upfrontdfwdata'
    fixed = []
    for tf in glob.glob(os.path.join(d, 'functions', '**', 'price-finder', 'pf', 't', '[[]code[]].js'), recursive=True):
        hdir = os.path.join(os.path.dirname(os.path.dirname(tf)), 'h')
        if os.path.isfile(os.path.join(hdir, '[code].js')):
            continue
        js = open(tf, encoding='utf-8').read()
        m = re.search(r'const PREFIX = ("[^"]+")', js)
        if not m or "PREFIX + 't/' + code" not in js:
            continue
        pre = json.loads(m.group(1))
        try:   # the hospital code files themselves (San Angelo's build has hosp/h/ but no hosp_index.json)
            if not s3.list_objects_v2(Bucket=B, Prefix=pre + 'hosp/h/', MaxKeys=1).get('KeyCount'):
                continue      # no hospital files for this area: nothing to serve
        except Exception:
            continue
        os.makedirs(hdir, exist_ok=True)
        open(os.path.join(hdir, '[code].js'), 'w', encoding='utf-8').write(
            js.replace(m.group(1), json.dumps(pre + 'hosp/h/')).replace("PREFIX + 't/' + code", "PREFIX + code"))
        fixed.append(os.path.relpath(hdir, os.path.join(d, 'functions')))
    if fixed:
        print('hospital-price routes added:', ', '.join(fixed), flush=True)
    return fixed
