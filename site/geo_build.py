"""Price Finder map: locations for one build (Oct 11, 2026). Runs in the monthly refresh (orchestrate.publish) and by hand.

Usage: python site/geo_build.py <page.html> <build-id>
  page.html  the merged Price Finder page for this build (D.fac order = R2 site/every/<build>/npis.json order)
Writes R2 site/every/<build>/geo.json, served at /price-finder/pf/geo.json by functions/price-finder/pf/geo.js.
Texas city pages (city_page.py, Oct 12, 2026) set GEO_NPIS_JSON (the city build's npis.json), GEO_OUT (where geo.json goes),
GEO_BBOX ("west,south,east,north" limits for accepting a location) and NPIS (the city's provider list).

Where locations come from (all public):
- Providers: practice address in the NPI file used for the build (env NPIS, default data/2026-09-29/dfw_npis_all.parquet),
  placed with the U.S. Census Bureau batch geocoder (benchmark Public_AR_Current). Suite/floor is dropped (same point).
- Hospitals and surgery centers the Census can't match: OpenStreetMap Nominatim structured search (1 request/second).
- Hospital price files and posted cash prices (no NPI on the page): matched by name and city to a placed facility; if no
  confident match, Nominatim search by name + city. Results kept only inside the DFW map area.
- ZIP codes for "near me": Census 2024 Gazetteer ZCTA internal points for all of Texas (R2 reference/geo/zcta_tx.json),
  kept to the map's area.
Cache: R2 reference/geo/cache.csv (address lookups) and reference/geo/names.json (name lookups), so each month only new
addresses are sent. Nothing about site visitors is involved.
"""
import csv, io, json, os, re, sys, time
from collections import Counter
import boto3, duckdb, requests

E = os.environ
page, BID = sys.argv[1], sys.argv[2]
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
B = E['R2_BUCKET']
UA = {'User-Agent': 'what-it-costs-price-map/1.0 (Texas healthcare price transparency site)'}
BBOX = tuple(float(x) for x in E['GEO_BBOX'].split(',')) if E.get('GEO_BBOX') else (-98.6, 31.6, -95.4, 34.2)   # lon/lat limits (default: DFW and the surrounding counties)
inside = lambda lat, lon: BBOX[1] <= lat <= BBOX[3] and BBOX[0] <= lon <= BBOX[2]
def log(*a): print(time.strftime('%H:%M:%S'), 'geo:', *a, flush=True)
def get(k):
    try: return s3.get_object(Bucket=B, Key=k)['Body'].read()
    except Exception: return None

D = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', open(page, encoding='utf-8').read(), re.S).group(1))
npis = json.loads(get(E.get('GEO_NPIS_JSON') or f'site/every/{BID}/npis.json'))
assert len(npis) == len(D['fac']), f"npis.json ({len(npis)}) and page providers ({len(D['fac'])}) differ"
os.makedirs('/tmp/geo', exist_ok=True)
s3.download_file(B, E.get('NPIS', 'data/2026-09-29/dfw_npis_all.parquet'), '/tmp/geo/npis.parquet')
addr = {r[0]: r[1:] for r in duckdb.connect().execute("select npi, address, city, zip5 from '/tmp/geo/npis.parquet'").fetchall()}

def norm(a, c, z):
    a = re.sub(r'\s+', ' ', (a or '').upper()).strip()
    a = re.sub(r'\s*(,|\b)(STE|SUITE|BLDG|BUILDING|FL|FLOOR|RM|ROOM|UNIT|#)\b\.?\s*[\w-]*\s*$', '', a).strip(' ,')
    return (a, (c or '').upper().strip(), (z or '')[:5])
key = {i: norm(*addr[n]) for i, n in enumerate(npis) if n in addr and addr[n][0]}

# ---------- address cache + Census batch ----------
FIELDS = ['address', 'city', 'zip', 'match', 'exact', 'matched', 'lat', 'lon']
cache = {}
raw = get('reference/geo/cache.csv')
if raw:
    for r in csv.DictReader(io.StringIO(raw.decode())): cache[(r['address'], r['city'], r['zip'])] = r
