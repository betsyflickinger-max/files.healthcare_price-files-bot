"""Oct 31, 2026 (Betsy chose regional pages): a state whose Price Finder page is too big for one file is published as regional
pages instead. California's statewide page came out at 32.5 MB; the website host takes files up to 25 MB.

Each region is a list of whole counties. A provider belongs to the region of the county its practice ZIP lies mostly in (the
Census ZIP-to-county file behind data/medicare_areas_zip.csv, the same one the Medicare doctor-fee areas use). A hospital file
belongs to the region of its hospital's ZIP (CMS Hospital General Information, as recorded in the hospital plan). The state's
own address (/california/price-finder/) becomes a short page that links to its regional pages.

REGIONS: state page slug -> {region slug: (page name, Medicare locality shown by default, locality name, map box, counties)}.
The default locality is the one with the most providers in the region; every provider is still compared with Medicare for their
own area (site/med_areas.py)."""
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))

REGIONS = {
    'california': {
        'los-angeles': ('Los Angeles, Orange & Ventura', '18', 'Los Angeles', '-119.8,33.0,-117.1,35.0',
                        ['Los Angeles', 'Orange', 'Ventura']),
        'san-diego-inland-empire': ('San Diego & Inland Empire', '62', 'Riverside-San Bernardino', '-117.9,32.3,-114.0,35.9',
                                    ['San Diego', 'Imperial', 'Riverside', 'San Bernardino']),
        'bay-area': ('San Francisco Bay Area', '05', 'San Francisco', '-123.8,36.6,-121.0,39.0',
                     ['Alameda', 'Contra Costa', 'Marin', 'Napa', 'San Francisco', 'San Mateo', 'Santa Clara', 'Solano', 'Sonoma',
                      'Santa Cruz']),
        'sacramento-northern-california': ('Sacramento & Northern California', '63', 'Sacramento', '-124.6,38.0,-119.5,42.3',
                                           ['Sacramento', 'Placer', 'Yolo', 'El Dorado', 'Sutter', 'Yuba', 'Nevada', 'Butte', 'Shasta',
                                            'Tehama', 'Glenn', 'Colusa', 'Lake', 'Mendocino', 'Humboldt', 'Del Norte', 'Siskiyou',
                                            'Trinity', 'Lassen', 'Modoc', 'Plumas', 'Sierra', 'Amador', 'Alpine']),
        'central-california': ('Central California', '56', 'Fresno', '-122.2,34.2,-115.4,38.8',
                               ['Fresno', 'Kern', 'Kings', 'Tulare', 'Madera', 'Merced', 'Stanislaus', 'San Joaquin', 'Mariposa',
                                'Tuolumne', 'Calaveras', 'Mono', 'Inyo', 'Monterey', 'San Benito', 'San Luis Obispo', 'Santa Barbara']),
    },
}
LIVE = True   # Oct 31, 2026: test split checked row by row (region-test.yml: 0 differences) and the LA page built at 12.1 MiB
SPLIT_V = 2   # Oct 31: v2 keeps every state code and the 'coming' list on regional pages; raising it splits again
STATE_CODE = {'california': 'CA'}
PARENT = {r: s for s, R in REGIONS.items() for r in R}
NEIGHBORS = {   # regions that share a border, linked from each regional page for people who live near one
    'los-angeles': ['san-diego-inland-empire', 'central-california'],
    'san-diego-inland-empire': ['los-angeles', 'central-california'],
    'bay-area': ['sacramento-northern-california', 'central-california'],
    'sacramento-northern-california': ['bay-area', 'central-california'],
    'central-california': ['los-angeles', 'bay-area', 'sacramento-northern-california', 'san-diego-inland-empire'],
}   # region slug -> state page slug


def zip_county(state_code):
    """{zip5: county} for one state (Census 2020 ZCTA -> county with the most land)"""
    for p in (os.path.join(HERE, '..', 'data', 'medicare_areas_zip.csv'), os.path.join(HERE, 'medicare_areas_zip.csv')):
        if os.path.exists(p):
            return {r['zip5']: r['county'] for r in csv.DictReader(open(p)) if r['state'] == state_code}
    raise FileNotFoundError('medicare_areas_zip.csv')


def county_region(state):
    m = {c: r for r, v in REGIONS[state].items() for c in v[4]}
    return m


def check(state):
    """every county of the state in exactly one region"""
    counties = set(zip_county(STATE_CODE[state]).values())
    listed = [c for v in REGIONS[state].values() for c in v[4]]
    dup = {c for c in listed if listed.count(c) > 1}
    missing, extra = counties - set(listed), set(listed) - counties
    if dup or missing or extra: raise ValueError(f'{state} regions: twice {sorted(dup)}, missing {sorted(missing)}, unknown {sorted(extra)}')
    return True


def region_of_zip(state, z, _cache={}):
    if state not in _cache: _cache[state] = (zip_county(STATE_CODE[state]), county_region(state))
    zc, cr = _cache[state]
    return cr.get(zc.get(str(z or '')[:5]))


def by_county_text(counties):
    return 'in a ZIP code that lies mostly in ' + ', '.join(counties[:-1]) + ' or ' + counties[-1] + ' County'


if __name__ == '__main__':
    for s in REGIONS: print(s, check(s))
