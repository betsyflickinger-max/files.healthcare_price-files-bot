"""Data accuracy audit, Layer 1: rule checks on what the site actually shows (Nov 6, 2026, Betsy OK'd).

Spec: Healthcare folder DATA-ACCURACY-AUDIT.md (project doc claude/data-accuracy-audit-spec-nov6.md). Read-only on the site.

What it reads: the deployed bundle (storage site/deploy/current.tgz), every area in site/cities.json, the area's page data and
its per-code insurer (t/) and hospital (h/) files, for the 89 featured procedures by default (--all-codes for every code).
What it checks (rule ids match the spec; Critical / Major / Review):
  A1  provider's practice ZIP is in another state than the page             Critical (procedure pages leave them out; Price Finder lists them)
  A3  hospital file's own address is in another state / the file belongs to another hospital (reports/file_identity.csv)   Critical
  A4  a quarantined file (site/source_quarantine.csv) still has rows in the page data                                    Major
  A9  page's state could not be told from its slug (area_state() fell back to Texas)                                    Critical
  B1  an insurer's rows link to a file host that is another insurer's main host                                         Critical
  B2  a network shows a code its own file scope doesn't list                                                            Major
  C1  NPI fails the check digit                                                                                         Critical
  C4  a facility fee filed under an individual clinician                                                                Major
  D1  $0 / negative / filler-looking dollar amount not flagged                                                          Critical
  D2  same dollar amount on 5+ featured procedures for one place and network, not labeled flat (match pilot: Aetna $3,682) Major
  D3  hospital stay (DRG) dollar rate under $100 (a weight, not a price; code review A1)                                Critical
  D6  percent-of-charges above 100%                                                                                     Major
  E1  file date missing or unreadable (code review A12: old-data flag fails open)                                       Major
  E1s file date older than the stale line (183 days): counted, the page flags these                                      Info
  E2  source link missing / out of range                                                                                Critical
  E4  source link dead (404/410/no such host), checked once per distinct link                                           Major
  F1  price moved more than 3x since the last audit (same place, network, code, fee)                                    Review
  F2  an insurer's lines on a page fell by more than 25% since the last audit                                           Review
  F3  a page lost more than 10% of its providers since the last audit                                                   Review

History (Betsy, Nov 6: keep everything for change over time): every run also writes what each page showed, one Parquet file per
area, to storage history/published/<YYYY-MM-DD>/<area>/{insurer,hospital}.parquet. Kept permanently; never deleted by any
cleanup (orchestrate.cleanup only touches site/every/ and work/every/). F1-F3 compare against the newest earlier snapshot.

Output: reports/audit/<date>/summary.md, counts.csv, examples.csv (up to 25 per rule and area), links.csv; the full list of
failures to storage audit/<date>/failures.csv.gz.

Usage: python site/audit_rules.py [--site DIR] [--areas dfw,georgia] [--all-codes] [--no-links] [--no-upload]
"""
import argparse, collections, csv, datetime as dt, gzip, io, json, os, re, sys, tarfile, time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import procedure_pages as pp   # noqa: E402  Layer 1 may share the bot's readers; Layer 2 (audit/) must not

from zoneinfo import ZoneInfo
TODAY = dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()   # Betsy works in Central time
LEVEL = {'A1': 'Major', 'A3': 'Critical', 'A3r': 'Review', 'A3b': 'Major', 'A4': 'Major', 'A9': 'Critical', 'B1': 'Critical', 'B2': 'Major', 'C1': 'Critical',
         'C4': 'Info', 'D1': 'Info', 'D2': 'Major', 'D3': 'Critical', 'D3i': 'Info', 'D6': 'Major', 'E1': 'Major', 'E1s': 'Info',
         'E2': 'Critical', 'E4': 'Major', 'F1': 'Review', 'F2': 'Review', 'F3': 'Review'}
