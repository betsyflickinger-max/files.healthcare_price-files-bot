"""V2 Redesign preview build (Oct 31, 2026). Never touches production or R2 site/deploy/current.tgz.

Starts from the live bundle (R2 site/deploy/current.tgz), then:
  1. data fixes in shared logic, used by BOTH versions:
       - source quarantine (site/source_quarantine.csv) -> /shared/hcf-data.js filters an area's hospital-file lines and map
         placements before page code reads them (review F01: the Perry, Iowa "Dallas County Hospital" file in DFW);
       - hospital profiles rebuilt with site/hospital_file_ccn.csv (F01b: Parkland's profile showed that file's $788);
       - Compare-view bill slips follow the payment choice (site/assets/pf-table.js via sitewide.py; F02);
       - Plan Calculator tab counts use the same unit and exclusions as its result count (F03).
  2. moves "Homepage v2" (Oct 18) from /v2/ to /home-b/, so /v2/ is the V2 Redesign;
  3. writes the V2 journey (site/redesign/v2_pages.py) and the shared files it reads;
  4. adds the "Original / V2 Redesign" switch to every page of both versions;
  5. deploys to the Cloudflare Pages PREVIEW branch "v2-redesign" (same password gate), unless --no-deploy;
  6. serves the result locally and takes screenshots of both journeys (/tmp/v2out/shots).

  python site/redesign/build_preview.py [--no-deploy] [--dir W] [--local-bundle DIR --local-pf DIR]
"""
import csv
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_PY = os.path.dirname(HERE)
ROOT = os.path.dirname(SITE_PY)
sys.path[:0] = [HERE, SITE_PY, os.path.join(ROOT, 'bot')]
BRANCH = 'v2-redesign'
LOG = []


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def data_block(html):
    i = html.find('id="data"')
    if i < 0:
        return None
    return json.loads(html[html.index('>', i) + 1:html.index('</script>', i)])


# ---------------------------------------------------------------- 1. shared data fixes
def quarantine(site):
    Q = list(csv.DictReader(open(os.path.join(SITE_PY, 'source_quarantine.csv'), encoding='utf-8')))
    rx = '|'.join(re.escape(q['url_contains']) for q in Q if q['url_contains'])
    areas = {}
    cities = json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8'))
    for c in cities:
        p = os.path.join(site, c['path'].strip('/'), 'index.html')
        if not os.path.exists(p):
            continue
        s = open(p, encoding='utf-8').read()
        if not any(q['url_contains'] in s for q in Q):
            continue
        D = data_block(s)
        src = (D.get('hosp') or {}).get('src') or []
        bad = [i for i, x in enumerate(src) if rx and re.search(rx, str(x[4] or ''), re.I)]
        if bad:
            areas[c['path']] = {'src': bad, 'hn': [f'{src[i][0]}|{src[i][1]}'.lower() for i in bad]}
            log(f'quarantine {c["path"]}: hospital files {bad} ({", ".join(src[i][0] for i in bad)})')
    files = [{k: q[k] for k in ('url_contains', 'file_state', 'file_ccn', 'reason', 'evidence', 'checked')} for q in Q]
    return {'rx': rx, 'files': files, 'areas': areas}


def patch_calculator(site):
    """F03: the Facility fees (N) / Doctor fees (N) tabs counted raw rate lines before exclusions; the result header counts
    distinct providers after them (e.g. 60 vs 58, 19 vs 10). Both now count distinct providers with the same exclusions."""
    p = os.path.join(site, 'plan-calculator', 'index.html')
    s = open(p, encoding='utf-8').read()
    old = "const all=D.rates.filter(r=>r[0]===p.k&&r[1]===pi);const nPro=all.filter(isPro).length;\n  $('kfac').textContent=`Facility fees (${all.length-nPro})`;$('kpro').textContent=`Doctor fees (${nPro})`;"
    new = ("const all=D.rates.filter(r=>r[0]===p.k&&r[1]===pi);"
           "/*F03 Oct 31: tab counts = distinct providers after the same exclusions as the list*/"
           "const okR=r=>(!window.__calcSkip||!window.__calcSkip(D.prov[r[2]][0],D.proc[pi]&&D.proc[pi][1]))&&!!p.cs[r[5]];"
           "const nU=f=>new Set(all.filter(r=>f(r)&&okR(r)).map(r=>r[2])).size;\n"
           "  $('kfac').textContent=`Facility fees (${nU(r=>!isPro(r))})`;$('kpro').textContent=`Doctor fees (${nU(isPro)})`;")
    # root cause found Oct 31: /calc-link.js (which defines window.__calcSkip, the "places that don't do this" rule) loads with
    # defer, so the FIRST render ran without it (60 facilities) and every later render with it (58). Render again once it is in.
    tail = "fillIns();fillPlans();fillProcs();render();"
    if tail in s and '/*F03b*/' not in s:
        s = s.replace(tail, tail + "/*F03b*/document.addEventListener('DOMContentLoaded',function(){try{render()}catch(e){}});", 1)
    if '/*F03 Oct 31' in s:
        open(p, 'w', encoding='utf-8').write(s)
        return 'already'
    if old not in s:
        log('STOP-ish: calculator tab-count code not found; F03 not applied')
        return 'not found'
    open(p, 'w', encoding='utf-8').write(s.replace(old, new, 1))
    return 'patched'


