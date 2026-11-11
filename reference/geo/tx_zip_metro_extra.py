"""Nov 10, 2026: add Texas ZIP codes that are not Census ZIP areas (single-building and PO-box ZIPs) to tx_zip_metro.csv.

Why: the table was built from Census ZIP areas only, and a ZIP not in it fell onto the Small towns page. Baylor Scott & White
Medical Center - Temple has its own ZIP (76508), so the biggest hospital in Central Texas sat on Small towns, not Killeen-Temple
(found by the Texas patient-flow check, Nov 10). Each missing ZIP is placed by its county (GeoNames postal codes, county FIPS)
and takes the page that county's Census ZIP areas already have in the table; a county with none in the table -> small-towns.
ZIPs in the five big-metro 3-digit areas are skipped: those pages go by 3-digit ZIP first (tx_split.py), so a row would not change
anything. Run: python reference/geo/tx_zip_metro_extra.py  (idempotent; rows it added carry source 'GeoNames ...').
Source: GeoNames postal code file for the US (download.geonames.org/export/zip/US.zip, CC BY 4.0), saved as
reference/geo/sources/geonames_US_postal_2026-11-10.txt."""
import csv, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(HERE, 'tx_zip_metro.csv')
G = os.path.join(HERE, 'sources', 'geonames_US_postal_2026-11-10.txt')
BIG3 = {f'{p}' for a, b in (('750', '753'), ('760', '762'), ('770', '775'), ('780', '782'), ('786', '787'), ('798', '799')) for p in range(int(a), int(b) + 1)}
SRC = 'GeoNames postal codes (county) + county page in this table; ZIP not a Census ZIP area'
rows = list(csv.DictReader(open(T, encoding='utf-8')))
cols = list(rows[0].keys())
rows = [r for r in rows if r['source'] != SRC]          # idempotent
have = {r['zip5'] for r in rows}
by_county = collections.defaultdict(collections.Counter)
info = {}
for r in rows:
    by_county[r['county_fips']][r['slug']] += 1
    info[r['county_fips']] = r
added = collections.Counter()
for line in open(G, encoding='utf-8'):
    f = line.rstrip('\n').split('\t')
    z, st, county, cfips = f[1], f[4], f[5], f[6]
    if st != 'TX' or z in have or z[:3] in BIG3 or not cfips: continue
    fips = '48' + cfips.zfill(3)
    if fips in by_county:
        slug = by_county[fips].most_common(1)[0][0]; base = info[fips]
        rows.append(dict(zip5=z, county_fips=fips, county_name=base['county_name'], cbsa_code=base['cbsa_code'],
                         cbsa_name=base['cbsa_name'], slug=slug, source=SRC))
    else:
        rows.append(dict(zip5=z, county_fips=fips, county_name=county + ' County', cbsa_code='', cbsa_name='', slug='small-towns', source=SRC))
        slug = 'small-towns'
    added[slug] += 1
rows.sort(key=lambda r: r['zip5'])
with open(T, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
print('added', sum(added.values()), 'ZIPs:', dict(added.most_common()))
