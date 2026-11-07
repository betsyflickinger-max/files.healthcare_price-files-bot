"""Data accuracy audit, Layer 3: evidence packets for the Claude sample audit (Nov 6, 2026, Betsy OK'd).

Builds 350 packets: 300 random price lines (200 insurer, 100 hospital-file) plus 50 "risky" ones (the worst Layer 1 findings and
the highest amounts on the sampled pages). Each packet holds everything an auditor needs without downloading any price file:
  - what the page data says (provider, NPI, insurer and network, amount, labels, file date, source link)
  - what the published procedure page says about that provider (text around the name), for the 89 featured procedures
  - the source: the insurer table rows for that code + NPI, or the cited line of the archived hospital file
  - the NPI Registry entry (name, practice address, specialty), fetched live
Same independence rule as Layer 2: imports only audit/roundtrip.py, never site/ or bot/.

Output: reports/audit/<date>/packets/batch-NN.md (25 packets each), packets/results_template.csv, and packets/AUDITOR.md (the
checklist the auditing Claude follows). Usage: python audit/evidence.py [--random 300] [--risky 50] [--seed N]
"""
import argparse, csv, html, json, os, random, re, sys, tarfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roundtrip as R   # noqa: E402

AUDITOR = """# Auditor instructions (Layer 3 sample audit)

You are auditing price lines on The Healthcare Files (files.healthcare) before it opens to the public. You did not build this
data. Judge only what the packet shows. Never fix anything; report.

For each packet, answer in results.csv (one row per packet, keep the packet id):

1. **page_ok**: does the page data line match what the published page says about this provider? (amount, insurer/network,
   provider) yes / no / not on a published page (fine for non-featured codes) / can't tell
2. **source_ok**: does the source (insurer table row or hospital file line) carry the same code, provider and amount? yes / no / can't tell
3. **place_ok**: is the provider really in the page's state and area (NPI Registry practice address)? yes / no / can't tell
4. **insurer_ok**: does the file's own insurer name match the insurer shown? yes / no / can't tell
5. **meaning_ok**: is the amount labeled right: facility vs doctor fee, in vs out of network, per day/per unit vs whole service,
   modifier (part only), capitation/bundle, expired, percent of charges? yes / no / can't tell. Plausible for this kind of
   provider (an audiologist with a colonoscopy rate is a "ghost rate": say so in the note)?
6. **link_ok**: does the page's source link name the same file the source rows came from? yes / no / can't tell
7. **fresh_ok**: is the file date shown, and if it's older than 6 months, is that obvious? yes / no
8. **verdict**: Pass / Critical / Major / Minor
   - Critical: wrong amount; wrong provider, insurer, network, code or state; out-of-network shown as in-network; one
     hospital's file on another hospital
   - Major: dead or wrong link; missing/wrong date; wrong or missing label (per day shown as total, part-only fee, capitation)
   - Minor: name formatting, typos
9. **note**: one sentence on why (required for anything but Pass).

"Can't tell" is an honest answer; never guess. Work in batches of 25 (one batch file per session).
"""


def bundle_texts():
    """Page lists plus plain text of every /costs/ procedure page, from the deployed bundle."""
    want = re.compile(r'^(site/cities\.json|site/.*price-finder/index\.html|functions/.*/price-finder/pf/[th]/\[code\]\.js)$')
    costs = re.compile(r'^site/costs/([^/]+)/([^/]+)/index\.html$')
    files, text = {}, {}
    body = R.s3.get_object(Bucket=R.B, Key='site/deploy/current.tgz')['Body']
    with tarfile.open(fileobj=body, mode='r|gz') as t:
        for m in t:
            n = m.name.lstrip('./')
            if not m.isfile():
                continue
            if want.match(n):
                files[n] = t.extractfile(m).read().decode('utf-8', 'replace')
            else:
                c = costs.match(n)
                if c:
                    s = t.extractfile(m).read().decode('utf-8', 'replace')
                    s = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', s, flags=re.S)
                    text[(c.group(1), c.group(2))] = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)))
    return files, text


def page_excerpt(text, area, code, name, value, slugs):
    au = 'dallas-fort-worth' if area == 'dfw' else area
    s = text.get((au, slugs.get(code, '')))
    if s is None:
        return 'no published procedure page for this code and area (not a featured page)'
    out, low = [], s.lower()
    key = (name or '').lower()[:28]
    i = low.find(key) if key else -1
    while i >= 0 and len(out) < 3:
        out.append(s[max(0, i - 160):i + 260])
        i = low.find(key, i + 1)
    amt = f'${value:,.2f}'
    return (f"amount {amt} {'appears' if amt in s else 'does not appear'} on the page. " +
            (' … '.join(out) if out else 'provider name not found on the page (the page lists the lowest and highest only)'))[:1400]


