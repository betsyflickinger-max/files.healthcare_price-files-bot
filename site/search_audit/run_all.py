"""Search audit on every Price Finder page (Nov 7, 2026). Usage: python site/search_audit/run_all.py w/site

Serves the pulled site on localhost, runs audit.js on each price-finder/index.html, and writes
out/board/search_audit.json (one row per page) plus a short report to the GitHub run summary.
Exit code 1 (a red run, which GitHub emails about) when any page has a care item its names can't find, a code that
doesn't open when typed, prices showing under a search, or a lone "5" opening a code.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
site = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'w/site')
work = tempfile.mkdtemp()
env = dict(os.environ, AUDIT_DIR=work)
subprocess.run([sys.executable, os.path.join(HERE, 'make_tests.py')], env=env, check=True)
pages = sorted('/' + os.path.relpath(os.path.dirname(p), site).replace(os.sep, '/') + '/'
               for p in glob.glob(os.path.join(site, '**', 'price-finder', 'index.html'), recursive=True)
               # only real Price Finders: Michigan and California are region hubs, two more are redirects (no price data)
               if re.search(r'const D\s*=', open(p, encoding='utf-8', errors='replace').read()))
srv = subprocess.Popen([sys.executable, '-m', 'http.server', '8765', '-d', site], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
rows, bad = [], 0
try:
    for n, pg in enumerate(pages):
        subprocess.run(['node', os.path.join(HERE, 'audit.js')], env=dict(env, PAGE_PATH=pg, PAGE_N=str(n)), timeout=900)
        r = json.load(open(os.path.join(work, f'result-{n}.json')))
        names = r.get('names', [])
        missed = sorted({f"{x['item']} (“{x['q']}”)" for x in names if not x['rank']})
        low = sum(1 for x in names if x['rank'] and x['rank'] > 3)
        codes_bad = [f"{x['code']} → {x['got']}" for x in r.get('codes', []) if not x['ok']]
        sv = r.get('searchView', {})
        problems = ([f"page didn't load: {r['crash']}"] if r.get('crash') else []) \
            + ([f"{len(missed)} names found nothing: " + '; '.join(missed[:8])] if missed else []) \
            + ([f"{len(codes_bad)} codes didn't open when typed: " + ', '.join(codes_bad[:8])] if codes_bad else []) \
            + (["prices show under a search"] if sv and not sv.get('pricesHidden') else []) \
            + (["?code= stays in the address under a search"] if sv and not sv.get('noCodeInUrl') else []) \
            + ([f"typing 5 opened {r['five']}"] if r.get('five', 'ok') != 'ok' else []) \
            + ([f"page errors: {'; '.join(r['errors'])}"] if r.get('errors') else [])
        bad += bool(problems)
        rows.append({'id': pg, 'page': pg, 'names_tested': len(names), 'names_top3': sum(1 for x in names if x['rank'] and x['rank'] <= 3),
                     'names_lower': low, 'names_missed': len(missed), 'codes_tested': len(r.get('codes', [])), 'codes_bad': len(codes_bad),
                     'status': 'OK' if not problems else 'Check', 'problems': ' | '.join(problems)})
        print(f"{pg}: {rows[-1]['status']} {rows[-1]['problems']}", flush=True)
finally:
    srv.terminate()
os.makedirs('out/board', exist_ok=True)
json.dump(rows, open('out/board/search_audit.json', 'w'), separators=(',', ':'))
summ = os.environ.get('GITHUB_STEP_SUMMARY')
if summ:
    with open(summ, 'a') as f:
        f.write(f"## Search audit: {len(rows) - bad} of {len(rows)} Price Finder pages OK\n\n| Page | Names found (top 3 / lower / missed) | Codes that open | Problems |\n|---|---|---|---|\n")
        for x in rows:
            f.write(f"| {x['page']} | {x['names_top3']} / {x['names_lower']} / {x['names_missed']} | {x['codes_tested'] - x['codes_bad']} of {x['codes_tested']} | {x['problems'] or 'none'} |\n")
print(f"search audit: {len(rows) - bad} of {len(rows)} pages OK")
sys.exit(1 if bad else 0)
