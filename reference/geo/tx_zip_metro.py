"""Makes tx_zip_metro.csv: every "rest of Texas" ZIP area -> county -> metro area page (Oct 12, 2026).

Rest of Texas = Texas 3-digit ZIP areas 733, 750-799 and 885, except DFW 750-753/760-762, Houston 770-775, San Antonio 780-782,
Austin 786-787 and El Paso 798-799 (as site/tx_split.py). Each Census ZIP area (ZCTA) goes to the county holding most of its
land, then to that county's metropolitan area (CBSA). Only the 18 metros below get their own page; every other ZIP
(micropolitan areas, counties in no metro) is "small-towns". A provider ZIP that is not a Census ZIP area (PO boxes, single
buildings) is not listed and also goes to small-towns.

  python reference/geo/tx_zip_metro.py tab20_zcta520_county20_natl.txt list1_2023.xlsx > reference/geo/tx_zip_metro.csv

Sources (downloaded Oct 12, 2026):
  https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt   2020 ZCTA-to-county relationship file
  https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx
      CBSA delineation file, list 1, July 2023 (OMB Bulletin 23-01)"""
import csv, sys, openpyxl

SLUGS = {'32580': 'mcallen', '28660': 'killeen-temple', '15180': 'brownsville-harlingen', '18580': 'corpus-christi',
         '13140': 'beaumont-port-arthur', '31180': 'lubbock', '47380': 'waco', '30980': 'longview', '17780': 'college-station-bryan',
         '11100': 'amarillo', '46340': 'tyler', '10180': 'abilene', '33260': 'midland', '36220': 'odessa', '48660': 'wichita-falls',
         '45500': 'texarkana', '41660': 'san-angelo', '47020': 'victoria'}
CITY3 = [('750', '753'), ('760', '762'), ('770', '775'), ('780', '782'), ('786', '787'), ('798', '799')]
def rest(z): return (z[:3] == '733' or '750' <= z[:3] <= '799' or z[:3] == '885') and not any(a <= z[:3] <= b for a, b in CITY3)

rel, xlsx = sys.argv[1:3]
best = {}   # zcta -> (land, water, county fips, county name)
for r in csv.DictReader(open(rel, encoding='utf-8-sig'), delimiter='|'):
    z = r['GEOID_ZCTA5_20']
    if not z or not rest(z): continue
    k = (int(r['AREALAND_PART'] or 0), int(r['AREAWATER_PART'] or 0), r['GEOID_COUNTY_20'], r['NAMELSAD_COUNTY_20'])
    if z not in best or k[:2] > best[z][:2] or (k[:2] == best[z][:2] and k[2] < best[z][2]): best[z] = k
cbsa = {}   # county fips -> (cbsa code, title, metro/micro)
for r in openpyxl.load_workbook(xlsx, read_only=True).active.iter_rows(min_row=4, values_only=True):
    if r[0] and r[9] and r[10]: cbsa[r[9] + r[10]] = (r[0], r[3], r[4])
missing = set(SLUGS) - {c for c, _, kind in cbsa.values() if kind == 'Metropolitan Statistical Area'}
if missing: sys.exit(f'STOP: metro areas not in the delineation file: {missing}')
w = csv.writer(sys.stdout, lineterminator='\n')
w.writerow(['zip5', 'county_fips', 'county_name', 'cbsa_code', 'cbsa_name', 'slug', 'source'])
for z in sorted(best):
    _, _, fips, cname = best[z]
    code, title, kind = cbsa.get(fips, ('', '', ''))
    w.writerow([z, fips, cname, code, title, SLUGS.get(code, 'small-towns') if kind == 'Metropolitan Statistical Area' else 'small-towns',
                'Census 2020 ZCTA-county (most land) + CBSA July 2023'])
