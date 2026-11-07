"""Robot tester, part 2 runner (Nov 7, 2026). Usage: python site/site_check/run_browser.py w [workers]

Starts serve.py on the pulled site (w/site + w/functions), runs browser_check.js on every Price Finder page with a fixed
set of common procedures plus a few random codes, and writes out/board/site_check_pages.json plus the run summary.
"""
import concurrent.futures as cf
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
W = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'w')
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
FIXED = ["27447", "45378", "73721", "58140", "743", "470", "59510", "80053", "29881", "66984", "99213", "74177"]
sys.path.insert(0, os.path.join(ROOT, 'site'))
import search_aliases as sa  # noqa: E402
CARE = [[n, cs] for n, _, cs in sa.build()]
pages = sorted('/' + os.path.relpath(os.path.dirname(p), os.path.join(W, 'site')).replace(os.sep, '/') + '/'
               for p in glob.glob(os.path.join(W, 'site', '**', 'price-finder', 'index.html'), recursive=True))
tmp = tempfile.mkdtemp()
srv = subprocess.Popen([sys.executable, os.path.join(HERE, 'serve.py'), W, '8765'])
time.sleep(5)


def one(a):
    n, pg = a
    out = os.path.join(tmp, f'{n}.json')
    env = dict(os.environ, PAGE_PATH=pg, OUT_FILE=out, CODES=json.dumps(FIXED), RANDOM_CODES='4', CARE=json.dumps(CARE))
    try:
        subprocess.run(['node', os.path.join(HERE, 'browser_check.js')], env=env, timeout=2400)
        return json.load(open(out))
    except Exception as e:
        return {'page': pg, 'crash': str(e)[:200], 'rows': []}


try:
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        res = list(ex.map(one, enumerate(pages)))
finally:
    srv.terminate()

rows = []
for r in res:
    probs = []
    if r.get('crash'):
        probs.append('page did not load: ' + r['crash'])
    for x in r['rows']:
        tag = f"{x['code']} {x['name'][:40]}"
        if x['loadFailed']: probs.append(f'{tag}: rates did not load')
        elif x['stillLoading']: probs.append(f'{tag}: still loading after 16 s')
        if not x['titleOk']: probs.append(f"{tag}: heading says “{x['title']}”")
        if x['leaks']: probs.append(f"{tag}: shows {', '.join(x['leaks'])}")
        if x['zero']: probs.append(f"{tag}: {x['zero']} prices of $0.00")
        if not x['prices'] and not x['loadFailed'] and x['code'] in FIXED: probs.append(f'{tag}: no prices shown')
        if x['errors']: probs.append(f"{tag}: page error {x['errors'][0]}")
        # a hospital-price file missing for one code just means no hospital posted that code here; missing for every
        # code checked means the page can't load hospital prices at all (San Angelo, Nov 7: no pf/h route)
        other = [h for h in x['httpErrors'] if '/pf/h/' not in h]
        if other: probs.append(f"{tag}: missing file {other[0]}")
    hmiss = [x for x in r['rows'] if any('/pf/h/' in h for h in x['httpErrors'])]
    if r['rows'] and len(hmiss) == len(r['rows']):
        probs.insert(0, f"hospital prices didn't load for any of the {len(r['rows'])} procedures checked (e.g. {hmiss[0]['httpErrors'][0]})")
    rows.append({'id': r['page'], 'page': r['page'], 'codes_on_page': r.get('nCodes', 0), 'codes_checked': len(r['rows']),
                 'common_missing': len(r.get('missing', [])), 'common_missing_list': '; '.join(r.get('missing', []))[:600],
                 'status': 'Check' if probs else 'OK', 'problems': ' | '.join(probs)[:1500]})
os.makedirs('out/board', exist_ok=True)
json.dump(rows, open('out/board/site_check_pages.json', 'w'), separators=(',', ':'))
bad = sum(r['status'] != 'OK' for r in rows)
print(f'browser check: {len(rows) - bad} of {len(rows)} Price Finder pages OK')
summ = os.environ.get('GITHUB_STEP_SUMMARY')
if summ:
    with open(summ, 'a') as f:
        f.write(f'## Robot tester: Price Finder pages ({len(rows) - bad} of {len(rows)} OK)\n\n| Page | Codes | Common procedures missing | Problems |\n|---|---|---|---|\n')
        for r in sorted(rows, key=lambda r: (r['status'] == 'OK', r['page'])):
            f.write(f"| {r['page']} | {r['codes_on_page']} | {r['common_missing']} | {r['problems'][:300] or 'none'} |\n")
