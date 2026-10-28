"""Price Finder "Compare" view (Oct 19, 2026, Betsy): every place x every insurer, Medicare and Medicare Advantage columns,
the doctor's fee row, one-network view, compare side by side. The view itself is site/assets/pf-table.js + pf-table.css.

  patch(s)          the tags and the "What it costs" eyebrow for one Price Finder page or stored layout (idempotent)
  apply(d)          copy the two files into DIR/site and patch every Price Finder page there (site/sitewide.py calls this
                    before every deploy, so city/state rebuilds keep it)
  write_ml(d)       ml.json next to each Price Finder: adds f = {provider index: wage index} (places matched to their Medicare
                    record, site/med_local.py) and h = {hospital file index: [provider index...]} (the file's CMS ID from
                    data/hospitals.csv, then that hospital's NPIs from med_local + site/hospital_npi_matches.csv). Needs R2_*.
  python site/pf_table.py DIR [--ml]
"""
import csv
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSS = '<link rel="stylesheet" href="/pf-table.css">'
JS = '<script src="/pf-table.js"></script>'
EYEBROW = re.compile(r'(<div class="eyebrow">)([^<]*?) · published prices(</div>)')


CALC_FROM = 'const ps=byIns[S.ins].slice().sort('
CALC_TO = ('const ps=(()=>{const seen={};return byIns[S.ins].filter(p=>{const k=JSON.stringify([p.n,p.m,p.d,p.x,p.k,p.cs]);'
           'if(seen[k])return false;seen[k]=1;return true})})().sort(')


MAP_FROM = "    if (!best) continue;\n    const [name, city, kind] = D.fac[fi];"
MAP_TO = ("    if (!best) continue;\n    if (window.__ptFits && M.fee === 0 && !window.__ptFits(S.code, +fi)) continue;   // places that don't do this (pf-table.js)\n"
          "    if (window.__ptDocOk && M.fee === 1 && !window.__ptDocOk(S.code, +fi)) continue;\n    const [name, city, kind] = D.fac[fi];")
CALC_ROWS_FROM = "const rows=all.filter(r=>S.kind==='pro'?isPro(r):!isPro(r));"
CALC_ROWS_TO = "const rows=all.filter(r=>S.kind==='pro'?isPro(r):!isPro(r)).filter(r=>!window.__calcSkip||!window.__calcSkip(D.prov[r[2]][0],D.proc[pi]&&D.proc[pi][1]));"
CALC_JS = '<script src="/calc-link.js" defer></script>'
CALC_OWN_FROM = "    if (cls === 0 && f[2] === 'P') continue;\n    list.push({f, r: mine[0],"
CALC_OWN_TO = ("    if (cls === 0 && f[2] === 'P') continue;\n    if (cls === 0 && window.__calcSkip && window.__calcSkip(f[0], M.codes[code] && M.codes[code][0])) continue;\n"
               "    list.push({f, r: mine[0],")
CALC_FLAT = ("'<span class=\"flag\">flat case rate</span>'", "'<span class=\"flag\">same price for many procedures</span>'")


def is_pf(s):
    return 'id="vPatient"' in s and 'function renderBoard()' in s


def patch(s):
    if not is_pf(s):
        return s
    if CSS not in s:
        i = s.find('</head>')
        s = s[:i] + CSS + s[i:] if i >= 0 else CSS + s
    if JS not in s:
        i = s.rfind('</body>')
        s = s[:i] + JS + s[i:] if i >= 0 else s + JS
    s = s.replace('<span class="flag flat">flat case rate</span>', '<span class="flag flat" title="The same amount is listed for five or more different procedures at this place, so it is not specific to this one">same price for many procedures</span>')
    # a shared link's &net= survives the first render, which rewrites the address to ?code= (second first-visitor test)
    s = s.replace('window.__uxQ=new URLSearchParams(location.search).get("q")}',
                  'window.__uxQ=new URLSearchParams(location.search).get("q");window.__uxNet=new URLSearchParams(location.search).get("net")}', 1)
    if 'window.__uxNet=' in s:
        s = s.replace("let chosen = !!new URLSearchParams(location.search).get('net');", "let chosen = !!window.__uxNet;")
        s = s.replace("/*netparam*/ { const qn = new URLSearchParams(location.search).get('net');", "/*netparam*/ { const qn = window.__uxNet;")
    return EYEBROW.sub(r'\1What it costs · \2\3', s)


