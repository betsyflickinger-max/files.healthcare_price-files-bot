"""Add new insurer networks to a finished Price Finder build without rebuilding it (Oct 18, 2026, Betsy OK'd).

Before: adding one insurer to a state meant a fresh build of every network (256 batches of all its tables). The Oct 16
Anthem rebuild of Colorado, Georgia and Missouri held every rented machine for 27 hours and was paused.
Now: every_code.py builds ONLY the new tables (an "add" build, ONLY_KEY), and this script merges that small build into
the state's finished build, writing a complete new build folder:

  BASE  finished build, e.g. site/every-st/georgia/2026-10/     (embed.json, npis.json, t/<code>.txt)
  ADD   add-only build, e.g. site/every-st-add/georgia/2026-10c/ (same layout, only the new networks)
  OUT   new build, e.g.     site/every-st/georgia/2026-10c/      (embed.json is written LAST: it marks the build finished)

Rules (nothing is averaged; every rate keeps its own insurer file link):
- A network in ADD that is also in BASE (same "insurer|network" key) REPLACES it: its old rows are dropped. So the same
  script refreshes one insurer's monthly files without touching the others.
- Lookup lists (networks, dates, file links, labels, providers) keep BASE's order and add new entries at the end, so
  every BASE row keeps its numbers. Providers new to the state are added at the end of npis.json / fac (map and quality
  files are re-made from npis.json each time a page is published, so they follow).
- Codes the new networks don't touch are copied inside R2 (no download).
- Flags on ADDED rows for "under a fifth of the code's median" (2) and "filler-looking" (8) are recomputed against the
  code's typical rate: BASE's own median for the code (stored by every_code.py in md/ from Oct 18, 2026), or, for builds
  made before that, the median of every network's headline rate in the merged code (no label, facility and doctor fees
  kept apart, 5+ rates needed). On real Colorado data that fallback flags fewer rates "unusually low" than a full build
  would (flags only; prices are never changed). BASE rows keep the flags their full build gave them. Flat-rate (1) and $0-listed (4) flags are per network and kept.
Writes OUT/merge.json: what was merged, replaced, added, and counts.

Env: R2_* as the other scripts; BASE, ADD, OUT; [PROCS=8]; [CODES=a,b,c testing: only these codes, embed not written
unless FULL=1].
"""
import base64, gzip, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
E = os.environ


def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)


def s3c():
    import boto3
    g = lambda k: ''.join(E[k].split())   # GitHub secrets can carry stray spaces/line breaks (as the other bot scripts do)
    return boto3.client('s3', endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                        aws_access_key_id=g('R2_ACCESS_KEY_ID'), aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name='auto')


def looks_placeholder(v, median):
    """same rule as every_code.py / procedure_pages.py"""
    import re
    if not median or v <= 5 * median:
        return False
    t = f'{v:.2f}'.rstrip('0').rstrip('.')
    nines = '9999' in t or bool(re.fullmatch(r'\d*999(\.99?)?', t))
    return nines or (v >= 100000 and v % 10000 == 0 and v > 20 * median) or v > 100 * median


def decode(body):
    """a page file: {'f': {provider: rows}} and, in a practice-view build, 'p': {practice: [[row, [doctor ids]], ...]}"""
    return json.loads(gzip.decompress(base64.b64decode(body)))
def encode(d): return base64.b64encode(gzip.compress(json.dumps({k: d[k] for k in ('f', 'p') if k in d}, separators=(',', ':')).encode(), 6))


# ---------- pure merge logic (tested in site/merge_build_test.py) ----------
def extend(base, add):
    """BASE list + ADD entries not in it; returns (combined, add index -> combined index)"""
    pos = {k: i for i, k in enumerate(base)}
    out = list(base)
    for k in add:
        if k not in pos: pos[k] = len(out); out.append(k)
    return out, [pos[k] for k in add]


