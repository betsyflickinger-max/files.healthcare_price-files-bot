"""Data accuracy audit, Layer 2: independent round-trip check (Nov 6, 2026, Betsy OK'd).

Independence rule: this file imports NOTHING from site/ or bot/. It reads the published pages its own way and goes back to the
sources its own way, so a bug in the bot's shared code can't make both sides agree.

1. Downloads the deployed site bundle and, for every area, picks random featured procedures and random price lines exactly as the
   pages carry them (insurer lines from the per-code t/ files, hospital-file lines from h/).
2. Insurer lines: finds the insurer table made from the file the page links to (same file name, anywhere under data/ or
   history/insurers/) and looks for the same code, NPI, billing class and amount. Also checks the file's own insurer name
   (reporting_entity_name) against the insurer shown, and whether the shown amount is the lowest plain rate in the source.
   (The insurers' original files are tens of GB each and aren't kept; the tables keep every field of every row.)
3. Hospital lines: opens the archived original hospital file (raw/hospitals/, the exact version by its fingerprint) and reads the
   line / JSON item the page cites, checking that it names the code and carries the amount.

Output: reports/audit/<date>/roundtrip.md and roundtrip.csv (every sampled line with its verdict).
Usage: python audit/roundtrip.py [--insurer 1000] [--hospital 400] [--seed 20261106] [--areas dfw,georgia]
"""
import argparse, base64, collections, csv, datetime as dt, gzip, io, json, os, random, re, tarfile, tempfile, zipfile
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import boto3

TODAY = dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
ENDPOINT = os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
s3 = boto3.client('s3', endpoint_url=ENDPOINT, aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                  region_name=os.environ.get('STORAGE_REGION') or 'auto')
B = E['R2_BUCKET']
NUM = re.compile(r'-?\d[\d,]*\.?\d*')


def ls(prefix):
    out, tok = [], None
    while True:
        kw = dict(Bucket=B, Prefix=prefix)
        if tok:
            kw['ContinuationToken'] = tok
        r = s3.list_objects_v2(**kw)
        out += [(o['Key'], o['Size']) for o in r.get('Contents', [])]
        if not r.get('IsTruncated'):
            return out
        tok = r['NextContinuationToken']


def per_code(body):
    raw = base64.b64decode(body.strip())
    try:
        return json.loads(gzip.decompress(raw))
    except OSError:
        return json.loads(raw)


def get_json(key):
    try:
        return per_code(s3.get_object(Bucket=B, Key=key)['Body'].read())
    except s3.exceptions.NoSuchKey:
        return None


def read_bundle(site_dir=None):
    """Only what this check needs from the deployed bundle: the area list, each Price Finder page, and each area's file prefix."""
    want = re.compile(r'^(site/cities\.json|site/.*price-finder/index\.html|functions/.*/price-finder/pf/[th]/\[code\]\.js)$')
    files = {}
    if site_dir:   # an already-extracted bundle (test runs)
        for root, _, fs in os.walk(site_dir):
            for fn in fs:
                n = os.path.relpath(os.path.join(root, fn), site_dir)
                if want.match(n):
                    files[n] = open(os.path.join(root, fn), encoding='utf-8', errors='replace').read()
        return files
    body = s3.get_object(Bucket=B, Key='site/deploy/current.tgz')['Body']
    with tarfile.open(fileobj=body, mode='r|gz') as t:
        for m in t:
            n = m.name.lstrip('./')
            if m.isfile() and want.match(n):
                files[n] = t.extractfile(m).read().decode('utf-8', 'replace')
    return files


