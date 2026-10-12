"""Price Finder page for one Texas city, built from the live DFW page and that city's finished insurer build.
Run by .github/workflows/city-page.yml (by hand, one city at a time).

  python site/city_page.py el-paso [--deploy]
  python site/city_page.py el-paso --template pf.html --embed embed.json --rvu rvu.zip --med-all med.json --t5 t5.txt --out /tmp/x   (offline test)

Reads (R2):
  site/deploy/price-finder.html                   the live DFW page: its layout and code is reused as is
  site/every-tx/<city>/<build>/embed.json         newest finished city build (written only when all 256 parts are in)
  reference/site/med_all.json, msdrg_table5.txt   the same names and Medicare inputs as the monthly refresh
  reference/2026-09-29/cms/rvu26d-*.zip           CMS 2026 physician fee schedule, for the city's Medicare doctor-fee locality
Writes the page to OUT/page.html. With --deploy: adds it to the preview site at /<city>/price-finder/ together with a small
function that serves the city's per-code rate files (R2 <build>/t/<code>.txt), deploys with wrangler, and saves the site
back to R2 site/deploy/current.tgz (the same steps as the monthly refresh).

What changes from the DFW page: the city's providers, networks and rates; doctor fees in the Medicare benchmark use the
city's Medicare locality; DFW-only parts are left out (hospital price files, posted cash prices, the map, the plan
calculator link); the words that name DFW. Every price shown still comes from an insurer file and links to it.
Any wording change that no longer matches the DFW page stops the build, so a city page never goes out half-edited."""
import argparse, csv, io, json, os, re, shutil, subprocess, sys, tarfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
# slug -> (name, 3-digit ZIP areas as in tx_split.py, Medicare locality number, locality name)
CITIES = {'el-paso': ('El Paso', '798–799', '99', 'Rest of Texas'),
          'austin': ('Austin', '786–787', '31', 'Austin'),
          'san-antonio': ('San Antonio', '780–782', '99', 'Rest of Texas'),
          'houston': ('Houston', '770–775', '18', 'Houston')}
TAG = '<script type="application/json" id="data">'
FEATURED_MIN = 45   # same broken-build test as the dashboard: a finished build needs rates and at least 45 of the 89 featured codes
FEATURED = {"00811", "00812", "19120", "216", "22551", "27130", "27447", "29826", "29827", "29881", "29888", "42820", "43235", "43239", "43644",
            "43775", "45378", "45380", "45385", "45391", "460", "470", "473", "47562", "49505", "55250", "55700", "55866", "59400", "59510", "59610",
            "62322", "62323", "63030", "64483", "64721", "66821", "66984", "70450", "70551", "70553", "72110", "72148", "72193", "73721", "74177",
            "743", "75571", "76700", "76805", "76830", "77065", "77066", "77067", "80048", "80053", "80055", "80061", "80069", "80076", "81000",
            "81001", "81002", "81003", "84153", "84154", "84443", "85025", "85027", "85610", "85730", "88305", "90832", "90834", "90837", "90846",
            "90847", "90853", "93000", "93452", "95810", "97110", "99203", "99204", "99205", "99243", "99244", "99385", "99386"}


def split(s):
    a = s.index(TAG) + len(TAG); b = s.index('</script>', a)
    return s[:a], json.loads(s[a:b]), s[b:]


