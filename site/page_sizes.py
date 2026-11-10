"""What makes a Price Finder page big (Nov 9, 2026: page slimming, one state first). Reads the deployed bundle, prints each
area page's size and the size of every key in its data block (and the biggest sub-keys), largest first. Changes nothing.
Usage: python site/page_sizes.py kansas,dfw,houston"""
import json, os, re, sys, tarfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procedure_pages as pp

want = set(sys.argv[1].split(','))
store = pp.Store('/tmp/sizes')
store.s3.download_file(store.B, 'site/deploy/current.tgz', '/tmp/sizes.tgz')
pages = {}
with tarfile.open('/tmp/sizes.tgz') as t:
    cities = json.load(t.extractfile([m for m in t if m.name.lstrip('./') == 'site/cities.json'][0]))
    paths = {('site/' + a['path'].strip('/') + '/index.html'): a['slug'] for a in cities if a['slug'] in want}
    for m in t.getmembers():
        n = m.name.lstrip('./')
        if n in paths:
            pages[paths[n]] = t.extractfile(m).read().decode('utf-8', 'replace')
sz = lambda o: len(json.dumps(o, separators=(',', ':')))
for slug, html in pages.items():
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    D = json.loads(m.group(1))
    print(f'\n== {slug}: page {len(html) / 2**20:.2f} MiB, data block {len(m.group(1)) / 2**20:.2f} MiB, rest {(len(html) - len(m.group(1))) / 2**20:.2f} MiB')
    for k, v in sorted(D.items(), key=lambda kv: -sz(kv[1])):
        s = sz(v)
        if s < 20000: continue
        kind = f'list[{len(v)}]' if isinstance(v, list) else (f'dict[{len(v)}]' if isinstance(v, dict) else type(v).__name__)
        print(f'  {k:<14} {s / 2**20:7.2f} MiB  {kind}')
        if isinstance(v, dict):
            for k2, v2 in sorted(v.items(), key=lambda kv: -sz(kv[1]))[:6]:
                print(f'      .{str(k2)[:30]:<30} {sz(v2) / 2**20:6.2f} MiB')
        elif isinstance(v, list) and v:
            print(f'      e.g. {json.dumps(v[0])[:160]}')
    # other big inline scripts/styles
    for tag, body in re.findall(r'<(script|style)[^>]*>(.*?)</\1>', html, re.S):
        if len(body) > 200000 and body != m.group(1) and not body.startswith('{'):
            print(f'  inline <{tag}> {len(body) / 2**20:.2f} MiB: {body[:80]!r}')
