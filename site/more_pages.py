"""More price pages (Betsy, Oct 19, 2026): the top procedures in every place, beyond the 89 featured ones.

Why R2 and not static files: Cloudflare Pages allows about 20,000 files per deploy and the site already uses ~8,000. 2,000
procedures x ~32 places is ~64,000 pages (plus a prices.csv each). So these pages are rendered here, with the same code and rules
as the featured pages (procedure_pages.summarize / procedure_page: nothing estimated, every price linked to its file), saved to R2
under site/more/, and served by the Pages Function functions/costs/[[path]].js (written into the deploy by procedure_pages.py).

  python site/more_pages.py plan DIR [--n 2000]      # once: pick each place's codes, fix their URLs -> R2 site/more/plan.json
  python site/more_pages.py build DIR --area SLUG [--shard I --of K]   # one place, or its I-th of K parts (matrix) -> R2
  python site/more_pages.py index DIR                # after all places: "every procedure" list per place + sitemap -> R2

DIR holds the pulled live site (python site/site_files.py pull DIR). Featured codes (codes89.csv) keep their static pages.
Codes picked: the place's codes with the most published rate lines (the Price Finder's own count), so thin codes come last.
Pages with too little data carry noindex, exactly like the featured pages.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import procedure_pages as pp   # noqa: E402

PFX = 'site/more/'
_W, _STORES = {}, {}


def own_store(site_dir):
    pid = os.getpid()
    if pid not in _STORES:
        _STORES[pid] = pp.Store(site_dir)
    return _STORES[pid]


def _call_batch(codes, threads=4):
    """Runs in a forked worker: this process's share of the codes, a few at a time (threads overlap the R2 downloads)."""
    out = []
    with ThreadPoolExecutor(threads) as ex:
        for j, r in enumerate(ex.map(_W['one'], codes)):
            if r:
                out.append(r)
            if (j + 1) % 50 == 0:
                print(f'  worker {os.getpid()}: {j + 1} of {len(codes)}', flush=True)
    return out
esc = pp.esc


def areas_of(site):
    return json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8'))


def page_path(site, a):
    return os.path.join(site, a['path'].strip('/'), 'index.html')


def put(store, key, body, ctype):
    store.s3.put_object(Bucket=store.B, Key=PFX + key, Body=body.encode('utf-8') if isinstance(body, str) else body,
                        ContentType=ctype, CacheControl='public, max-age=3600')


def get_json(store, key, default=None):
    try:
        return json.loads(store.s3.get_object(Bucket=store.B, Key=PFX + key)['Body'].read())
    except Exception:
        return default


def plan(site_dir, store, n):
    site = os.path.join(site_dir, 'site')
    featured = {r['code'] for r in csv.DictReader(open(os.path.join(HERE, 'codes89.csv')))}
    per, names, cats = {}, {}, {}
    for a in areas_of(site):
        p = page_path(site, a)
        if not os.path.isfile(p):
            continue
        D = pp.page_data(p)[0]
        top = sorted((c for c, v in D['codes'].items() if c not in featured and (v.get('n') or 0) > 0),
                     key=lambda c: -(D['codes'][c].get('n') or 0))[:n]
        per[a['slug']] = top
        for c in top:
            names.setdefault(c, D['codes'][c]['name'])
            cats.setdefault(c, D['codes'][c].get('cat', ''))
        del D
        print(a['slug'], len(top), flush=True)
    allc = sorted({c for v in per.values() for c in v})
    slugs = load_slugs_fast(allc, names)
    put(store, 'plan.json', json.dumps({'areas': per, 'slugs': {c: slugs[c] for c in allc}, 'names': names, 'cats': cats,
                                        'built': pp.TODAY.isoformat()}, separators=(',', ':')), 'application/json')
    print(f'plan: {len(per)} places, {len(allc)} distinct codes')


def load_slugs_fast(codes, names):
    """Same rules as procedure_pages.load_slugs (stable once given, short name unless two codes share it), but O(n) and
    without writing procedure_slugs.csv: featured slugs come from that file and are never reused."""
    path = os.path.join(HERE, 'procedure_slugs.csv')
    have = {r['code']: r['slug'] for r in csv.DictReader(open(path))} if os.path.isfile(path) else {}
    out, used = {}, set(have.values())
    short = {c: pp.slugify(re.sub(r'\([^)]*\)', '', names[c])) for c in codes}
    count = Counter(short.values())
    for c in codes:
        if c in have:
            out[c] = have[c]
            continue
        s = pp.SLUG_OVERRIDE.get(c) or (pp.slugify(names[c]) if count[short[c]] > 1 else short[c]) or c.lower()
        if s in used:
            s = f'{s}-{c.lower()}'
        out[c] = s
        used.add(s)
    return out


