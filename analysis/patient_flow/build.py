"""Where patients go: price areas checked against real hospital use (Nov 13, 2026; Research Desk v1, story 2.2).

Betsy's rule (Nov 13, 2026): every Census metro (2023, whole counties) is its own area; each rural county joins the metro
its residents' hospital stays go to most; a small metro whose own residents mostly use another metro joins that metro.
Counties with under 50 stays, or none at a metro hospital, stay in "Rest of <state>". Display rule that goes with it
(not applied here): every real price always shows, and an area's middle price needs 5+ providers, otherwise the wider
region's middle is shown, labeled. First run by hand Nov 12 (claude/national-patient-flow-nov12.md).

  python analysis/patient_flow/build.py fetch  DIR          download the public source files into DIR
  python analysis/patient_flow/build.py build  DIR OUT      write OUT/areas.json, counties.json, summary.json (+ .csv)

Sources: CMS Hospital Service Area File (Medicare inpatient stays by hospital and patient ZIP), Census 2023 metro
delineation (list 1), Census 2020 ZCTA-to-county relationship file (county with most land), GeoNames postal codes for
PO-box ZIPs (reference/geo/sources), and the bot's hospital list (reference/geo/medicare_hospitals.csv).
Limits: traditional Medicare inpatient stays only; CMS hides counts under 11.
"""
import collections
import csv
import datetime
import json
import os
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
GEONAMES = os.path.join(ROOT, 'reference', 'geo', 'sources', 'geonames_US_postal_2026-11-10.txt')
HOSPITALS = os.path.join(ROOT, 'reference', 'geo', 'medicare_hospitals.csv')
SOURCES = [   # (file name, url, title)
    ('hsaf.csv', 'https://data.cms.gov/sites/default/files/2026-06/5c0137be-b61d-4493-af6b-63a79b4a314c/Hospital_Service_Area_2025.csv',
     'CMS Hospital Service Area File 2025'),
    ('list1_2023.xlsx', 'https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx',
     'Census 2023 metro delineation, list 1'),
    ('zcta_county.txt', 'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt',
     'Census 2020 ZCTA-to-county relationship file'),
]
ST = {'01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA',
      '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD', '25': 'MA',
      '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY',
      '37': 'NC', '38': 'ND', '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX',
      '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI', '56': 'WY'}
# Connecticut: the 2020 ZIP file uses its 8 old counties; 2023 metros use planning regions. Old county -> 2023 metro (most people).
CT = {'09001': '14860', '09003': '25540', '09007': '25540', '09009': '35300', '09011': '35980', '09013': '25540', '09015': '35980'}
MIN_STAYS = 50


def is_hospital(ccn):
    """Short-term acute (0001-0879), critical access (1300-1399) and children's (3300-3399) hospitals."""
    n = ccn[2:]
    if len(ccn) != 6 or not n.isdigit():
        return False
    n = int(n)
    return 1 <= n <= 879 or 1300 <= n <= 1399 or 3300 <= n <= 3399


def read_metros(path):
    import openpyxl
    metro, name = {}, {}
    ws = openpyxl.load_workbook(path, read_only=True).active
    for r in ws.iter_rows(min_row=4, values_only=True):
        if r[0] and r[4] == 'Metropolitan Statistical Area' and r[9]:
            metro[str(r[9]) + str(r[10])] = str(r[0]); name[str(r[0])] = r[3]
    metro.update(CT)
    return metro, name


def read_zip_county(path, geonames=GEONAMES):
    best, cname = {}, {}
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter='|'):
            z, c = r['GEOID_ZCTA5_20'], r['GEOID_COUNTY_20']
            if not c:
                continue
            cname[c] = r['NAMELSAD_COUNTY_20']
            if not z:
                continue
            a = int(r['AREALAND_PART'] or 0)
            if z not in best or a > best[z][1]:
                best[z] = (c, a)
    zc = {z: c for z, (c, a) in best.items()}
    fips = {v: k for k, v in ST.items()}
    if os.path.isfile(geonames):   # PO-box and single-building ZIPs (many hospitals use one) have no ZCTA
        for line in open(geonames, encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) > 6 and p[1] not in zc and p[4] in fips and p[6].isdigit():
                zc[p[1]] = fips[p[4]] + p[6].zfill(3)
    return zc, cname


