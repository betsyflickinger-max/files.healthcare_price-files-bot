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
- ZIP codes for "near me": Census 2024 Gazetteer ZCTA internal points for all of Texas (R2 reference/geo/zcta_tx.json), or for
  the whole U.S. (reference/geo/zcta_us.json) on pages outside Texas, kept to the map's area.
Cache: R2 reference/geo/cache.csv (address lookups) and reference/geo/names.json (name lookups), so each month only new
addresses are sent. Nothing about site visitors is involved.
"""
import csv, io, json, math, os, re, sys, time
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
# ---------- hospital price files: Medicare's own street address (Oct 15, 2026) ----------
# Each hospital file is tied to a Medicare ID (CCN) in data/hospitals.csv (by the file's fingerprint, else its URL); Medicare's
# Hospital General Information file gives that hospital's street address, which is geocoded like any provider address. A file
# without a known CCN is matched to Medicare's list by name within its city. Works for every state, not a hand list.
HERE = os.path.dirname(os.path.abspath(__file__))
HGI_URL = ('https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1785189955/'
           'Hospital_General_Information.csv')   # July 22, 2026 release; a copy is kept in R2 reference/geo/hgi.csv
raw = get('reference/geo/hgi.csv')
if not raw:
    try: raw = requests.get(HGI_URL, timeout=120).content; s3.put_object(Bucket=B, Key='reference/geo/hgi.csv', Body=raw)
    except Exception as e: log('Medicare hospital list unavailable:', e); raw = b''
HGI = {r['Facility ID']: r for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))} if raw else {}
HROWS = list(csv.DictReader(open(os.path.join(HERE, '..', 'data', 'hospitals.csv')))) if os.path.exists(os.path.join(HERE, '..', 'data', 'hospitals.csv')) else []
BY_SHA = {r['last_sha256'][:16]: r['ccn'] for r in HROWS if r.get('last_sha256')}
BY_URL = {r['mrf_url']: r['ccn'] for r in HROWS if r.get('mrf_url')}
ZC = json.loads(get('reference/geo/zcta_us.json') or b'{}')   # ZIP code center points, to check every hospital location found
STOPH = set('the of at and llc lp inc ltd co dba a an health hospital hospitals medical center system systems regional campus'.split())
htoks = lambda s: {t for t in re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split() if t not in STOPH and len(t) > 1}
HGI_CITY = {}
for c_, r in HGI.items(): HGI_CITY.setdefault((r['City/Town'].upper(), r['State']), []).append((htoks(r['Facility Name']), c_))
def ccn_of(src):
    c = BY_SHA.get(src[5]) if len(src) > 5 else None
    c = c or BY_URL.get(src[4] if len(src) > 4 else '')
    if c in HGI: return c, True
    best, bc = 0, None   # no known CCN: the Medicare hospital in the same city whose name shares the most words
    for nm in (src[0], *(src[2] or '').split(' · ')):
        a = htoks(nm)
        if not a: continue
        for t, c_ in HGI_CITY.get(((src[1] or '').upper(), GST), []):
            sc = len(a & t) / max(len(a), len(t))
            if sc > best: best, bc = sc, c_
    return (bc, False) if best >= 0.6 else (c, False)
KST = {}
HKEY = {}   # file id -> (CCN, address key, CCN came from the file's own fingerprint or URL)
for s_ in D['hosp']['src']:
    c, exact = ccn_of(s_)
    if c in HGI:
        h = HGI[c]; k = norm(h['Address'], h['City/Town'], h['ZIP Code'])
        HKEY[s_[5] if len(s_) > 5 else s_[0]] = (c, k, exact); KST[k] = h['State']
# the address each price file gives for itself (CMS requires hospital_address and type_2_npi in every file), read from the parsed
# rows (R2 data/hosp_every/rows/<id>.parquet, one row, ~2 s) once per file and remembered in names.json as "file:<id>"
names = json.loads(get('reference/geo/names.json') or b'{}')
def parse_addrs(a):   # every street address the file lists (some list each campus); P.O. boxes are billing addresses, skipped
    out = []
    for x in re.split(r'\s*[|;]\s*|\s*\n\s*|"\s*,\s*"', (a or '').strip().strip('[]"')):
        m = re.search(r'^(.*?),\s*([^,]+?),\s*([A-Z]{2})\b,?\s*(\d{5})', x.strip().strip('"'))
        if m and not re.search(r'\bP\.?\s*O\.?\s*BOX\b|\bPOB\b', m.group(1), re.I): out.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return out
FADDR, FALL, FNPI, FRAW = {}, {}, {}, {}
need = [s_[5] for s_ in D['hosp']['src'] if len(s_) > 5 and f'file:{s_[5]}' not in names]
if need:
    try:
        con = duckdb.connect(); con.execute('INSTALL httpfs; LOAD httpfs;')
        con.execute(f"CREATE SECRET r2 (TYPE R2, KEY_ID '{E['R2_ACCESS_KEY_ID'].strip()}', SECRET '{E['R2_SECRET_ACCESS_KEY'].strip()}', ACCOUNT_ID '{E['R2_ACCOUNT_ID'].strip()}')")
        for sid in need:
            try: r = con.execute(f"select hospital_address, type_2_npi from 'r2://{B}/data/hosp_every/rows/{sid}.parquet' limit 1").fetchone()
            except Exception: r = None
            names[f'file:{sid}'] = list(r) if r else ['', '']
        log('read the address in', len(need), 'hospital price files')
    except Exception as e: log('could not read hospital files for their addresses:', e)
for s_ in D['hosp']['src']:
    if len(s_) < 6 or not names.get(f'file:{s_[5]}'): continue
    a, npi = names[f'file:{s_[5]}']
    pas = parse_addrs(a)
    if pas: pa = pas[0]; k = norm(pa[0], pa[1], pa[3]); FADDR[s_[5]] = (k, pa[2], pa[3]); KST[k] = pa[2]
    # every state + ZIP the file names (also addresses written without a comma before the city), for the wrong-file check
    zs = [(m.group(1), m.group(2)) for part in re.split(r'\s*[|;]\s*', a or '') if not re.search(r'P\.?\s*O\.?\s*BOX', part, re.I)
          for m in re.finditer(r'\b([A-Z]{2})\b,?\s+(\d{5})', part)]
    if zs: FALL[s_[5]] = zs; FRAW[s_[5]] = re.sub(r'\s+', ' ', a)[:120]
    n1 = re.findall(r'\d{10}', npi or '')
    if n1: FNPI[s_[5]] = n1
todo = sorted({k for k in list(key.values()) + [v[1] for v in HKEY.values()] + [v[0] for v in FADDR.values()] if k not in cache})
log('providers', len(npis), 'with address', len(key), 'cached addresses', len(cache), 'new', len(todo))
for i in range(0, len(todo), 2000):
    chunk = todo[i:i + 2000]; body = io.StringIO(); w = csv.writer(body)
    for j, (a, c, z) in enumerate(chunk): w.writerow([j, a, c, KST.get((a, c, z), GST), z])
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

NOMI = {'err': False}
def nomi(params):
    time.sleep(1.1)
    try: res = requests.get('https://nominatim.openstreetmap.org/search', headers=UA, timeout=30, params=dict(params, format='json', limit=1, countrycodes='us')).json()
    except Exception: NOMI['err'] = True; return None
    # an error reply comes back as a dict, not a list (Oct 15, 2026: that crashed Mississippi's map); treat it as no match
    if isinstance(res, list) and res and inside(float(res[0]['lat']), float(res[0]['lon'])): return round(float(res[0]['lat']), 5), round(float(res[0]['lon']), 5)
    if not isinstance(res, list): log('OpenStreetMap lookup error:', str(res)[:120]); NOMI['err'] = True
    return None
def nomi_any(params):
    time.sleep(1.1)
    try: res = requests.get('https://nominatim.openstreetmap.org/search', headers=UA, timeout=30, params=dict(params, format='json', limit=1, countrycodes='us')).json()
    except Exception: NOMI['err'] = True; return None
    if not isinstance(res, list): NOMI['err'] = True; return None
    return (round(float(res[0]['lat']), 5), round(float(res[0]['lon']), 5)) if res else None
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
# hand-checked locations (site/geo_places.csv: CMS Hospital General Information, NPI Registry or OpenStreetMap, source in each row)
_pf = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geo_places.csv')
HAND = {}
if os.path.exists(_pf):
    for r in csv.DictReader(open(_pf)): HAND[r['key'].strip().lower()] = names[r['key'].strip().lower()] = [float(r['lat']), float(r['lon'])]
def near_zip(g, z, miles_=15):   # a location found by search must be within ~15 miles of the hospital's ZIP code center
    c = ZC.get((z or '')[:5])
    if not c or not g: return bool(g)
    t = math.pi / 180; dl = (g[0] - c[0]) * t; dn = (g[1] - c[1]) * t
    h = math.sin(dl / 2) ** 2 + math.cos(g[0] * t) * math.cos(c[0] * t) * math.sin(dn / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h)) <= miles_
WHY = {}   # why a hospital file couldn't be placed, for the hand list (reference/geo/unplaced/)
def place_hosp(src):
    """hand-checked (site/geo_places.csv, by "ccn:<CCN>" or "name|city") > Medicare's address for the file's own CCN > the address
    the file gives for itself (or its NPI's NPPES address) > Medicare's address for a CCN matched by name > the older name matching.
    Official addresses are geocoded (Census, then OpenStreetMap by street) and may sit outside the map's frame if in the page's state;
    anything found by searching a name must be within ~15 miles of the hospital's ZIP code."""
    name, city = src[0], src[1]; sid = src[5] if len(src) > 5 else name
    c, k, exact = HKEY.get(sid, (None, None, False))
    if c and f'ccn:{c}' in HAND: return HAND[f'ccn:{c}']
    if f'{name}|{city}'.lower() in HAND: return HAND[f'{name}|{city}'.lower()]
    def official(k, st, z, nk, label=None):
        g = cache.get(k) or {}
        ok = lambda pt: pt and (inside(*pt) or (st == GST and near_zip(pt, z, 25)))
        if g.get('lat') and ok([float(g['lat']), float(g['lon'])]): return [float(g['lat']), float(g['lon'])]
        if names.get(nk) and ok(names[nk]): return names[nk]
        if nk not in names:
            NOMI['err'] = False
            hit = nomi_any(dict(street=street(k[0]), city=k[1].title(), state=st, postalcode=z))
            hit = hit if hit and near_zip(hit, z) else None
            if not hit and label:   # then the hospital's name in its town (Medicare's spelling), same ZIP check
                hit = nomi_any(dict(q=f'{label}, {k[1].title()}, {st}'))
                hit = hit if hit and near_zip(hit, z) else None
            if hit or not NOMI['err']: names[nk] = list(hit) if hit else None   # a busy or failed lookup is tried again next time
            return hit
        return None
    # a price file whose own address is far from Medicare's address for the hospital it is filed under belongs to another
    # hospital (Oct 15, 2026: e.g. "Baytown Medical Center" filed with Boston Medical Center's file). Not placed; flagged.
    if c and exact and sid in FALL:
        h = HGI[c]
        same = lambda st, z: st == h['State'] and (not ZC.get(z) or not ZC.get(h['ZIP Code'][:5]) or near_zip(ZC[z], h['ZIP Code'], 30))
        if not any(same(st, z) for st, z in FALL[sid]):
            WHY[name] = (f"WRONG FILE? this price file gives its address as {FRAW[sid]}, but Medicare's address "
                         f"for CCN {c} is {h['Address']}, {h['City/Town']} {h['State']}; fix data/hospitals.csv")
            return None
    tries = []
    if c and exact: tries.append(('ccn', c))
    if sid in FADDR: tries.append(('file', sid))
    if sid in FNPI: tries.append(('npi', sid))
    if c and not exact: tries.append(('ccn', c))
    for kind, v in tries:
        if kind == 'ccn':
            h = HGI[v]; g = official(k, h['State'], h['ZIP Code'], f'ccn:{v}', h['Facility Name'].title())
        elif kind == 'file':
            fk, st, z = FADDR[v]; g = official(fk, st, z, f'faddr:{v}', name)
        else:
            g = None
            for n in FNPI[v]:
                if n in addr and addr[n][0]:
                    nk_ = norm(*addr[n]); cg = cache.get(nk_) or {}
                    if cg.get('lat') and inside(float(cg['lat']), float(cg['lon'])): g = [float(cg['lat']), float(cg['lon'])]; break
        if g: return g
    if c:
        h = HGI[c]
        if h['State'] != GST: WHY[name] = f"Medicare lists this hospital (CCN {c}) in {h['State']}, not this page's state; check the file is the right hospital's"
        else: WHY[name] = f"address not found: {h['Address']}, {h['City/Town']} {h['State']} {h['ZIP Code']}"
    elif sid in FADDR: WHY[name] = 'the address in the price file was not found: ' + ', '.join(FADDR[sid][0])
    else: WHY[name] = 'no Medicare ID (CCN) and no address in the file'
    g = place(name, city, src[2] if len(src) > 2 else '')
    if g: WHY.pop(name, None)
    return g
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
        alt = (also or '').split(' · ')[0]   # several other names come joined by " · "; the search takes one (a long one is refused)
        hit = nomi(dict(q=f'{alt or name}, {city}, {GSTN}')) or (nomi(dict(q=f'{name}, {city}, {GSTN}')) if alt else None)
    names[k] = list(hit) if hit else None
    if len(names) % 10 == 0: s3.put_object(Bucket=B, Key='reference/geo/names.json', Body=json.dumps(names, indent=0).encode())   # survive a timeout
    return names[k]
hn, nh = {}, 0
for s in D['hosp']['src']:
    g = place_hosp(s)
    if g: hn[f'{s[0]}|{s[1]}'.lower()] = loc(*g); nh += 1
# the hand list: every hospital file still off the map, with Medicare's address and why (site/unplaced_report.py gathers them)
unplaced = []
for s in D['hosp']['src']:
    if f'{s[0]}|{s[1]}'.lower() in hn: continue
    c = HKEY.get(s[5] if len(s) > 5 else s[0], (None,))[0]; h = HGI.get(c) or {}
    fa = FADDR.get(s[5] if len(s) > 5 else '')
    unplaced.append(dict(name=s[0], city=s[1], ccn=c or '', key=f'{s[0]}|{s[1]}'.lower(), why=WHY.get(s[0], 'not found'),
                         address=f"{h['Address']}, {h['City/Town']}, {h['State']} {h['ZIP Code']}" if h else (f"{fa[0][0]}, {fa[0][1]}, {fa[1]} {fa[2]}" if fa else '')))
cash, nc = {}, 0
for c in {(c['name'], c['city']) for c in D['cash']}:
    g = place(*c)
    if g: cash[f'{c[0]}|{c[1]}'.lower()] = loc(*g); nc += 1
s3.put_object(Bucket=B, Key='reference/geo/names.json', Body=json.dumps(names, indent=0).encode())

# ZIP codes for "near me": the state's own file when there is one (zcta_tx.json), otherwise every U.S. ZIP code (zcta_us.json,
# Census 2024 Gazetteer, Oct 15, 2026; state pages had no ZIP list before this). Either way kept to this map's area.
zips = json.loads(get(f'reference/geo/zcta_{GST.lower()}.json') or get('reference/geo/zcta_us.json') or b'{}')
zips = {z: v for z, v in zips.items() if BBOX[1] - .3 <= v[0] <= BBOX[3] + .3 and BBOX[0] - .3 <= v[1] <= BBOX[2] + .3}
geo = dict(build=BID, made=time.strftime('%Y-%m-%d'), locs=locs, p=p, hn=hn, cash=cash, zips=zips, unplaced=unplaced,
           stats=dict(providers=len(npis), placed=placed, hospital_files=len(D['hosp']['src']), hospital_files_placed=nh,
                      cash_places=len({(c['name'], c['city']) for c in D['cash']}), cash_places_placed=nc,
                      by_kind={k: [sum(1 for i, f in enumerate(D['fac']) if f[2] == k and p[i] >= 0), sum(1 for f in D['fac'] if f[2] == k)] for k in 'HAGP'}))
OUT = E.get('GEO_OUT') or f'site/every/{BID}/geo.json'
s3.put_object(Bucket=B, Key=OUT, Body=json.dumps(geo, separators=(',', ':')).encode(), ContentType='application/json')
log('wrote', OUT, 'placed', placed, 'of', len(npis), 'hospital files', nh, 'of', len(D['hosp']['src']), 'cash places', nc, 'locations', len(locs))
