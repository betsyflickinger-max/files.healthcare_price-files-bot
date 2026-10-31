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
