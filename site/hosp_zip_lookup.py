"""Oct 31, 2026: hospitals in a state's hospital plan whose ZIP isn't known (long-term care and rehab hospitals aren't on
Medicare's Hospital General Information list): look each one up in the federal NPI Registry (NPPES API) by name, in the
state, as an organization. Prints every candidate; writes data/hospital_zip_extra.csv rows only for an exact name match
(punctuation and case aside) that is unique. Read-only on R2. Usage: python site/hosp_zip_lookup.py california CA SP"""
import csv, json, os, re, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import regions, region_split as rs
slug, st, sp = sys.argv[1:4]
s3 = rs.s3c(); B = rs.B
plan = json.loads(s3.get_object(Bucket=B, Key=sp + 'areas.json')['Body'].read())
src = {x[5]: x[0] for x in json.loads(s3.get_object(Bucket=B, Key=plan[slug]['prefix'] + 'hosp/hosp_index.json')['Body'].read())['src'] if len(x) > 5}
norm = lambda s: re.sub(r'[^a-z0-9]+', ' ', (s or '').lower().replace('rehabilitaton', 'rehabilitation')).strip()
out = []
POS = 'https://data.cms.gov/data-api/v1/dataset/8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5/data'   # Provider of Services, hospital & non-hospital
for j in plan[slug]['jobs']:
    if regions.region_of_zip(slug, j.get('zip')): continue
    # 1) CMS Provider of Services file (every Medicare provider by its CMS number, long-term care and rehab hospitals included)
    pos = None
    if j.get('ccn'):
        try:
            u = POS + '?' + urllib.parse.urlencode({'filter[PRVDR_NUM]': j['ccn'], 'size': 5})
            rows = json.loads(urllib.request.urlopen(u, timeout=60).read())
            rows = [r for r in rows if r.get('PRVDR_NUM') == j['ccn'] and (r.get('ZIP_CD') or '')[:5]]
            if rows: pos = rows[0]
        except Exception as e: print('  POS lookup failed', j['ccn'], e)
    if pos:
        z = pos['ZIP_CD'][:5]
        print(f"{j.get('name')} | ccn {j.get('ccn')} | POS: {pos.get('FAC_NAME')}, {pos.get('CITY_NAME')} {z} -> {z}")
        out.append({'state': st, 'ccn': j['ccn'], 'name': j.get('name', ''), 'zip': z, 'npi': '', 'region': regions.region_of_zip(slug, z) or '',
                    'source': f"CMS Provider of Services file ({pos.get('FAC_NAME')}, {pos.get('CITY_NAME')})"}); continue
    names = {norm(j.get('name')), norm(src.get(j.get('id')))} - {''}
    cands = {}
    for nm in names:
        words = nm.split()[:3]
        q = urllib.parse.urlencode({'version': '2.1', 'organization_name': ' '.join(words) + '*', 'state': st, 'enumeration_type': 'NPI-2', 'limit': 200})
        try: res = json.loads(urllib.request.urlopen('https://npiregistry.cms.hhs.gov/api/?' + q, timeout=60).read()).get('results', [])
        except Exception as e: print('  lookup failed', nm, e); res = []
        for r in res:
            a = next((a for a in r.get('addresses', []) if a.get('address_purpose') == 'LOCATION'), {})
            tx = next((t for t in r.get('taxonomies', []) if t.get('primary')), {})
            cands[r['number']] = (r['basic'].get('organization_name', ''), a.get('city', ''), (a.get('postal_code') or '')[:5], tx.get('desc', ''), r['basic'].get('status', ''))
        time.sleep(0.3)
    exact = {n: c for n, c in cands.items() if norm(c[0]) in names and c[2]}
    zips = {c[2] for c in exact.values()}
    pick = next(iter(zips)) if len(zips) == 1 else ''
    print(f"{j.get('name')} | ccn {j.get('ccn')} | exact matches {len(exact)} {sorted(zips)} -> {pick or 'NOT PLACED'}")
    for n, c in list(cands.items())[:8]: print('    ', n, c)
    if pick:
        ex = next(n for n, c in exact.items() if c[2] == pick)
        out.append({'state': st, 'ccn': j.get('ccn', ''), 'name': j.get('name', ''), 'zip': pick, 'npi': ex, 'region': regions.region_of_zip(slug, pick) or '',
                    'source': 'NPI Registry location address, exact organization name match'})
print(len(out), 'placed by exact NPI Registry name')
print('CSV:'); w = csv.DictWriter(sys.stdout, fieldnames=['state', 'ccn', 'name', 'zip', 'npi', 'region', 'source']); w.writeheader(); w.writerows(out)
