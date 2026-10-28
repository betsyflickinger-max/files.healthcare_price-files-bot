"""Hospital file vs insurer file price match: DFW pilot (Betsy OK'd Oct 23, 2026; moved up Oct 24 to start right away).

Both files describe the same contract: the hospital's price file lists what each insurer pays it, and the insurer's file
lists what it pays that hospital. Where both give a dollar amount for the same hospital, insurer, billing code and setting,
they should agree. Agreement = "confirmed by both files"; disagreement = at least one file is wrong (Price File Watch).

Inputs (all already in R2, no rented machines):
  live DFW build      site/every/CURRENT -> BID; site/every/<BID>/build_env.json (the insurer tables it used);
                      site/builds/<BID>/hosp_index.json (the hospital files it used: src)
  insurer side        work/every/Acache/xpart/bucket=<b>/<table tag>.parquet (every_code.py stage A: one row per rate,
                      columns ins, net, code, npi, tin, fee, t, v, modi, st, nt, dt, url), only the buckets of the 89 codes
  hospital side       data/hosp_every/rows/<sha16>.parquet (hosp_every.py: every coded row of each hospital file, untouched values)
  hospital NPIs       the NPIs each hospital file lists itself (type_2_npi), R2 reference/geo/names.json, CMS Hospital
                      Enrollments for the file's CMS number (site/builds/hosp-*/areas.json), site/hospital_npi_matches.csv

Rules (fixed before looking at any result, Oct 24, 2026):
  - Same billing code, facility fee only (hospital billing_class facility; insurer billing_class institutional), no modifier,
    same setting (inpatient/outpatient; a side that doesn't say, or says "both", fits either). MS-DRGs are inpatient.
  - Hospital rows for Medicare Advantage or Medicaid plans are left out (insurer price files cover commercial and
    marketplace plans only). Rows whose product line isn't known are kept.
  - Only dollar amounts are compared. Percent of charges, per diem and formula-only rows are "not comparable", with the reason.
  - Nothing is averaged. A hospital file can list several plan rows for one insurer and the insurer file several networks:
    every hospital amount is compared with every insurer amount, and the CLOSEST pair decides the label. The ranges on both
    sides are reported too, each amount with its source (hospital file + row/line, insurer file link + date).
  - Bands: match = within $1 or 0.5% of the larger amount; close = within 5%; otherwise "files disagree".
  - File dates more than 60 days apart are flagged.
Output: OUT/pairs.csv (one row per hospital file + insurer + code + setting), OUT/summary.md.
Env: R2_*; [OUT=reports/match-pilot/<YYYY-MM>]; [BID=build id, default the live one]; [THREADS=32]."""
import csv, datetime, gzip, json, os, re, shutil, sys, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
import boto3, duckdb

E = os.environ
HERE = os.path.dirname(os.path.abspath(__file__))
g = lambda k: ''.join(E[k].split())
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"), aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                  aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = g('R2_BUCKET')
OUT = E.get('OUT') or f"reports/match-pilot/{time.strftime('%Y-%m')}"
W = E.get('WORK', '/tmp/mp')
TH = int(E.get('THREADS', '32'))
os.makedirs(OUT, exist_ok=True); shutil.rmtree(W, ignore_errors=True); os.makedirs(W, exist_ok=True)

# ---- bands (decided before looking at results)
MATCH_ABS, MATCH_PCT, CLOSE_PCT, DATE_DAYS = 1.0, 0.005, 0.05, 60
def band(a, b):
    d, big = abs(a - b), max(a, b)
    if d <= MATCH_ABS or d <= MATCH_PCT * big: return 'match'
    if d <= CLOSE_PCT * big: return 'close'
    return 'files disagree'

def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def getj(k): return json.loads(s3.get_object(Bucket=B, Key=k)['Body'].read())
def ls(pfx):
    out = []
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pfx): out += [(o['Key'], o['Size']) for o in pg.get('Contents', [])]
    return out

CODES = [r['code'] for r in csv.DictReader(open(f'{HERE}/codes89.csv'))]
NAMES = {}
for f in ('plain_names_auto.tsv', 'plain_names_cpt.tsv'):
    p = f'{HERE}/{f}'
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            if '\t' in l: c, n = l.rstrip('\n').split('\t', 1); NAMES[c] = n
try:
    for r in csv.DictReader(open(f'{HERE}/../data/codes.csv')): NAMES.setdefault(r['code'], r.get('plain_name', ''))