def apply(d):
    site = os.path.join(d, 'site')
    if not os.path.isdir(site):
        return 0
    for f in ('pf-table.js', 'pf-table.css'):
        shutil.copyfile(os.path.join(HERE, 'assets', f), os.path.join(site, f))
    n = 0
    pc = os.path.join(site, 'plan-calculator', 'index.html')     # one entry per plan design (Oct 19 test: plans sold under several IDs listed twice)
    shutil.copyfile(os.path.join(HERE, 'assets', 'calc-link.js'), os.path.join(site, 'calc-link.js'))
    mj = os.path.join(site, 'price-finder', 'map.js')
    if os.path.isfile(mj):
        t0 = open(mj, encoding='utf-8').read()
        if MAP_FROM in t0 and '__ptFits' not in t0:
            open(mj, 'w', encoding='utf-8').write(t0.replace(MAP_FROM, MAP_TO, 1)); n += 1
    if os.path.isfile(pc):
        t0 = open(pc, encoding='utf-8').read()
        t1 = t0.replace(CALC_FROM, CALC_TO) if CALC_TO not in t0 else t0
        if CALC_ROWS_TO not in t1:
            t1 = t1.replace(CALC_ROWS_FROM, CALC_ROWS_TO)
        if 'window.__calcSkip(f[0]' not in t1:
            t1 = t1.replace(CALC_OWN_FROM, CALC_OWN_TO)
        t1 = t1.replace(*CALC_FLAT)
        if CALC_JS not in t1 and '</head>' in t1:
            t1 = t1.replace('</head>', CALC_JS + '</head>', 1)
        if t1 != t0:
            open(pc, 'w', encoding='utf-8').write(t1)
            n += 1
    for root, _, fs in os.walk(site):
        if os.path.basename(root) == 'price-finder' and 'index.html' in fs:
            p = os.path.join(root, 'index.html')
            s = open(p, encoding='utf-8').read()
            t = patch(s)
            if t != s:
                open(p, 'w', encoding='utf-8').write(t)
                n += 1
    return n


def nice(t):
    sys.path.insert(0, HERE)
    from procedure_pages import nice as _n
    return _n(t)


def _sig(xs):
    import hashlib
    return hashlib.sha1('|'.join(map(str, xs)).encode()).hexdigest()[:12]


