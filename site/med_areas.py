"""Medicare doctor-fee area for each provider (Oct 30, 2026, Betsy: "as accurate as possible").

Medicare pays doctors by "locality". A state page used to compare every doctor with one locality (for example Miami for all of
Florida). Now each doctor is compared with Medicare for the locality of the doctor's own practice address:

  practice ZIP (NPPES, npis.parquet zip5) -> county (Census 2020 ZCTA-to-county file: the county with the most land in that ZIP,
  same rule as reference/geo/tx_zip_metro.csv) -> Medicare locality (CMS 26LOCCO.csv, typed out in AREAS below).

A ZIP that isn't a Census ZCTA (PO boxes, single-building ZIPs) takes the locality every ZCTA in its 3-digit area shares; if they
don't all share one, the provider has no known area and is compared with the page's own area, labeled as such. Nothing is
estimated: every Medicare figure is CMS's own formula for a real locality, and the page says which locality it used.

Fees on the page: CMS's formula is (work RVU x work GPCI + PE RVU x PE GPCI + MP RVU x MP GPCI) x conversion factor, rounded to
cents (pfs_for in city_page.py). The page carries each code's RVUs once and each area's three GPCIs, and works the fee out in
the browser with the same arithmetic. attach() checks every code in every area against the Python figure and stores the few
that round differently as exact overrides, so the browser always shows CMS's number.

  python site/med_areas.py build tab20_zcta520_county20_natl.txt 26LOCCO.csv   -> data/medicare_areas_zip.csv
     (Census: https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt;
      CMS 26LOCCO.csv is inside rvu26d-updated-08-26-2026.zip)
"""
import csv
import io
import os
import sys
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP_FILE = os.path.join(HERE, '..', 'data', 'medicare_areas_zip.csv')

FIPS = {'TX': '48', 'NJ': '34', 'MI': '26', 'OR': '41', 'CA': '06', 'PA': '42', 'MD': '24', 'NY': '36', 'MA': '25', 'LA': '22',
        'GA': '13', 'ME': '23', 'FL': '12', 'WA': '53', 'MO': '29', 'IL': '17', 'VA': '51', 'DC': '11'}
STATE_NAME = {'TX': 'Texas', 'NJ': 'New Jersey', 'MI': 'Michigan', 'OR': 'Oregon', 'CA': 'California', 'PA': 'Pennsylvania',
              'MD': 'Maryland', 'NY': 'New York', 'MA': 'Massachusetts', 'LA': 'Louisiana', 'GA': 'Georgia', 'ME': 'Maine',
              'FL': 'Florida', 'WA': 'Washington', 'MO': 'Missouri', 'IL': 'Illinois', 'VA': 'Virginia', 'DC': 'District of Columbia'}
