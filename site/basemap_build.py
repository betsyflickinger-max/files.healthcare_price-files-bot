"""Price Finder map background (Oct 12, 2026): counties, roads, lakes and city names for one area, from U.S. Census TIGERweb.

Usage: python site/basemap_build.py <geo.json> <page.html> <out basemap.json>
  geo.json   the area's map locations (geo_build.py); the map covers where most of its providers are (1st-99th percentile + margin)
  page.html  the area's Price Finder page: city names are labeled by how many providers on the page list that city
Same layers as the DFW map: county lines; primary roads (interstates, toll roads) and U.S./state highways; named lakes and
reservoirs over 1 km2; incorporated places with providers. Road markers (I-35, US 75, SH 121, tollways) are placed along
long stretches, one per ~0.14 degrees. Read by /price-finder/map.js."""
import json, math, re, sys, time
from collections import Counter
import requests

geo_path, page, out = sys.argv[1:4]
G = json.load(open(geo_path))
pts = sorted(G['locs'])
if len(pts) < 20: sys.exit('too few placed providers for a map')
la = sorted(p[0] for p in pts); lo = sorted(p[1] for p in pts); q = lambda a, f: a[int(f * (len(a) - 1))]
bb = [round(q(lo, .01) - .12, 4), round(q(la, .01) - .12, 4), round(q(lo, .99) + .12, 4), round(q(la, .99) + .12, 4)]
D = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', open(page, encoding='utf-8').read(), re.S).group(1))
TW = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb'


def query(svc, layer, fields, where='1=1', offset=0.002, geom=True):
    res, start = [], 0
    while True:
        for attempt in range(4):
            try:
                r = requests.get(f'{TW}/{svc}/MapServer/{layer}/query', timeout=150, params=dict(
                    where=where, geometry=','.join(map(str, bb)), geometryType='esriGeometryEnvelope', inSR=4326, spatialRel='esriSpatialRelIntersects',
                    outFields=fields, returnGeometry='true' if geom else 'false', outSR=4326, maxAllowableOffset=offset,
                    f='geojson' if geom else 'json', resultOffset=start, resultRecordCount=1000)).json(); break
            except Exception as e:
                print('tigerweb retry', attempt, e, flush=True); time.sleep(15 * (attempt + 1))
        else: raise SystemExit('TIGERweb unavailable')
        res += r.get('features', [])
        if not r.get('exceededTransferLimit') and not r.get('properties', {}).get('exceededTransferLimit'): return res
        start += 1000


def rnd(g): return [rnd(x) for x in g] if isinstance(g[0], list) else [round(g[0], 4), round(g[1], 4)]
def nm(n):
    n = re.sub(r'\bI- ?(\d)', r'I-\1', n or ''); n = re.sub(r'^Lk (.*)$', r'Lake \1', n); n = re.sub(r' Lk$', ' Lake', n)
    n = re.sub(r'\bTpke\b', 'Turnpike', n); n = n.replace('Mtn ', 'Mountain ')
    return n.strip()


counties = [dict(name=f['properties']['BASENAME'], g=rnd(f['geometry']['coordinates']), t=f['geometry']['type'])
            for f in query('State_County', 1, 'BASENAME', offset=0.003) if f.get('geometry')]
roads = []
for layer, cls, where, off in ((2, 'p', '1=1', 0.0012), (5, 's', "RTTYP in ('U','S')", 0.0015)):
    for f in query('Transportation', layer, 'NAME,RTTYP', where=where, offset=off):
        g = f.get('geometry')
        if not g: continue
        for s in ([g['coordinates']] if g['type'] == 'LineString' else g['coordinates']):
            if len(s) > 1: roads.append(dict(name=nm(f['properties'].get('NAME')), c=cls, g=rnd(s), t='LineString'))
water, wl = [], {}
for f in query('Hydro', 1, 'NAME,AREAWATER', where='AREAWATER > 1000000', offset=0.0015):
    n = nm(f['properties'].get('NAME'))
    if not f.get('geometry') or not re.search(r'Lake|Reservoir|Bay$', n): continue
    water.append(dict(g=rnd(f['geometry']['coordinates']), t=f['geometry']['type']))
    flat = []; (lambda w: w(w, f['geometry']['coordinates']))(lambda w, a: flat.append(a) if isinstance(a[0], (int, float)) else [w(w, x) for x in a])
    a = f['properties'].get('AREAWATER') or 0
    if n not in wl or a > wl[n][0]:
        xs = [p[0] for p in flat]; ys = [p[1] for p in flat]; wl[n] = (a, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
wlabels = [dict(name=n, lon=round(v[1], 4), lat=round(v[2], 4), a=v[0]) for n, v in sorted(wl.items(), key=lambda x: -x[1][0])]
cands = []
for r in roads:
    n = re.sub(r'^I-(\d+) ([EW])$', r'I-\1\2', r['name']).replace('US Hwy ', 'US ').replace('State Hwy ', 'SH ')
    n = re.sub(r' [NSEW]$', '', n)
    if 'Bus' in n or not (re.match(r'^(I-\d|US \d|SH \d|Loop \d)', n) or re.search(r'Tollway|Turnpike', n)): continue
    g = r['g']; L = sum(math.hypot(g[k + 1][0] - g[k][0], g[k + 1][1] - g[k][1]) for k in range(len(g) - 1))
    if L >= 0.04: cands.append((r['c'] == 'p', L, n, g[len(g) // 2]))
lab, seen = [], set()
for p, L, n, m in sorted(cands, key=lambda x: (-x[0], -x[1])):
    cell = (n, round(m[0] / 0.14), round(m[1] / 0.14))
    if cell in seen or any(abs(m[0] - l['lon']) < .07 and abs(m[1] - l['lat']) < .07 for l in lab): continue
    seen.add(cell); lab.append(dict(name=n, lon=m[0], lat=m[1], p=int(p)))
cnt = Counter(f[1].upper() for f in D['fac'])
pl = [dict(name=a['BASENAME'], lat=float(a['INTPTLAT']), lon=float(a['INTPTLON']), n=cnt.get(a['BASENAME'].upper(), 0))
      for a in (f['attributes'] for f in query('Places_CouSub_ConCity_SubMCD', 4, 'BASENAME,INTPTLAT,INTPTLON', geom=False))]
pl = sorted(pl, key=lambda p: -p['n'])
pl = [p for p in pl if p['n'] >= (10 if sum(1 for x in pl if x['n'] >= 10) >= 25 else 2)]
json.dump(dict(bbox=bb, counties=counties, water=water, wlabels=wlabels, roads=roads, rlabels=lab, places=pl,
               source='U.S. Census Bureau TIGERweb (counties, primary and secondary roads, lakes, incorporated places), retrieved ' + time.strftime('%Y-%m-%d')),
          open(out, 'w'), separators=(',', ':'))
print('basemap', len(counties), 'counties', len(roads), 'road pieces', len(water), 'lakes', len(lab), 'road markers', len(pl), 'city names', flush=True)
