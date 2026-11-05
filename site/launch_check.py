"""Launch check (Nov 4, 2026), read-only: reads the deployed bundle (R2 site/deploy/current.tgz) and reports on the
seven "do now" items from Betsy's TODO.md, so we can see what's actually live before changing anything."""
import io, re, sys, tarfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import procedure_pages as pp

def text(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))

store = pp.Store('/tmp/live')
body = store.s3.get_object(Bucket=store.B, Key='site/deploy/current.tgz')['Body'].read()
t = tarfile.open(fileobj=io.BytesIO(body))
names = {m.name.lstrip('./'): m for m in t.getmembers() if m.isfile()}
def get(k):
    return t.extractfile(names[k]).read().decode('utf-8', 'replace') if k in names else None
out = ['# Launch check (deployed bundle)', f'files in bundle: {len(names)}', '']

# 1. V2 data fixes
out.append('## 1. V2 data fixes')
hp = [n for n in names if n.startswith('site/hospitals/') and 'parkland' in n]
for k in hp[:3]:
    x = text(get(k)); out.append(f'- {k}: has $788: {"$788" in x}; mentions Perry/dallascohospital: {"Perry" in x or "dallascohospital" in x}')
pf = get('site/pf-table.js') or ''
out.append(f'- pf-table.js present: {bool(pf)}; cash slip fix: {"lowest to highest cash price" in pf}')
calc = get('site/plan-calculator/index.html') or ''
out.append(f'- calculator: F03 tab fix: {"/*F03 Oct 31" in calc}; F03b re-render: {"/*F03b*/" in calc}; '
           f'old tab code present: {"const nPro=all.filter(isPro).length;" in calc}; render tail present: {"fillIns();fillPlans();fillProcs();render();" in calc}')
geo = [n for n in names if re.search(r'(geo|map)[^/]*\.json$', n)][:8]
for k in geo:
    s = get(k) or ''
    if 'dallascohospital' in s or 'Dallas County Hospital' in s:
        i = s.find('Dallas County Hospital'); out.append(f'- {k}: mentions Dallas County Hospital: {s[max(0,i-150):i+200]!r}')
out.append('')

# 2. sign-ups
out.append('## 2. Email sign-up forms')
forms = {}
for n in names:
    if n.endswith('.html'):
        s = get(n)
        if 'type="email"' in s or "type='email'" in s:
            for m in re.finditer(r'<form[^>]*>', s):
                forms.setdefault(m.group(0)[:200], []).append(n)
            if '<form' not in s:
                forms.setdefault('(email input, no <form>)', []).append(n)
for f, ps in forms.items():
    out.append(f'- {f}  -> {len(ps)} pages, e.g. {ps[:4]}')
fn = sorted(n for n in names if n.startswith('functions/'))
out.append(f'- functions/: {fn}')
for n in fn:
    s = get(n) or ''
    for kw in ('signup', 'subscribe', 'alert', 'email', 'KV', 'R2', 'fetch('):
        if kw in s:
            out.append(f'  - {n} mentions {kw!r}')
for n in fn:
    s = get(n) or ''
    m = re.search(r'.{0,300}(signup|subscribe).{0,600}', s, re.S | re.I)
    if m: out.append(f'  - {n} excerpt: {m.group(0)[:900]!r}')
for n in [n for n in names if n.endswith('.html')][:5000]:
    s = get(n)
    m = re.search(r"fetch\(['\"](/[^'\"]*(sign|sub|alert|notify)[^'\"]*)", s or '', re.I)
    if m: out.append(f'- {n} posts to {m.group(1)}'); break
for kw in ('Price alert', 'price alert', 'weekly receipt', 'Weekly receipt', 'Detach and return'):
    hits = [n for n in names if n.endswith('.html') and kw in (get(n) or '')]
    if hits: out.append(f'- "{kw}" on {len(hits)} pages, e.g. {hits[:3]}')
out.append('')

# 3. My Plan
out.append('## 3. My Plan')
mp = [n for n in names if 'my-plan' in n or 'myplan' in n][:10]
out.append(f'- files: {mp}')
for k in mp:
    s = get(k) or ''
    d = sorted(set(re.findall(r'20\d\d-\d\d-\d\d', s)))
    out.append(f'  - {k}: dates in file: {d[-6:]}')
out.append('')

# 4. Methodology
out.append('## 4. Methodology')
mt = get('site/methodology/index.html')
if mt:
    x = text(mt)
    for pat in (r'[^.]{0,200}(12 months|twelve months|six months|6 months)[^.]{0,200}\.', r'[^.]{0,250}(contact|reached out|right of reply|right-of-reply)[^.]{0,250}\.'):
        for m in re.finditer(pat, x, re.I):
            out.append(f'- {m.group(0).strip()[:450]}')
else:
    out.append('- methodology page not found')
out.append('')

# 7. packages + coming list
out.append('## 7. Procedure packages and "pulling these prices now"')
pk = [n for n in names if 'package' in n.lower()][:10]
out.append(f'- package files: {pk}')
for kw in ('package', 'Package'):
    hits = [n for n in names if n.endswith('.html') and re.search(r'(facility \+ doctor|Procedure package|package price)', get(n) or '', re.I)]
    out.append(f'- pages with package wording: {len(hits)}, e.g. {hits[:4]}'); break
hits = [n for n in names if n.endswith(('.html', '.js', '.json')) and re.search(r"pulling these prices|We're pulling|\"coming\"", get(n) or '')]
out.append(f'- "pulling these prices now"/coming: {len(hits)} files, e.g. {hits[:5]}')
print('\n'.join(out))