# CMS 26LOCCO.csv (CY2026), typed out: state -> [(GPCI state, locality, short name, [Census county names in that state])],
# then the locality for every other county. Census names are matched exactly (build stops on any miss). Two CMS spellings
# fixed: "ORAGNGE" = Orange, "DADE" = Miami-Dade. The DC locality takes in Maryland and Northern Virginia counties.
AREAS = {
    'CA': [('CA', '18', 'Los Angeles', ['Los Angeles', 'Orange']), ('CA', '52', 'Marin County', ['Marin']),
           ('CA', '05', 'San Francisco', ['San Francisco', 'Alameda', 'Contra Costa', 'San Mateo']),
           ('CA', '09', 'San Jose (Santa Clara County)', ['Santa Clara']), ('CA', '51', 'Napa', ['Napa']), ('CA', '53', 'Vallejo', ['Solano']),
           ('CA', '54', 'Bakersfield', ['Kern']), ('CA', '55', 'Chico', ['Butte']), ('CA', '56', 'Fresno', ['Fresno']),
           ('CA', '57', 'Hanford-Corcoran', ['Kings']), ('CA', '58', 'Madera', ['Madera']), ('CA', '59', 'Merced', ['Merced']),
           ('CA', '60', 'Modesto', ['Stanislaus']), ('CA', '61', 'Redding', ['Shasta']),
           ('CA', '62', 'Riverside-San Bernardino', ['San Bernardino', 'Riverside']),
           ('CA', '63', 'Sacramento', ['Sacramento', 'Placer', 'Yolo', 'El Dorado']), ('CA', '64', 'Salinas', ['Monterey']),
           ('CA', '65', 'San Benito County', ['San Benito']), ('CA', '66', 'Santa Cruz', ['Santa Cruz']),
           ('CA', '67', 'Santa Rosa', ['Sonoma']), ('CA', '68', 'Stockton', ['San Joaquin']), ('CA', '69', 'Visalia', ['Tulare']),
           ('CA', '70', 'Yuba City', ['Sutter', 'Yuba']), ('CA', '71', 'El Centro', ['Imperial']), ('CA', '72', 'San Diego', ['San Diego']),
           ('CA', '73', 'San Luis Obispo', ['San Luis Obispo']), ('CA', '74', 'Santa Barbara', ['Santa Barbara']),
           ('CA', '17', 'Ventura', ['Ventura']), ('CA', '75', 'Rest of California', None)],
    'FL': [('FL', '03', 'Fort Lauderdale', ['Broward', 'Collier', 'Indian River', 'Lee', 'Martin', 'Palm Beach', 'St. Lucie']),
           ('FL', '04', 'Miami', ['Miami-Dade', 'Monroe']), ('FL', '99', 'Rest of Florida', None)],
    'GA': [('GA', '01', 'Atlanta', ['Butts', 'Cherokee', 'Clayton', 'Cobb', 'DeKalb', 'Douglas', 'Fayette', 'Forsyth', 'Fulton', 'Gwinnett',
                                     'Henry', 'Newton', 'Paulding', 'Rockdale', 'Walton']), ('GA', '99', 'Rest of Georgia', None)],
    'IL': [('IL', '16', 'Chicago', ['Cook']),
           ('IL', '12', 'East St. Louis', ['Bond', 'Calhoun', 'Clinton', 'Jersey', 'Macoupin', 'Madison', 'Monroe', 'Montgomery', 'Randolph',
                                           'St. Clair', 'Washington']),
           ('IL', '15', 'Suburban Chicago', ['DuPage', 'Kane', 'Lake', 'Will']), ('IL', '99', 'Rest of Illinois', None)],
    'LA': [('LA', '01', 'New Orleans', ['Jefferson', 'Orleans', 'Plaquemines', 'St. Bernard']), ('LA', '99', 'Rest of Louisiana', None)],
    'ME': [('ME', '03', 'Southern Maine', ['Cumberland', 'York']), ('ME', '99', 'Rest of Maine', None)],
    'MD': [('MD', '01', 'Baltimore and surrounding counties', ['Anne Arundel', 'Baltimore', 'Baltimore city', 'Carroll', 'Harford', 'Howard']),
           ('DC', '01', 'DC + MD/VA suburbs', ['Montgomery', "Prince George's"]), ('MD', '99', 'Rest of Maryland', None)],
    'MA': [('MA', '01', 'Metropolitan Boston', ['Middlesex', 'Norfolk', 'Suffolk']), ('MA', '99', 'Rest of Massachusetts', None)],
    'MI': [('MI', '01', 'Detroit', ['Macomb', 'Oakland', 'Washtenaw', 'Wayne']), ('MI', '99', 'Rest of Michigan', None)],
    'MO': [('MO', '02', 'Metropolitan Kansas City', ['Clay', 'Jackson', 'Platte']),
           ('MO', '01', 'Metropolitan St. Louis', ['Jefferson', 'St. Charles', 'St. Louis', 'St. Louis city']), ('MO', '99', 'Rest of Missouri', None)],
    'NJ': [('NJ', '01', 'Northern New Jersey', ['Bergen', 'Essex', 'Hudson', 'Hunterdon', 'Middlesex', 'Morris', 'Passaic', 'Somerset', 'Sussex',
                                                'Union', 'Warren']), ('NJ', '99', 'Rest of New Jersey', None)],
    'NY': [('NY', '01', 'Manhattan', ['New York']), ('NY', '02', 'NYC suburbs and Long Island', ['Bronx', 'Kings', 'Nassau', 'Richmond', 'Rockland', 'Suffolk', 'Westchester']),
           ('NY', '03', 'Poughkeepsie and northern NYC suburbs', ['Columbia', 'Delaware', 'Dutchess', 'Greene', 'Orange', 'Putnam', 'Sullivan', 'Ulster']),
           ('NY', '04', 'Queens', ['Queens']), ('NY', '99', 'Rest of New York', None)],
    'OR': [('OR', '01', 'Portland', ['Clackamas', 'Multnomah', 'Washington']), ('OR', '99', 'Rest of Oregon', None)],
    'PA': [('PA', '01', 'Metropolitan Philadelphia', ['Bucks', 'Chester', 'Delaware', 'Montgomery', 'Philadelphia']), ('PA', '99', 'Rest of Pennsylvania', None)],
    'TX': [('TX', '31', 'Austin', ['Travis']), ('TX', '20', 'Beaumont', ['Jefferson']), ('TX', '09', 'Brazoria', ['Brazoria']),
           ('TX', '11', 'Dallas', ['Dallas']), ('TX', '28', 'Fort Worth', ['Tarrant']), ('TX', '15', 'Galveston', ['Galveston']),
           ('TX', '18', 'Houston', ['Harris']), ('TX', '99', 'Rest of Texas', None)],
    'VA': [('DC', '01', 'DC + MD/VA suburbs', ['Alexandria city', 'Arlington', 'Fairfax', 'Fairfax city', 'Falls Church city']),
           ('VA', '00', 'Rest of Virginia', None)],
    'WA': [('WA', '02', 'Seattle (King County)', ['King']), ('WA', '99', 'Rest of Washington', None)],
}
SUFFIX = (' County', ' Parish')