except Exception: pass

# ---- the live DFW build
BID = E.get('BID') or s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
TOUT, SP = f'site/every/{BID}/', f'site/builds/{BID}/'
try: benv = getj(TOUT + 'build_env.json')
except Exception:
    # builds made before Oct 18 have no build_env.json: use the DFW insurer tables as they are now (every_code.py defaults:
    # RATES data/full/rates/, NB 256, stage A in work/every/Acache/); each table's cached work is found under either tag form
    benv = {'files': [list(x) for x in ls('data/full/rates/') if x[0].endswith('.parquet')], 'env': {}, 'fallback': 1}
    log('no build_env.json for', BID, '- using the current insurer tables in data/full/rates/:', len(benv['files']))
hidx = getj(SP + 'hosp_index.json')
src = hidx['src']   # [name, city, other locations, last updated, url, sha16, unit]
log('live DFW build', BID, '|', len(benv['files']), 'insurer tables |', len(src), 'hospital files')

# ---- hospital side: the 89 codes from every hospital file of the build
con = duckdb.connect(f'{W}/mp.duckdb')
con.execute(f"set memory_limit='{E.get('MEM', '10GB')}'; set temp_directory='{W}/duck'; set preserve_insertion_order=false")
CODE_LIST = ','.join(f"'{c}'" for c in CODES)
con.execute("create table h (sha16 varchar, code varchar, setting varchar, billing_class varchar, modifiers varchar, payer_name varchar, plan_name varchar, "
            "dol varchar, pct varchar, alg varchar, methodology varchar, source_row varchar, last_updated_on varchar, source_url varchar, "
            "hospital_name varchar, type_2_npi varchar)")
def dl_h(x):
    k = f'data/hosp_every/rows/{x[5]}.parquet'; p = f'{W}/h_{x[5]}.parquet'
    try: s3.download_file(B, k, p); return p
    except Exception as e: log('hospital rows missing', x[0], k, repr(e)[:80]); return None
missing_h = []
with ThreadPoolExecutor(8) as P:
    for x, p in zip(src, P.map(dl_h, src)):
        if not p: missing_h.append(x[0]); continue
        cols = {r[0] for r in con.execute(f"describe select * from read_parquet('{p}')").fetchall()}
        c = lambda n: n if n in cols else 'null'
        con.execute(f"""insert into h select '{x[5]}', upper(trim(code)), lower(trim(coalesce({c('setting')},''))), lower(trim(coalesce({c('billing_class')},''))),
          trim(coalesce({c('modifiers')},'')), coalesce(payer_name,''), coalesce(plan_name,''), {c('negotiated_dollar')}, {c('negotiated_percentage')},
          {c('negotiated_algorithm')}, lower(trim(coalesce({c('methodology')},''))), {c('source_row')}::varchar, {c('last_updated_on')}::varchar,
          {c('source_url')}, {c('hospital_name')}, {c('type_2_npi')}::varchar
          from read_parquet('{p}') where upper(trim(code)) in ({CODE_LIST}) and trim(coalesce(payer_name,''))<>''""")
        os.remove(p)
log('hospital rows (89 codes, payer rows)', con.execute('select count(*) from h').fetchone()[0], '| files without rows:', len(missing_h))

# ---- payer classification (same rules as h2_build.py, DFW)
PROD_CODE = {"Com": 'commercial', "Ex": 'marketplace', "MA": 'Medicare Advantage', "Mcd": 'Medicaid'}
mapping, by_payer = {}, defaultdict(Counter)
for m in csv.DictReader(open(f'{HERE}/payer_name_mapping.csv', encoding='utf-8-sig')):
    ins = m["grid_column"] if m["grid_column"] != "(not in grid)" else ""
    mapping[(m["payer_name"], m["plan_name"])] = (ins, PROD_CODE.get(m["product_line"], ''))
    if ins: by_payer[m["payer_name"]][ins] += 1
NAME_RULES = [(("aetna",), "Aetna"), (("humana",), "Humana"), (("cigna",), "Cigna"),
              (("unitedhealth", "united health", "uhc", "optum", "umr"), "UnitedHealthcare"),
              (("blue cross", "bluecross", "bcbs", "blue shield"), "BCBSTX"), (("molina",), "Molina"),
              (("ambetter", "superior health", "wellcare", "centene"), "Superior/Ambetter/Wellcare (Centene)"),
              (("oscar",), "Oscar"), (("wellpoint", "amerigroup"), "Wellpoint/Amerigroup"),
              (("baylor scott", "bsw"), "BSW Health Plan"), (("curative",), "Curative")]