WHAT = {
    'A1': "provider's practice ZIP is in another state than the page (procedure pages leave them out; Price Finder lists them)",
    'A3': "hospital price file's own address is in another state than the page",
    'A3r': "hospital price file was filed under another hospital (same state; check the name shown)",
    'A3b': "page names a hospital differently than the hospital whose file it is",
    'A4': "quarantined hospital file still has rows in the page data",
    'A9': "page's state guessed (slug not in the state list)",
    'B1': "insurer's rows link to another insurer's file host",
    'B2': "network shows a code its own file doesn't list",
    'C1': "NPI fails the check digit",
    'C4': "facility fee filed under an individual clinician (in the data; the pages' own filters keep it off the price lists)",
    'D1': "$0, negative or filler-looking amount not flagged in the data (the pages' own filters keep these out of prices)",
    'D2': "same amount on 5+ procedures for one place and network, not labeled flat",
    'D3': "hospital-file stay rate under $100 (a weight, not a price; reaches the pages)",
    'D3i': "insurer-file stay rate under $100 (the pages' low-rate filter drops these)",
    'D6': "percent of charges above 100%",
    'E1': "file date missing or unreadable",
    'E1s': "file date older than 183 days (page flags it)",
    'E2': "source link missing",
    'E4': "source link dead",
    'F1': "price moved more than 3x since the last audit",
    'F2': "insurer's lines fell more than 25% since the last audit",
    'F3': "page lost more than 10% of its providers since the last audit",
}
EX_CAP = 25
ALL_CAP = 50000
FIELDS = ['rule', 'level', 'area', 'code', 'provider', 'npi', 'insurer', 'plan', 'value', 'file_date', 'url', 'detail']


def npi_ok(n):
    """Luhn check with the 80840 prefix (CMS NPI standard)."""
    n = str(n or '')
    if not re.fullmatch(r'\d{10}', n):
        return False
    digits = '80840' + n[:9]
    tot = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        tot += d
    return (10 - tot % 10) % 10 == int(n[9])


def host(u):
    h = (urlparse(u or '').hostname or '').lower()
    parts = h.split('.')
    # storage hosts carry the bucket/account in the first label; keep it (it's what tells two insurers apart)
    return h if any(s in h for s in ('amazonaws.com', 'blob.core.windows.net', 'cloudfront.net', 'googleapis.com')) else '.'.join(parts[-2:])


def load_identity():
    out = {}
    try:
        for r in csv.DictReader(open(os.path.join(REPO, 'reports', 'file_identity.csv'), encoding='utf-8')):
            if r.get('mrf_url'):
                out[r['mrf_url'].strip()] = r
    except OSError:
        pass
    return out


def load_file_ccn():
    """hand-checked file -> hospital (site/hospital_file_ccn.csv), with Medicare's name for that hospital"""
    names = {}
    try:
        for r in csv.DictReader(open(os.path.join(REPO, 'reference', 'geo', 'medicare_hospitals.csv'), encoding='utf-8')):
            names[r['ccn']] = r['name']
    except OSError:
        pass
    out = []
    try:
        for r in csv.DictReader(open(os.path.join(HERE, 'hospital_file_ccn.csv'), encoding='utf-8')):
            out.append((r['url_contains'].lower(), r['ccn'], names.get(r['ccn'], '')))
    except OSError:
        pass
    return out


COMMON = set('the of and at for medical center hospital hospitals health healthcare system llc llp inc regional general memorial '
             'surgical surgery texas tx campus'.split())


def distinct(name):
    return {w for w in re.findall(r'[a-z]{3,}', (name or '').lower()) if w not in COMMON}


def file_state(r):
    m = re.search(r'file gives its address as ([A-Z]{2}) \d{5}', r.get('reason') or '')
    return m.group(1) if m else None


TX_SLUGS = set()
try:
    for r in csv.DictReader(open(os.path.join(REPO, 'reference', 'geo', 'tx_zip_metro.csv'), encoding='utf-8')):
        for k in ('slug', 'metro_slug', 'page'):
            if r.get(k):
                TX_SLUGS.add(r[k])
except OSError:
    pass