def build_area(site_dir, store, slug, threads=16, shard=0, of=1):
    site = os.path.join(site_dir, 'site')
    pp.site_settings(site)
    P = get_json(store, 'plan.json')
    if not P or slug not in P['areas']:
        sys.exit(f'no plan for {slug}; run plan first')
    areas = areas_of(site)
    a = next(x for x in areas if x['slug'] == slug)
    au = pp.area_url_slug(slug)
    D, med_area, _ = pp.page_data(page_path(site, a))
    loc = store.local_medicare(a, len(D['fac']))
    pst = store.provider_states(a, D)   # out-of-state providers left out, same as the featured pages
    codes = [c for c in P['areas'][slug] if c in D['codes']]
    mine = codes[shard::of]   # this job's share (jobs for one place run side by side)
    slugs, live = P['slugs'], {s: set(v) for s, v in P['areas'].items()}
    others_by = {x['slug']: (x['name'], pp.area_url_slug(x['slug'])) for x in areas}

    def one(c):
        store = own_store(site_dir)   # one R2 client per worker process (clients aren't safe to share across a fork)
        try:
            S = pp.summarize(D, c, store.get(a, 't', c), store.get(a, 'h', c), loc, pp.area_state(a), pst)
        except Exception as e:
            print(f'  {c}: skipped ({type(e).__name__}: {e})', flush=True)
            return None
        if not S or not S.get('any'):
            return None
        ps = slugs[c]
        others = [(others_by[s][0], f'/costs/{others_by[s][1]}/{ps}/') for s in live if s != slug and c in live[s] and s in others_by]
        related = [(P['names'][x], f'/costs/{au}/{slugs[x]}/') for x in codes if x != c and P['cats'].get(x) == S['cat']][:12]
        html_ = pp.procedure_page(a, S, others, related, med_area, a['path'], au, ps)
        put(store, f'{au}/{ps}/index.html', html_, 'text/html; charset=utf-8')
        rows = S.pop('csv', None)
        if rows is not None:
            import io
            b = io.StringIO()
            w = csv.writer(b)
            w.writerow([f"# {S['name']} ({S['type']} {S['code']}) in {a['name']}. Source files linked per row. Built {pp.TODAY.isoformat()} by {pp.SITE['name']}."])
            w.writerow(['type', 'provider', 'city', 'kind', 'insurer', 'network or label', 'price', 'file date', 'source'])
            w.writerows(rows)
            put(store, f'{au}/{ps}/prices.csv', b.getvalue(), 'text/csv; charset=utf-8')
        return {'code': c, 'slug': ps, 'name': S['name'], 'cat': S['cat'], 'providers': S['providers'],
                'lo': S['lo']['v'] if S.get('lo') else None, 'hi': S['hi']['v'] if S.get('hi') else None,
                'index': bool(S.get('index', S['any']))}

    done = []
    # The work is mostly Python (reading big rate files, working out figures), so one thread pool only used one core
    # (Oct 19 test: 200 pages in 40 min). Forked worker processes, each with a few threads for the R2 waits, use every core.
    _W['one'] = one
    import multiprocessing as mp
    procs = os.cpu_count() or 2
    with ProcessPoolExecutor(procs, mp_context=mp.get_context('fork')) as ex:
        for r in ex.map(_call_batch, [mine[k::procs] for k in range(procs)]):
            done += r
    put(store, f'{au}/manifest-{shard}-of-{of}.json', json.dumps({'area': slug, 'name': a['name'], 'built': pp.TODAY.isoformat(), 'pages': done},
                                                 separators=(',', ':')), 'application/json')
    print(f'{slug} part {shard + 1}/{of}: {len(done)} pages ({sum(1 for d in done if d["index"])} indexable) of {len(mine)} codes')