def _county(name):
    for s in SUFFIX:
        if name.endswith(s):
            return name[:-len(s)]
    return name   # "Baltimore city", "St. Louis city", "Alexandria city" keep their "city"


def build(zcta_file, out=ZIP_FILE):
    """ZIP -> Medicare area for every multi-area state, from the Census file. Stops if a CMS county name isn't found."""
    land = defaultdict(dict)   # (state, zip) -> {county: land}
    names = defaultdict(set)
    with open(zcta_file, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter='|'):
            z, g = r['GEOID_ZCTA5_20'], r['GEOID_COUNTY_20']
            names[g[:2]].add(_county(r['NAMELSAD_COUNTY_20']))
            if z:
                land[(g[:2], z)][_county(r['NAMELSAD_COUNTY_20'])] = land[(g[:2], z)].get(_county(r['NAMELSAD_COUNTY_20']), 0) + int(r['AREALAND_PART'] or 0)
    rows = []
    for st, spec in AREAS.items():
        fp, cmap = FIPS[st], {}
        for gst, loc, nm, counties in spec:
            for c in counties or ():
                if c not in names[fp]:
                    sys.exit(f'STOP: {st} county {c!r} (Medicare locality {gst}-{loc}) is not a Census county name')
                cmap[c] = f'{gst}-{loc}'
        rest = next(f'{g}-{l}' for g, l, _, c in spec if c is None)
        for (f_, z), cl in land.items():
            if f_ != fp:
                continue
            top = max(cl.items(), key=lambda kv: (kv[1], kv[0]))[0]
            rows.append((z, st, cmap.get(top, rest), top))
    rows.sort()
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['zip5', 'state', 'area', 'county'])
        w.writerows(rows)
    print(f'{len(rows):,} ZIP codes in {len(AREAS)} states -> {out}')


def zip_areas(st):
    """{zip5: area} for one state, plus {zip3: area} where every ZCTA in that 3-digit area shares one area."""
    if st not in AREAS:
        return {}, {}
    z5, by3 = {}, defaultdict(set)
    for r in csv.DictReader(open(ZIP_FILE)):
        if r['state'] == st:
            z5[r['zip5']] = r['area']
            by3[r['zip5'][:3]].add(r['area'])
    return z5, {k: next(iter(v)) for k, v in by3.items() if len(v) == 1}


def area_names(st):
    return {f'{g}-{l}': nm for g, l, nm, _ in AREAS.get(st, ())}