def npi_registry(npi):
    import requests
    if not npi or not re.fullmatch(r'\d{10}', str(npi)):
        return ''
    for _ in range(3):
        try:
            j = requests.get('https://npiregistry.cms.hhs.gov/api/', params={'version': '2.1', 'number': npi}, timeout=20).json()
            r = (j.get('results') or [None])[0]
            if not r:
                return 'not in the NPI Registry'
            b = r.get('basic', {})
            nm = b.get('organization_name') or f"{b.get('first_name', '')} {b.get('last_name', '')} {b.get('credential', '')}".strip()
            loc = next((a for a in r.get('addresses', []) if a.get('address_purpose') == 'LOCATION'), {})
            tx = next((t for t in r.get('taxonomies', []) if t.get('primary')), (r.get('taxonomies') or [{}])[0])
            return f"{nm}; practice: {loc.get('city', '')}, {loc.get('state', '')} {str(loc.get('postal_code', ''))[:5]}; {tx.get('desc', '')}"
        except Exception:
            time.sleep(2)
    return 'registry lookup failed'


def risky_from_layer1(n):
    """Critical and Major examples from the newest Layer 1 run (reports/audit/<day>/examples.csv), as a list of hints."""
    import glob
    ps = sorted(glob.glob(os.path.join(R.REPO, 'reports', 'audit', '*', 'examples.csv')))
    if not ps:
        return []
    p = ps[-1]
    rows = [r for r in csv.DictReader(open(p)) if r['level'] in ('Critical', 'Major') and r.get('code') and ',' not in r['code']]
    rows.sort(key=lambda r: r['level'] != 'Critical')
    seen, out = set(), []
    for r in rows:
        k = (r['rule'], r['area'])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
        if len(out) >= n:
            break
    return out