MA_WORDS = ('medicare', 'advantage', ' mapd', 'dsnp', 'd-snp', ' ppo ma', ' hmo ma', 'senior', 'dual')
MCD_WORDS = ('medicaid', 'chip', 'star kids', 'starkids', 'star+plus', 'star plus', 'starplus', 'star health')
def classify(payer, plan):
    ins, prod = mapping.get((payer, plan), ('', None))
    if not ins and payer in by_payer: ins = by_payer[payer].most_common(1)[0][0]
    if not ins:
        p = payer.lower()
        ins = next((v for w, v in NAME_RULES if any(x in p for x in w)), '')
    if not prod:   # not in the mapping: read the product line off the names (only to leave Medicare Advantage / Medicaid out)
        t = f' {payer} {plan} '.lower()
        prod = 'Medicare Advantage' if any(w in t for w in MA_WORDS) else 'Medicaid' if any(w in t for w in MCD_WORDS) else ''
    return ins, prod
TO_INS = {'Wellpoint/Amerigroup': 'Wellpoint', 'Superior/Ambetter/Wellcare (Centene)': 'Ambetter'}   # hospital label -> insurer-file label
pairs_ = con.execute("select distinct payer_name, plan_name from h").fetchall()
con.execute("create table cls (payer_name varchar, plan_name varchar, ins varchar, prod varchar)")
con.executemany("insert into cls values (?,?,?,?)", [[a, b, TO_INS.get(i, i), p] for (a, b), (i, p) in ((x, classify(*x)) for x in pairs_)])

# ---- hospital NPIs
npi_of = defaultdict(dict)   # sha16 -> {npi: how}
for sha, v in con.execute("select sha16, string_agg(distinct type_2_npi, ' ') from h where type_2_npi is not null group by 1").fetchall():
    for n in re.findall(r'\b\d{10}\b', v or ''): npi_of[sha].setdefault(n, "the hospital's own price file lists it")
try:
    names = getj('reference/geo/names.json')
    for x in src:
        own = names.get('file:' + x[5])
        for n in re.findall(r'\b\d{10}\b', str(own[1] if own and len(own) > 1 else '')): npi_of[x[5]].setdefault(n, "the hospital's own price file lists it")
except Exception as e: log('names.json not read', repr(e)[:100])
ccn_of = {}
try:
    for k, _ in ls('site/builds/hosp-'):
        if k.endswith('/areas.json'):
            for a in getj(k).values():
                for j in a.get('jobs', []): ccn_of.setdefault(j['id'], j.get('ccn'))
except Exception as e: log('areas.json not read', repr(e)[:100])
for r in csv.DictReader(open(f'{HERE}/hospital_file_ccn.csv')):
    for x in src:
        if r['url_contains'] in (x[4] or ''): ccn_of[x[5]] = r['ccn']
en = defaultdict(set)
try:
    s3.download_file(B, 'data/names/hospital_enrollments.csv', f'{W}/enroll.csv')
    for r in csv.DictReader(open(f'{W}/enroll.csv', encoding='latin-1')): en[r['CCN']].add(r['NPI'])
except Exception as e: log('enrollments not read', repr(e)[:100])
man = defaultdict(set)
for r in csv.DictReader(open(f'{HERE}/hospital_npi_matches.csv')):
    if r['npi']: man[r['ccn']].add(r['npi'])
for x in src:
    cc = ccn_of.get(x[5])
    if cc:
        for n in en.get(cc, ()): npi_of[x[5]].setdefault(n, 'CMS Hospital Enrollments lists it for the CMS number')
        for n in man.get(cc, ()): npi_of[x[5]].setdefault(n, 'site/hospital_npi_matches.csv')
con.execute("create table hn (sha16 varchar, npi varchar, how varchar)")
con.executemany("insert into hn values (?,?,?)", [[s, n, h] for s, d in npi_of.items() for n, h in d.items()])
log('hospital files with NPIs', len(npi_of), 'of', len(src), '| NPIs', con.execute('select count(distinct npi) from hn').fetchone()[0])