def gpci(rvu_zip):
    Z = zipfile.ZipFile(rvu_zip)
    return {f'{r[1]}-{r[2]}': [float(r[4]), float(r[5]), float(r[6])]
            for r in csv.reader(io.TextIOWrapper(Z.open('GPCI2026.csv'), encoding='latin-1')) if len(r) > 6 and len(r[1]) == 2}


def rvus(rvu_zip, codes):
    """code -> {'pfs'|'pfs26': [work, PE non-facility or None (NA), PE facility or None (NA), MP, conversion factor]}, the
    rows and filters of pfs_for (city_page.py)."""
    Z = zipfile.ZipFile(rvu_zip)

    def num(x):
        try:
            return float(str(x).replace('$', '').replace(',', '').strip())
        except ValueError:
            return None
    L = list(csv.reader(io.TextIOWrapper(Z.open('PPRRVU2026_Oct_nonQPP.csv'), encoding='latin-1')))
    k = next(j for j, r in enumerate(L) if r and r[0].strip() == 'HCPCS')
    out = {}
    for r in L[k + 1:]:
        if len(r) < 26 or r[0] not in codes or r[1] not in ('', '26') or r[3] not in ('A', 'R', 'T'):
            continue
        w, pen, nfna, pef, fna, mp, cf = num(r[5]), num(r[6]), r[7].strip(), num(r[8]), r[9].strip(), num(r[10]), num(r[25])
        out.setdefault(r[0], {})['pfs26' if r[1] == '26' else 'pfs'] = [w, None if nfna == 'NA' else pen, None if fna == 'NA' else pef, mp, cf]
    return out


def fee_py(r, g):
    """pfs_for's own arithmetic (Python round)."""
    w, pn, pf, mp, cf = r
    nf = None if pn is None else round((w * g[0] + pn * g[1] + mp * g[2]) * cf, 2)
    fa = None if pf is None else round((w * g[0] + pf * g[1] + mp * g[2]) * cf, 2)
    return [nf, fa if fa is not None else nf]