def calc_core(site):
    """The Original calculator's own cost-sharing function and fee-type test, copied verbatim for V2 (checked below)."""
    s = open(os.path.join(site, 'plan-calculator', 'index.html'), encoding='utf-8').read()
    def grab(start, end):
        i = s.index(start)
        return s[i:s.index(end, i)]
    money = grab('const money=v=>', '\n')
    ins = grab('const INS=', '\n')
    oop = grab('function oop(rate,c,dedRem,oopRem){', '\nconst QASC=')
    img = grab('const IMG=new Set(', '\n')
    ispro = grab('const isPro=r=>', '\n')
    js = ('/* Copied at build time from the Original Plan Calculator (/plan-calculator/), unchanged, so both versions use the same\n'
          '   cost-sharing math. site/redesign/build_preview.py checks each piece is found verbatim in the live page. */\n'
          'window.HCF_CALC=(function(){\n' + money + '\n' + ins + '\n' + oop + '\n'
          'function isProFor(D){' + img + '\n' + ispro + '\nreturn isPro;}\n'
          'return {oop:oop,isProFor:isProFor,INS:INS,money:money};})();\n')
    # the calculator's "places that don't do this procedure" rule, from the same file the Original loads (/calc-link.js)
    cl = open(os.path.join(site, 'calc-link.js'), encoding='utf-8').read()
    i, j = cl.index('  var NOT_HERE ='), cl.index('    return false;\n  };', cl.index('window.__calcSkip')) + len('    return false;\n  };')
    js += '(function () {\n' + cl[i:j] + '\n})();\n'
    for piece in (money, oop, img, ispro):
        assert piece in s
    return js


def profiles(site, w):
    """F01b: rebuild /hospitals/ with the corrected file -> hospital ties (site/hospital_file_ccn.csv)."""
    try:
        import hospital_profiles
        hospital_profiles.main(w, os.path.join(w, '.hosp_cache'))
        return 'rebuilt'
    except Exception as ex:
        log('hospital profiles NOT rebuilt:', repr(ex)[:300])
        return 'failed'