# ---- insurer side: stage-A rows for the 89 codes at the hospitals' NPIs
import hashlib
LABEL_KEYS = set(benv.get('label_keys', []))
NFL = bool(benv.get('env', {}).get('NETS_FROM_LABEL'))
TAG = {'t' + hashlib.sha1((f'{k}|{sz}' + ('|label' if (NFL or k in LABEL_KEYS) else '')).encode()).hexdigest()[:12]: k for k, sz in benv['files']}
if benv.get('fallback'):   # label-named or not isn't recorded: take both tag forms; only one has cached work
    TAG.update({'t' + hashlib.sha1(f'{k}|{sz}|label'.encode()).hexdigest()[:12]: k for k, sz in benv['files']})
NB = int(benv.get('env', {}).get('NB', '256'))
AC = benv.get('env', {}).get('ACACHE', 'work/every/Acache/')
bk = sorted({con.execute(f'select hash(?::varchar) % {NB}', [c]).fetchone()[0] for c in CODES})
con.execute("create table npis as select distinct npi from hn")
con.execute("create table ins (ins varchar, net varchar, code varchar, npi varchar, tin varchar, fee int, t int, v double, modi varchar, st varchar, nt varchar, dt varchar, url varchar, tbl varchar)")
got_tags, nfiles, nbytes = set(), 0, 0
for b in bk:
    keys = [(k, s) for k, s in ls(f'{AC}xpart/bucket={b}/') if benv.get('fallback') or k.rsplit('/', 1)[1][:-8].split('_')[0] in TAG]
    d = f'{W}/b{b}'; os.makedirs(d, exist_ok=True)
    with ThreadPoolExecutor(TH) as P: list(P.map(lambda ks: s3.download_file(B, ks[0], f"{d}/{ks[0].rsplit('/', 1)[1]}"), keys))
    nfiles += len(keys); nbytes += sum(s for _, s in keys)
    if bk.index(b) % 10 == 0: log(f'bucket {bk.index(b)+1}/{len(bk)}: {len(keys)} files, {sum(s for _, s in keys)/1e9:.2f} GB; so far {nbytes/1e9:.1f} GB')
    got_tags |= {k.rsplit('/', 1)[1][:-8].split('_')[0] for k, _ in keys}
    if keys:
        con.execute(f"""insert into ins select x.ins, x.net, x.code, x.npi, x.tin, x.fee, x.t, x.v, x.modi, x.st, x.nt, x.dt::varchar, x.url,
          regexp_extract(x.filename, '([^/]+)\\.parquet$', 1)
          from read_parquet('{d}/*.parquet', filename=true, union_by_name=true) x join npis using (npi) where x.code in ({CODE_LIST})""")
    shutil.rmtree(d)
log('insurer stage-A files read', nfiles, f'({nbytes/1e9:.1f} GB) from', len(bk), 'buckets |', len(got_tags), 'cached tables read (', len({TAG[t] for t in got_tags if t in TAG}), 'of', len(set(TAG.values())), 'current tables by name)',
    '| rows at hospital NPIs', con.execute('select count(*) from ins').fetchone()[0])
if benv.get('fallback'):
    # Oct 24: without the build's table list, every cached insurer table was read (older months too). Keep, for each insurer
    # network, only the rows from its newest file date: the prices in force now. Nothing is averaged or mixed across months.
    n0 = con.execute('select count(*) from ins').fetchone()[0]
    con.execute("create table ins2 as select i.* from ins i join (select ins, net, max(dt) mdt from ins group by all) m on m.ins=i.ins and m.net=i.net and m.mdt=i.dt")
    con.execute("drop table ins; alter table ins2 rename to ins")
    log('newest file per network kept:', con.execute('select count(*) from ins').fetchone()[0], 'of', n0, 'rows |',
        con.execute("select count(distinct ins||'|'||net) from ins").fetchone()[0], 'networks')
missing_tables = [] if benv.get('fallback') else sorted(k.rsplit('/', 1)[1] for k in set(TAG.values()) - {TAG[t] for t in got_tags})

# ---- compare
NUM = lambda c: f"try_cast(replace(replace(trim({c}),'$',''),',','') AS DOUBLE)"
con.execute(f"""create table hh as select h.sha16, h.code, h.setting, h.billing_class, h.modifiers, h.payer_name, h.plan_name, c.ins, c.prod,
  {NUM('h.dol')} dol, {NUM('h.pct')} pct, trim(coalesce(h.alg,'')) alg, h.methodology, h.source_row, h.last_updated_on, h.source_url
  from h join cls c using (payer_name, plan_name) where c.ins <> ''""")
