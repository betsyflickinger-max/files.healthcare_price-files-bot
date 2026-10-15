"""Hand list of hospital price files that aren't on any Price Finder map (Oct 15, 2026).

Usage: python site/unplaced_report.py            writes reports/unplaced_hospitals.csv (and R2 reference/geo/unplaced_hospitals.csv)

geo_build.py places each hospital file by Medicare's street address for its CCN (Hospital General Information), then
OpenStreetMap, each checked against the hospital's ZIP code. What's left is listed here, one row per file, with Medicare's
address, why it failed and a Google Maps search link.

To pin one by hand: open the link, right-click the hospital's building in Google Maps and click the coordinates at the top of
the menu (copies "lat, lon"), then add a row to site/geo_places.csv:
    ccn:<CCN>,<lat>,<lon>,"<where the location came from>"      (works for every file of that hospital, in any state)
or, when there is no CCN, use the row's geo_places_key ("name|city") as the key. The next map build picks it up.
Rows whose reason starts "WRONG FILE?" or says "Medicare lists this hospital in <state>" mean the price file was matched to the wrong
hospital:
fix data/hospitals.csv rather than pinning.
"""
import csv, io, json, os, sys, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boto3
from city_page import CITIES, root

E = os.environ
s3 = boto3.client('s3', endpoint_url=f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com",
                  aws_access_key_id=''.join(E['R2_ACCESS_KEY_ID'].split()), aws_secret_access_key=''.join(E['R2_SECRET_ACCESS_KEY'].split()),
                  region_name='auto')
B = E.get('R2_BUCKET', 'upfrontdfwdata')
def get(k):
    try: return s3.get_object(Bucket=B, Key=k)['Body'].read()
    except Exception: return None
def newest(area):
    dirs = [c['Prefix'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=f'{root(area)}{area}/', Delimiter='/')
            for c in pg.get('CommonPrefixes', [])]
    best = None
    for d in dirs:
        try: t = s3.head_object(Bucket=B, Key=d + 'geo.json')['LastModified']
        except Exception: continue
        if best is None or t > best[0]: best = (t, d)
    return best[1] + 'geo.json' if best else None

areas = [('dfw', 'site/every/' + (get('site/every/CURRENT') or b'2026-10-08').decode().strip() + '/geo.json')] + [(a, newest(a)) for a in CITIES]
rows, tot = [], 0
for area, k in areas:
    g = json.loads(get(k) or b'{}') if k else {}
    if not g: print(f'{area}: no map yet'); continue
    tot += g['stats'].get('hospital_files', 0)
    if 'unplaced' not in g: print(f'{area}: map made before the hand list existed (rebuild with city_page.py {area} --map-only)'); continue
    for u in g['unplaced']:
        q = u['address'] or f"{u['name']} {u['city']}"
        rows.append(dict(area=area, hospital=u['name'], city=u['city'], ccn=u['ccn'], medicare_address=u['address'], why=u['why'],
                         google_maps='https://www.google.com/maps/search/?api=1&query=' + urllib.parse.quote(f"{u['name']}, {q}"),
                         geo_places_key=f"ccn:{u['ccn']}" if u['ccn'] else u['key']))
os.makedirs(os.path.join(HERE, '..', 'reports'), exist_ok=True)
out = io.StringIO(); w = csv.DictWriter(out, ['area', 'hospital', 'city', 'ccn', 'medicare_address', 'why', 'google_maps', 'geo_places_key'])
w.writeheader(); w.writerows(rows)
open(os.path.join(HERE, '..', 'reports', 'unplaced_hospitals.csv'), 'w').write(out.getvalue())
s3.put_object(Bucket=B, Key='reference/geo/unplaced_hospitals.csv', Body=out.getvalue().encode(), ContentType='text/csv')
print(f'{len(rows)} of {tot} hospital price files not on a map; list in reports/unplaced_hospitals.csv')