GST, GSTN = os.environ.get('GEO_STATE', 'TX'), os.environ.get('GEO_STATE_NAME', 'Texas')   # state pages (Oct 13, 2026)
todo = sorted({k for k in key.values() if k not in cache})
log('providers', len(npis), 'with address', len(key), 'cached addresses', len(cache), 'new', len(todo))
for i in range(0, len(todo), 2000):
    chunk = todo[i:i + 2000]; body = io.StringIO(); w = csv.writer(body)
    for j, (a, c, z) in enumerate(chunk): w.writerow([j, a, c, GST, z])
    text = None
    for attempt in range(4):
        try:
            r = requests.post('https://geocoding.geo.census.gov/geocoder/locations/addressbatch', files={'addressFile': ('a.csv', body.getvalue())},
                              data={'benchmark': 'Public_AR_Current'}, timeout=900)
            r.raise_for_status(); text = r.text; break
        except Exception as e: log('census retry', attempt, e); time.sleep(20 * (attempt + 1))
    if text is None: log('census geocoder unavailable; new addresses wait for next month'); break
    got = {}
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit(): continue
        m = row[2] if len(row) > 2 else 'No_Match'; lat = lon = ''
        if m == 'Match' and len(row) > 5 and ',' in row[5]: lon, lat = row[5].split(',')
        got[int(row[0])] = dict(match=m, exact=row[3] if m == 'Match' else '', matched=row[4] if m == 'Match' else '', lat=lat, lon=lon)
    for j, k in enumerate(chunk):
        cache[k] = dict(address=k[0], city=k[1], zip=k[2], **got.get(j, dict(match='No_Match', exact='', matched='', lat='', lon='')))
    log(f'census {min(i + 2000, len(todo))}/{len(todo)}')

def nomi(params):
    time.sleep(1.1)
    try: res = requests.get('https://nominatim.openstreetmap.org/search', headers=UA, timeout=30, params=dict(params, format='json', limit=1, countrycodes='us')).json()
    except Exception: return None
    if res and inside(float(res[0]['lat']), float(res[0]['lon'])): return round(float(res[0]['lat']), 5), round(float(res[0]['lon']), 5)
    return None
def street(a):
    a = re.sub(r'\bI\s*-?\s*(\d+)\b', r'Interstate \1', a.title(), flags=re.I)
    return re.sub(r'\bUs\b', 'US', re.sub(r'\b(Hwy|Highway)\b', 'Highway', a, flags=re.I))
# hospitals / surgery centers the Census missed (OSM), at most 120 per run
miss = [i for i, k in key.items() if D['fac'][i][2] in 'HA' and not cache[k]['lat'] and cache[k]['match'] != 'OSM_none'] if cache else []
for i in miss[:120]:
    k = key[i]; hit = None
    for s in (street(k[0]), k[0].title()):
        hit = nomi(dict(street=s, city=k[1].title(), state=GST, postalcode=k[2])) or nomi(dict(street=s, city=k[1].title(), state=GST))
        if hit: break
    cache[k] = dict(cache[k], match='OSM' if hit else 'OSM_none', lat=hit[0] if hit else '', lon=hit[1] if hit else '')
log('OpenStreetMap tried', min(len(miss), 120), 'facilities')
out = io.StringIO(); w = csv.DictWriter(out, FIELDS, extrasaction='ignore'); w.writeheader(); w.writerows(cache.values())
s3.put_object(Bucket=B, Key='reference/geo/cache.csv', Body=out.getvalue().encode())

# ---------- locations ----------
locs, lidx = [], {}
def loc(lat, lon):
    k = (round(float(lat), 5), round(float(lon), 5))
    if k not in lidx: lidx[k] = len(locs); locs.append(list(k))
    return lidx[k]