def fee_js(r, g):
    """What the page's JavaScript gives: same arithmetic, then Number(x.toFixed(2)) (round half up on the exact value)."""
    def fx(x):
        return float(Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    w, pn, pf, mp, cf = r
    nf = None if pn is None else fx((w * g[0] + pn * g[1] + mp * g[2]) * cf)
    fa = None if pf is None else fx((w * g[0] + pf * g[1] + mp * g[2]) * cf)
    return [nf, fa if fa is not None else nf]


JS = r"""<script>/*medArea*/
// Oct 30, 2026: Medicare doctor fees for each provider's own Medicare area (site/med_areas.py). medArea(code, providerIndex)
// -> [office, facility, area name] or null when the page has one area or the provider's area isn't known.
window.medArea = function (code, i) {
  var A = D.med && D.med.ar; if (!A || i == null) return null;
  var c = A.p.charAt(+i); if (!c || c === '-') return null;
  var a = parseInt(c, 36), m = D.med.codes[code]; if (!m || !m.pfs) return null;
  return window.medAreaFee(code, a, 'pfs');
};
window.medAreaFee = function (code, a, k) {
  var A = D.med && D.med.ar; if (!A) return null;
  var x = A.x[code] && A.x[code][k] && A.x[code][k][a]; if (x) return [x[0], x[1], A.n[a]];
  var r = (A[k === 'pfs26' ? 'r26' : 'r'] || {})[code], g = A.g[a]; if (!r || !g) return null;
  var f = function (pe) { return pe == null ? null : +((r[0] * g[0] + pe * g[1] + r[3] * g[2]) * r[4]).toFixed(2); };
  var nf = f(r[1]), fa = f(r[2]);
  return [nf, fa != null ? fa : nf, A.n[a]];
};
/*/medArea*/</script>"""

MED_FROM = "  if (m.lab) L.push(['Lab test', 'national payment limit', m.lab, 'lab']);"
MED_TO = MED_FROM + r"""
  var MA = '';   /*medAreas*/
  if (D.med.ar) { const A = D.med.ar, R = [];
    A.n.forEach((nm, a) => { if (a === A.d || !A.c[a]) return; const f = window.medAreaFee(code, a, 'pfs'); if (!f || (f[0] == null && f[1] == null)) return;
      R.push(`<div class="pline"><div class="who"><b>${esc(nm)}</b><div class="meta">${A.c[a] === 1 ? '1 provider' : A.c[a].toLocaleString() + ' providers'} on this page</div></div><span class="lead"></span><div class="right"><span class="price">${f[1] != null ? money(f[1]) : '—'}${f[0] != null && f[0] !== f[1] ? ' · office ' + money(f[0]) : ''}</span></div></div>`); });
    if (R.length) MA = `<p class="sub" style="margin-top:10px">Medicare pays doctors differently in different parts of ${esc(A.s)}. The doctor figures above are for the ${esc(A.n[A.d])} area. On this page, each doctor's price is compared with Medicare for the area of the doctor's practice address. Doctor's fee for this service in the other areas (in a hospital or surgery center, and in an office where it differs):</p>` + R.join(''); }"""
MED_JOIN_FROM = ".join('') + mlLocal(code);"
MED_JOIN_TO = ".join('') + MA + mlLocal(code);"


def attach(D, st, npis, zip_of, rvu_zip, default_loc, log=print):
    """Add D['med']['ar'] when this page's providers are in more than one Medicare area; returns a summary line or None.
    D: the page's data block (after its Medicare doctor fees were set to default_loc, e.g. '04'); npis: npis.json (one NPI per
    D['fac'] row); zip_of: {npi: zip5}. The page's own figures (pfs 'dal') are left exactly as they are."""
    if st not in AREAS:
        return None
    z5, z3 = zip_areas(st)
    names, G = area_names(st), gpci(rvu_zip)
    if len(npis) != len(D['fac']):
        raise ValueError(f'STOP: npis.json ({len(npis)}) and page providers ({len(D["fac"])}) differ; Medicare areas not added')
    dflt = next((k for k in names if k.split('-')[1] == default_loc and k.split('-')[0] == st), None) or \
        next((k for k in names if k.split('-')[1] == default_loc), None)
    if not dflt:
        raise ValueError(f'STOP: the page area {st} {default_loc} is not one of {sorted(names)}')
    keys = [dflt] + sorted(k for k in names if k != dflt)
    idx = {k: i for i, k in enumerate(keys)}
    if len(keys) > 36:
        raise ValueError('STOP: more than 36 Medicare areas in one state')
    prov, cnt, unknown = [], Counter(), 0
    for n in npis:
        z = str(zip_of.get(n) or '')[:5]
        a = z5.get(z) or z3.get(z[:3])
        if a is None:
            prov.append('-'); unknown += 1
        else:
            prov.append('0123456789abcdefghijklmnopqrstuvwxyz'[idx[a]]); cnt[a] += 1
    if len([k for k in keys if cnt[k]]) < 2:
        return f'Medicare areas: every placed provider is in {names[keys[0]]}; nothing added'
    codes = D['med']['codes']
    R = rvus(rvu_zip, set(codes))
    r, r26, x, checked = {}, {}, {}, 0
    for c, m in codes.items():
        for k, out in (('pfs', r), ('pfs26', r26)):
            if k not in m or k not in R.get(c, {}):
                continue
            row = R[c][k]
            if fee_py(row, G[dflt]) != m[k]['dal']:
                raise ValueError(f'STOP: {c} {k}: CMS formula for {names[dflt]} gives {fee_py(row, G[dflt])}, page has {m[k]["dal"]}')
            out[c] = row
            for a, key in enumerate(keys):
                checked += 1
                py = fee_py(row, G[key])
                if fee_js(row, G[key]) != py:
                    x.setdefault(c, {}).setdefault(k, {})[a] = py
    D['med']['ar'] = {'s': STATE_NAME[st], 'k': keys, 'n': [names[k] for k in keys], 'g': [G[k] for k in keys], 'd': 0,
                      'c': [cnt[k] for k in keys], 'p': ''.join(prov), 'r': r, 'r26': r26, 'x': x,
                      'src': 'CMS 26LOCCO.csv + GPCI2026.csv; Census 2020 ZCTA-to-county; site/med_areas.py'}
    by = ', '.join(f'{names[k]} {cnt[k]:,}' for k in keys if cnt[k])
    return (f'Medicare areas: {by}; {unknown:,} providers with no known area (compared with {names[dflt]}); '
            f'{checked:,} code-area fees checked, {sum(len(v) for d in x.values() for v in d.values())} stored exactly')


def patch_page(s):
    """The page's JavaScript: the medArea helpers, and the Medicare block lists the other areas. Idempotent; stops if the
    page's wording changed."""
    if '/*medArea*/' not in s:
        i = s.find('<script type="application/json" id="data">')
        j = s.find('</script>', i) + len('</script>')
        if i < 0:
            sys.exit('STOP: page has no data block; Medicare areas not added')
        s = s[:j] + '\n' + JS + s[j:]
    if '/*medAreas*/' not in s:
        for a, b in ((MED_FROM, MED_TO), (MED_JOIN_FROM, MED_JOIN_TO)):
            if s.count(a) != 1:
                sys.exit(f'STOP: page wording for the Medicare block changed ({a[:50]!r}); Medicare areas not added')
            s = s.replace(a, b)
    return s


TAG = '<script type="application/json" id="data">'


def apply_to_page(page, st, npis_json, npis_parquet, rvu_zip, loc, log=print):
    """Whole-page version for pages not built by city_page.py (the DFW page, site/orchestrate.py publish): reads the page,
    drops any old D.med.ar, adds this build's areas and the page code. Never stops a publish: on any problem the page is
    left with one Medicare area, as before, and the log says why."""
    import json
    s = open(page, encoding='utf-8').read()
    i = s.find(TAG); j = s.find('</script>', i)
    D = json.loads(s[i + len(TAG):j])
    D.get('med', {}).pop('ar', None)
    try:
        import duckdb
        zip_of = dict(duckdb.connect().execute(f"select npi, zip5 from read_parquet('{npis_parquet}')").fetchall())
        msg = attach(D, st, json.load(open(npis_json)), zip_of, rvu_zip, loc)
    except Exception as e:
        D.get('med', {}).pop('ar', None)
        msg = f'Medicare areas: NOT added ({type(e).__name__}: {e})'
    out = s[:i + len(TAG)] + json.dumps(D, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/') + s[j:]
    if D['med'].get('ar'):
        out = patch_page(out)
    open(page, 'w', encoding='utf-8').write(out)
    log(msg)
    return msg


MAP_FROM = "function medFor(kind) {\n  const m = D.med.codes[S.code]; if (!m) return null;\n"
MAP_TO = ("function medFor(kind, fi) {   /*medArea map*/\n  const m = D.med.codes[S.code]; if (!m) return null;\n"
          "  const ar = M.fee === 1 && m.pfs && fi != null && window.medArea ? window.medArea(S.code, fi) : null;\n"
          "  if (ar) return kind === 'P' || kind === 'G' ? [ar[0] ?? ar[1], `a doctor or clinic in an office (${ar[2]} Medicare area)`] : "
          "[ar[1] ?? ar[0], `the doctor when the service is done in a hospital or surgery center (${ar[2]} Medicare area)`];\n")
MAP_CALL = "const first = items[0], m = medFor(first.kind);"


def patch_map(d):
    """site/price-finder/map.js (in the deployed site, not in this repo): a clicked place's doctor fee is compared with Medicare
    for that provider's own area (window.medArea); pages with one area behave as before. Run by sitewide.py on every deploy."""
    p = os.path.join(d, 'site', 'price-finder', 'map.js')
    if not os.path.isfile(p):
        return 0
    s = open(p, encoding='utf-8').read()
    if '/*medArea map*/' in s:
        return 0
    if s.count(MAP_FROM) != 1 or s.count(MAP_CALL) != 1:
        print('med_areas: map.js wording changed; map keeps the page-wide Medicare area')
        return 0
    s = s.replace(MAP_FROM, MAP_TO).replace(MAP_CALL, "const first = items[0], m = medFor(first.kind, first.fi);")
    open(p, 'w', encoding='utf-8').write(s)
    return 1


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'build':
        build(sys.argv[2])
    else:
        print(__doc__)