def page_D(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def prefixes(files, slug):
    if slug == 'dfw':
        cur = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
        return f'site/every/{cur}/t/', f'site/every/{cur}/h/', f'site/every/{cur}/npis.json'
    out = []
    for k in ('t', 'h'):
        src = files.get(f'functions/{slug}/price-finder/pf/{k}/[code].js', '')
        m = re.search(r'PREFIX = "([^"]+)"', src)
        if not m:
            return None
        p = m.group(1)
        out.append(p + 't/' if k == 't' and "PREFIX + 't/'" in src else p)
    t = out[0]
    return out[0], out[1], (t[:-2] + 'npis.json' if t.endswith('t/') else None)


def money_in(text, v):
    for x in NUM.findall(text or ''):
        try:
            if abs(float(x.replace(',', '')) - v) < 0.006:
                return True
        except ValueError:
            pass
    return False


# ------------------------------------------------------------------ sampling
def sample(files, areas, n_ins, n_hosp, rnd, featured):
    per_area_i = max(1, -(-n_ins // len(areas)))
    per_area_h = max(1, -(-n_hosp // len(areas)))
    ins, hosp = [], []
    for a in areas:
        html = files.get(f"site/{a['path'].strip('/')}/index.html")
        px = prefixes(files, a['slug'])
        if not html or not px:
            print('  skip', a['slug'], '(no page or prefix)', flush=True)
            continue
        D = page_D(html)
        npis = []
        if px[2]:
            try:
                npis = json.loads(s3.get_object(Bucket=B, Key=px[2])['Body'].read())
            except Exception:
                npis = []
        codes = [c for c in featured if c in D['codes']]
        rnd.shuffle(codes)
        nets, urls, dates = D['nets'], D['urls'], D['dates']
        H = D.get('hosp') or {}
        got_i = got_h = 0
        for c in codes[:12]:
            if got_i < per_area_i:
                t = get_json(px[0] + c + '.txt') or {}
                lines = [(fi, r) for fi, rs in (t.get('f') or {}).items() for r in rs if r[3] > 0]
                for fi, r in rnd.sample(lines, min(len(lines), max(1, per_area_i // 3))):
                    i = int(fi)
                    ins.append(dict(area=a['slug'], code=c, provider=D['fac'][i][0], npi=npis[i] if i < len(npis) else '',
                                    net=nets[r[0]], fee='facility' if r[1] == 0 else 'doctor', pct=bool(r[2]), value=r[3],
                                    file_date=dates[r[5]] if r[5] < len(dates) else '', url=urls[r[6]] if r[6] < len(urls) else ''))
                    got_i += 1
            if got_h < per_area_h and H.get('src'):
                h = get_json(px[1] + c + '.txt') or {}
                lines = [('r', r) for r in h.get('r') or [] if r[0] < len(H['src'])] + \
                        [('c', r) for r in h.get('c') or [] if r[0] < len(H['src'])]
                for kind, r in rnd.sample(lines, min(len(lines), max(1, per_area_h // 3))):
                    x = H['src'][r[0]]
                    if kind == 'r':
                        d = dict(value=r[6], row=r[7] if len(r) > 7 else None, payer=H['ins'][r[1]] if r[1] < len(H.get('ins') or []) else '',
                                 pct=bool(r[5]), what='insurer rate in hospital file')
                    else:
                        d = dict(value=r[2], row=r[4] if len(r) > 4 else None, payer='', pct=False, what='cash price')
                    hosp.append(dict(area=a['slug'], code=c, hospital=x[0], file_date=x[3], url=x[4], sha16=x[5], unit=x[6] if len(x) > 6 else 'row', **d))
                    got_h += 1
        print(f"  {a['slug']}: {got_i} insurer lines, {got_h} hospital-file lines sampled", flush=True)
    return ins, hosp


# ------------------------------------------------------------------ insurer side
def table_index():
    idx = collections.defaultdict(list)
    for pre in ('data/', 'history/insurers/'):
        for k, size in ls(pre):
            if '/rates/' in k and k.endswith('.parquet'):
                idx[os.path.basename(k)[:-len('.parquet')]].append((k, size))
    return idx


def stem(url):
    b = os.path.basename((url or '').split('?')[0])
    for ext in ('.json.gz', '.json', '.gz', '.zip'):
        if b.endswith(ext):
            return b[:-len(ext)]
    return b


def check_insurer(ins, max_gb):
    import duckdb
    con = duckdb.connect()
    host = ENDPOINT.replace('https://', '').rstrip('/')
    con.execute(f"""INSTALL httpfs; LOAD httpfs; CREATE SECRET s (TYPE S3, KEY_ID '{E['R2_ACCESS_KEY_ID']}', SECRET '{E['R2_SECRET_ACCESS_KEY']}',
                    ENDPOINT '{host}', URL_STYLE 'path', REGION '{os.environ.get('STORAGE_REGION') or 'auto'}')""")
    con.execute("SET threads=8; SET enable_progress_bar=false")
    idx = table_index()
    by_table = collections.defaultdict(list)
    for x in ins:
        by_table[stem(x['url'])].append(x)
    for st, xs in by_table.items():
        keys = idx.get(st, [])
        if not keys:
            for x in xs:
                x.update(verdict='source table not found', detail=f'no table named {st}')
            continue
        gb = sum(s for _, s in keys) / 1e9
        if gb > max_gb:
            for x in xs:
                x.update(verdict='not checked (table too big for this run)', detail=f'{gb:.0f} GB')
            continue
        codes = sorted({x['code'] for x in xs})
        npis = sorted({x['npi'] for x in xs if x['npi']})
        if not npis:
            for x in xs:
                x.update(verdict='not checked (no NPI on page)', detail='')
            continue
        lst = '[' + ','.join(f"'s3://{B}/{k}'" for k, _ in keys) + ']'
        q = f"""select billing_code, npi, billing_class, negotiated_type, negotiated_rate, billing_code_modifier, negotiation_arrangement,
                       expiration_date, reporting_entity_name, last_updated_on
                from read_parquet({lst}, union_by_name=true)
                where billing_code in ({','.join(repr(c) for c in codes)}) and npi in ({','.join(repr(n) for n in npis)})"""
        try:
            rows = con.execute(q).fetchall()
        except Exception as e:
            for x in xs:
                x.update(verdict='not checked (read error)', detail=f'{type(e).__name__}: {str(e)[:150]}')
            continue
        print(f"  table {st}: {len(xs)} sampled lines, {len(rows)} source rows ({gb:.1f} GB)", flush=True)
        src = collections.defaultdict(list)
        for r in rows:
            src[(r[0], r[1])].append(r)
        for x in xs:
            rs = src.get((x['code'], x['npi']), [])
            inst = x['fee'] == 'facility'
            mine = [r for r in rs if (str(r[2] or '').lower().startswith('inst')) == inst]
            def val(r):
                try:
                    return float(r[4])
                except (TypeError, ValueError):
                    return None
            exact = [r for r in mine if val(r) is not None and abs(val(r) - x['value']) < 0.006
                     and (str(r[3] or '').lower().startswith('percent')) == x['pct']]
            ent = {str(r[8] or '') for r in rs}
            x['source_entity'] = '; '.join(sorted(ent))[:120]
            x['source_date'] = '; '.join(sorted({str(r[9] or '') for r in rs}))[:60]
            if not rs:
                x.update(verdict='not found in source', detail='no row for this code and NPI in the file')
            elif not exact:
                near = sorted((abs(val(r) - x['value']), val(r)) for r in mine if val(r) is not None)
                x.update(verdict='amount not found in source', detail=f"nearest source amounts {[v for _, v in near[:4]]}")
            else:
                plain = [val(r) for r in mine if val(r) and val(r) > 0 and not (r[5] or '').strip()
                         and not str(r[3] or '').lower().startswith('percent')
                         and str(r[6] or 'ffs').lower() in ('ffs', '')
                         and not (str(r[7] or '9999') < TODAY)]
                lowest_ok = not plain or x['pct'] or min(plain) >= x['value'] - 0.006
                x.update(verdict='match' if lowest_ok else 'match, but not the lowest plain rate',
                         detail='' if lowest_ok else f'lowest plain source rate {min(plain)}')
                e0 = exact[0]
                notes = []
                if (e0[5] or '').strip():
                    notes.append(f'modifier {e0[5]}')
                if str(e0[6] or 'ffs').lower() not in ('ffs', ''):
                    notes.append(f'arrangement {e0[6]}')
                if str(e0[7] or '9999') < TODAY:
                    notes.append(f'expired {e0[7]}')
                if str(e0[3] or '').lower() not in ('negotiated', 'fee schedule', 'percentage', 'derived', 'ffs', ''):
                    notes.append(f'rate type {e0[3]}')
                if notes:
                    x['detail'] = (x['detail'] + '; ' if x['detail'] else '') + ', '.join(notes)
            label = x['net'].split('|')[0].lower()
            if rs and not entity_ok(label, ent):
                x['entity_flag'] = f"page says {x['net'].split('|')[0]}, file says {x['source_entity']}"


FAMILY = [r'blue|bcbs|anthem|wellpoint|elevance|highmark|regence|premera|carefirst|excellus|independence|horizon|florida blue',
          r'united|uhc|optum|umr|golden rule|all savers', r'centene|ambetter|superior|wellcare|celtic|health net|peach state|meridian|buckeye|sunshine',
          r'aetna|cvs|coventry', r'cigna|evernorth', r'humana', r'molina', r'oscar', r'curative', r'baylor|bsw|scott', r'imperial', r'devoted',
          r'parkland', r'cook children', r'community health choice', r'christus', r'moda', r'kaiser', r'priority', r'quartz', r'medica\b',
          r'health ?partners', r'ucare', r'geisinger', r'upmc', r'caresource', r'select health', r'avera', r'sanford', r'wellmark',
          r'mvp', r'emblem', r'healthfirst', r'fidelis', r'oxford', r'harvard pilgrim', r'tufts', r'point32', r'dean', r'ascension']


def entity_ok(label, ents):
    ents_l = ' '.join(e.lower().replace('-', ' ').replace('_', ' ') for e in ents)
    lab = label.replace('-', ' ')
    for f in FAMILY:
        if re.search(f, lab):
            return bool(re.search(f, ents_l))
    toks = [w for w in re.findall(r'[a-z]{4,}', lab) if w not in ('health', 'plan', 'plans', 'texas', 'network', 'insurance', 'company')]
    return not toks or any(w in ents_l for w in toks)


# ------------------------------------------------------------------ hospital side
def raw_index():
    idx = {}
    for k, size in ls('raw/hospitals/'):
        b = os.path.basename(k)
        idx.setdefault(b[:12], (k, size))
    return idx


def stream_lines(key):
    import zstandard
    if '.zip' in key.lower():   # a zipped original: unpack the zip to a temp file, read its first data file
        tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        body = s3.get_object(Bucket=B, Key=key)['Body']
        src = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(body) if key.endswith('.zst') else body
        while True:
            b = src.read(1 << 22)
            if not b:
                break
            tmp.write(b)
        tmp.close()
        z = zipfile.ZipFile(tmp.name)
        name = next(n for n in z.namelist() if not n.endswith('/') and not n.startswith('__MACOSX'))
        return io.TextIOWrapper(z.open(name), encoding='utf-8-sig', errors='replace', newline='')
    body = s3.get_object(Bucket=B, Key=key)['Body']
    rd = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(body) if key.endswith('.zst') else body
    return io.TextIOWrapper(io.BufferedReader(rd, 1 << 20), encoding='utf-8-sig', errors='replace', newline='')


def check_hospital_file(key, xs):
    """xs: sampled lines from this one file. CSV: physical line number; JSON: item number in standard_charge_information."""
    want = {}
    for x in xs:
        if x.get('row') in (None, '', 0):
            x.update(verdict='not checked (no row number on page)', detail='')
        else:
            want.setdefault(int(x['row']), []).append(x)
    if not want:
        return
    last = max(want)
    try:
        f = stream_lines(key)
        head = f.read(4096)
        if head.lstrip()[:1] in ('{', '['):
            import ijson
            f = stream_lines(key)
            for n, item in enumerate(ijson.items(f.buffer if hasattr(f, 'buffer') else f, 'standard_charge_information.item', use_float=True), 1):
                if n in want:
                    text = json.dumps(item)
                    for x in want[n]:
                        judge(x, text)
                if n >= last:
                    break
        else:
            f = stream_lines(key)
            for n, line in enumerate(f, 1):
                if n in want:
                    for x in want[n]:
                        judge(x, line)
                if n >= last:
                    break
    except Exception as e:
        for x in xs:
            if 'verdict' not in x:
                x.update(verdict='not checked (read error)', detail=f'{type(e).__name__}: {str(e)[:120]}')
    for x in xs:
        if 'verdict' not in x:
            x.update(verdict='not found in source', detail='file ended before the cited line')


def judge(x, text):
    has_code = bool(re.search(r'(?<![0-9A-Za-z])0*' + re.escape(x['code'].lstrip('0') or '0') + r'(?![0-9A-Za-z])', text))
    has_amt = money_in(text, float(x['value']))
    x['verdict'] = 'match' if has_code and has_amt else 'amount not on cited line' if has_code else 'code not on cited line'
    x['detail'] = '' if x['verdict'] == 'match' else text[:200].replace('\n', ' ')


def check_hospital(hosp, max_gb):
    idx = raw_index()
    by = collections.defaultdict(list)
    for x in hosp:
        k = idx.get((x['sha16'] or '')[:12])
        if not k:
            x.update(verdict='source file not found', detail=f"no archived original with fingerprint {x['sha16']}")
        elif k[1] / 1e9 > max_gb:
            x.update(verdict='not checked (file too big for this run)', detail=f'{k[1] / 1e9:.1f} GB compressed')
        else:
            by[k[0]].append(x)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda kv: check_hospital_file(*kv), by.items()))


# ------------------------------------------------------------------ report
def report(ins, hosp, args):
    od = os.path.join(REPO, 'reports', 'audit', TODAY)
    os.makedirs(od, exist_ok=True)
    cols = ['side', 'verdict', 'area', 'code', 'provider', 'npi', 'net', 'fee', 'pct', 'value', 'file_date', 'url', 'detail',
            'source_entity', 'source_date', 'entity_flag', 'hospital', 'payer', 'what', 'row', 'unit', 'sha16']
    with open(os.path.join(od, 'roundtrip.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, cols, extrasaction='ignore')
        w.writeheader()
        for x in ins:
            w.writerow(dict(x, side='insurer'))
        for x in hosp:
            w.writerow(dict(x, side='hospital'))
    L = [f'# Data accuracy audit, Layer 2 (independent round trip): {TODAY}', '',
         'audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.', '']
    for side, xs in (('Insurer lines', ins), ('Hospital-file lines', hosp)):
        c = collections.Counter(x.get('verdict', 'not checked') for x in xs)
        checked = sum(v for k, v in c.items() if not k.startswith('not checked') and k != 'source table not found' and k != 'source file not found')
        ok = sum(v for k, v in c.items() if k.startswith('match'))
        L += [f'## {side}: {len(xs)} sampled, {checked} traced, {ok} matched ({(100 * ok / checked if checked else 0):.1f}%)', '',
              '| Verdict | Lines |', '|---|---|'] + [f'| {k} | {v} |' for k, v in c.most_common()] + ['']
    ef = [x for x in ins if x.get('entity_flag')]
    L += [f"Insurer name check: {len(ef)} sampled lines where the file's own insurer name doesn't match the insurer shown.", '']
    notes = collections.Counter()
    for x in ins:
        for n in ('modifier', 'arrangement', 'expired', 'rate type'):
            if n in (x.get('detail') or ''):
                notes[n] += 1
    if notes:
        L += ['Matched lines whose source row carries a caveat: ' + ', '.join(f'{k} {v}' for k, v in notes.items()), '']
    L += ['Every sampled line with its verdict: roundtrip.csv.', f'Seed {args.seed}; rerun with the same seed to get the same sample.']
    open(os.path.join(od, 'roundtrip.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--insurer', type=int, default=1000)
    ap.add_argument('--hospital', type=int, default=400)
    ap.add_argument('--seed', type=int, default=int(TODAY.replace('-', '')))
    ap.add_argument('--areas')
    ap.add_argument('--site', help='an extracted bundle (test runs)')
    ap.add_argument('--max-table-gb', type=float, default=40)
    ap.add_argument('--max-file-gb', type=float, default=4)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    print('reading the deployed site...', flush=True)
    files = read_bundle(args.site)
    areas = json.loads(files['site/cities.json'])
    if args.areas:
        areas = [a for a in areas if a['slug'] in args.areas.split(',')]
    featured = [r['code'] for r in csv.DictReader(open(os.path.join(REPO, 'site', 'codes89.csv')))]   # a list of codes, not bot code
    ins, hosp = sample(files, areas, args.insurer, args.hospital, rnd, featured)
    del files
    print(len(ins), 'insurer lines and', len(hosp), 'hospital-file lines sampled', flush=True)
    check_hospital(hosp, args.max_file_gb)
    check_insurer(ins, args.max_table_gb)
    report(ins, hosp, args)


if __name__ == '__main__':
    main()
