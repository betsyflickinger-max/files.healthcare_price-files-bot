"""Check what's actually live (Oct 31, 2026): reads the deployed bundle (site/deploy/current.tgz) and prints, for a few DFW price
pages and the methodology page, whether card #2's pieces are there. The live site is password-protected, so this is how to check it."""
import io, re, sys, tarfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import procedure_pages as pp

PAGES = ['costs/dallas-fort-worth/gallbladder-removal', 'costs/dallas-fort-worth/vaginal-birth', 'costs/dallas-fort-worth/knee-arthroscopy',
         'costs/dallas-fort-worth/cataract-surgery', 'costs/dallas-fort-worth/colonoscopy', 'methodology']


def text(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


store = pp.Store('/tmp/live')
body = store.s3.get_object(Bucket=store.B, Key='site/deploy/current.tgz')['Body'].read()
t = tarfile.open(fileobj=io.BytesIO(body))
names = {m.name.lstrip('./'): m for m in t.getmembers() if m.isfile()}
out = ['# What is live (deployed bundle)', '']
for p in PAGES:
    k = f'site/{p}/index.html'
    if k not in names:
        alt = [n for n in names if n.startswith('site/costs/dallas-fort-worth/') and p.split('/')[-1].split('-')[0] in n][:3]
        out += [f'## {p}: not in bundle (similar: {alt})', '']
        continue
    h = t.extractfile(names[k]).read().decode()
    x = text(h)
    out += [f'## {p}', '',
            f"- proof lines: {len(re.findall(r'(Medicare|Medicaid): [0-9,]+ ', x))}",
            f"- 'Ranked:' caption (old, option A): {'Ranked: places with a Medicare' in x}",
            f"- price-order caption (option B): {'Order is by price only. Where Medicare or Medicaid' in x}",
            f"- 'No record found' labels: {x.count('No Medicare or Medicaid record found')}",
            "- also-listed: " + ((re.search(r'Also listed, may not offer this procedure \(\d+\)', x) or [''])[0]),
            "- methodology records section: " + str('id="proof"' in h or "id='proof'" in h) + f" (old 'Who's ranked' title: {'Who' + chr(39) + 's ranked' in x})",
            f"- anesthesia caption: {(re.search(r'[0-9,]+ anesthesia clinicians? listed under this', x) or [''])[0]}",
            ]
    m = re.search(r'(Lowest|least expensive).{0,900}', x, re.I)
    out += [f"- lowest excerpt: {m.group(0)[:900] if m else '(not found)'}", '']
print('\n'.join(out))

# Oct 31, 2026: states-first area dropdowns (site/area_menu.py): the script, its place -> state list, and which pages link it
import json, collections
out = ['# Area dropdowns (states first)', '']
js = names.get('site/area-menu.js')
if not js:
    out.append('- /area-menu.js: MISSING')
else:
    s = t.extractfile(js).read().decode()
    m = re.search(r'/\*AREA_MAP\*/(.*?)/\*AREA_MAP_END\*/', s, re.S)
    M = json.loads(m.group(1)) if m else {'names': {}}
    by = collections.defaultdict(list)
    for n, st in M['names'].items():
        by[st].append(n)
    out.append(f"- /area-menu.js: present, {len(M['names'])} places in {len(by)} states")
    out += [f"  - {st}: {len(v)} ({', '.join(sorted(v)) if len(v) > 1 else v[0]})" for st, v in sorted(by.items())]
for k in ('site/index.html', 'site/v2/index.html', 'site/story/index.html', 'site/price-finder/index.html', 'site/control/index.html'):
    if k in names:
        out.append(f"- {k}: linked {'area-menu.js' in t.extractfile(names[k]).read().decode()}")
miss = [n for n in names if n.endswith('.html') and b'<select' in t.extractfile(names[n]).read() and b'area-menu.js' not in t.extractfile(names[n]).read()]
out.append(f"- pages with a dropdown but no link: {len(miss)} {miss[:5]}")
print('\n'.join(out))