def publish(od, what):
    """On GitHub Actions: commit and push the packets folder now, so each batch is readable as soon as it's written."""
    if not os.environ.get('GITHUB_ACTIONS'):
        return
    import subprocess
    sh = lambda *a: subprocess.run(a, cwd=R.REPO, capture_output=True, text=True)
    sh('git', 'config', 'user.name', 'price-files-bot')
    sh('git', 'config', 'user.email', 'price-files-bot@users.noreply.github.com')
    sh('git', 'add', od)
    if sh('git', 'commit', '-m', f'Evidence packets {R.TODAY}: {what}').returncode == 0:
        ref = os.environ.get('GITHUB_REF_NAME', 'audit')
        for _ in range(3):
            sh('git', 'pull', '--rebase', '-q', 'origin', ref)
            if sh('git', 'push', 'origin', f'HEAD:{ref}').returncode == 0:
                print('pushed', what, flush=True)
                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--random', type=int, default=300)
    ap.add_argument('--risky', type=int, default=50)
    ap.add_argument('--seed', type=int, default=int(R.TODAY.replace('-', '')) + 3)
    A = ap.parse_args()
    rnd = random.Random(A.seed)
    print('reading the deployed site...', flush=True)
    files, text = bundle_texts()
    areas = json.loads(files['site/cities.json'])
    featured = [r['code'] for r in csv.DictReader(open(os.path.join(R.REPO, 'site', 'codes89.csv')))]
    slugs = {r['code']: r['slug'] for r in csv.DictReader(open(os.path.join(R.REPO, 'site', 'procedure_slugs.csv')))} \
        if os.path.isfile(os.path.join(R.REPO, 'site', 'procedure_slugs.csv')) else {}
    n_ins, n_h = A.random * 2 // 3, A.random - A.random * 2 // 3
    ins, hosp = R.sample(files, areas, n_ins + 40, n_h + 20, rnd, featured)
    rnd.shuffle(ins)
    rnd.shuffle(hosp)
    ins, hosp = ins[:n_ins], hosp[:n_h]
    for x in ins + hosp:
        x['why'] = 'random'
    # risky: half from Layer 1's worst findings, half the highest amounts among lines on the sampled areas' featured pages
    hints = risky_from_layer1(A.risky // 2)
    extra_i, extra_h = R.sample(files, areas, 600, 200, random.Random(A.seed + 1), featured)
    top = sorted(extra_i, key=lambda x: -x['value'])[:A.risky - len(hints)]
    for x in top:
        x['why'] = 'risky: among the highest amounts sampled'
    ins += top
    for hnt in hints:
        hit = [x for x in extra_h if x['area'] == hnt['area'] and x['code'] == hnt['code'] and x['hospital'] == hnt['provider']] + \
              [x for x in extra_i if x['area'] == hnt['area'] and x['code'] == hnt['code'] and x['provider'] == hnt['provider']]
        if hit:
            hit[0]['why'] = f"risky: Layer 1 {hnt['rule']} ({hnt['level']}): {hnt['detail'][:80]}"
            (hosp if 'hospital' in hit[0] else ins).append(hit[0])
        else:   # keep the Layer 1 example itself as a packet (the auditor reads it from the page data fields given)
            ins.append(dict(area=hnt['area'], code=hnt['code'], provider=hnt['provider'], npi=hnt['npi'], net=f"{hnt['insurer']}|{hnt['plan']}",
                            fee='', pct=False, value=float(hnt['value'] or 0), file_date=hnt['file_date'], url=hnt['url'],
                            why=f"risky: Layer 1 {hnt['rule']} ({hnt['level']}): {hnt['detail'][:80]}"))
    del files
    print(f'{len(ins)} insurer and {len(hosp)} hospital packets; tracing sources...', flush=True)
    R.KEEP_ROWS = True
    od = os.path.join(R.REPO, 'reports', 'audit', R.TODAY, 'packets')
    os.makedirs(od, exist_ok=True)
    open(os.path.join(od, 'AUDITOR.md'), 'w').write(AUDITOR)
    allp = [('I', x) for x in ins] + [('H', x) for x in hosp]
    rnd.shuffle(allp)
    with open(os.path.join(od, 'results_template.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['packet', 'why', 'page_ok', 'source_ok', 'place_ok', 'insurer_ok', 'meaning_ok', 'link_ok', 'fresh_ok', 'verdict', 'note'])
        for i, (k, x) in enumerate(allp, 1):
            w.writerow([f'P{i:03d}', x.get('why', ''), '', '', '', '', '', '', '', '', ''])
    publish(od, 'checklist and results template')
    import time
    stop = time.time() + 150 * 60          # whole run: batches not reached in time are written untraced, never lost
    for b in range(0, len(allp), 25):
        part = allp[b:b + 25]   # Nov 7 (Betsy): each batch is traced, written and pushed as soon as it's done, so review can start
        if time.time() < stop:
            R.check_hospital([x for k, x in part if k == 'H'], 6)
            R.check_insurer([x for k, x in part if k == 'I' and x.get('npi')], 15, max(1, (stop - time.time()) / 60))
        L = [f'# Evidence packets {b + 1}-{min(b + 25, len(allp))} ({R.TODAY})', '', 'Follow AUDITOR.md. One results row per packet.', '']
        for i, (k, x) in enumerate(allp[b:b + 25], b + 1):
            name = x.get('provider') or x.get('hospital')
            L += [f'## P{i:03d} · {x["area"]} · code {x["code"]} · {x.get("why", "random")}', '',
                  '**Page data says:** ' + (f"{name} (NPI {x.get('npi') or 'none on page'}) · {x.get('net', '').replace('|', ' / ')} · "
                                            f"{x.get('fee', '')} fee · {'percent of charges ' if x.get('pct') else ''}${x['value']:,.2f} · "
                                            f"file date {x.get('file_date') or 'none'}" if k == 'I' else
                                            f"{name} · {x.get('what')} · payer {x.get('payer') or 'n/a'} · "
                                            f"{'percent ' if x.get('pct') else ''}${float(x['value']):,.2f} · file date {x.get('file_date') or 'none'} · "
                                            f"cited {x.get('unit')} {x.get('row')}"),
                  f"**Source link on the page:** {x.get('url') or 'none'}",
                  f"**Published procedure page:** {page_excerpt(text, x['area'], x['code'], name, float(x['value']), slugs)}",
                  f"**Automatic trace:** {x.get('verdict', 'not traced')}{(' · ' + x['detail']) if x.get('detail') else ''}"]
            if k == 'I':
                L += [f"**File's own insurer name / date:** {x.get('source_entity') or 'n/a'} / {x.get('source_date') or 'n/a'}",
                      f"**Source rows (code + NPI, up to 6):** {json.dumps(x.get('source_rows') or [])[:1500]}",
                      f"**NPI Registry:** {npi_registry(x.get('npi'))}"]
            else:
                L += [f"**Cited line of the archived original:** {(x.get('source_text') or 'n/a')[:900]}"]
            L.append('')
        open(os.path.join(od, f'batch-{b // 25 + 1:02d}.md'), 'w').write('\n'.join(L))
        publish(od, f'batch {b // 25 + 1}')
    print(f'{len(allp)} packets in {(len(allp) + 24) // 25} batches: {od}')


if __name__ == '__main__':
    main()