TX_SLUGS |= {'dfw', 'houston', 'austin', 'san-antonio', 'el-paso', 'small-towns', 'texas'}


class Out:
    def __init__(self, area):
        self.area, self.n, self.ex, self.all = area, collections.Counter(), [], []
        self.checked = collections.Counter()

    def add(self, rule, **kw):
        self.n[rule] += 1
        row = dict(rule=rule, level=LEVEL[rule], area=self.area, **kw)
        if self.n[rule] <= ALL_CAP:          # the counts are always complete; the stored list stops at ALL_CAP per rule and area
            self.all.append(row)
        if sum(1 for e in self.ex if e['rule'] == rule) < EX_CAP:
            self.ex.append(row)


def audit_area(args):
    """One area: rules A-E over its featured (or all) codes, and the snapshot rows. Runs in its own process."""
    site_dir, a, all_codes, snap_dir, only = args
    import pyarrow as pa, pyarrow.parquet as pq
    store = pp.Store(site_dir)
    slug = a['slug']
    o = Out(slug)
    page = os.path.join(site_dir, 'site', a['path'].strip('/'), 'index.html')
    if not os.path.isfile(page):
        o.add('E2', detail='no Price Finder page in the bundle for ' + a['path'])
        return o.__dict__
    D, _, fp = pp.page_data(page)
    st = pp.area_state(a)
    if slug not in pp.STATES and slug not in pp.CA_REGIONS and slug not in TX_SLUGS:
        o.add('A9', detail=f'slug {slug!r} not in state lists; read as {st}')
    featured = [r['code'] for r in csv.DictReader(open(os.path.join(HERE, 'codes89.csv')))]
    codes = [c for c in (D['codes'] if all_codes else featured) if c in D['codes'] and (not only or c in only)]
    nets = [n.split('|', 1) for n in D['nets']]
    fac, dates, urls, labs = D['fac'], D['dates'], D['urls'], D.get('labs') or []
    scope = {k: set(v) for k, v in (D.get('scope') or {}).items()}
    pst = store.provider_states(a, D) or {}
    npis = []
    pre = store.prefix(a, 't')
    if pre and pre.endswith('t/'):
        try:
            npis = json.loads(store.s3.get_object(Bucket=store.B, Key=pre[:-2] + 'npis.json')['Body'].read())
        except Exception:
            npis = []
    if len(npis) != len(fac):
        npis = [''] * len(fac)
    # C1 once per provider
    for i, n in enumerate(npis):
        if n and not npi_ok(n):
            o.add('C1', provider=fac[i][0], npi=n)
    away = {i for i, s in pst.items() if s and s != st}
    date_bad = {i for i, d in enumerate(dates) if not pp.parse_date(d)}
    date_old = {i for i, d in enumerate(dates) if pp.is_stale(d)}
    # B1: each insurer's main file host
    hosts_by_ins = collections.defaultdict(collections.Counter)
    # quarantine + identity (hospital side)
    ident = load_identity()
    qrx = pp.WRONG_AREA
    H = D.get('hosp') or {}
    hsrc = H.get('src') or []
    hins = H.get('ins') or []
    bad_src = {}
    fccn = load_file_ccn()
    for s, x in enumerate(hsrc):
        url = (x[4] if len(x) > 4 else '') or ''
        if qrx.search(url):
            bad_src[s] = 'A4'
        for frag, ccn, mname in fccn:
            if frag and frag in url.lower() and mname and distinct(mname) and not (distinct(mname) & distinct(x[0])):
                o.add('A3b', provider=x[0], url=url, detail=f'the file is {mname.title()} (CCN {ccn}, site/hospital_file_ccn.csv) but the page names it {x[0]}')
        r = ident.get(url.strip())
        if r:
            fs = file_state(r)
            if fs and fs != st:
                o.add('A3', provider=x[0], url=url, detail=f"{r['verdict']}: {r['reason'][:240]}")
            elif r['verdict'] == 'wrong':
                o.add('A3r', provider=x[0], url=url, detail=f"{r['reason'][:240]}")
        d = x[3] if len(x) > 3 else ''
        if not pp.parse_date(d):
            o.add('E1', provider=x[0], url=url, file_date=d, detail='hospital file date')
        elif pp.is_stale(d):
            o.n['E1s'] += 1
        if not url:
            o.add('E2', provider=x[0], detail='hospital file with no link')

    w_ins = w_h = None
    os.makedirs(os.path.join(snap_dir, slug), exist_ok=True)
    ins_schema = pa.schema([('code', pa.string()), ('npi', pa.string()), ('provider', pa.string()), ('city', pa.string()),
                            ('kind', pa.string()), ('insurer', pa.string()), ('plan', pa.string()), ('fee', pa.string()),
                            ('pct', pa.bool_()), ('value', pa.float64()), ('flags', pa.int16()), ('label', pa.string()),
                            ('file_date', pa.string()), ('url', pa.string()), ('other_values', pa.string())])
    h_schema = pa.schema([('code', pa.string()), ('hospital', pa.string()), ('city', pa.string()), ('insurer', pa.string()),
                          ('plan', pa.string()), ('product', pa.string()), ('doctor_line', pa.bool_()), ('pct', pa.bool_()),
                          ('value', pa.float64()), ('cash', pa.bool_()), ('file_date', pa.string()), ('url', pa.string()),
                          ('source_row', pa.string())])
    flat_seen = collections.defaultdict(set)    # (fi, net, v) -> featured codes, facility dollar rows not labeled flat
    for c in codes:
        C = D['codes'][c]
        drg = 'DRG' in (C.get('type') or '')
        t = store.get(a, 't', c) or {}
        f = t.get('f') or C.get('f') or {}
        cols = {k: [] for k in ins_schema.names}
        med = {}
        for fee in (0, 1):
            vs = sorted(r[3] for rs in f.values() for r in rs if r[1] == fee and not r[2] and r[3] > 0)
            med[fee] = vs[len(vs) // 2] if len(vs) >= 5 else None
        for fi, rs in f.items():
            i = int(fi)
            x = fac[i] if i < len(fac) else ['?', '', '?']
            kd = pp.kind_of(x)
            npi = npis[i] if i < len(npis) else ''
            for r in rs:
                o.checked['insurer lines'] += 1
                ni, fee, pct, v, fl, di, ui = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
                ins, plan = nets[ni] if ni < len(nets) else ('?', '?')
                url = urls[ui] if isinstance(ui, int) and 0 <= ui < len(urls) else ''
                fdate = dates[di] if isinstance(di, int) and 0 <= di < len(dates) else ''
                lab = labs[r[10]] if len(r) > 10 and isinstance(r[10], int) and 0 <= r[10] < len(labs) else ''
                base = dict(code=c, provider=x[0], npi=npi, insurer=ins, plan=plan, value=v, file_date=fdate, url=url)
                if not url:
                    o.add('E2', **base, detail='insurer line with no file link')
                else:
                    hosts_by_ins[ins][host(url)] += 1
                if di in date_bad or not fdate:
                    o.add('E1', **base, detail='insurer file date')
                elif di in date_old:
                    o.n['E1s'] += 1
                if i in away:
                    o.add('A1', **base, detail=f'practice ZIP in {pst.get(i)}, page is {st}')
                if scope and f'{ins}|{plan}' in scope and c not in scope[f'{ins}|{plan}']:
                    o.add('B2', **base, detail='code not in this network\'s file scope')
                if fee == 0 and kd == 'P':
                    o.add('C4', **base, detail='facility fee under an individual')
                if pct:
                    if v > 100:
                        o.add('D6', **base, detail=f'{v}% of charges')
                else:
                    if v < 0 or (v == 0 and not fl & 4):
                        o.add('D1', **base, detail='zero or negative, not flagged')
                    elif v > 0 and med.get(fee) and pp.looks_placeholder(v, med[fee]) and not fl & 8:
                        o.add('D1', **base, detail=f'filler-looking, median {med[fee]}')
                    if drg and fee == 0 and 0 < v < 100:
                        o.add('D3i', **base, detail='hospital stay under $100 (insurer file; pages drop rates under 20% of the median)')
                    if fee == 0 and v > 0 and not fl & 1 and not pp.PART_FAC.search(lab) and not pp.NOT_WHOLE.search(lab):
                        flat_seen[(i, ni, v)].add(c)
                for col, val in (('code', c), ('npi', npi), ('provider', x[0]), ('city', x[1] if len(x) > 1 else ''), ('kind', kd),
                                 ('insurer', ins), ('plan', plan), ('fee', 'doctor' if fee else 'facility'), ('pct', bool(pct)),
                                 ('value', float(v)), ('flags', int(fl)), ('label', lab), ('file_date', fdate), ('url', url),
                                 ('other_values', json.dumps([z[0] for z in (r[8] if len(r) > 8 and isinstance(r[8], list) else [])]))):
                    cols[col].append(val)
        if cols['code']:
            tb = pa.table(cols, schema=ins_schema)
            if w_ins is None:
                w_ins = pq.ParquetWriter(os.path.join(snap_dir, slug, 'insurer.parquet'), ins_schema, compression='zstd')
            w_ins.write_table(tb)
        # hospital files
        h = store.get(a, 'h', c) or {}
        hc = {k: [] for k in h_schema.names}
        plans = h.get('p') or H.get('plans') or []
        for r in h.get('r', []) or []:
            o.checked['hospital lines'] += 1
            s = r[0]
            if s >= len(hsrc):
                continue
            x = hsrc[s]
            ins = hins[r[1]] if r[1] < len(hins) else '?'
            v = r[6]
            base = dict(code=c, provider=x[0], insurer=ins, value=v, file_date=x[3] if len(x) > 3 else '', url=x[4] if len(x) > 4 else '')
            if bad_src.get(s) == 'A4':
                o.add('A4', **base, detail='quarantined file')
            if not r[5]:
                if v < 0:
                    o.add('D1', **base, detail='negative hospital rate')
                if drg and not r[4] and 0 < v < 100:
                    o.add('D3', **base, detail='hospital stay under $100 in the hospital file')
            elif v > 100:
                o.add('D6', **base, detail=f'{v}% of charges (hospital file)')
            for col, val in (('code', c), ('hospital', x[0]), ('city', x[1]), ('insurer', ins),
                             ('plan', plans[r[3]] if r[3] < len(plans) else ''), ('product', pp.PROD[r[2]] if r[2] < len(pp.PROD) else str(r[2])),
                             ('doctor_line', bool(r[4])), ('pct', bool(r[5])), ('value', float(v)), ('cash', False),
                             ('file_date', base['file_date']), ('url', base['url']), ('source_row', str(r[7]) if len(r) > 7 else '')):
                hc[col].append(val)
        for r in h.get('c', []) or []:
            o.checked['cash lines'] += 1
            s = r[0]
            if s >= len(hsrc):
                continue
            x = hsrc[s]
            if r[2] is not None and r[2] < 0:
                o.add('D1', code=c, provider=x[0], value=r[2], url=x[4], detail='negative cash price')
            for col, val in (('code', c), ('hospital', x[0]), ('city', x[1]), ('insurer', ''), ('plan', ''), ('product', 'cash'),
                             ('doctor_line', False), ('pct', False), ('value', float(r[2] or 0)), ('cash', True),
                             ('file_date', x[3] if len(x) > 3 else ''), ('url', x[4] if len(x) > 4 else ''), ('source_row', str(r[4]) if len(r) > 4 else '')):
                hc[col].append(val)
        if hc['code']:
            tb = pa.table(hc, schema=h_schema)
            if w_h is None:
                w_h = pq.ParquetWriter(os.path.join(snap_dir, slug, 'hospital.parquet'), h_schema, compression='zstd')
            w_h.write_table(tb)
    for w in (w_ins, w_h):
        if w:
            w.close()
    # D2: flat-looking amounts the build didn't label
    for (i, ni, v), cs in flat_seen.items():
        if len(cs) >= 5:
            ins, plan = nets[ni]
            o.add('D2', code=','.join(sorted(cs))[:120], provider=fac[i][0], npi=npis[i], insurer=ins, plan=plan, value=v,
                  detail=f'same ${v:,.2f} on {len(cs)} featured procedures')
    # B1: a host that is another insurer's main host and not this insurer's own
    main = {ins: c.most_common(1)[0][0] for ins, c in hosts_by_ins.items() if c}
    owner = collections.defaultdict(set)
    for ins, hst in main.items():
        owner[hst].add(ins)
    for ins, c in hosts_by_ins.items():
        for hst, n in c.items():
            others = owner.get(hst, set()) - {ins}
            if others and hst not in {main[ins]} and not any(_family(ins, y) for y in others):
                o.add('B1', insurer=ins, url=hst, value=n, detail=f'{n} lines link to {hst}, the main file host of {", ".join(sorted(others))}')
    o.n_codes = len(codes)
    o.fp = fp
    o.state = st
    o.providers = len(fac)
    return o.__dict__


FAMILY = [re.compile(p, re.I) for p in (r'bcbs|blue|anthem|wellpoint|elevance|empire|highmark|regence|premera|carefirst|horizon', r'united|uhc|optum|umr', r'centene|ambetter|superior|wellcare',
                                        r'aetna|cvs', r'cigna|evernorth', r'humana', r'molina')]


def _family(a, b):
    return any(rx.search(a) and rx.search(b) for rx in FAMILY)


def check_links(urls, workers=24):
    """E4: one request per distinct link. 403/401/429 count as 'blocked' (opens in a browser, refuses robots), not dead."""
    import requests
    def one(u):
        try:
            r = requests.head(u, timeout=25, allow_redirects=True, headers={'User-Agent': 'files.healthcare link check'})
            if r.status_code >= 400:   # many file servers answer HEAD with 404/405 but serve the file (Craneware, Box, Sitecore)
                r = requests.get(u, timeout=30, stream=True, allow_redirects=True,
                                 headers={'Range': 'bytes=0-0', 'User-Agent': 'Mozilla/5.0 (files.healthcare link check)'})
                r.close()
            s = r.status_code
            return u, s, 'ok' if s < 400 else 'blocked' if s in (401, 403, 429) else 'dead' if s in (404, 410) else 'error'
        except requests.exceptions.ConnectionError as e:
            return u, 0, 'dead' if 'Name or service not known' in str(e) or 'NameResolution' in str(e) else 'error'
        except Exception:
            return u, 0, 'error'
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, sorted(urls)))