# ---------------------------------------------------------------- shared files for V2
def shared_files(site, w, Q, local_pf=None):
    sh = os.path.join(site, 'shared')
    os.makedirs(os.path.join(sh, 'npi'), exist_ok=True)
    js = open(os.path.join(HERE, 'shared', 'hcf-data.js'), encoding='utf-8').read()
    js = re.sub(r'/\*Q\*/.*?/\*/Q\*/', lambda m: '/*Q*/' + json.dumps(Q, ensure_ascii=False) + '/*/Q*/', js, count=1, flags=re.S)
    # the Original Price Finder's provider-name tidy rule, copied verbatim so both versions spell names the same way
    pfh = open(os.path.join(site, 'price-finder', 'index.html'), encoding='utf-8').read()
    m = re.search(r"const tidy = t => .*?'Muenster'\);", pfh, re.S)
    if m:
        js += '\nwindow.HCF && (window.HCF.tidy = (function () { ' + m.group(0) + ' return tidy; })());\n'
    else:
        log('name tidy rule not found on the Price Finder; V2 shows names as filed')
    open(os.path.join(sh, 'hcf-data.js'), 'w', encoding='utf-8').write(js)
    shutil.copyfile(os.path.join(HERE, 'shared', 'version-switch.css'), os.path.join(sh, 'version-switch.css'))
    # areas, grouped by state with the same rule as the site's area menus (site/area_menu.py)
    cities = json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8'))
    try:
        import area_menu
        sm = area_menu.state_map(site)
        st = lambda c: sm['keys'].get(c['path']) or sm['keys'].get(c['slug']) or sm['names'].get(c['name']) or c['name']
    except Exception as ex:
        log('area_menu state map unavailable:', repr(ex)[:120])
        st = lambda c: 'Texas' if c['slug'] in ('dfw',) else c['name']
    costs_slug = lambda c: 'dallas-fort-worth' if c['slug'] == 'dfw' else c['path'].strip('/').split('/')[0]
    areas = [{'slug': c['slug'], 'name': c['name'], 'path': c['path'], 'costs': costs_slug(c), 'state': st(c)} for c in cities]
    json.dump(areas, open(os.path.join(sh, 'areas.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    texas = sorted(a['name'] for a in areas if a['state'] == 'Texas')
    log(f'areas: {len(areas)}; under Texas: {len(texas)} -> {", ".join(texas)}')
    for bad in ('Arkansas', 'Maryland', 'Montana'):
        a = next((x for x in areas if x['name'] == bad), None)
        log(f'  F05 check: {bad} -> {a and a["state"]}')
    # procedures for the homepage search: every featured / plain-named code, with the DFW page's names
    D = data_block(open(os.path.join(site, 'price-finder', 'index.html'), encoding='utf-8').read())
    want = set()
    for f in ('plain_names_cpt.tsv',):
        for line in open(os.path.join(SITE_PY, f), encoding='utf-8'):
            c = line.split('\t')[0].strip()
            if c and c != 'code':
                want.add(c)
    want |= set(D.get('shop') or [])
    for r in csv.DictReader(open(os.path.join(SITE_PY, 'procedure_slugs.csv'), encoding='utf-8')):
        want.add(r['code'])
    procs = [{'code': c, 'name': D['codes'][c]['name'], 'cat': D['codes'][c].get('cat', '')} for c in sorted(want) if c in D['codes']]
    json.dump(procs, open(os.path.join(sh, 'procedures.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    log(f'procedures for search: {len(procs)}')
    # NPIs for DFW providers (same order as the page's provider list), for the receipt's NPI Registry link
    npis = None
    try:
        if local_pf:
            npis = json.load(open(os.path.join(local_pf, 'npis.json')))
        else:
            import boto3  # noqa
            from site_files import s3, B
            cur = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
            npis = json.loads(s3.get_object(Bucket=B, Key=f'site/every/{cur}/npis.json')['Body'].read())
    except Exception as ex:
        log('npis unavailable:', repr(ex)[:120])
    if npis and len(npis) == len(D['fac']):
        json.dump(npis, open(os.path.join(sh, 'npi', 'dfw.json'), 'w'))
    # hospital profile pages by NPI and by price-file address
    P = {'npi': {}, 'file': {}}
    for p in glob.glob(os.path.join(site, 'hospitals', '*', 'index.html')):
        slug = os.path.basename(os.path.dirname(p))
        s = open(p, encoding='utf-8').read()
        m = re.search(r'NPIs?</(?:th|dt|td|b)>\s*<(?:td|dd)[^>]*>([\d, ]+)<', s)
        for n in re.findall(r'\b\d{10}\b', m.group(1) if m else ''):
            P['npi'][n] = slug
        for u in re.findall(r'href="(https?://[^"]+)"', s):
            if not re.search(r'cms\.gov|archive\.org|googleapis|medicare\.gov', u):
                P['file'][u.replace('&amp;', '&')] = slug
    json.dump(P, open(os.path.join(sh, 'profiles.json'), 'w'))
    log(f'profiles: {len(P["npi"])} NPIs, {len(P["file"])} file links')
    open(os.path.join(sh, 'calc-core.js'), 'w', encoding='utf-8').write(calc_core(site))
    # version switch with the procedure-page slugs and areas filled in
    slugs = {r['slug']: r['code'] for r in csv.DictReader(open(os.path.join(SITE_PY, 'procedure_slugs.csv'), encoding='utf-8'))}
    vs = open(os.path.join(HERE, 'shared', 'version-switch.js'), encoding='utf-8').read()
    vs = vs.replace('/*SLUGS*/{}/*/SLUGS*/', '/*SLUGS*/' + json.dumps(slugs) + '/*/SLUGS*/', 1)
    vs = vs.replace('/*AREAS*/[]/*/AREAS*/', '/*AREAS*/' + json.dumps(areas, ensure_ascii=False) + '/*/AREAS*/', 1)
    open(os.path.join(sh, 'version-switch.js'), 'w', encoding='utf-8').write(vs)


# ---------------------------------------------------------------- 2. move Homepage v2
def move_home_b(site):
    src, dst = os.path.join(site, 'v2'), os.path.join(site, 'home-b')
    if os.path.isdir(src) and not os.path.isdir(dst):
        shutil.move(src, dst)
        p = os.path.join(dst, 'index.html')
        s = open(p, encoding='utf-8').read()
        s = s.replace('https://files.healthcare/v2/', 'https://files.healthcare/home-b/').replace('href="/v2/"', 'href="/home-b/"')
        open(p, 'w', encoding='utf-8').write(s)
        n = 0
        for f in glob.glob(os.path.join(site, '**', '*.html'), recursive=True):
            if '/v2/' in f.replace(site, '') or f.endswith('home-b/index.html'):
                continue
            t = open(f, encoding='utf-8').read()
            if 'href="/v2/"' in t:
                open(f, 'w', encoding='utf-8').write(t.replace('href="/v2/"', 'href="/home-b/"'))
                n += 1
        log(f'Homepage v2 moved to /home-b/ ({n} pages linked to it)')


# ---------------------------------------------------------------- 4. the switch on every Original page
TAG = ('<link rel="stylesheet" href="/shared/version-switch.css"><script src="/shared/hcf-data.js"></script>'
       '<script src="/shared/version-switch.js" defer></script>')


def add_switch(site):
    n = 0
    for f in glob.glob(os.path.join(site, '**', '*.html'), recursive=True):
        rel = f[len(site):]
        if rel.startswith('/v2/') or rel.startswith('/control/') or rel.startswith('/shared/'):
            continue
        s = open(f, encoding='utf-8').read()
        if '/shared/version-switch.js' in s:
            continue
        m = re.search(r'<head[^>]*>', s[:6000], re.I)
        if not m:
            continue
        s = s[:m.end()] + TAG + s[m.end():]
        open(f, 'w', encoding='utf-8').write(s)
        n += 1
    log(f'version switch added to {n} Original pages')


# ---------------------------------------------------------------- 5. deploy to the preview branch only
def deploy(w):
    from site_files import E
    env = dict(os.environ, **E, CLOUDFLARE_ACCOUNT_ID=E['R2_ACCOUNT_ID'])
    r = subprocess.run(['npx', '--yes', 'wrangler@3.114.0', 'pages', 'deploy', 'site', '--project-name', 'upfront-dfw-preview',
                        '--branch', BRANCH, '--commit-dirty=true'], cwd=w, env=env, capture_output=True, text=True)
    out = (r.stdout or '') + (r.stderr or '')
    print(out[-2500:])
    if r.returncode != 0:
        sys.exit('preview deploy failed; production is unchanged either way')
    urls = sorted(set(re.findall(r'https://[a-z0-9.-]+\.pages\.dev', out)))
    log('deployed to the preview branch only:', ', '.join(urls) or '(see log)', f'· branch alias https://{BRANCH}.upfront-dfw-preview.pages.dev')
    return urls


def main(out='/tmp/v2out', argv=None):
    argv = sys.argv[1:] if argv is None else argv
    w = argv[argv.index('--dir') + 1] if '--dir' in argv else '/tmp/v2w'
    local = argv[argv.index('--local-bundle') + 1] if '--local-bundle' in argv else None
    local_pf = argv[argv.index('--local-pf') + 1] if '--local-pf' in argv else None
    os.makedirs(out, exist_ok=True)
    if os.path.isdir(w):
        shutil.rmtree(w)
    if local:
        shutil.copytree(local, w)
    else:
        from site_files import s3, B
        raw = s3.get_object(Bucket=B, Key='site/deploy/current.tgz')['Body'].read()
        tarfile.open(fileobj=io.BytesIO(raw)).extractall(w, filter='fully_trusted')
        log(f'live bundle: {len(raw)/1e6:.0f} MB')
    site = os.path.join(w, 'site')
    move_home_b(site)
    if not local:
        import sitewide
        sitewide.apply(w)                      # every deploy path runs this: name, look, pf-table.js (F02 fix), area menus
        log('profiles:', profiles(site, w))
    else:
        shutil.copyfile(os.path.join(SITE_PY, 'assets', 'pf-table.js'), os.path.join(site, 'pf-table.js'))
    log('calculator F03:', patch_calculator(site))
    Q = quarantine(site)
    shared_files(site, w, Q, local_pf)
    add_switch(site)
    import v2_pages
    log('V2 pages:', v2_pages.write(site))
    json.dump({'log': LOG}, open(os.path.join(out, 'build.json'), 'w'), indent=1)
    if '--no-deploy' not in argv and not local:
        deploy(w)
    if '--shots' in argv or not local:
        try:
            import shots
            shots.run(w, out, local_pf)
        except Exception as ex:
            log('screenshots failed:', repr(ex)[:300])
    open(os.path.join(out, 'build-log.txt'), 'w').write('\n'.join(LOG))


if __name__ == '__main__':
    main()