def index(site_dir, store):
    """Per place: /costs/<place>/all/ (every procedure, grouped by kind, each group closed until tapped) + one sitemap."""
    site = os.path.join(site_dir, 'site')
    pp.site_settings(site)
    urls = []
    for a in areas_of(site):
        au = pp.area_url_slug(a['slug'])
        parts = [o['Key'] for o in store.s3.list_objects_v2(Bucket=store.B, Prefix=f'{PFX}{au}/manifest-').get('Contents', [])]
        if parts:   # merge the side-by-side jobs' lists (only the newest split, in case the number of parts changed)
            of = max(int(k.rsplit('-of-', 1)[1].split('.')[0]) for k in parts)
            got = [get_json(store, k[len(PFX):]) for k in parts if k.endswith(f'-of-{of}.json')]
            M = {'area': a['slug'], 'name': a['name'], 'built': pp.TODAY.isoformat(), 'pages': [r for g in got if g for r in g['pages']]}
            put(store, f'{au}/manifest.json', json.dumps(M, separators=(',', ':')), 'application/json')
        else:
            M = get_json(store, f'{au}/manifest.json')
        if not M:
            continue
        cats = {}
        for r in sorted(M['pages'], key=lambda r: r['name'].lower()):
            cats.setdefault(r['cat'] or 'Other', []).append(r)
        groups = ''.join(
            f"<details class='st'><summary class='chip'>{esc(c)} <span class='m'>· {len(rs)}</span></summary><div class='chips'>"
            + ''.join(f"<a class='chip' href='/costs/{au}/{r['slug']}/'>{esc(r['name'])}</a>" for r in rs) + "</div></details>"
            for c, rs in sorted(cats.items()))
        n = len(M['pages'])
        title = f"Every Procedure Priced in {a['name']} ({pp.TODAY.year}): {n:,} Pages | {pp.SITE['name']}"
        desc = (f"{n:,} more procedures, tests and services in {a['name']}, each with the lowest and highest published negotiated rate "
                f"and a link to the file it came from.")
        body = (f'<main><section class="board"><div class="wrap"><p class="eyebrow"><a href="/costs/">All places</a> · '
                f'<a href="/costs/{au}/">{esc(a["name"])}</a></p><h1 class="letters">Every procedure<em> in {esc(a["name"])}</em></h1>'
                f'<p class="lead">{esc(desc)} Tap a group to open it.</p></div></section><div class="wrap"><section class="sec">'
                f"<div class='chips states'>{groups}</div></section></div></main>")
        put(store, f'{au}/all/index.html', pp.shell(title, desc, f'/costs/{au}/all/', body,
                                                   {'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': title}),
            'text/html; charset=utf-8')
        urls.append(f'/costs/{au}/all/')
        urls += [f"/costs/{au}/{r['slug']}/" for r in M['pages'] if r['index']]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + ''.join(f'<url><loc>{esc(pp.SITE["origin"] + u)}</loc><lastmod>{pp.TODAY.isoformat()}</lastmod></url>\n' for u in urls[:50000])
           + '</urlset>\n')
    put(store, 'more-sitemap.xml', xml, 'application/xml')
    print(f'index: {len(urls)} URLs in the sitemap')


# The Pages Function, written into the deploy by procedure_pages.py (keep in sync with PFX above).
FUNCTION_JS = r'''// /costs/* : pages kept in R2 (site/more/) by site/more_pages.py, for procedures beyond the featured ones.
// Written by price-files-bot site/procedure_pages.py; edits here are replaced on the next run.
// R2 is checked first only for paths that look like those pages; everything else (and any R2 miss) goes to the static site.
const PFX = 'site/more/';
const TYPES = {html: 'text/html; charset=utf-8', csv: 'text/csv; charset=utf-8', xml: 'application/xml', json: 'application/json'};
export async function onRequest(ctx) {
  const url = new URL(ctx.request.url);
  const m = url.pathname.match(/^\/costs\/(more-sitemap\.xml|[a-z0-9-]+\/[a-z0-9-]+\/(?:index\.html|prices\.csv)?)$/);
  if (!m || !ctx.env.PF || !['GET', 'HEAD'].includes(ctx.request.method)) return ctx.next();
  const key = PFX + (m[1].endsWith('/') ? m[1] + 'index.html' : m[1]);
  const obj = await ctx.env.PF.get(key);
  if (!obj) return ctx.next();
  const ext = key.split('.').pop();
  const h = {'content-type': TYPES[ext] || 'application/octet-stream', 'cache-control': 'public, max-age=3600'};
  if (ext === 'csv') h['content-disposition'] = 'inline';
  return new Response(ctx.request.method === 'HEAD' ? null : obj.body, {headers: h});
}
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['plan', 'build', 'index'])
    ap.add_argument('dir')
    ap.add_argument('--area')
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--shard', type=int, default=0)
    ap.add_argument('--of', type=int, default=1)
    x = ap.parse_args()
    store = pp.Store(x.dir)
    if x.cmd == 'plan':
        plan(x.dir, store, x.n)
    elif x.cmd == 'build':
        build_area(x.dir, store, x.area, shard=x.shard, of=x.of)
    else:
        index(x.dir, store)


if __name__ == '__main__':
    main()