groups = defaultdict(lambda: {'h': [], 'hx': Counter(), 'i': [], 'ix': Counter()})
DRG = lambda c: c.isdigit() and len(c) <= 3
def st_norm(s, code):
    s = (s or '').lower()
    if s.startswith('in'): return 'inpatient'
    if s.startswith('out'): return 'outpatient'
    return 'inpatient' if DRG(code) else ''
for sha, code, st, bc, modi, pn, pl, ins, prod, dol, pct, alg, meth, row, lu, url in \
        con.execute("select sha16, code, setting, billing_class, modifiers, payer_name, plan_name, ins, prod, dol, pct, alg, methodology, source_row, last_updated_on, source_url from hh").fetchall():
    G = groups[(sha, ins, code)]
    why = None
    if prod in ('Medicare Advantage', 'Medicaid'): why = f'{prod} plan rows (not in insurer files)'
    elif bc.startswith('prof'): why = 'professional fee only'
    elif modi: why = 'row has a modifier'
    elif not (dol and dol > 0):
        why = 'percent of billed charges' if (pct and pct > 0) else 'formula only (no dollar amount)' if alg else 'no dollar amount'
    elif 'per diem' in meth: why = 'per diem (a daily rate, not a price for the service)'
    elif meth == 'other' and alg: why = 'estimate from a formula (methodology "other" with an algorithm; the dollar amount is an estimate)'
    elif DRG(code) and dol < 100: why = 'under $100 for a hospital stay: looks like a DRG weight, not a dollar price'
    elif 'percent' in meth: why = 'percent of billed charges'
    if why: G['hx'][why] += 1; continue
    G['h'].append(dict(prod=prod, v=dol, st=st_norm(st, code), plan=f'{pn} · {pl}'.strip(' ·'), meth=meth, row=row, date=lu or '', url=url or ''))

def is_mkt(net):
    n = (net or '').lower()
    return any(w in n for w in ('marketplace', 'exchange', 'individual', 'ifp')) or n.startswith('ifp')
# an NPI listed for more than one hospital file can't say which hospital an insurer rate is for: flagged on the row
shared = {n: c for n, c in con.execute("select npi, count(distinct sha16) from hn group by 1 having count(distinct sha16) > 1").fetchall()}
ins_rows = con.execute("""select n.sha16, i.ins, i.code, i.net, i.npi, i.tin, i.fee, i.t, i.v, i.modi, i.st, i.nt, i.dt, i.url
  from ins i join hn n using (npi)""").fetchall()
for sha, ins, code, net, npi, tin, fee, t, v, modi, st, nt, dt, url in ins_rows:
    G = groups[(sha, ins, code)]
    why = None
    if fee != 0: why = 'professional fee only'
    elif modi: why = 'row has a modifier'
    elif t == 1: why = 'percent of billed charges'
    elif not (v and v > 0): why = '$0 listed'
    if why: G['ix'][why] += 1; continue
    G['i'].append(dict(mkt=is_mkt(net), v=v, st=st_norm(st, code), net=net, npi=npi, nt=nt, date=dt or '', url=url or ''))
log('groups (hospital file x insurer x code)', len(groups))

def pdate(s):
    for f in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
        try: return datetime.datetime.strptime((s or '')[:10], f).date()
        except Exception: pass
    return None
