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
    return EYEBROW.sub(r'\1What it costs · \2\3', s)


def apply(d):
    site = os.path.join(d, 'site')
    if not os.path.isdir(site):
        return 0
    for f in ('pf-table.js', 'pf-table.css'):
        shutil.copyfile(os.path.join(HERE, 'assets', f), os.path.join(site, f))
    n = 0
    for root, _, fs in os.walk(site):
        if os.path.basename(root) == 'price-finder' and 'index.html' in fs:
            p = os.path.join(root, 'index.html')
            s = open(p, encoding='utf-8').read()
            t = patch(s)
            if t != s:
                open(p, 'w', encoding='utf-8').write(t)
                n += 1
    return n


def _sig(xs):
    import hashlib
    return hashlib.sha1('|'.join(map(str, xs)).encode()).hexdigest()[:12]


def write_ml(d, only_stale=False):
    import boto3
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    if not all(E.values()):
        return 0
    s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
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
    url_ccn = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'hospitals.csv'), encoding='utf-8')):
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
            if only_stale and old.get('nf') == len(D['fac']) and old.get('hs') == _sig(srcs):
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
        h = {}
        for si, x in enumerate((D.get('hosp') or {}).get('src') or []):
            fis = sorted({i for c in url_ccn.get(str(x[4]).strip(), ()) for npi in ccn_npis.get(c, ()) for i in ni.get(npi, ())
                          if fac[i][2] in ('H', 'A')})
            if fis:
                h[si] = [x[5], fis]           # the file's own key, so a rebuilt page with files in a new order can't misattribute
        out.update({'r': r or out.get('r', {}), 'f': f, 'h': h, 'nf': len(fac), 'hs': _sig(srcs)})
        open(mp, 'w').write(json.dumps(out, separators=(',', ':')))
        n += 1
        print(f"  {a['slug']}: {len(f)} places with local Medicare, {len(h)} of {len((D.get('hosp') or {}).get('src') or [])} hospital files tied to places")
    return n


if __name__ == '__main__':
    print(f'pf_table: {apply(sys.argv[1])} Price Finder pages patched')
    if '--ml' in sys.argv:
        print(f'pf_table: ml.json written for {write_ml(sys.argv[1])} Price Finders')