def plan(be, bn, ae, an):
    """Combined lookup lists and index maps. be/ae = embed dicts, bn/an = npis lists."""
    nets, nmap = extend(be['nets'], ae['nets'])
    dates, dmap = extend(be['dates'], ae['dates'])
    urls, umap = extend(be['urls'], ae['urls'])
    labs, lmap = extend(be['labs'], ae['labs'])
    npis, pmap = extend(bn, an)
    fac = list(be['fac']) + [ae['fac'][i] for i, k in enumerate(an) if pmap[i] >= len(bn)]
    assert len(fac) == len(npis)
    replaced = sorted({nmap[i] for i in range(len(ae['nets'])) if nmap[i] < len(be['nets'])})
    return dict(nets=nets, dates=dates, urls=urls, labs=labs, npis=npis, fac=fac, nmap=nmap, dmap=dmap, umap=umap,
                lmap=lmap, pmap=pmap, replaced=replaced)


def remap_row(r, P):
    """an ADD row [net, fee, t, v, flags, date, url, more, others[[v, lab]], zeros, lab] -> combined numbering"""
    L = P['lmap']
    r = list(r)
    r[0] = P['nmap'][r[0]]; r[5] = P['dmap'][r[5]]; r[6] = P['umap'][r[6]]
    r[8] = [[o[0], L[o[1]] if o[1] >= 0 else -1] for o in r[8]]
    r[10] = L[r[10]] if r[10] >= 0 else -1
    return r


def medians(f, extra=()):
    """{fee: (median, count)} of headline rates: t=0, no modifier label, a real price (flag 4 = only $0 listed).
    extra: more rows (a practice-view build's practice rows)"""
    by = {}
    for r in [r for rows in f.values() for r in rows] + list(extra):
            if r[2] == 0 and r[10] == -1 and r[3] > 0 and not (r[4] & 4): by.setdefault(r[1], []).append(r[3])
    out = {}
    for fee, vs in by.items():
        vs.sort(); n = len(vs)
        out[fee] = ((vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2), n)
    return out


def merge_code(bf, af, P, base_md=None, keep_flags=False):
    """BASE rows (minus replaced networks) + remapped ADD rows; returns (f, row count, set of network indexes).
    base_md = {fee: [median, n]} from the BASE build's md/ files (every_code.py, from Oct 18, 2026): the same typical rate
    BASE's own rows were flagged against. Without it, the median of the merged code's headline rates is used."""
    d, n, nets = merge_doc({'f': bf} if bf is not None else None, {'f': af} if af is not None else None, P, base_md, keep_flags)
    return d['f'], n, nets


def merge_doc(bd, ad, P, base_md=None, keep_flags=False):
    """merge_code for whole page files. Oct 22, 2026: practice-view builds also carry 'p' (practice -> [[row, doctor ids]]).
    Its rows follow the same rules as 'f' (replaced networks dropped, ADD rows remapped, flags 2/8 recomputed) and doctor
    ids are remapped like provider ids. Before this, a merge kept only 'f', so a practice-view state lost its practice rows.
    Returns ({'f': ..., ['p': ...]}, rows + practice entries, network indexes)."""
    bf, af = (bd or {}).get('f'), (ad or {}).get('f')
    bp, ap = (bd or {}).get('p'), (ad or {}).get('p')
    rep = set(P['replaced'])
    f = {}
    for pi, rows in (bf or {}).items():
        keep = [r for r in rows if r[0] not in rep]
        if keep: f[pi] = keep
    added = []
    for pi, rows in (af or {}).items():
        npi_i = str(P['pmap'][int(pi)])
        for r in rows:
            r2 = remap_row(r, P); f.setdefault(npi_i, []).append(r2); added.append(r2)
    p = None
    if bp is not None or ap is not None:
        p = {}
        for pid, ents in (bp or {}).items():
            keep = [e for e in ents if e[0][0] not in rep]
            if keep: p[pid] = keep
        for pid, ents in (ap or {}).items():
            for r, docs in ents:
                r2 = remap_row(r, P); p.setdefault(pid, []).append([r2, sorted(P['pmap'][i] for i in docs)]); added.append(r2)
    md = {} if keep_flags else medians(f, [e[0] for ents in (p or {}).values() for e in ents])
    for r in ([] if keep_flags else added):   # flags 2 and 8 against the merged code (see header)
        m = (base_md or {}).get(str(r[1]))
        if not m or m[1] < 5: m = md.get(r[1])
        r[4] &= ~(2 | 8)
        if m and m[1] >= 5 and r[2] == 0 and r[3] > 0 and not (r[4] & 4):
            if r[3] < 0.2 * m[0]: r[4] |= 2
            if looks_placeholder(r[3], m[0]): r[4] |= 8
    for pi in f: f[pi].sort(key=lambda r: (r[0], r[1], r[2]))
    out = {'f': f}
    if p is not None:
        for pid in p: p[pid].sort(key=lambda e: (e[0][0], e[0][1], e[0][2], e[0][3]))
        out['p'] = p
    nets = {r[0] for rows in f.values() for r in rows} | {e[0][0] for ents in (p or {}).values() for e in ents}
    return out, sum(len(v) for v in f.values()) + sum(len(v) for v in (p or {}).values()), nets