def fits(a, b): return not a or not b or a == b
def prod_fits(h, i): return not h['prod'] or (h['prod'] == 'marketplace') == i['mkt']
name_of = {x[5]: x[0] for x in src}
url_of = {x[5]: x[4] for x in src}
rows = []
for (sha, ins, code), G in groups.items():
    H_, I_ = G['h'], G['i']
    r = dict(hospital=name_of.get(sha, sha), hospital_file=url_of.get(sha, ''), insurer=ins, code=code, procedure=NAMES.get(code, ''))
    best = None
    for a in H_:
        for b in I_:
            if not fits(a['st'], b['st']) or not prod_fits(a, b): continue
            d = abs(a['v'] - b['v'])
            if best is None or d < best[0]: best = (d, a, b)
    if best:
        d, a, b = best
        lab = band(a['v'], b['v'])
        hv = sorted({x['v'] for x in H_}); iv = sorted({x['v'] for x in I_})
        da, db = pdate(a['date']), pdate(b['date'])
        r.update(result=lab, setting=a['st'] or b['st'], hospital_price=a['v'], insurer_price=b['v'],
                 diff=round(b['v'] - a['v'], 2), diff_pct=round(100 * (b['v'] - a['v']) / max(a['v'], b['v']), 1),
                 hospital_plan=a['plan'], hospital_row=a['row'], hospital_methodology=a['meth'], hospital_file_date=a['date'],
                 insurer_network=b['net'], insurer_npi=b['npi'], insurer_rate_type=b['nt'], insurer_file=b['url'], insurer_file_date=b['date'],
                 npi_shared_by=shared.get(b['npi'], ''), hospital_product=a['prod'],
                 dates_far_apart='yes' if (da and db and abs((da - db).days) > DATE_DAYS) else '',
                 hospital_range=f"{hv[0]:,.2f}-{hv[-1]:,.2f} ({len(H_)} rows)", insurer_range=f"{iv[0]:,.2f}-{iv[-1]:,.2f} ({len(I_)} rows)", reason='')
    elif H_ and I_:
        r.update(result='not comparable', reason='different settings (inpatient vs outpatient) or plan types (marketplace vs employer)')
    elif (H_ or G['hx']) and (I_ or G['ix']):
        why = [f'hospital file: {k} ({n})' for k, n in G['hx'].most_common(2)] if not H_ else []
        why += [f'insurer file: {k} ({n})' for k, n in G['ix'].most_common(2)] if not I_ else []
        r.update(result='not comparable', reason='; '.join(why))
    elif H_ or G['hx']:
        r.update(result='hospital file only', reason='; '.join(f'{k} ({n})' for k, n in G['hx'].most_common(2)) if not H_ else '')
    else:
        r.update(result='insurer file only', reason='; '.join(f'{k} ({n})' for k, n in G['ix'].most_common(2)) if not I_ else '')
    rows.append(r)

COLS = ['result', 'hospital', 'insurer', 'code', 'procedure', 'setting', 'hospital_price', 'insurer_price', 'diff', 'diff_pct',
        'hospital_plan', 'hospital_row', 'hospital_methodology', 'hospital_file_date', 'hospital_file', 'hospital_range',
        'insurer_network', 'insurer_npi', 'insurer_rate_type', 'insurer_file_date', 'insurer_file', 'insurer_range', 'npi_shared_by', 'hospital_product', 'dates_far_apart', 'reason']
