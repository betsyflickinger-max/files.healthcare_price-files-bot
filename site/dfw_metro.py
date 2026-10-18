"""Which DFW Price Finder cities are outside the Dallas-Fort Worth-Arlington metro area (Oct 18, 2026).

The metro area is the Census Bureau / OMB definition (OMB Bulletin 23-01, July 2023): 11 counties. The Price Finder's DFW area
is wider (ZIPs 750-753 and 760-762), so places like Gainesville, Corsicana and Sherman appear in it. Pages keep them and tag
them "outside the DFW metro".

How a city gets its county: each provider's map location (R2 site/every/<build>/geo.json, U.S. Census geocoder) is placed in a
county polygon from the Price Finder basemap (U.S. Census TIGERweb counties); a city takes the county most of its providers fall in.

Usage: python site/dfw_metro.py <price-finder page.html> <geo.json> <basemap.json>   -> writes site/dfw_metro.json
"""
import collections
import json
import os
import re
import sys

MSA = ['Collin', 'Dallas', 'Denton', 'Ellis', 'Hunt', 'Kaufman', 'Rockwall', 'Johnson', 'Parker', 'Tarrant', 'Wise']
SRC = ('Dallas-Fort Worth-Arlington, TX Metropolitan Statistical Area, OMB Bulletin 23-01 (July 2023), via the Census Bureau '
       'delineation files: https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html')


def norm(city):
    return re.sub(r'[^a-z]+', ' ', (city or '').lower()).strip()


def inside(pt, ring):
    x, y = pt
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i - 1]
        x2, y2 = ring[i]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def county_of(lat, lon, counties):
    for c in counties:
        polys = [c['g']] if c['t'] == 'Polygon' else c['g']
        for p in polys:
            if inside((lon, lat), p[0]) and not any(inside((lon, lat), h) for h in p[1:]):
                return c['name']
    return None


def main(page, geo, basemap):
    s = open(page, encoding='utf-8').read()
    D = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', s, re.S).group(1))
    G = json.load(open(geo))
    counties = json.load(open(basemap))['counties']
    votes = collections.defaultdict(collections.Counter)
    cache = {}
    for i, f in enumerate(D['fac']):
        li = G['p'][i] if i < len(G['p']) else -1
        if li < 0:
            continue
        if li not in cache:
            lat, lon = G['locs'][li]
            cache[li] = county_of(lat, lon, counties)
        if cache[li]:
            votes[norm(f[1])][cache[li]] += 1
    city_county = {c: v.most_common(1)[0][0] for c, v in votes.items() if c}
    outside = {c: k for c, k in sorted(city_county.items()) if k not in MSA}
    out = dict(msa_counties=MSA, source=SRC, outside=outside,
               method='city = county most of its providers are mapped to (Census geocoder points, TIGERweb county shapes)')
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dfw_metro.json')
    json.dump(out, open(p, 'w'), indent=1, sort_keys=True)
    print(len(city_county), 'cities placed;', len(outside), 'outside the metro:', ', '.join(f'{c} ({k})' for c, k in outside.items()))


if __name__ == '__main__':
    main(*sys.argv[1:4])