def compare(prev_dir, cur_dir, slug):
    """F1-F3 against the newest earlier snapshot of this area. Returns (rows, note)."""
    import duckdb
    p0, p1 = os.path.join(prev_dir, slug, 'insurer.parquet'), os.path.join(cur_dir, slug, 'insurer.parquet')
    if not (os.path.isfile(p0) and os.path.isfile(p1)):
        return [], 'no earlier snapshot'
    con = duckdb.connect()
    key = "code, npi, insurer, plan, fee"
    rows = []
    q = f"""with a as (select {key}, min(value) v from '{p0}' where not pct and value > 0 group by all),
                 b as (select {key}, min(value) v from '{p1}' where not pct and value > 0 group by all)
            select b.code, b.npi, b.insurer, b.plan, b.fee, a.v, b.v from a join b using ({key})
            where b.v > 3 * a.v or a.v > 3 * b.v"""
    for code, npi, ins, plan, fee, v0, v1 in con.execute(q).fetchall():
        rows.append(dict(rule='F1', code=code, npi=npi, insurer=ins, plan=plan, value=v1, detail=f'{fee}: ${v0:,.2f} -> ${v1:,.2f}'))
    q = f"""with a as (select insurer, count(*) n from '{p0}' group by 1), b as (select insurer, count(*) n from '{p1}' group by 1)
            select a.insurer, a.n, coalesce(b.n, 0) from a left join b using (insurer) where coalesce(b.n, 0) < 0.75 * a.n"""
    for ins, n0, n1 in con.execute(q).fetchall():
        rows.append(dict(rule='F2', insurer=ins, value=n1, detail=f'{n0:,} lines -> {n1:,}'))
    n0, n1 = [con.execute(f"select count(distinct npi) from '{p}'").fetchone()[0] for p in (p0, p1)]
    if n1 < 0.9 * n0:
        rows.append(dict(rule='F3', value=n1, detail=f'{n0:,} providers -> {n1:,}'))
    return rows, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', help='an extracted bundle (default: download the deployed one)')
    ap.add_argument('--areas')
    ap.add_argument('--all-codes', action='store_true')
    ap.add_argument('--codes', help='test run: only these codes')
    ap.add_argument('--no-links', action='store_true')
    ap.add_argument('--no-upload', action='store_true')
    ap.add_argument('--workers', type=int, default=3)
    A = ap.parse_args()
    t0 = time.time()
    store = pp.Store('/tmp')
    s3, B = store.s3, store.B
    site_dir = A.site
    if not site_dir:
        site_dir = '/tmp/audit-site'
        os.makedirs(site_dir, exist_ok=True)
        print('downloading the deployed site...', flush=True)
        s3.download_file(B, 'site/deploy/current.tgz', '/tmp/audit-current.tgz')
        with tarfile.open('/tmp/audit-current.tgz') as t:
            t.extractall(site_dir, filter='data') if sys.version_info >= (3, 12) else t.extractall(site_dir)
        os.remove('/tmp/audit-current.tgz')
    areas = json.load(open(os.path.join(site_dir, 'site', 'cities.json'), encoding='utf-8'))
    if A.areas:
        areas = [a for a in areas if a['slug'] in A.areas.split(',')]
    print(len(areas), 'areas', flush=True)
    snap = f'/tmp/audit-snap/{TODAY}'
    os.makedirs(snap, exist_ok=True)
    res = []
    with ProcessPoolExecutor(A.workers) as ex:
        for r in ex.map(audit_area, [(site_dir, a, A.all_codes, snap, set(A.codes.split(',')) if A.codes else None) for a in areas]):
            print(f"  {r['area']}: {sum(r['n'].values())} findings, {dict(r['checked'])}", flush=True)
            res.append(r)
    # links
    links = []
    if not A.no_links:
        us = set()
        for a in areas:
            p = os.path.join(site_dir, 'site', a['path'].strip('/'), 'index.html')
            if os.path.isfile(p):
                D = pp.page_data(p)[0]
                us |= {u for u in D['urls'] if u}
                us |= {x[4] for x in (D.get('hosp') or {}).get('src') or [] if len(x) > 4 and x[4]}
        print(len(us), 'distinct source links to check', flush=True)
        links = check_links(us)
    # snapshots: upload, then compare with the newest earlier one
    prev = None
    if not A.no_upload:
        days = sorted({k.split('/')[2] for k in _ls(s3, B, 'history/published/') if k.count('/') >= 3} - {TODAY})
        prev = days[-1] if days else None
        for root, _, fs in os.walk(snap):
            for fn in fs:
                p = os.path.join(root, fn)
                s3.upload_file(p, B, 'history/published/' + os.path.relpath(p, '/tmp/audit-snap'))
    F = []
    if prev:
        pdir = f'/tmp/audit-snap/{prev}'
        for r in res:
            for k in ('insurer.parquet',):
                key = f"history/published/{prev}/{r['area']}/{k}"
                try:
                    os.makedirs(f"{pdir}/{r['area']}", exist_ok=True)
                    s3.download_file(B, key, f"{pdir}/{r['area']}/{k}")
                except Exception:
                    pass
            rows, _ = compare(pdir, snap, r['area'])
            for x in rows:
                x.update(level=LEVEL[x['rule']], area=r['area'])
                F.append(x)
                r['n'][x['rule']] = r['n'].get(x['rule'], 0) + 1
                if sum(1 for e in r['ex'] if e['rule'] == x['rule']) < EX_CAP:
                    r['ex'].append(x)
    write_reports(res, links, F, prev, s3 if not A.no_upload else None, B, time.time() - t0, A)


