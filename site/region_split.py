"""Oct 31, 2026 (Betsy chose regional pages for California): split a state's finished insurer build into one build per region
(site/regions.py), so each regional Price Finder page is a normal page built from its own files.

Everything on a page and in its per-code price files refers to providers by their position in the build's provider list
(embed.json fac, npis.json, t/<code>.txt keys and practice doctor lists, the practice table). A region gets:
  - fac / npis.json: only its providers, in the same order, so positions are renumbered 0..n-1;
  - t/<code>.txt: the same rows, re-keyed to the new positions; providers outside the region dropped; a practice row keeps
    only the region's doctors (dropped when none are left); a code with no row in the region gets no file and leaves codes;
  - codes: each code's row count recounted for the region (same count as every_code.py: provider rows + practice rows);
  - scope (networks that have only some codes): narrowed to the region's codes that network has rows for;
  - prac: practices with at least one doctor in the region, doctor lists renumbered;
  - nets, dates, urls, labs: unchanged (rows refer to them by position, and they are the same for the whole state);
  - coming (codes not built yet, built on request into the state's build): left off; a request on a regional page would
    land in the state build, not the region's. Those codes reach the regions with the next split.
No price is changed, averaged or estimated: every row is copied as it is from the state build.
A provider is placed by its practice ZIP's county; a provider with no usable ZIP is placed by its city when every placed
provider with that city name is in one region, else left off the regional pages (counted in the log and in split.json).
Writes site/every-st/<region>/<YYYY-MM>/{t/, npis.json, build_env.json, embed.json, split.json}; split.json (last) records
the state build it came from, so hosp_area.py splits again when the state build changes.
Usage: python site/region_split.py california   (runs on a rented machine from hosp_area.py; reads and writes R2)"""
import base64, collections, gzip, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regions