def write_ml(d, only_stale=False):
    import boto3
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    if not all(E.values()):
        return 0
    s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
    B = E['R2_BUCKET']
    ML = json.loads(s3.get_object(Bucket=B, Key='site/med_local/2026.json')['Body'].read())['npi']
    ccn_npis = {}
    for npi, m in ML.items():
        if m[0] == 'H' and len(m) > 2 and m[2]:
            ccn_npis.setdefault(m[2], set()).add(npi)
    for fn in ('hospital_npi_matches.csv', 'hospital_npi_manual.csv'):
        p = os.path.join(HERE, fn)
        if os.path.isfile(p):
            for r in csv.DictReader(open(p, encoding='utf-8')):
                ccn_npis.setdefault(r['ccn'], set()).add(r['npi'])
    url_ccn, ccn_name = {}, {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'hospitals.csv'), encoding='utf-8')):
        if r.get('name'):
            ccn_name[r['ccn']] = r['name'].strip()
        if r.get('mrf_url'):
            url_ccn.setdefault(r['mrf_url'].strip(), set()).add(r['ccn'])
    site, n = os.path.join(d, 'site'), 0
    for a in json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8')):
        page = os.path.join(site, a['path'].strip('/'), 'index.html')
        if not os.path.isfile(page):
            continue
        mp = os.path.join(os.path.dirname(page), 'ml.json')
        try:
            t = open(page, encoding='utf-8').read()
            i = t.find('id="data"')
            D = json.loads(t[t.find('>', i) + 1:t.find('</script>', i)])
            old = json.load(open(mp)) if os.path.isfile(mp) else {}
            srcs = [x[5] for x in (D.get('hosp') or {}).get('src') or []]
            if only_stale and old.get('nf') == len(D['fac']) and old.get('hs') == _sig(srcs) and 'nm' in old and ('outc' in old or a['slug'] != 'dfw'):
                continue
            if a['slug'] == 'dfw':
                root = 'site/every/' + s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip() + '/'
            else:
                fn = os.path.join(d, 'functions', a['slug'], 'price-finder', 'pf', 't', '[code].js')
                root = re.search(r'PREFIX = "([^"]+)"', open(fn, encoding='utf-8').read()).group(1)
                root = root[:-2] if root.endswith('t/') else root
            npis = json.loads(s3.get_object(Bucket=B, Key=root + 'npis.json')['Body'].read())
        except Exception as e:
            print(f"  {a['slug']}: skipped ({type(e).__name__})")
            continue
        fac = D['fac']
        if len(fac) != len(npis):
            print(f"  {a['slug']}: provider list and npis.json differ; skipped")
            continue
        out = old or {'src': 'site/med_local.py'}
        r, f, ni = {}, {}, {}
        for i, (x, npi) in enumerate(zip(fac, npis)):
            ni.setdefault(npi, []).append(i)
            m = ML.get(npi)
            kd = 'H' if x[2] == 'A' and re.search(r'\bhospital\b', x[0], re.I) else x[2]
            if m and m[0] == kd:
                f[i] = m[1]
                q = r.setdefault(kd, [m[1], m[1], 0])
                q[0], q[1], q[2] = min(q[0], m[1]), max(q[1], m[1]), q[2] + 1
        # the name people know: CMS's hospital name for the place's Medicare ID, when only one place in this list has that ID
        nm, by_ccn = {}, {}
        for i, (x, npi) in enumerate(zip(fac, npis)):
            m = ML.get(npi)
            if m and m[0] == 'H' and len(m) > 2 and m[2] and m[2] in ccn_name:
                by_ccn.setdefault(m[2], []).append(i)
        for c, idx in by_ccn.items():
            if len({re.sub(r'[^a-z]', '', fac[i][0].lower()) for i in idx}) != 1:
                continue
            nice_name = nice(ccn_name[c])
            for i in idx:
                if nice_name.lower() != fac[i][0].lower():
                    nm[i] = nice_name
        h = {}
        for si, x in enumerate((D.get('hosp') or {}).get('src') or []):
            fis = sorted({i for c in url_ccn.get(str(x[4]).strip(), ()) for npi in ccn_npis.get(c, ()) for i in ni.get(npi, ())
                          if fac[i][2] in ('H', 'A')})
            if fis:
                h[si] = [x[5], fis]           # the file's own key, so a rebuilt page with files in a new order can't misattribute
        if a['slug'] == 'dfw':
            try:
                out['outc'] = sorted(json.load(open(os.path.join(HERE, 'dfw_metro.json')))['outside'])
            except Exception:
                pass
        out.update({'r': r or out.get('r', {}), 'f': f, 'h': h, 'nm': nm, 'nf': len(fac), 'hs': _sig(srcs)})
        open(mp, 'w').write(json.dumps(out, separators=(',', ':')))
        n += 1
        print(f"  {a['slug']}: {len(nm)} common hospital names, {len(f)} places with local Medicare, {len(h)} of {len((D.get('hosp') or {}).get('src') or [])} hospital files tied to places")
    return n


if __name__ == '__main__':
    print(f'pf_table: {apply(sys.argv[1])} Price Finder pages patched')
    if '--ml' in sys.argv:
        print(f'pf_table: ml.json written for {write_ml(sys.argv[1])} Price Finders')