p = []
for i in range(len(npis)):
    g = cache.get(key.get(i)) if i in key else None
    p.append(loc(g['lat'], g['lon']) if g and g['lat'] and inside(float(g['lat']), float(g['lon'])) else -1)
placed = sum(1 for x in p if x >= 0)

# ---------- hospital price files + posted cash prices: match by name and city ----------
STOP = set('the of at and llc lp l p inc pllc pa ltd co company subsidiary dba a an texas tx health system systems hospitals'.split())
toks = lambda s: {t for t in re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split() if t not in STOP and len(t) > 1}
by_city = {}
for i, (nm, city, kind) in enumerate(D['fac']):
    if kind != 'P' and p[i] >= 0: by_city.setdefault(city.lower(), []).append((toks(nm), p[i]))
names = json.loads(get('reference/geo/names.json') or b'{}')
# hand-checked locations (site/geo_places.csv: CMS Hospital General Information, NPI Registry or OpenStreetMap, source in each row)
_pf = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geo_places.csv')
if os.path.exists(_pf):
    for r in csv.DictReader(open(_pf)): names[r['key']] = [float(r['lat']), float(r['lon'])]
def place(name, city, also=''):
    k = f'{name}|{city}'.lower()
    if k in names: return names[k]
    best, bl = 0, None
    for nm in (also, name):
        a = toks(nm)
        if not a: continue
        for t, li in by_city.get((city or '').lower(), []):
            sc = len(a & t) / len(a)
            if sc > best: best, bl = sc, locs[li]
    hit = bl if best >= 0.8 else None
    if not hit and city and 'multiple' not in city.lower():
        hit = nomi(dict(q=f'{also or name}, {city}, {GSTN}')) or (nomi(dict(q=f'{name}, {city}, {GSTN}')) if also else None)
    names[k] = list(hit) if hit else None
    if len(names) % 10 == 0: s3.put_object(Bucket=B, Key='reference/geo/names.json', Body=json.dumps(names, indent=0).encode())   # survive a timeout
    return names[k]
hn, nh = {}, 0
for s in D['hosp']['src']:
    g = place(s[0], s[1], s[2])
    if g: hn[f'{s[0]}|{s[1]}'.lower()] = loc(*g); nh += 1
cash, nc = {}, 0
for c in {(c['name'], c['city']) for c in D['cash']}:
    g = place(*c)
    if g: cash[f'{c[0]}|{c[1]}'.lower()] = loc(*g); nc += 1
s3.put_object(Bucket=B, Key='reference/geo/names.json', Body=json.dumps(names, indent=0).encode())

zips = json.loads(get(f'reference/geo/zcta_{GST.lower()}.json') or b'{}')   # every Texas ZIP (Census 2024 Gazetteer), kept to this map's area
zips = {z: v for z, v in zips.items() if BBOX[1] - .3 <= v[0] <= BBOX[3] + .3 and BBOX[0] - .3 <= v[1] <= BBOX[2] + .3}
geo = dict(build=BID, made=time.strftime('%Y-%m-%d'), locs=locs, p=p, hn=hn, cash=cash, zips=zips,
           stats=dict(providers=len(npis), placed=placed, hospital_files=len(D['hosp']['src']), hospital_files_placed=nh,
                      cash_places=len({(c['name'], c['city']) for c in D['cash']}), cash_places_placed=nc,
                      by_kind={k: [sum(1 for i, f in enumerate(D['fac']) if f[2] == k and p[i] >= 0), sum(1 for f in D['fac'] if f[2] == k)] for k in 'HAGP'}))
OUT = E.get('GEO_OUT') or f'site/every/{BID}/geo.json'
s3.put_object(Bucket=B, Key=OUT, Body=json.dumps(geo, separators=(',', ':')).encode(), ContentType='application/json')
log('wrote', OUT, 'placed', placed, 'of', len(npis), 'hospital files', nh, 'of', len(D['hosp']['src']), 'cash places', nc, 'locations', len(locs))