def join(pre, D, post):
    return pre + json.dumps(D, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/') + post


class Words:
    """Wording changes on the page's own text (never inside the price data). Each must match, or the build stops."""
    def __init__(self, s): self.s = s
    def sub(self, old, new, n=1, regex=False):
        found = len(re.findall(old, self.s, flags=re.S)) if regex else self.s.count(old)
        if found != n: sys.exit(f'STOP: page wording changed: expected {n} x {old[:90]!r}, found {found}. Update city_page.py.')
        self.s = re.sub(old, new.replace('\\', '\\\\'), self.s, flags=re.S) if regex else self.s.replace(old, new)


def pfs_for(rvu_zip, loc, codes):
    """Medicare doctor fees for one locality: same formula and filters as build_med_all.py. code -> {'pfs'|'pfs26': [office, facility]}"""
    Z = zipfile.ZipFile(rvu_zip)
    G = {r[2]: [float(r[4]), float(r[5]), float(r[6])] for r in csv.reader(io.TextIOWrapper(Z.open('GPCI2026.csv'), encoding='latin-1'))
         if len(r) > 6 and r[1] == 'TX'}
    def num(x):
        try: return float(str(x).replace('$', '').replace(',', '').strip())
        except ValueError: return None
    L = list(csv.reader(io.TextIOWrapper(Z.open('PPRRVU2026_Oct_nonQPP.csv'), encoding='latin-1')))
    k = next(j for j, r in enumerate(L) if r and r[0].strip() == 'HCPCS')
    out = {}
    for r in L[k + 1:]:
        if len(r) < 26 or r[0] not in codes or r[1] not in ('', '26') or r[3] not in ('A', 'R', 'T'): continue
        w, pen, nfna, pef, fna, mp, cf = num(r[5]), num(r[6]), r[7].strip(), num(r[8]), r[9].strip(), num(r[10]), num(r[25])
        def at(l):
            gw, gp, gm = G[l]
            nf = None if nfna == 'NA' else round((w * gw + pen * gp + mp * gm) * cf, 2)
            fa = None if fna == 'NA' else round((w * gw + pef * gp + mp * gm) * cf, 2)
            return [nf, fa if fa is not None else nf]
        if all(x is None or x == 0 for x in at('11')): continue   # build_med_all.py skips these on the Dallas figures
        out.setdefault(r[0], {})['pfs26' if r[1] == '26' else 'pfs'] = {'11': at('11'), loc: at(loc)}
    return out


def build(slug, template, embed, rvu, med_all, t5, out):
    name, zips, loc, locname = CITIES[slug]
    os.makedirs(out, exist_ok=True)
    pre, T, post = split(open(template, encoding='utf-8').read())
    E = json.load(open(embed))
    lines = sum(c.get('n', 0) for c in E['codes'].values()); have = sum(c in E['codes'] for c in FEATURED)
    if lines == 0 or have < FEATURED_MIN:
        sys.exit(f'STOP: the {name} build looks broken: {len(E["codes"])} codes, {lines} rate lines, {have} of 89 featured codes')
    print(f'{name}: {len(E["codes"]):,} codes, {len(E["fac"]):,} providers, {lines:,} rate lines, {have} of 89 featured codes')

    # 1. price data: the city's insurer build in place of DFW's (merge_page.py, as in the monthly refresh); no DFW hospital
    #    price files and no DFW posted cash prices (empty, same shape, so the page shows "none")
    T['hosp'] = {k: ([] if isinstance(v, list) else {} if isinstance(v, dict) else v) for k, v in T['hosp'].items()}
    T['cash'] = []
    page, hosp = f'{out}/page.html', f'{out}/hosp_empty.json'
    open(page, 'w', encoding='utf-8').write(join(pre, T, post)); json.dump(T['hosp'], open(hosp, 'w'))
    py = sys.executable
    subprocess.run([py, f'{HERE}/merge_page.py', page, embed, hosp], check=True)
    names = f'{out}/plain_names_all.tsv'; rows = {}
    for f in (f'{HERE}/plain_names_auto.tsv', f'{HERE}/plain_names_cpt.tsv'):   # hand-written names win, as in orchestrate.py
        if os.path.exists(f):
            for l in open(f):
                if '\t' in l: c, n = l.rstrip('\n').split('\t', 1); rows[c] = n
    open(names, 'w').write(''.join(f'{c}\t{n}\n' for c, n in rows.items()))
    subprocess.run([py, f'{HERE}/apply_names_med.py', page, med_all, names, t5], check=True)
    pre, D, post = split(open(page, encoding='utf-8').read())

    # 2. Medicare doctor fees for the city's locality. Check first: the same formula must give the page's own Dallas figures.
    M = D['med']['codes']
    P = pfs_for(rvu, loc, set(M))
    checked = bad = 0
    for c, m in M.items():
        for k in ('pfs', 'pfs26'):
            if k in m:
                checked += 1
                if P.get(c, {}).get(k, {}).get('11') != m[k].get('dal'): bad += 1
    print(f'Medicare doctor fees: {checked:,} checked against the DFW page, {bad} differ')
    if not checked or bad > 0.001 * checked: sys.exit('STOP: Medicare doctor fees do not reproduce the DFW page; nothing written')
    dropped = 0
    for c, m in M.items():
        for k in ('pfs', 'pfs26'):
            if k not in m: continue
            v = P.get(c, {}).get(k, {}).get(loc)
            if v is None or bad and P.get(c, {}).get(k, {}).get('11') != m[k].get('dal'): m.pop(k); dropped += 1   # never leave a Dallas figure
            else: m[k] = {'dal': v}   # the page reads the 'dal' key; it now holds this city's locality
    M = {c: m for c, m in M.items() if m}; D['med']['codes'] = M
    print(f'Medicare doctor fees set to the {locname} locality ({loc}); {dropped} left out')

    # 3. wording
    w = Words(pre + '\x00' + post)
    w.sub('<title>What It Costs Price Finder</title>', f'<title>{name} Price Finder · What It Costs</title>')
    w.sub('content="Price Finder · What It Costs"', f'content="{name} Price Finder · What It Costs"')
    w.sub('content="https://upfront-dfw-preview.pages.dev/price-finder/"', f'content="https://upfront-dfw-preview.pages.dev/{slug}/price-finder/"')
    w.sub(r'<meta property="og:image[^>]*>', '', n=4, regex=True)   # the share image shows a DFW hospital
    w.sub('content="summary_large_image"', 'content="summary"')
    w.sub('every DFW hospital, surgery center, doctor, lab and imaging center for 89 procedures,',
          f'every {name}-area hospital, surgery center, doctor, lab and imaging center,', n=2)
    w.sub('<div class="eyebrow">Dallas–Fort Worth · published prices</div>', f'<div class="eyebrow">{name} · published prices</div>')
    w.sub(r'<div class="note" id="planNote">.*?</div>',
          f'<div class="note" id="planNote"><b>Have a HealthCare.gov plan?</b> Insurer prices below are not what you pay. Your share '
          f'depends on your plan\'s deductible, copay and coinsurance. Our plan calculator doesn\'t cover {name} plans yet.</div>', regex=True)
    w.sub(' If you have a marketplace plan, the <a href="/plan-calculator/">plan calculator</a> works it out for you.', '')
    w.sub(' DFW providers have a published rate in this network.', f' {name}-area providers have a published rate in this network.')
    w.sub("'This network has no published rate for this code in DFW.'", f"'This network has no published rate for this code in the {name} area.'")
    dates = sorted(d for d in set(D['dates']) if d)
    ins = sorted({n.split('|', 1)[0] for n in D['nets'] if D.get('scope', {}).get(n)}) or sorted({n.split('|', 1)[0] for n in D['nets']})
    w.sub(r'<p><b>Sources\.</b>.*?</p>',
          f'<p><b>Sources.</b> Insurer Transparency in Coverage files dated {dates[0]} to {dates[-1]}: {", ".join(ins)}. Each file was read '
          f'for every Texas provider, then narrowed to providers whose practice address in the federal NPI Registry is in a ZIP code '
          f'starting {zips}. Each rate links to the file it came from. Some insurer links expire and must be re-opened from the '
          f'insurer\'s own page. Hospital price files and providers\' posted cash prices are not on the {name} page yet.</p>', regex=True)
    # hospital files, cash prices and quality ratings aren't on city pages yet: say so instead of "none found"
    notyet = lambda what: f'{what} are not on the {name} page yet.'
    w.sub('No hospital price file lists a rate from this insurer for this code.', notyet('Hospital price files'))
    w.sub('No hospital price file lists this code for this insurer.', notyet('Hospital price files'))
    w.sub("None of the hospitals' price files lists a cash price for this code.", notyet('Hospital price files'))
    w.sub('No provider on our list posts a cash price for this code yet.', notyet("Providers' posted cash prices"))
    w.sub(r'<p><b>Quality ratings\.</b>.*?</p>', f'<p><b>Quality ratings.</b> {notyet("Public quality ratings")}</p>', regex=True)
    w.sub(r'<p><b>Map\.</b>.*?</p>', '', regex=True)
    w.sub('(October release, Dallas locality)', f'(October release, {locname} locality)')
    w.sub('Every DFW provider in the federal NPI Registry is included',
          f'Every provider in the federal NPI Registry with a practice address in a ZIP code starting {zips} is included')
    w.sub(' Fort Worth amounts differ by a few dollars.', '')
    w.sub("'Dallas area", f"'{locname} Medicare area", n=w.s.count("'Dallas area") or 1)
    w.sub('<button type="button" id="vMap" aria-pressed="false">Map</button>',
          '<button type="button" id="vMap" aria-pressed="false" hidden>Map</button>')   # the map's base layer and locations are DFW only
    left = [m.group(0) for m in re.finditer(r'.{40}(?:DFW|Dallas|Fort Worth).{40}', w.s)]
    if left: sys.exit('STOP: DFW wording left on the page:\n  ' + '\n  '.join(left[:10]))
    pre, post = w.s.split('\x00')
    open(page, 'w', encoding='utf-8').write(join(pre, D, post))
    print(f'wrote {page}: {len(D["codes"]):,} codes, {len(D["fac"]):,} providers, {len(D["nets"])} networks, insurers {", ".join(ins)}')
    return page


QUALITY_KEYS = {'hs', 'pm', 'PR', 'pper', 'nat', 'h', 'H', 'a', 'd', 'hn', 'src', 'checked'}
BY_PROVIDER = {'hs', 'pm', 'h', 'a', 'd'}   # keyed by the DFW page's provider or hospital-file positions


def empty_quality(dfw_quality_txt, out):
    """The quality ratings file is matched to providers by their position in the DFW page, so it must never be served
    with a city page. The city gets the same file with every provider match removed (no ratings shown, nothing wrong shown).
    dfw_quality_txt: the DFW file (base64 of gzip JSON) to copy the shape from, or None to use the known shape."""
    import base64, gzip
    if dfw_quality_txt:
        Q = json.loads(gzip.decompress(base64.b64decode(open(dfw_quality_txt).read().strip())))
        if set(Q) != QUALITY_KEYS: sys.exit(f'STOP: the quality file changed shape ({sorted(set(Q) ^ QUALITY_KEYS)}); update city_page.py')
    else:
        Q = {'hs': {}, 'pm': {}, 'PR': {}, 'pper': {}, 'nat': {}, 'h': {}, 'H': {}, 'a': {}, 'd': {}, 'hn': [], 'src': {}, 'checked': ''}
    for k in BY_PROVIDER: Q[k] = {}
    open(out, 'w').write(base64.b64encode(gzip.compress(json.dumps(Q, separators=(',', ':')).encode(), 6)).decode())
    return out


FUNC = """// {name} Price Finder: per-code insurer rate files from R2 (written by price-files-bot site/city_page.py)
const PREFIX = {prefix};
export async function onRequestGet({{ params, env }}) {{
  const code = String(params.code || '').replace(/\\.txt$/, '');
  if (!/^[A-Za-z0-9.-]{{1,12}}$/.test(code)) return new Response('not found', {{ status: 404 }});
  const obj = await env.PF.get(PREFIX + 't/' + code + '.txt');
  if (!obj) return new Response('not found', {{ status: 404 }});
  return new Response(obj.body, {{ headers: {{ 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' }} }});
}}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('city'); ap.add_argument('--deploy', action='store_true'); ap.add_argument('--out', default='/tmp/city')
    for a in ('template', 'embed', 'rvu', 'med-all', 't5', 'quality'): ap.add_argument('--' + a)
    A = ap.parse_args()
    if A.city not in CITIES: sys.exit(f'unknown city {A.city!r}; choose one of {", ".join(CITIES)}')
    name = CITIES[A.city][0]
    os.makedirs(A.out, exist_ok=True)
    if A.template:   # offline test: local files only
        empty_quality(A.quality, f'{A.out}/quality.txt')
        return build(A.city, A.template, A.embed, A.rvu, A.med_all, A.t5, A.out)
    import boto3
    E = os.environ
    for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET', 'CLOUDFLARE_API_TOKEN'):
        if k in E: E[k] = ''.join(E[k].split())
    B = E.get('R2_BUCKET', 'upfrontdfwdata')
    s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
    def written(k):
        try: return s3.head_object(Bucket=B, Key=k)['LastModified']
        except Exception: return None
    dirs = [c['Prefix'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=f'site/every-tx/{A.city}/', Delimiter='/')
            for c in pg.get('CommonPrefixes', [])]
    done = sorted((t, d) for d in dirs if (t := written(d + 'embed.json')))   # newest finished build by when its embed.json was written
    if not done: sys.exit(f'{name}: no finished build yet (no embed.json under site/every-tx/{A.city}/); nothing to do')
    prefix = done[-1][1]
    print('using', prefix)
    f = {k: f'{A.out}/{n}' for k, n in [('template', 'dfw.html'), ('embed', 'embed.json'), ('rvu', 'rvu.zip'), ('med', 'med.json'), ('t5', 't5.txt')]}
    for k, key in [('template', 'site/deploy/price-finder.html'), ('embed', prefix + 'embed.json'), ('rvu', 'reference/2026-09-29/cms/rvu26d-updated-08-26-2026.zip'),
                   ('med', 'reference/site/med_all.json'), ('t5', 'reference/site/msdrg_table5.txt')]:
        s3.download_file(B, key, f[k])
    page = build(A.city, f['template'], f['embed'], f['rvu'], f['med'], f['t5'], A.out)
    s3.upload_file(page, B, f'site/deploy/cities/{A.city}/price-finder.html')
    if not A.deploy: print('built, not deployed (run with deploy on to publish)'); return
    if not E.get('CLOUDFLARE_API_TOKEN'): sys.exit('CLOUDFLARE_API_TOKEN is not set; built but not deployed')
    # deploy: same steps as orchestrate.publish
    d = f'{A.out}/deploy'; shutil.rmtree(d, ignore_errors=True)
    s3.download_file(B, 'site/deploy/current.tgz', f'{A.out}/site.tgz')
    with tarfile.open(f'{A.out}/site.tgz') as t: t.extractall(d)
    if not os.path.isdir(f'{d}/functions/price-finder') or not os.path.isfile(f'{d}/site/price-finder/index.html'):
        sys.exit('STOP: site/deploy/current.tgz does not have the expected site/ and functions/ folders; nothing deployed')
    os.makedirs(f'{d}/site/{A.city}/price-finder', exist_ok=True)
    shutil.copy(page, f'{d}/site/{A.city}/price-finder/index.html')
    os.makedirs(f'{d}/site/{A.city}/price-finder/pf/q', exist_ok=True)
    dq = f'{d}/site/price-finder/pf/q/quality.txt'
    empty_quality(dq if os.path.isfile(dq) else None, f'{d}/site/{A.city}/price-finder/pf/q/quality.txt')
    fn = f'{d}/functions/{A.city}/price-finder/pf/t'; os.makedirs(fn, exist_ok=True)
    open(f'{fn}/[code].js', 'w').write(FUNC.format(name=name, prefix=json.dumps(prefix)))
    env = dict(E, CLOUDFLARE_ACCOUNT_ID=E['R2_ACCOUNT_ID'])
    r = subprocess.run(['npx', '--yes', 'wrangler@3.114.0', 'pages', 'deploy', 'site', '--project-name', 'upfront-dfw-preview', '--branch', 'main',
                        '--commit-dirty=true'], cwd=d, env=env, capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode != 0: sys.exit('deploy failed; the preview site is unchanged')
    with tarfile.open(f'{A.out}/site.tgz', 'w:gz') as t: t.add(d, arcname='.')
    s3.upload_file(f'{A.out}/site.tgz', B, 'site/deploy/current.tgz')
    print(f'live: https://upfront-dfw-preview.pages.dev/{A.city}/price-finder/')


if __name__ == '__main__':
    main()