def s3c():
    import boto3
    E = os.environ
    return boto3.client('s3', endpoint_url=(E.get('STORAGE_ENDPOINT') or f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com"),
                        aws_access_key_id=''.join(E['R2_ACCESS_KEY_ID'].split()), aws_secret_access_key=''.join(E['R2_SECRET_ACCESS_KEY'].split()),
                        region_name=(E.get('STORAGE_REGION') or 'auto'))


B = ''.join(os.environ.get('R2_BUCKET', 'upfrontdfwdata').split())
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def dec(b): return json.loads(gzip.decompress(base64.b64decode(b)))
def enc(o): return base64.b64encode(gzip.compress(json.dumps(o, separators=(',', ':')).encode(), 6))


G = {}
def _init(newi, src, dst):
    G.update(newi=newi, src=src, dst=dst, s3=s3c())


def one(code):
    """one code's price file -> one file per region; returns {region: (row count, networks with rows)}"""
    s3 = G['s3']
    for t in range(5):
        try: o = dec(s3.get_object(Bucket=B, Key=f"{G['src']}t/{code}.txt")['Body'].read()); break
        except Exception:
            if t == 4: raise
            time.sleep(5 * (t + 1))
    f, p = o.get('f', {}), o.get('p')
    res = {}
    for r, newi in G['newi'].items():
        nf = {}
        for k, rows in f.items():
            j = newi[int(k)]
            if j >= 0: nf[str(j)] = rows
        out = {'f': nf}
        n = sum(len(v) for v in nf.values()); nets = {row[0] for v in nf.values() for row in v}
        if p is not None:
            np_ = {}
            for pid, lst in p.items():
                keep = []
                for row, docs in lst:
                    d = [newi[x] for x in docs if newi[x] >= 0]
                    if d: keep.append([row, d])
                if keep: np_[pid] = keep
            out['p'] = np_
            n += sum(len(v) for v in np_.values()); nets |= {e[0][0] for v in np_.values() for e in v}
        if n:
            body = enc(out)
            for t in range(5):
                try: s3.put_object(Bucket=B, Key=f"{G['dst'][r]}t/{code}.txt", Body=body, ContentType='text/plain'); break
                except Exception:
                    if t == 4: raise
                    time.sleep(5 * (t + 1))
        res[r] = (n, sorted(nets))
    return code, res


def main(state):
    import city_page, duckdb
    from hosp_area import newest_build
    s3 = s3c()
    regions.check(state)
    R = regions.REGIONS[state]
    src = newest_build(s3, B, state)
    if not src: sys.exit(f'{state}: no finished build to split')
    month = src.rstrip('/').rsplit('/', 1)[1]
    dst = {r: f'site/every-st/{r}/{month}/' for r in R}
    src_mod = s3.head_object(Bucket=B, Key=src + 'embed.json')['LastModified'].isoformat()
    log('splitting', src, 'into', ', '.join(R))
    E = json.loads(s3.get_object(Bucket=B, Key=src + 'embed.json')['Body'].read())
    npis = json.loads(s3.get_object(Bucket=B, Key=src + 'npis.json')['Body'].read())
    if len(npis) != len(E['fac']): sys.exit(f'STOP: npis.json has {len(npis)} providers, embed.json {len(E["fac"])}')
    s3.download_file(B, city_page.npis_key(state), '/tmp/split_npis.parquet')
    zip_of = dict(duckdb.connect().execute("select npi, zip5 from read_parquet('/tmp/split_npis.parquet')").fetchall())

    # each provider's region: practice ZIP's county; else by city name when that city is in one region only
    reg = [regions.region_of_zip(state, zip_of.get(n)) for n in npis]
    by_city = collections.defaultdict(set)
    for i, r in enumerate(reg):
        if r: by_city[E['fac'][i][1]].add(r)
    by_city_n = 0
    for i, r in enumerate(reg):
        if not r and len(by_city.get(E['fac'][i][1], ())) == 1: reg[i] = next(iter(by_city[E['fac'][i][1]])); by_city_n += 1
    left_off = sum(1 for r in reg if not r)
    newi, pos = {}, {}
    for r in R:
        pos[r] = [i for i, x in enumerate(reg) if x == r]
        m = [-1] * len(npis)
        for j, i in enumerate(pos[r]): m[i] = j
        newi[r] = m
    log('providers:', ', '.join(f'{r} {len(pos[r]):,}' for r in R), f'| placed by city {by_city_n:,} | left off (no usable ZIP or city) {left_off:,}')

    # per-code price files, the biggest first and fewer at a time (one huge code can need several GB once read)
    sizes = {}
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=src + 't/'):
        for o in pg.get('Contents', []): sizes[o['Key'].rsplit('/', 1)[1][:-4]] = o['Size']
    missing = [c for c in E['codes'] if c not in sizes]
    if missing: log('codes in embed.json without a price file (left off):', len(missing), missing[:10])
    todo = sorted((c for c in E['codes'] if c in sizes), key=lambda c: -sizes[c])
    TEST = os.environ.get('SPLIT_TEST')   # test: the 89 featured codes only, and no split.json (hosp_area.py won't use it)
    if TEST:
        todo = [c for c in todo if c in city_page.FEATURED]
        log('TEST split:', len(todo), 'featured codes,', f'{sum(sizes[c] for c in todo) / 1e9:.1f} GB')
    res, done, t0 = {}, 0, time.time()
    for lo, hi, procs in ((150e6, 1e12, 1), (40e6, 150e6, 2), (8e6, 40e6, 4), (0, 8e6, 8)):
        batch = [c for c in todo if lo <= sizes[c] < hi]
        if not batch: continue
        with Pool(procs, initializer=_init, initargs=(newi, src, dst), maxtasksperchild=50) as P:
            for code, rr in P.imap_unordered(one, batch):
                res[code] = rr; done += 1
                if done % 200 == 0 or sizes[code] >= 40e6:
                    log(f'{done:,} of {len(todo):,} price files ({code}, {sizes[code] / 1e6:.0f} MB) {round(time.time() - t0)} s')
    log('price files done', round(time.time() - t0), 's')

    nidx = {k: i for i, k in enumerate(E['nets'])}
    summary = {'src': src, 'src_embed_modified': src_mod, 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'placed_by_city': by_city_n, 'left_off': left_off, 'regions': {}}
    for r in R:
        codes = {c: dict(E['codes'][c], n=res[c][r][0]) for c in E['codes'] if c in res and res[c][r][0] > 0}
        has = {c: set(res[c][r][1]) for c in codes}
        out = {k: v for k, v in E.items() if k not in ('codes', 'fac', 'prac', 'scope', 'coming')}
        out['codes'] = codes
        out['fac'] = [E['fac'][i] for i in pos[r]]
        if 'scope' in E:
            out['scope'] = {k: [c for c in lst if c in codes and nidx.get(k) in has[c]] for k, lst in E['scope'].items()}
        if 'prac' in E:
            m = newi[r]; pr = {}
            for pid, v in E['prac'].items():
                d = [m[x] for x in v[3] if m[x] >= 0]
                if d: pr[pid] = [v[0], v[1], v[2], d]
            out['prac'] = pr
        s3.put_object(Bucket=B, Key=dst[r] + 'npis.json', Body=json.dumps([npis[i] for i in pos[r]], separators=(',', ':')).encode())
        try: s3.copy_object(Bucket=B, Key=dst[r] + 'build_env.json', CopySource={'Bucket': B, 'Key': src + 'build_env.json'})
        except Exception: pass
        s3.put_object(Bucket=B, Key=dst[r] + 'embed.json', Body=json.dumps(out, separators=(',', ':')).encode())
        lines = sum(c['n'] for c in codes.values())
        summary['regions'][r] = {'providers': len(pos[r]), 'codes': len(codes), 'rate_lines': lines, 'practices': len(out.get('prac', {}))}
        log(f"{r}: {len(pos[r]):,} providers, {len(codes):,} codes, {lines:,} rate lines, {len(out.get('prac', {})):,} practices, "
            f"embed {len(json.dumps(out, separators=(',', ':'))) / 1e6:.1f} MB")
    if TEST: log('TEST split done (no split.json):', json.dumps(summary['regions'])); return
    for r in R:   # written last: a region counts as split only when all of its files are there
        s3.put_object(Bucket=B, Key=dst[r] + 'split.json', Body=json.dumps(summary, indent=1).encode())
    log('split done:', json.dumps(summary['regions']))


if __name__ == '__main__':
    main(sys.argv[1])