def _ls(s3, B, prefix):
    out, tok = [], None
    while True:
        kw = dict(Bucket=B, Prefix=prefix)
        if tok:
            kw['ContinuationToken'] = tok
        r = s3.list_objects_v2(**kw)
        out += [o['Key'] for o in r.get('Contents', [])]
        if not r.get('IsTruncated'):
            return out
        tok = r['NextContinuationToken']


def write_reports(res, links, F, prev, s3, B, secs, A):
    od = os.path.join(REPO, 'reports', 'audit', TODAY)
    os.makedirs(od, exist_ok=True)
    tot = collections.Counter()
    areas_hit = collections.defaultdict(set)
    checked = collections.Counter()
    for r in res:
        for k, v in r['n'].items():
            tot[k] += v
            if v:
                areas_hit[k].add(r['area'])
        checked.update(r['checked'])
    for u, s, verdict in links:
        if verdict == 'dead':
            tot['E4'] += 1
    with open(os.path.join(od, 'counts.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['area', 'state', 'providers', 'codes'] + list(LEVEL))
        for r in sorted(res, key=lambda r: r['area']):
            w.writerow([r['area'], r.get('state', ''), r.get('providers', ''), r.get('n_codes', '')] + [r['n'].get(k, 0) for k in LEVEL])
    with open(os.path.join(od, 'examples.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, FIELDS, extrasaction='ignore')
        w.writeheader()
        for r in res:
            w.writerows(r['ex'])
    with open(os.path.join(od, 'links.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['url', 'status', 'verdict'])
        w.writerows(sorted(links, key=lambda x: (x[2] != 'dead', x[0])))
    if s3:
        buf = io.StringIO()
        w = csv.DictWriter(buf, FIELDS, extrasaction='ignore')
        w.writeheader()
        for r in res:
            w.writerows(r['all'])
        w.writerows(F)
        s3.put_object(Bucket=B, Key=f'audit/{TODAY}/failures.csv.gz', Body=gzip.compress(buf.getvalue().encode()))
    crit = sum(v for k, v in tot.items() if LEVEL[k] == 'Critical')
    lv = collections.Counter(x[2] for x in links)
    L = [f'# Data accuracy audit, Layer 1: {TODAY}', '',
         f"Read-only rule checks on the deployed site (site/audit_rules.py). {len(res)} areas, "
         f"{'every code' if A.all_codes else 'the 89 featured procedures'}; {checked['insurer lines']:,} insurer lines, "
         f"{checked['hospital lines']:,} hospital-file lines, {checked['cash lines']:,} cash lines checked in {secs / 60:.0f} min.", '',
         f"**Critical findings: {crit:,}.** " + ('Launch gate not met.' if crit else 'Launch gate met for Layer 1.'), '',
         '| Rule | Level | What | Findings | Areas |', '|---|---|---|---|---|']
    for k in LEVEL:
        L.append(f"| {k} | {LEVEL[k]} | {WHAT[k]} | {tot.get(k, 0):,} | {len(areas_hit.get(k, ()))} |")
    L += ['', f"Source links checked: {len(links):,} distinct; ok {lv['ok']:,}, blocked to robots {lv['blocked']:,}, "
          f"dead {lv['dead']:,}, other errors {lv['error']:,} (links.csv).",
          '', f"Change since last audit: {'compared with ' + prev if prev else 'first snapshot, nothing to compare yet'}.",
          '', f"History snapshot: storage history/published/{TODAY}/<area>/insurer.parquet and hospital.parquet (kept permanently).",
          f"Full list: storage audit/{TODAY}/failures.csv.gz. Examples (up to {EX_CAP} per rule and area): examples.csv. Per area: counts.csv."]
    open(os.path.join(od, 'summary.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