def read_flows(hsaf, zc, hosp_zip):
    """(patient county, hospital county) -> stays; hospital -> county; counts of what was left out."""
    flows, hcounty = collections.Counter(), {}
    left = collections.Counter()
    with open(hsaf, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            ccn = r['MEDICARE_PROV_NUM']
            if not is_hospital(ccn):
                continue
            if r['TOTAL_CASES'].strip() == '*':
                left['hidden_cells'] += 1; continue
            n = int(r['TOTAL_CASES'])
            pc, hc = zc.get(r['ZIP_CD_OF_RESIDENCE']), zc.get(hosp_zip.get(ccn, ''))
            if not pc or not hc or pc[:2] not in ST or hc[:2] not in ST:
                left['stays_unplaced'] += n; continue
            flows[(pc, hc)] += n; hcounty[ccn] = hc; left['stays_counted'] += n
    return flows, hcounty, left


def home_state(title):
    return title.split(', ')[1].split('-')[0]


def assign(flows, metro, mname):
    """county -> area id ('M<cbsa>' or 'R<state>'), plus notes per county."""
    F = collections.defaultdict(collections.Counter)
    for (p, h), n in flows.items():
        F[p][h] += n
    area, note = {}, {}
    for p, dests in F.items():   # rural counties join the metro they use most
        if p in metro:
            continue
        mc = collections.Counter()
        for h, n in dests.items():
            if h in metro:
                mc[metro[h]] += n
        if not mc or sum(dests.values()) < MIN_STAYS:
            note[p] = f'under {MIN_STAYS} stays or no metro use: stays in rest of state'
            continue
        cb = mc.most_common(1)[0][0]
        area[p] = 'M' + cb
        if ST[p[:2]] not in mname[cb].split(', ')[1]:
            note[p] = 'joins a metro across the state line'
    mm = collections.defaultdict(collections.Counter)   # small metros whose own residents mostly use another metro
    for p, dests in F.items():
        if p in metro:
            for h, n in dests.items():
                if h in metro:
                    mm[metro[p]][metro[h]] += n
    merge = {}
    for cb, c in mm.items():
        other = [(x, n) for x, n in c.most_common() if x != cb]
        if other and other[0][1] > c[cb] and sum(c.values()) >= 200:
            merge[cb] = other[0][0]
    out = {}
    for c in set(F) | {h for d in F.values() for h in d}:
        if c[:2] not in ST:
            continue
        a = 'M' + metro[c] if c in metro else area.get(c, 'R' + ST[c[:2]])
        if a[0] == 'M' and a[1:] in merge:
            a = 'M' + merge[a[1:]]
            if c in metro:
                note[c] = 'small metro whose residents mostly use ' + mname[merge[metro[c]]]
        out[c] = a
    return out, note, F, merge


def area_name(a, mname):
    return mname[a[1:]] if a[0] == 'M' else 'Rest of ' + a[1:]


def area_state(a, mname):
    return home_state(mname[a[1:]]) if a[0] == 'M' else a[1:]


def build(src, out_dir, metro=None, mname=None, zc=None, cname=None, hosp_zip=None):
    if metro is None:
        metro, mname = read_metros(os.path.join(src, 'list1_2023.xlsx'))
    if zc is None:
        zc, cname = read_zip_county(os.path.join(src, 'zcta_county.txt'))
    if hosp_zip is None:
        hosp_zip = {r['ccn']: r['zip'][:5] for r in csv.DictReader(open(HOSPITALS, encoding='utf-8'))}
    flows, hcounty, left = read_flows(os.path.join(src, 'hsaf.csv'), zc, hosp_zip)
    A, note, F, merge = assign(flows, metro, mname)
    res, own, cnt, hosp = collections.Counter(), collections.Counter(), collections.Counter(), collections.defaultdict(set)
    for c, a in A.items():
        cnt[a] += 1
    for ccn, hc in hcounty.items():
        if hc in A:
            hosp[A[hc]].add(ccn)
    for p, dests in F.items():
        if p not in A:
            continue
        for h, n in dests.items():
            res[A[p]] += n
            own[A[p]] += n if A.get(h) == A[p] else 0
    areas = [{'area_id': a, 'name': area_name(a, mname), 'state': area_state(a, mname), 'counties': cnt[a], 'hospitals': len(hosp[a]),
              'resident_stays': res[a], 'pct_kept': round(100 * own[a] / res[a], 1) if res[a] else None,
              'under_5_hospitals': len(hosp[a]) < 5}
             for a in sorted(cnt, key=lambda a: (area_state(a, mname), area_name(a, mname)))]
    counties = []
    for p in sorted(A):
        dests = F.get(p, {})
        t = sum(dests.values())
        to = collections.Counter()
        for h, n in dests.items():
            if h in A:
                to[A[h]] += n
        counties.append({'fips': p, 'county': (cname or {}).get(p, ''), 'state': ST[p[:2]], 'metro_2023': mname.get(metro.get(p, ''), ''),
                         'area_id': A[p], 'area': area_name(A[p], mname), 'resident_stays': t,
                         'pct_own_county': round(100 * dests.get(p, 0) / t, 1) if t else None,
                         'pct_in_area': round(100 * to[A[p]] / t, 1) if t else None,
                         'top_areas': [[area_name(a, mname), round(100 * n / t, 1)] for a, n in to.most_common(3)] if t else [],
                         'note': note.get(p, '')})
    tot = sum(res.values()); kept = sum(own.values())
    rural = [c for c in counties if not c['metro_2023'] and c['resident_stays']]
    rt = sum(c['resident_stays'] for c in rural)
    summary = {'areas': len(areas), 'metro_areas': sum(1 for a in areas if a['area_id'][0] == 'M'),
               'areas_under_5_hospitals': sum(1 for a in areas if a['under_5_hospitals']),
               'pct_all_stays_kept_in_area': round(100 * kept / tot, 1) if tot else None,
               'pct_rural_stays_kept_in_area': round(100 * sum(c['resident_stays'] * c['pct_in_area'] for c in rural) / 100 / rt, 1) if rt else None,
               'rural_counties_across_state_line': sum(1 for c in counties if c['note'].startswith('joins a metro across')),
               'counties_too_few_stays': sum(1 for c in counties if c['note'].startswith('under')),
               'small_metros_merged': len(merge), **left}
    meta = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'rule': 'Census 2023 metros (whole counties); rural counties join the metro their residents use most; small metros '
                    'whose residents mostly use another metro join it (Betsy, Nov 13, 2026).',
            'sources': [{'title': t, 'url': u} for _, u, t in SOURCES] + [{'title': 'GeoNames US postal codes (PO-box ZIPs)', 'url': 'https://download.geonames.org/export/zip/'}],
            'leaves_out': 'Traditional Medicare inpatient stays only (no Medicare Advantage, commercial, outpatient or surgery centers); '
                          'CMS hides counts under 11, so small rural flows are undercounted.'}
    os.makedirs(out_dir, exist_ok=True)
    for nm, rows in (('areas', areas), ('counties', counties), ('summary', summary)):
        json.dump(dict(meta, rows=rows), open(os.path.join(out_dir, nm + '.json'), 'w'), indent=None if nm == 'counties' else 1)
        if isinstance(rows, list):
            with open(os.path.join(out_dir, nm + '.csv'), 'w', newline='', encoding='utf-8') as f:
                f.write(f"# {meta['sources'][0]['title']} and others; built {meta['built_at']}; rule: {meta['rule']}\n")
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for r in rows:
                    w.writerow({k: ('; '.join(f'{a} {p}%' for a, p in v) if k == 'top_areas' else v) for k, v in r.items()})
    print(json.dumps(summary, indent=1))
    return summary


def fetch(dst):
    os.makedirs(dst, exist_ok=True)
    for fn, url, _ in SOURCES:
        p = os.path.join(dst, fn)
        if not os.path.isfile(p):
            print('downloading', url)
            urllib.request.urlretrieve(url, p)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['fetch'] and len(a) == 2:
        fetch(a[1])
    elif a[:1] == ['build'] and len(a) == 3:
        build(a[1], a[2])
    else:
        sys.exit(__doc__)