def prac_check(be, ae, BASE, ADD):
    """Oct 22, 2026: both builds must be practice-view builds, or neither. A mix would show some networks' doctors grouped by
    practice and others one by one on the same page (or drop the practice table). ALLOW_MIX=1 overrides (tests only)."""
    if ('prac' in be) != ('prac' in ae) and not E.get('ALLOW_MIX'):
        raise SystemExit(f"STOP: {BASE} {'is' if 'prac' in be else 'is not'} a practice-view build but {ADD} "
                         f"{'is' if 'prac' in ae else 'is not'}. Build the add build with PRACTICE=1 to match (or neither); nothing written.")


def merged_prac(be, ae, P):
    """the merged practice table (practice_names.merge_prac), or None for builds without one"""
    if 'prac' not in be and 'prac' not in ae: return None
    import practice_names
    return practice_names.merge_prac(be.get('prac') or {}, ae.get('prac') or {}, P['pmap'])


# ---------- R2 work ----------
S3, GP = None, None   # GP: the index maps, set before the worker processes fork (shared, not sent with every code)
def _init():
    global S3
    S3 = s3c()


def _one(args):
    code, in_base, in_add, BASE, ADD, OUT, Bk, bmd = args
    P = GP
    keep = bool(P.get('keep_flags'))
    bd = decode(S3.get_object(Bucket=Bk, Key=f'{BASE}t/{code}.txt')['Body'].read()) if in_base else None
    ad = decode(S3.get_object(Bucket=Bk, Key=f'{ADD}t/{code}.txt')['Body'].read()) if in_add else None
    d, n, nets = merge_doc(bd, ad, P, bmd, keep)
    if n:
        S3.put_object(Bucket=Bk, Key=f'{OUT}t/{code}.txt', Body=encode(d), ContentType='text/plain')
    return code, n, sorted(nets)


