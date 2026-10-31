"""Before/after preview of card #2 (proof a provider does the procedure) on Dallas-Fort Worth price pages. Deploys nothing.

Reads the live site bundle and the DFW Price Finder's per-code files exactly as site/procedure_pages.py does, runs summarize()
without and with proof (site/proof.py), and writes reports/proof-preview/dfw.md: for each sample procedure, the lowest 10
before and after, the proof line on each ranked provider, and who would be listed as "also listed, may not offer this procedure".

  python site/proof_preview.py [--codes 29881,66984,...]   (also renders the DFW gallbladder page: reports/proof-preview/dfw-gallbladder.html)
"""
import argparse
import collections
import datetime as dt
import json
import os
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import procedure_pages as pp   # noqa: E402
from proof import Proof, line, load_taxonomy, for_page  # noqa: E402

SAMPLE = ['29881', '66984', '47562', '64721', '45378', '27447', '73721', '59400', '99213']


def money(v):
    return f"${v:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes')
    A = ap.parse_args()
    d = '/tmp/proofprev'
    os.makedirs(d, exist_ok=True)
    store = pp.Store(d)
    s3, B = store.s3, store.B
    s3.download_file(B, 'site/deploy/current.tgz', f'{d}/site.tgz')
    with tarfile.open(f'{d}/site.tgz') as t:
        mem = {m.name.lstrip('./'): m for m in t.getmembers() if m.isfile()}
        areas = json.load(t.extractfile(mem['site/cities.json']))
        a = next(x for x in areas if x['slug'] == 'dfw')
        want = f"site/{a['path'].strip('/')}/index.html"
        os.makedirs(os.path.dirname(f'{d}/{want}'), exist_ok=True)
        open(f'{d}/{want}', 'wb').write(t.extractfile(mem[want]).read())
        open(f'{d}/site/index.html', 'wb').write(t.extractfile(mem['site/index.html']).read())
    D = pp.page_data(f'{d}/{want}')[0]
    loc = store.local_medicare(a, len(D['fac']))
    pst = store.provider_states(a, D)
    pre = store.prefix(a, 't')
    npis = json.loads(s3.get_object(Bucket=B, Key=pre[:-2] + 'npis.json')['Body'].read())
    assert len(npis) == len(D['fac']), 'npis.json is not aligned with the page providers'
    P = Proof(s3, B, tax=load_taxonomy(s3, B))
    codes = [c for c in (A.codes.split(',') if A.codes else SAMPLE) if c in D['codes']]
    out = [f"# Card #2 preview: Dallas-Fort Worth price pages, before and after", "",
           f"Built {dt.date.today().isoformat()} by site/proof_preview.py. Nothing deployed. Proof data: Medicare 2024 + Medicaid 2023-2024 "
           f"(Texas). Order stays by price; proof only decides who is in the ranked lists.", ""]
    tot = collections.Counter()
    for c in codes:
        C = D['codes'][c]
        t, h = store.get(a, 't', c), store.get(a, 'h', c)
        drg = 'DRG' in (C.get('type') or '')
        f = (t or {}).get('f') or C.get('f') or {}
        prf, why = {}, collections.Counter()
        for fi in f:
            i = int(fi)
            x = D['fac'][i]
            kind = pp.kind_of(x)
            ccn = (loc.get(i) or [None, None, None])[2]
            st, info = P.status(kind, npis[i], ccn, c, C['name'], C.get('cat', ''), drg)
            prf[i] = (st, {'text': line(info), 'url': info['url']} if st == 'proved' else info)
            why[(kind, st)] += 1
            tot[(kind, st)] += 1
        S0 = pp.summarize(D, c, t, h, loc, 'TX', pst)
        S1 = pp.summarize(D, c, t, h, loc, 'TX', pst, prf)
        out += [f"## {C['name']} ({c})", "",
                "Providers on the page by kind and proof: " + "; ".join(f"{pp.KIND.get(k, k)} {s}: {n}" for (k, s), n in sorted(why.items())), ""]
        out += ["| # | Before (today) | After | Proof shown |", "|---|---|---|---|"]
        for j in range(max(len(S0['lowest']), len(S1['lowest']))):
            b = S0['lowest'][j] if j < len(S0['lowest']) else None
            n = S1['lowest'][j] if j < len(S1['lowest']) else None
            out.append(f"| {j + 1} | {(b['name'] + ' ' + money(b['v'])) if b else ''} | {(n['name'] + ' ' + money(n['v'])) if n else ''} | "
                       f"{(n.get('proof') or {}).get('text', '') if n else ''} |")
        al = S1['also_listed']
        for e in al:
            cc = (loc.get(e['fi']) or [None, None, None])[2]
            e['diag'] = f"CCN {cc}, {P.ccn_groups.get(cc, 0)} Medicare outpatient groups on record" if cc else 'no CCN'
        out += ["", f"Left out of the figures (anesthesia clinicians under this code): {S1['n_wrong_specialty']}; lowest before {money(S0['lo']['v']) if S0['lo'] else '-'}, after {money(S1['lo']['v']) if S1['lo'] else '-'}"]
        out += ["", f"Also listed, may not offer this procedure: {len(al)}" + (" (" + "; ".join(f"{e['name']} {money(e['v'])} [{e.get('diag', '')}]" for e in al[:8])
                                                                               + (" ..." if len(al) > 8 else "") + ")" if al else ""), ""]
        if c == '47562':   # one full page, rendered exactly as the live build would, to check the HTML
            pp.site_settings(f'{d}/site')
            slug = pp.load_slugs([c], {c: C['name']})[c]
            html_ = pp.procedure_page(a, S1, [], [], pp.page_data(f'{d}/{want}')[1], a['path'], pp.area_url_slug('dfw'), slug)
            (HERE.parent / 'reports' / 'proof-preview').mkdir(parents=True, exist_ok=True)
            (HERE.parent / 'reports' / 'proof-preview' / 'dfw-gallbladder.html').write_text(html_)
    out += ["## All sample procedures together", "", "| Kind | Proved | Ranked as before (no file covers them) | Held out (no record) |",
            "|---|---|---|---|"]
    for k in sorted({k for k, _ in tot}):
        out.append(f"| {pp.KIND.get(k, k)} | {tot[(k, 'proved')]} | {tot[(k, 'not_covered')]} | {tot[(k, 'no_record')]} |")
    rp = HERE.parent / 'reports' / 'proof-preview'
    rp.mkdir(parents=True, exist_ok=True)
    (rp / 'dfw.md').write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == '__main__':
    main()