rows.sort(key=lambda r: (r['hospital'], r['insurer'], r['code']))
with open(f'{OUT}/pairs.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, COLS, extrasaction='ignore'); w.writeheader(); w.writerows(rows)

# ---- summary
RES = ['match', 'close', 'files disagree', 'not comparable', 'hospital file only', 'insurer file only']
def table(key, keep=None, top=None):
    c = defaultdict(Counter)
    for r in rows: c[r[key]][r['result']] += 1
    ks = sorted(c, key=lambda k: -(c[k]['match'] + c[k]['close'] + c[k]['files disagree']))
    if keep: ks = [k for k in ks if k in keep]
    if top: ks = ks[:top]
    out = [f"| {key.title()} | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |", '|---|---:|---:|---:|---:|---:|---:|---:|']
    for k in ks:
        x = c[k]; both = x['match'] + x['close'] + x['files disagree']
        out.append(f"| {k} | {both:,} | {x['match']:,} | {x['close']:,} | {x['files disagree']:,} | {x['not comparable']:,} | {x['hospital file only']:,} | {x['insurer file only']:,} |")
    return '\n'.join(out)
tot = Counter(r['result'] for r in rows)
both = tot['match'] + tot['close'] + tot['files disagree']
ins_rank = Counter(r['insurer'] for r in rows if r['result'] in ('match', 'close', 'files disagree'))
BIG_INS = [k for k, _ in ins_rank.most_common(5)]
dis = sorted([r for r in rows if r['result'] == 'files disagree' and r['insurer'] in BIG_INS],
             key=lambda r: -abs(r['diff']))
far = sum(1 for r in rows if r.get('dates_far_apart'))
pc = lambda n: f"{100*n/both:.0f}%" if both else '-'
md = [f"# Hospital file vs insurer file: DFW pilot ({time.strftime('%b %d, %Y')})", '',
      f"Live DFW build `{BID}`: {len(src)} hospital files, {len(benv['files'])} insurer tables. The 89 core procedures, facility fees only.",
      f"Bands (set before looking): match = within $1 or 0.5%; close = within 5%; otherwise files disagree. The closest pair of",
      f"amounts decides; nothing is averaged. Hospital rows for Medicare Advantage / Medicaid plans are left out. File dates more than {DATE_DAYS} days apart are flagged.", '',
      f"**Where both files give a dollar amount: {both:,}** (hospital file + insurer + procedure + setting)", '',
      f"- Match: {tot['match']:,} ({pc(tot['match'])})", f"- Close: {tot['close']:,} ({pc(tot['close'])})", f"- Files disagree: {tot['files disagree']:,} ({pc(tot['files disagree'])})",
      f"- Not comparable (percent of charges, per diem, formula, professional fee only...): {tot['not comparable']:,}",
      f"- Only the hospital file has it: {tot['hospital file only']:,} · only the insurer file has it: {tot['insurer file only']:,}",
      f"- File dates more than {DATE_DAYS} days apart: {far:,}",
      f"- Compared at an NPI that more than one hospital file lists (can't tell which campus the insurer rate is for): {sum(1 for r in rows if r.get('npi_shared_by'))}", '',
      "Rules added after the first run (Oct 24, data-type rules, not the bands): a hospital-stay (MS-DRG) amount under $100 is a DRG weight,",
      "not a dollar price (not comparable); a hospital row for a marketplace plan is compared only with marketplace networks, and an",
      "employer-plan row only with the others. If the build's insurer table list isn't recorded, every saved insurer table is read and",
      "each network keeps only its newest file.",
      "Added Oct 24 after the hand-check (reports/match-pilot/2026-10/handcheck/): a hospital row whose methodology is \"other\" and that gives a",
      "formula is an estimate, not a set price (not comparable): e.g. Methodist's \"Case rate ($76,005.38). If operating cost ... \".", '',
      "Note (Oct 24, 2026): UnitedHealthcare Core / Core EPO / Select Plus / Navigate and Aetna's four national networks are being added to DFW this week;",
      "their prices reach this comparison at the next DFW build, so UnitedHealthcare and Aetna results may shift. Re-run: push a change to",
      "site/match_pilot.py or run the \"Match pilot\" workflow by hand (it also runs on the 10th of each month).", '',
      '## By insurer', '', table('insurer', top=8), '', '## Biggest hospitals (most procedures both files price)', '', table('hospital', top=15), '',
      '## Biggest disagreements (big insurers)', '',
      '| Hospital | Insurer | Procedure | Hospital file says | Insurer file says | Dates (hospital / insurer) |', '|---|---|---|---:|---:|---|']
for r in dis[:15]:
    md.append(f"| {r['hospital']} | {r['insurer']} ({r['insurer_network']}) | {r['code']} {r['procedure']} ({r['setting'] or 'setting not given'}) | "
              f"${r['hospital_price']:,.2f} ({r['hospital_plan']}; row {r['hospital_row']}) | ${r['insurer_price']:,.2f} | {r['hospital_file_date']} / {r['insurer_file_date']}{' ⚑' if r['dates_far_apart'] else ''}{' (NPI shared by ' + str(r['npi_shared_by']) + ' files)' if r.get('npi_shared_by') else ''} |")
nc = Counter(x for r in rows if r['result'] == 'not comparable' for x in [r['reason'].split(' (')[0]])
md += ['', '## Why rows were not comparable (most common)', ''] + [f"- {k}: {n:,}" for k, n in nc.most_common(8)]
md += ['', '## Data notes', '', f"- Hospital files without saved rows: {len(missing_h)}" + (f" ({', '.join(missing_h[:8])})" if missing_h else ''),
       f"- Hospital files with no NPI found (can't be matched to insurer files): {sum(1 for x in src if x[5] not in npi_of)}",
       f"- Insurer tables of the build not found in the stage-A cache: {len(missing_tables)}" + (f" ({', '.join(missing_tables[:6])})" if missing_tables else ''),
       f"- Full list: pairs.csv (one row per hospital file + insurer + procedure; both amounts with their sources)."]
open(f'{OUT}/summary.md', 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print('\n'.join(md))
log('DONE', len(rows), 'rows')