def main():
    BASE, ADD, OUT, Bk = E['BASE'].strip(), E['ADD'].strip(), E['OUT'].strip(), ''.join(E['R2_BUCKET'].split())
    s3 = s3c()
    gj = lambda k: json.loads(s3.get_object(Bucket=Bk, Key=k)['Body'].read())
    be, ae = gj(BASE + 'embed.json'), gj(ADD + 'embed.json')
    bn, an = gj(BASE + 'npis.json'), gj(ADD + 'npis.json')
    P = plan(be, bn, ae, an)
    prac_check(be, ae, BASE, ADD)
    rep_names = [P['nets'][i] for i in P['replaced']]
    log('base', len(be['codes']), 'codes', len(be['nets']), 'networks', len(bn), 'providers |',
        'add', len(ae['codes']), 'codes', len(ae['nets']), 'networks', len(an), 'providers | replacing', rep_names or 'none')
    # codes that need rewriting: every code in ADD, plus BASE codes that carry a replaced network
    touched = set(ae['codes'])
    for i in P['replaced']:
        key = be['nets'][i]
        touched |= set(be['scope'][key]) if key in be['scope'] else set(be['codes'])
    allc = set(be['codes']) | set(ae['codes'])
    # Oct 18, 2026: a code BASE lists as coming (common codes first, not built yet) stays coming: merging only ADD's rows
    # would show it with just the added networks. ADD is recorded so the code's later build (on request or by the
    # background fill) adds ADD's rows for it too.
    held = (set(be.get('coming', {})) - set(be['codes'])) & set(ae['codes'])
    touched -= held; allc -= held
    if held: log(len(held), 'codes ADD has are still coming in BASE: left coming, ADD noted in coming_adds')
    if E.get('CODES'):
        only = set(E['CODES'].split(',')); allc &= only; touched &= only
    copy = sorted(allc - touched)
    log(len(touched), 'codes to merge,', len(copy), 'to copy unchanged')
    Pslim = {k: P[k] for k in ('nmap', 'dmap', 'umap', 'lmap', 'pmap', 'replaced')}
    MDB = {}
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=Bk, Prefix=BASE + 'md/'):
        for o in pg.get('Contents', []): MDB.update(gj(o['Key']))
    log('base medians for', len(MDB), 'codes' if MDB else 'codes (none stored: merged-code medians used for flags)')
    global GP
    GP = Pslim
    jobs = [(c, c in be['codes'], c in ae['codes'], BASE, ADD, OUT, Bk, MDB.get(c)) for c in sorted(touched)]
    counts, nets_of, t0 = {}, {}, time.time()
    with get_context('fork').Pool(int(E.get('PROCS', '8')), initializer=_init) as pool:
        for i, (code, n, nets) in enumerate(pool.imap_unordered(_one, jobs, chunksize=4), 1):
            if n: counts[code] = n; nets_of[code] = nets
            if i % 1000 == 0: log(f'merged {i}/{len(jobs)} ({round(time.time() - t0)} s)')
    def cp(code):
        s3.copy_object(Bucket=Bk, Key=f'{OUT}t/{code}.txt', CopySource={'Bucket': Bk, 'Key': f'{BASE}t/{code}.txt'})
    with ThreadPoolExecutor(32) as tp: list(tp.map(cp, copy))
    log('copied', len(copy), 'unchanged codes')
    for c in copy: counts[c] = be['codes'][c]['n']
    # network scope: exact for merged codes; for copied codes, BASE's scope (a BASE network not in its scope list had
    # (nearly) every code, as every_code.py writes it)
    rep = set(P['replaced'])
    scope = {}
    for c, nets in nets_of.items():
        for n_ in nets: scope.setdefault(P['nets'][n_], set()).add(c)
    for c in copy:
        for i, key in enumerate(be['nets']):
            if i in rep: continue
            if key not in be['scope'] or c in be['scope'][key]: scope.setdefault(key, set()).add(c)
    codes = {}
    for c, n in counts.items():
        e = dict(be['codes'].get(c) or ae['codes'][c]); e['n'] = n; e['f'] = None; codes[c] = e
    embed = {**be, 'codes': codes, 'fac': P['fac'], 'nets': P['nets'], 'dates': P['dates'], 'urls': P['urls'], 'labs': P['labs'],
             'scope': {k: sorted(v) for k, v in scope.items() if len(v) < len(codes) - 20}}
    pr = merged_prac(be, ae, P)
    if pr is not None: embed['prac'] = pr
    if held: embed['coming_adds'] = be.get('coming_adds', []) + [ADD]
    info = dict(at=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), base=BASE, add=ADD, out=OUT, replaced=rep_names,
                added_networks=[k for k in ae['nets'] if k not in be['nets']], merged=len(touched), copied=len(copy),
                codes=len(codes), new_codes=len(set(ae['codes']) - set(be['codes'])), providers=len(P['npis']),
                new_providers=len(P['npis']) - len(bn), lines=sum(counts.values()), seconds=round(time.time() - t0))
    s3.put_object(Bucket=Bk, Key=OUT + 'merge.json', Body=json.dumps(info, indent=1).encode())
    if E.get('CODES') and not E.get('FULL'):
        log('test run (CODES set): embed.json not written', info); return info
    s3.put_object(Bucket=Bk, Key=OUT + 'npis.json', Body=json.dumps(P['npis']).encode())
    if BASE != OUT and be.get('coming'):   # requested codes are built with BASE's tables (the merged lists start with BASE's)
        try: s3.copy_object(Bucket=Bk, Key=OUT + 'build_env.json', CopySource={'Bucket': Bk, 'Key': BASE + 'build_env.json'})
        except Exception as e_: log('build_env.json not copied:', repr(e_)[:100])
    s3.put_object(Bucket=Bk, Key=OUT + 'embed.json', Body=json.dumps(embed, separators=(',', ':')).encode())   # last: marks it finished
    log('DONE', info)
    return info


def carry_main():
    """Oct 18, 2026 (Betsy: keep the codes already built). CARRY=1: BASE = a new "common codes first" build (rare codes
    listed in embed "coming"), ADD = the area's previous full build. Every coming code the previous build has is carried
    over with its own rows, dates and file links (remapped to the new lookup lists, flags kept), marked "carried": <the
    build it came from>, so the page shows last time's prices with their original checked dates instead of "We're pulling
    these prices now". A carried code is replaced as soon as it's rebuilt (on request or by the background fill)."""
    BASE, ADD, OUT, Bk = E['BASE'].strip(), E['ADD'].strip(), E['OUT'].strip(), ''.join(E['R2_BUCKET'].split())
    s3 = s3c()
    gj = lambda k: json.loads(s3.get_object(Bucket=Bk, Key=k)['Body'].read())
    be, ae = gj(BASE + 'embed.json'), gj(ADD + 'embed.json')
    bn, an = gj(BASE + 'npis.json'), gj(ADD + 'npis.json')
    P = plan(be, bn, ae, an)
    prac_check(be, ae, BASE, ADD)
    coming = be.get('coming', {})
    carry = sorted(c for c in coming if c in ae['codes'] and ae['codes'][c].get('n'))
    built = sorted(be['codes'])
    log(len(built), 'codes built new,', len(carry), 'carried over from', ADD, ',', len(coming) - len(carry), 'still coming')
    global GP
    GP = {k: P[k] for k in ('nmap', 'dmap', 'umap', 'lmap', 'pmap')}; GP['replaced'] = []; GP['keep_flags'] = True
    jobs = [(c, False, True, BASE, ADD, OUT, Bk, None) for c in carry]
    counts, t0 = {}, time.time()
    with get_context('fork').Pool(int(E.get('PROCS', '8')), initializer=_init) as pool:
        for i, (code, n, nets) in enumerate(pool.imap_unordered(_one, jobs, chunksize=4), 1):
            if n: counts[code] = n
            if i % 1000 == 0: log(f'carried {i}/{len(jobs)} ({round(time.time() - t0)} s)')
    def cp(code): s3.copy_object(Bucket=Bk, Key=f'{OUT}t/{code}.txt', CopySource={'Bucket': Bk, 'Key': f'{BASE}t/{code}.txt'})
    if BASE != OUT:
        with ThreadPoolExecutor(32) as tp: list(tp.map(cp, built))
    codes = dict(be['codes'])
    when = ADD.rstrip('/').rsplit('/', 1)[-1]
    for c, n in counts.items():
        e = dict(ae['codes'][c]); e.update(n=n, f=None, carried=when); codes[c] = e
    left = {c: v for c, v in coming.items() if c not in counts}
    embed = {**be, 'codes': codes, 'fac': P['fac'], 'nets': P['nets'], 'dates': P['dates'], 'urls': P['urls'], 'labs': P['labs']}
    pr = merged_prac(be, ae, P)
    if pr is not None: embed['prac'] = pr
    if left: embed['coming'] = left
    else: embed.pop('coming', None)
    info = dict(at=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), mode='carry', base=BASE, add=ADD, out=OUT,
                built_new=len(built), carried=len(counts), still_coming=len(left),
                seconds=round(time.time() - t0))
    s3.put_object(Bucket=Bk, Key=OUT + 'merge.json', Body=json.dumps(info, indent=1).encode())
    s3.put_object(Bucket=Bk, Key=OUT + 'npis.json', Body=json.dumps(P['npis']).encode())
    if BASE != OUT:   # requested codes are built with BASE's tables and lookup lists (the merged lists start with them)
        try: s3.copy_object(Bucket=Bk, Key=OUT + 'build_env.json', CopySource={'Bucket': Bk, 'Key': BASE + 'build_env.json'})
        except Exception as e_: log('build_env.json not copied:', repr(e_)[:100])
    s3.put_object(Bucket=Bk, Key=OUT + 'embed.json', Body=json.dumps(embed, separators=(',', ':')).encode())
    log('DONE', info)
    return info


if __name__ == '__main__':
    carry_main() if E.get('CARRY') else main()
