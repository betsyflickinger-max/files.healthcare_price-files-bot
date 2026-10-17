"""Monthly site build (from the Oct 8, 2026 every-code build): build Price Finder files for EVERY CPT/HCPCS/MS-DRG code in the DFW insurer full tables.
Runs on a rented machine. Same row format and rules as 09r_build_site_v2.py (+ trim.py caps), but:
- reads data/full/rates/*.parquet (all codes) instead of the 89-code slices,
- CPT/HCPCS codes keep leading zeros (anesthesia 00811 etc.); DRGs are ltrimmed ('470'),
- works bucket by bucket (hash(code) % NB) so it never holds everything in memory,
- writes the insurer's own description per code (most common wording) for codes without a plain-English name.
Outputs to R2: TOUT/t/<code>.txt, TOUT/embed.json, TOUT/npis.json, OUTP/log.txt.
Monthly changes: input prefix RATES, provider list NPIS, stage A saved per insurer table (not per list position) in
ACACHE so unchanged tables are reused next month; several machines can run it at once (AORDER/BORDER=desc for
the second one); embed.json is written only when all NB buckets are done."""
import hashlib
import os, sys, csv, json, gzip, base64, time, duckdb, boto3, glob, shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
E = os.environ
s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
B = E['R2_BUCKET']; OUTP = E.get('OUTP', 'site/every/2026-10-08/'); D = Path(E.get('WORK', '/d')); NB = int(E.get('NB', '256')); SPLIT = int(E.get('SPLIT', '1')); TOUT = E.get('TOUT', 'site/every/2026-10-08/')
LOG = []
def log(*a):
    m = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(m, flush=True); LOG.append(m)
    if len(LOG) % 3 == 1: s3.put_object(Bucket=B, Key=OUTP + 'log.txt', Body='\n'.join(LOG).encode())
def ls(pfx):
    out = []
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pfx): out += [(o['Key'], o['Size']) for o in pg.get('Contents', [])]
    return out
# a crashed earlier attempt on this machine leaves DuckDB spill files (and, with NOXPART, downloaded buckets) behind; clear them
shutil.rmtree(D / 'tmp', ignore_errors=True)
if E.get('NOXPART'): shutil.rmtree(D / 'xpart', ignore_errors=True)
for sub in ('xpart', 'stage', 'aux', 'flat', 'names', 'tmp', 'in'): (D / sub).mkdir(parents=True, exist_ok=True)
con = duckdb.connect()
con.execute(f"set enable_progress_bar=false; set memory_limit='{E.get('MEM','12GB')}'; set threads={E.get('THREADS','8')}; set preserve_insertion_order=false; set temp_directory='{D}/tmp'; set partitioned_write_max_open_files=8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import blues  # noqa: E402  (Oct 15, 2026: each Blue plan by name, not every Blue Cross price as BCBSTX)
SHORT = """case """ + blues.SQL_SHORT + """
 when reporting_entity_name ilike '%uhic%' or reporting_entity_name ilike '%united%' then 'UnitedHealthcare'
 when reporting_entity_name ilike '%aetna%' then 'Aetna' when reporting_entity_name ilike '%cigna%' then 'Cigna'
 when reporting_entity_name ilike '%curative%' then 'Curative' when reporting_entity_name ilike '%baylor%' then 'BSW Health Plan'
 when reporting_entity_name ilike '%centene%' then 'Ambetter' when reporting_entity_name ilike '%oscar%' then 'Oscar'
 when reporting_entity_name ilike '%molina%' then 'Molina' when reporting_entity_name ilike '%wellpoint%' or reporting_entity_name ilike '%elevance%' or reporting_entity_name ilike '%anthem%' or source_file ilike 'TX_JBLX%' then 'Wellpoint'
 else reporting_entity_name end"""
NET = """case when reporting_entity_name ilike '%aetna%' then replace(replace(file_label, 'Aetna ', ''), 'Health Inc. - Texas ', '')
 when reporting_entity_name ilike '%centene%' then replace(file_label, 'Ambetter ', '') when reporting_entity_name ilike '%molina%' then 'Marketplace (Texas)'
 when reporting_entity_name ilike '%oscar%' then replace(network_name, 'Individual Texas ', 'Individual ')
 when network_name = 'IFP TEXAS CONNECT' then 'IFP Texas Connect (marketplace)'
 when network_name = 'NATIONAL OAP' then 'Open Access Plus' when network_name = 'PATHWELL OAP' then 'Pathwell OAP'
 when network_name = 'LOCALPLUS' then 'LocalPlus' when network_name ilike 'BCBSTX %' then substr(network_name, 8)
 when source_file ilike 'TX_JBLX%' then 'Texas Essential (marketplace)' else network_name end"""
KEY = """case when billing_code_type ilike '%drg%' then ltrim(trim(billing_code), '0') else upper(trim(billing_code)) end"""
TYPE = """case when billing_code_type ilike '%drg%' then 'MS-DRG' when billing_code_type ilike 'hcpcs%' then 'HCPCS' else 'CPT' end"""

# ---------- Stage A: one pass per insurer file ----------
files = sorted(ls(E.get('RATES', 'data/full/rates/')), key=lambda x: x[1])
if E.get('AORDER') == 'desc': files = files[::-1]
if E.get('ONLY'): files = [f for f in files if E['ONLY'] in f[0]]
if E.get('ASTART'): r_ = int(E['ASTART']) % max(1, len(files)); files = files[r_:] + files[:r_]   # machines start at different tables
log('stage A', len(files), 'files', round(sum(s for _, s in files) / 1e9, 1), 'GB')
WK = E.get('WK', 'work/every/2026-10-08/')
AC = E.get('ACACHE', WK + 'A/')   # stage A results, shared across monthly builds
TAG = {key: 't' + hashlib.sha1(f'{key}|{size}'.encode()).hexdigest()[:12] for key, size in files}   # same table + size -> same results
TAGS = set(TAG.values())
doneA = {k.rsplit('/', 1)[1][:-5] for k, _ in ls(AC) if k.endswith('.done')}
def isdone(tag): 
    try: s3.head_object(Bucket=B, Key=AC + f'{tag}.done'); return True
    except Exception: return False
def mine(fn):  # a cached A file ('<tag>.parquet' or '<tag>_<piece>.parquet') belongs to this build's tables
    return fn.rsplit('.', 1)[0].split('_')[0] in TAGS   # Oct 12, 2026 fix: '.parquet' was left on unsplit tables, so they were never downloaded
import math
def save_a(i):
    outs = glob.glob(f'{D}/xpart/bucket=*/{i}.parquet') + [p for p in (f'{D}/flat/{i}.parquet', f'{D}/names/{i}.parquet', f'{D}/aux/{i}.parquet') if os.path.exists(p)]
    with ThreadPoolExecutor(16) as P_: list(P_.map(lambda p: s3.upload_file(p, B, AC + os.path.relpath(p, D)), outs))   # ~260 files per table
    s3.put_object(Bucket=B, Key=AC + f'{i}.done', Body=b'1')
_LA = None
def restore_a(i):
    global _LA
    if _LA is None: _LA = [x for sub in ('aux/', 'flat/', 'names/') for x in ls(AC + sub)] if E.get('NOXPART') else ls(AC)
    for k, _ in _LA:
        rel = k[len(AC):]
        fn = rel.rsplit('/', 1)[-1][:-8] if rel.endswith('.parquet') else None
        if E.get('NOXPART') and rel.startswith('xpart/'): continue
        if fn is not None and (fn == str(i) or ('_' not in str(i) and fn.startswith(f'{i}_'))):
            dest = D / rel; dest.parent.mkdir(parents=True, exist_ok=True); s3.download_file(B, k, str(dest))
NEWP = [0]
def LOGFLUSH(): s3.put_object(Bucket=B, Key=OUTP + 'log.txt', Body='\n'.join(LOG).encode())
PIECE_GB = float(E.get('PIECE_GB', '0.4'))
# ACLAIM=1: many machines share stage A. Each table is claimed (AC/<tag>.claim) before it is read, so machines take
# different tables; a claim older than CLAIM_H hours (machine died) can be taken over. After its own tables, a
# machine waits for the others' tables and then moves on to stage B with all of them.
ROLE = E.get('ROLE', 'local'); CLAIM_S = float(E.get('CLAIM_H', '2')) * 3600
def claim(i):
    try:
        o = s3.get_object(Bucket=B, Key=AC + f'{i}.claim'); who = o['Body'].read().decode()
        if who != ROLE and time.time() - o['LastModified'].timestamp() < CLAIM_S: return False
    except Exception: pass
    s3.put_object(Bucket=B, Key=AC + f'{i}.claim', Body=ROLE.encode()); time.sleep(3)   # two machines can claim at once:
    try: return s3.get_object(Bucket=B, Key=AC + f'{i}.claim')['Body'].read().decode() == ROLE   # the last write wins
    except Exception: return True
waiting = []
for ii, (key, size) in enumerate(files):
    i = TAG[key]
    if E.get('ONLYIDX') and ii != int(E['ONLYIDX']): continue
    if str(i) in doneA or isdone(i):
        restore_a(i); log(f'A {ii+1}/{len(files)} restored from saved work', key.rsplit('/', 1)[1]); continue
    K = max(1, math.ceil(size / (PIECE_GB * 1e9))) if size > float(E.get('MINSPLIT', '0.8e9')) else 1
    if K == 1 and E.get('ACLAIM') and not claim(i):   # big tables are shared piece by piece instead
        waiting.append((ii, key, i, K)); continue
    loc, locm = D / 'in/r.parquet', D / 'in/m.parquet'
    got = False; others = False
    total = 0
    for p in range(K):
        tag = f'{i}' if K == 1 else f'{i}_{p}'
        if K > 1 and (tag in doneA or isdone(tag)):
            restore_a(tag); log(f'A {ii+1}/{len(files)} piece {p+1}/{K} restored'); continue
        if K > 1 and E.get('ACLAIM') and not claim(tag): others = True; continue
        if not got:   # download only once this machine has work in the table
            s3.download_file(B, key, str(loc))
            try: s3.download_file(B, key.replace('/rates/', '/membership/'), str(locm)); mj = True
            except Exception: mj = False
            got = True
        pf = f"hash(npi) % {K} = {p}" if K > 1 else "true"
        mem = f"(select npi, tin, any_value(network_name) network_name from read_parquet('{locm}') where {pf} group by all)" if mj else "(select null::varchar npi, null::varchar tin, null::varchar network_name where false)"
        con.execute(f"""create or replace temp view r0 as
          select r.*, coalesce(m.network_name, r.file_label) network_name from (select * from read_parquet('{loc}') where {pf}) r left join {mem} m using (npi, tin)
          where (billing_code_type ilike 'cpt%' or billing_code_type ilike 'hcpcs%' or billing_code_type ilike 'ms-drg%' or billing_code_type ilike 'drg%')
            and lower(negotiated_type) in ('negotiated','fee schedule','derived','percentage') and try_cast(negotiated_rate as double) >= 0""")
        con.execute(f"""create or replace temp view r1 as select {SHORT} ins, {NET} net, {KEY} code, {TYPE} ctype, name, npi, tin,
          case when billing_class ilike 'inst%' then 0 else 1 end fee, case when negotiated_type ilike 'percent%' then 1 else 0 end t,
          round(try_cast(negotiated_rate as double), 2) v, coalesce(billing_code_modifier,'') modi, coalesce(setting,'') st,
          lower(negotiated_type) nt, last_updated_on dt, source_url url from r0""")
        con.execute(f"""create or replace temp view r2 as select * from r1
          where (ctype <> 'MS-DRG' and regexp_matches(code, '^[0-9A-Z][0-9]{{3}}[0-9A-Z]$')) or (ctype = 'MS-DRG' and regexp_matches(code, '^[0-9]{{1,3}}$'))""")
        sd = D / f'stage/src={tag}'
        shutil.rmtree(sd, ignore_errors=True)
        con.execute(f"copy (select ins, net, code, ctype, name, npi, tin, fee, t, v, modi, st, nt, dt, url, hash(code) % {NB} bucket from r2) to '{sd}' (format parquet, compression zstd, partition_by (bucket), overwrite_or_ignore)")
        if not glob.glob(f'{sd}/*/*.parquet'):
            if K > 1: s3.put_object(Bucket=B, Key=AC + f'{tag}.done', Body=b'1')
            continue
        src = f"read_parquet('{sd}/*/*.parquet')"
        con.execute(f"copy (select code, ctype, name, count(*) n from {src} where name is not null and name <> '' group by all) to '{D}/names/{tag}.parquet' (format parquet)")
        con.execute(f"copy (select npi, ins, net, v from {src} where fee=0 and t=0 and v>0 and modi='' group by all having count(distinct code) >= 5) to '{D}/flat/{tag}.parquet' (format parquet)")
        con.execute(f"copy (select distinct 'n' k, ins||'|'||net val from {src} union select distinct 'd', dt from {src} union select distinct 'u', url from {src} union select distinct 'p', npi from {src} union select distinct 'm', modi||'~'||st||'~'||nt from {src}) to '{D}/aux/{tag}.parquet' (format parquet)")
        for bdir in glob.glob(f'{sd}/bucket=*'):
            b = bdir.rsplit('=', 1)[1]; (D / f'xpart/bucket={b}').mkdir(parents=True, exist_ok=True)
            con.execute(f"copy (select ins, net, code, npi, tin, fee, t, v, modi, st, nt, dt, url from read_parquet('{bdir}/*.parquet')) to '{D}/xpart/bucket={b}/{tag}.parquet' (format parquet, compression zstd)")
        shutil.rmtree(sd)
        if K > 1:
            save_a(tag); log(f'A {ii+1}/{len(files)} piece {p+1}/{K} done')
            NEWP[0] += 1
            if E.get('MAXPIECES') and NEWP[0] >= int(E['MAXPIECES']): log('MAXPIECES reached, restarting fresh'); LOGFLUSH(); os._exit(3)
    loc.unlink(missing_ok=True); locm.unlink(missing_ok=True)
    if K > 1 and others and not all(isdone(f'{i}_{p}') for p in range(K)):
        waiting.append((ii, key, i, K)); continue   # other machines still have pieces of this table
    gl = f'{D}/xpart/bucket=*/{i}.parquet' if K == 1 else f'{D}/xpart/bucket=*/{i}_*.parquet'
    n = con.execute(f"select sum(num_rows) from (select distinct file_name, row_group_id, row_group_num_rows num_rows from parquet_metadata('{gl}'))").fetchone()[0] if glob.glob(gl) else 0
    if K == 1: save_a(i)
    else: s3.put_object(Bucket=B, Key=AC + f'{i}.done', Body=b'1')
    log(f'A {ii+1}/{len(files)}', f'{(n or 0):,} rows' + (f' in {K} pieces' if K > 1 else ''), key.rsplit('/', 1)[1], f'disk {shutil.disk_usage(str(D)).used/1e9:.0f} GB')

if waiting:
    log('A waiting for', len(waiting), 'tables other machines are reading'); LOGFLUSH()
    while waiting:
        time.sleep(60)
        for w in list(waiting):
            ii_, key_, i_, K_ = w
            if K_ > 1 and not isdone(i_) and all(isdone(f'{i_}_{p}') for p in range(K_)):
                s3.put_object(Bucket=B, Key=AC + f'{i_}.done', Body=b'1')   # last piece came in: mark the whole table
            if isdone(i_):
                _LA = None; restore_a(i_); waiting.remove(w); log(f'A {ii_+1}/{len(files)} read by other machines', key_.rsplit('/', 1)[1])
            elif any(claim(t_) for t_ in ([i_] if K_ == 1 else [f'{i_}_{p}' for p in range(K_) if not isdone(f'{i_}_{p}')])):
                log('A taking over', key_.rsplit('/', 1)[1]); LOGFLUSH(); os._exit(4)   # its machine stopped: restart and read it here
if E.get('ACLAIM'):
    # Oct 12, 2026 fix: the file listing used by restore_a was taken when the first table was restored, so tables other
    # machines finished later were missing their lookup files here and machines built different provider lists.
    # Restore every table's lookup files again from a fresh listing before building the lookups.
    _LA = None
    for sub in ('aux', 'flat', 'names'): shutil.rmtree(D / sub, ignore_errors=True); (D / sub).mkdir(parents=True, exist_ok=True)
    for t_ in sorted(TAGS): restore_a(t_)
    log('A all', len(TAGS), 'tables restored from a fresh listing')
if E.get('STOPA'): log('STOPA'); sys.exit(0)
# ---------- lookups ----------
s3.download_file(B, E.get('NPIS', 'data/2026-09-29/dfw_npis_all.parquet'), str(D / 'npis.parquet'))
s3.download_file(B, 'site/site_codes.csv', str(D / 'site_codes.csv'))
NP = {r[0]: r[1:] for r in con.execute(f"select npi, entity_type, name, credential, taxonomy_1, city from '{D}/npis.parquet'").fetchall()}
FEAT = {r['code']: r for r in csv.DictReader(open(D / 'site_codes.csv'))}
NAMES = {c: (t, nm) for c, t, nm in con.execute(f"""select code, arg_max(ctype, n), arg_max(name, n) from
  (select code, ctype, name, sum(n) n from read_parquet('{D}/names/*.parquet') group by all) group by code""").fetchall()}
log('lookups', len(NP), 'npis', len(NAMES), 'codes')

MOD = {'26': 'professional part only', 'TC': 'technical part only', '52': 'reduced service', '53': 'discontinued procedure',
       '54': 'surgery only', '55': 'after-surgery care only', '56': 'pre-surgery care only', '78': 'return to operating room',
       '50': 'both sides', '51': 'multiple procedures', '59': 'separate procedure', '80': 'assistant surgeon', '82': 'assistant surgeon',
       'AS': 'assistant at surgery', 'LT': 'left side', 'RT': 'right side', 'QK': 'anesthesia, supervised', 'QX': 'nurse anesthetist, supervised',
       'QY': 'nurse anesthetist, supervised', 'QZ': 'nurse anesthetist alone', 'AA': 'anesthesiologist personally', 'GT': 'telehealth', '95': 'telehealth', 'GP': 'physical therapy plan'}
def label_str(modi, st, nt, other):
    p = [MOD.get(m, 'modifier ' + m) for m in modi.split('|') if m] if modi else []
    if st in ('inpatient', 'outpatient'): p.append(st)
    if nt in ('fee schedule', 'derived'): p.append(nt)
    if other: p.append('billed under another tax ID')
    return ', '.join(p)
def provider(npi):
    et, name, cred, tax, city = NP.get(npi, ('2', None, None, '', '')); tax = tax or ''
    kind = 'P' if et == '1' else 'A' if tax.startswith('261QA') else 'H' if tax[:3] in ('282', '283', '284', '286', '273', '275', '276') else 'G'
    nm = (name or f'NPI {npi}').strip()
    if nm.isupper():
        nm = nm.title()
        for a, b in ((' Llc', ' LLC'), (' Pllc', ' PLLC'), (' Pa', ' PA'), (' Lp', ' LP'), (' Md', ' MD'), (' Dds', ' DDS')): nm = nm.replace(a, b)
    if cred and kind == 'P': nm = f"{nm}, {cred.replace('.', '')}"
    return [nm, (city or '').title(), kind]
# ---------- global lookup tables (fixed before stage B so workers can run in parallel) ----------
AUX = {}
for k_, v_ in con.execute(f"select k, val from read_parquet('{D}/aux/*.parquet') group by all order by k, val").fetchall(): AUX.setdefault(k_, []).append(v_ if v_ is not None else '')
nets, dates, urls, npis = AUX.get('n', []), AUX.get('d', []), AUX.get('u', []), AUX.get('p', [])
ptab = [provider(n_) for n_ in npis]
labs = sorted({x for m in AUX.get('m', []) for o in (0, 1) for x in [label_str(*(m.split('~') + [''] * 3)[:3], o)] if x})
log('index', len(nets), 'networks', len(dates), 'dates', len(urls), 'urls', len(ptab), 'providers', len(labs), 'labels')
# every machine of a build must use the same lookup lists, or their batches won't match embed.json: the first machine
# records a fingerprint, the others refuse to run stage B with a different one
FP = hashlib.sha1(json.dumps([nets, dates, urls, npis, labs]).encode()).hexdigest()[:16]
try: FP0 = s3.get_object(Bucket=B, Key=WK + 'index.fp')['Body'].read().decode()
except Exception: FP0 = None; s3.put_object(Bucket=B, Key=WK + 'index.fp', Body=FP.encode())
if FP0 and FP0 != FP: log('ERROR lookup lists differ from the other machines', FP, FP0); LOGFLUSH(); sys.exit(5)
nidx = {k_: i_ for i_, k_ in enumerate(nets)}; didx = {k_: i_ for i_, k_ in enumerate(dates)}; uidx = {k_: i_ for i_, k_ in enumerate(urls)}
pidx = {k_: i_ for i_, k_ in enumerate(npis)}; lidx = {k_: i_ for i_, k_ in enumerate(labs)}; KIND = [p_[2] for p_ in ptab]
def lab(modi, st, nt, tin, tin0):
    x = label_str(modi or '', st or '', nt or '', tin != tin0)
    return lidx.get(x, -1) if x else -1
Q = """with md as (select code, fee, median(v) m, count(*) n from x where t=0 and v>0 and modi='' group by code, fee),
  y as (select x.*, fl.v is not null and x.fee=0 and x.t=0 and x.modi='' isflat,
          coalesce(md.n >= 5 and x.t=0 and x.v>0 and x.v < 0.2*md.m, false) islow
        from x left join flat fl on fl.npi=x.npi and fl.ins=x.ins and fl.net=x.net and fl.v=x.v left join md on md.code=x.code and md.fee=x.fee),
  g as (select code, npi, ins, net, fee, t, count(*) filter (where v=0) zeros,
    arg_min([v::varchar, tin, modi, st, nt, dt, url, isflat::varchar, islow::varchar], (modi<>'')::int*1e12 + v) filter (where v>0) h,
    count(*) filter (where v>0) npos, any_value(dt) dt0, any_value(url) url0 from y group by all),
  o as (select code, npi, ins, net, fee, t, list([v::varchar, tin, modi, st, nt] order by v) ot from
    (select *, row_number() over (partition by code, npi, ins, net, fee, t order by v) rn from x where v>0) where rn<=9 group by all)
  select g.*, o.ot from g left join o using (code, npi, ins, net, fee, t) order by code"""
FLAT = None
# Stage B sorts on small integer ids instead of the long text columns (url, npi, insurer|network, date). Oct 12, 2026:
# (1) DuckDB 1.1.3 returned rows OUT OF ORDER when sorting on these 13 text-heavy columns (27,965 of 8.3M rows in an
#     El Paso test), so the "lowest rate" headline and the count of other rates could be wrong; the integer sort is exact;
# (2) the text sort spilled 50+ GB per Houston batch and filled the disk.
# npis/dates/urls are already sorted (AUX query), so a list position sorts like the text; networks get their (ins, net) rank.
NETS2 = sorted(tuple((k_.split('|', 1) + [''])[:2]) for k_ in nets)
SORTV = E.get('SORTV', '2')   # 2 = integer sort + Python walk (default); 3 = per-group SQL, opt-in only: on Oct 12, 2026 it ran
# fine on El Paso/San Antonio-size batches but Houston and Austin machines restarted for hours without finishing a batch
# (most likely memory: the window step can't stream like the plain sort). 1 = original text sort (out-of-order bug).
def unit_parts(u):
    """Oct 14: a unit of stage-B work is a whole bucket k (int) or, with SPLIT>1, piece s of bucket k ('k_s'): the rows of
    bucket k whose hash(code) % (NB*SPLIT) == k + NB*s. Every code of bucket k is in exactly one piece (hash % NB == k)."""
    if isinstance(u, str) and '_' in u: k_, s_ = u.split('_'); return int(k_), int(s_)
    return int(u), None
def bucket_done(k): return exists_key(f'{WK}B/{k}.json')
def exists_key(key):
    try: s3.head_object(Bucket=B, Key=key); return True
    except Exception: return False
# Oct 15: BCLAIM=1: claim a stage-B unit before working on it (WK/Bclaim/<u>), so machines don't all work the same
# unfinished pieces (at 3:40am CT 2-3 Georgia machines were on each of pieces 33_2, 33_3, 34_1, 34_2, 35_0). A claim older
# than BCLAIM_H hours (machine died) can be taken over; a skipped unit is picked up by whichever machine runs next.
BCLAIM_S = float(E.get('BCLAIM_H', '3')) * 3600
def bclaim(u):
    key = f'{WK}Bclaim/{u}'
    try:
        o = s3.get_object(Bucket=B, Key=key); who = o['Body'].read().decode()
        if who != ROLE and time.time() - o['LastModified'].timestamp() < BCLAIM_S: return False
    except Exception: pass
    s3.put_object(Bucket=B, Key=key, Body=ROLE.encode()); time.sleep(2)   # two machines can claim at once: last write wins
    try: return s3.get_object(Bucket=B, Key=key)['Body'].read().decode() == ROLE
    except Exception: return True
def work(u):
    """One bucket (or one piece of one). DuckDB only sorts (spills to disk, so memory stays bounded); Python walks the sorted rows and
    applies the same rules as 09r: headline = lowest positive rate with no modifier (else lowest positive), up to 8
    other rates, $0 count, flat-case-rate, unusually-low and unusually-high flags (median via approx_quantile;
    flag bits: 1 flat case rate, 2 under a fifth of the median, 4 $0 listed, 8 over 20 times the median)."""
    k, sp = unit_parts(u)
    try:
        return tuple(json.loads(s3.get_object(Bucket=B, Key=f'{WK}B/{u}.json')['Body'].read()))
    except Exception: pass
    if sp is not None and bucket_done(k): return (u, 0, {}, {})   # an older machine finished the whole bucket meanwhile
    if E.get('BCLAIM') and not bclaim(u): return (u, 0, {}, {})   # another machine is on it (not written: it isn't done)
    global FLAT
    if E.get('NOXPART'):
        xd = D / f'xpart/bucket={k}'; xd.mkdir(parents=True, exist_ok=True)
        listed = ls(f'{AC}xpart/bucket={k}/')
        if listed and not any(mine(kk_.rsplit('/', 1)[1]) for kk_, _ in listed):
            raise RuntimeError(f'bucket {k}: {len(listed)} stage-A files but none match this build (insurer tables changed since stage A?)')
        todo_ = [kk_ for kk_, _ in listed if mine(kk_.rsplit('/', 1)[1]) and not (xd / kk_.rsplit('/', 1)[1]).exists()]
        with ThreadPoolExecutor(8) as P_: list(P_.map(lambda kk_: s3.download_file(B, kk_, str(xd / kk_.rsplit('/', 1)[1])), todo_))
    if not glob.glob(f'{D}/xpart/bucket={k}/*.parquet'):   # small areas (El Paso) can have empty buckets
        res = (u, 0, {}, {})
        s3.put_object(Bucket=B, Key=f'{WK}B/{u}.json', Body=json.dumps(res).encode())
        return res
    c = duckdb.connect()
    c.execute(f"set enable_progress_bar=false; set memory_limit='{E.get('WMEM','3GB')}'; set threads={E.get('WTHREADS','2')}; set preserve_insertion_order=false; set temp_directory='{D}/tmp/w{u}'")
    if FLAT is None:
        FLAT = set(c.execute(f"select distinct npi, ins, net, v from read_parquet('{D}/flat/*.parquet')").fetchall())
    src = f"read_parquet('{D}/xpart/bucket={k}/*.parquet')"
    if sp is not None: src = f"(select * from {src} where hash(code) % {NB * SPLIT} = {k + NB * sp})"
    if SORTV in ('2', '3'):
        c.execute("create temp table pn as select unnest(?::varchar[]) npi, unnest(range(?::bigint))::int pi", [npis, len(npis)])
        c.execute("create temp table dn as select unnest(?::varchar[]) dt, unnest(range(?::bigint))::int di", [dates, len(dates)])
        c.execute("create temp table un as select unnest(?::varchar[]) url, unnest(range(?::bigint))::int ui", [urls, len(urls)])
        c.execute("create temp table nn as select unnest(?::varchar[]) ins, unnest(?::varchar[]) net, unnest(range(?::bigint))::int ni",
                  [[a_ for a_, _ in NETS2], [b_ for _, b_ in NETS2], len(NETS2)])
    MD = {(cd, fe): (m, n) for cd, fe, m, n in c.execute(f"select code, fee, approx_quantile(v, 0.5), count(*) from {src} where t=0 and v>0 and modi='' group by all").fetchall()}
    if SORTV == '3':
        return work3(u, c, src, MD)
    if SORTV == '2':
        cur = c.execute(f"""select x.code, pn.pi, nn.ni, x.fee, x.t, x.v, x.tin, x.modi, x.st, x.nt, dn.di, un.ui from {src} x
                       left join pn on pn.npi = x.npi left join nn on nn.ins = x.ins and nn.net = x.net
                       left join dn on dn.dt = x.dt left join un on un.url = x.url
                       order by x.code, pn.pi, nn.ni, x.fee, x.t, x.v, x.modi, x.tin, x.st, x.nt, dn.di, un.ui""")
    else:
        cur = c.execute(f"""select code, npi, ins, net, fee, t, v, tin, modi, st, nt, dt, url from {src}
                       order by code, npi, ins, net, fee, t, v, modi, tin, st, nt, dt, url""")
    summ, scp = {}, {}; nx = 0
    pool = ThreadPoolExecutor(8); futs = []
    def put(code, f):
        for kk, rows in f.items():
            cap = 0 if KIND[int(kk)] == 'P' else 4
            for r in rows: r[8] = r[8][:cap]
        summ[code] = sum(len(v) for v in f.values())
        body = base64.b64encode(gzip.compress(json.dumps({'f': f}, separators=(',', ':')).encode(), 6))
        futs.append(pool.submit(s3.put_object, Bucket=B, Key=f'{TOUT}t/{code}.txt', Body=body, ContentType='text/plain'))
    D0 = didx.get('', 0); U0 = uidx.get('', 0)
    def emit(f, g, rows):
        code, npi, ins, net, fee, t = g
        nk = f'{ins}|{net}'; n = nidx[nk]; scp.setdefault(nk, set()).add(code)
        zeros = sum(1 for r in rows if r[0] == 0); pos = [r for r in rows if r[0] > 0]
        if pos:
            h = next((r for r in pos if not r[2]), pos[0])
            v, tin, modi, st, nt, dt, url = h
            isflat = fee == 0 and t == 0 and not modi and (npi, ins, net, v) in FLAT
            m = MD.get((code, fee)); islow = bool(m and m[1] >= 5 and t == 0 and v < 0.2 * m[0])
            ishigh = bool(m and m[1] >= 5 and t == 0 and v > 20 * m[0])   # unusually high: over 20x the median, likely a placeholder (e.g. 59999.99)
            rest = [r for r in pos[:9] if r is not h]
            others = [[float(r[0]), lab(r[2], r[3], r[4], r[1], tin)] for r in rest[:8]]
            if SORTV == '2': di_, ui_ = (D0 if dt is None else dt), (U0 if url is None else url)
            else: di_, ui_ = didx.get(dt or '', 0), uidx.get(url or '', 0)
            row = [n, fee, t, float(v), (1 if isflat else 0) | (2 if islow else 0) | (8 if ishigh else 0), di_, ui_, len(pos) - 1, others, zeros, lab(modi, st, nt, tin, tin)]
        else:
            r0 = rows[0]
            if SORTV == '2': di_, ui_ = (D0 if r0[5] is None else r0[5]), (U0 if r0[6] is None else r0[6])
            else: di_, ui_ = didx.get(r0[5] or '', 0), uidx.get(r0[6] or '', 0)
            row = [n, fee, t, 0, 4, di_, ui_, 0, [], zeros, -1]
        f.setdefault(str(pidx[npi]), []).append(row)
    curcode, f, g0, grp = None, {}, None, []; prev = None
    while True:
        batch = cur.fetchmany(200000)
        if not batch: break
        nx += len(batch)
        for rw in batch:
            if rw == prev: continue
            prev = rw
            if SORTV == '2':
                code, pi, ni, fee, t, v, tin, modi, st, nt, dt, url = rw
                npi = npis[pi]; ins, net = NETS2[ni]
            else: code, npi, ins, net, fee, t, v, tin, modi, st, nt, dt, url = rw
            g = (code, npi, ins, net, fee, t)
            if g != g0:
                if g0: emit(f, g0, grp)
                if code != curcode:
                    if curcode: put(curcode, f)
                    curcode, f = code, {}
                g0, grp = g, []
            grp.append((v, tin, modi or '', st or '', nt or '', dt, url))
    if g0: emit(f, g0, grp)
    if curcode: put(curcode, f)
    for fu in futs: fu.result()
    c.close(); finish_dirs(u); shutil.rmtree(D / f'tmp/w{u}', ignore_errors=True)
    res = (u, nx, summ, {kk: sorted(v) for kk, v in scp.items()})
    s3.put_object(Bucket=B, Key=f'{WK}B/{u}.json', Body=json.dumps(res).encode())
    return res
def finish_dirs(u):
    k, sp = unit_parts(u)
    if sp is None: shutil.rmtree(D / f'xpart/bucket={k}', ignore_errors=True)   # pieces share bucket k's files: keep them
def work3(u, c, src, MD):
    """Stage B, SORTV=3: DuckDB does the per-row work (dedupe, order, $0 count, headline = lowest positive rate with no
    modifier else lowest positive, up to 8 other rates) and returns one row per provider/network/fee/type group; Python
    only formats them. Same output as SORTV=2 (tested Oct 12, 2026), about 5x fewer rows cross into Python."""
    c.execute("create temp table pk as select unnest(range(?::bigint))::int pi, unnest(?::varchar[]) kind", [len(KIND), KIND])
    nx = c.execute(f"select count(*) from {src}").fetchone()[0]
    cur = c.execute(f"""
      with d as (select distinct x.code, pn.pi, nn.ni, x.fee, x.t, x.v, x.tin, x.modi, x.st, x.nt, dn.di, un.ui from {src} x
                 left join pn on pn.npi = x.npi left join nn on nn.ins = x.ins and nn.net = x.net
                 left join dn on dn.dt = x.dt left join un on un.url = x.url),
      r as (select d.*, pk.kind <> 'P' keep,
                   row_number() over (partition by code, pi, ni, fee, t, v > 0 order by v, modi, tin, st, nt, di, ui) rp
            from d join pk using (pi))
      select code, pi, ni, fee, t, count(*) filter (where v = 0) zeros, count(*) filter (where v > 0) npos,
             arg_min(struct_pack(v := v, tin := tin, modi := modi, st := st, nt := nt, di := di, ui := ui, rp := rp),
                     case when v > 0 and modi = '' then rp when v > 0 then 1e8 + rp else 2e8 + rp end) h,
             list(struct_pack(v := v, tin := tin, modi := modi, st := st, nt := nt, rp := rp) order by rp) filter (where keep and v > 0 and rp <= 9) ot
      from r group by all order by code, pi, ni, fee, t""")
    summ, scp = {}, {}
    pool = ThreadPoolExecutor(8); futs = []
    D0 = didx.get('', 0); U0 = uidx.get('', 0); LC = {}
    def labc(modi, st, nt, other):
        key = (modi, st, nt, other)
        if key not in LC:
            x = label_str(modi or '', st or '', nt or '', other); LC[key] = lidx.get(x, -1) if x else -1
        return LC[key]
    def put(code, f):
        for kk, rows in f.items():
            cap = 0 if KIND[int(kk)] == 'P' else 4
            for r in rows: r[8] = r[8][:cap]
        summ[code] = sum(len(v) for v in f.values())
        body = base64.b64encode(gzip.compress(json.dumps({'f': f}, separators=(',', ':')).encode(), 6))
        futs.append(pool.submit(s3.put_object, Bucket=B, Key=f'{TOUT}t/{code}.txt', Body=body, ContentType='text/plain'))
    curcode, f = None, {}
    while True:
        batch = cur.fetchmany(100000)
        if not batch: break
        for code, pi, ni, fee, t, zeros, npos, h, ot in batch:
            v, tin, modi, st, nt, di, ui, hrp = h['v'], h['tin'], h['modi'], h['st'], h['nt'], h['di'], h['ui'], h['rp']
            if code != curcode:
                if curcode: put(curcode, f)
                curcode, f = code, {}
            ins, net = NETS2[ni]; nk = f'{ins}|{net}'; n = nidx[nk]; scp.setdefault(nk, set()).add(code)
            di_, ui_ = (D0 if di is None else di), (U0 if ui is None else ui)
            if npos:
                isflat = fee == 0 and t == 0 and not modi and (npis[pi], ins, net, v) in FLAT
                m = MD.get((code, fee)); islow = bool(m and m[1] >= 5 and t == 0 and v < 0.2 * m[0])
                ishigh = bool(m and m[1] >= 5 and t == 0 and v > 20 * m[0])   # unusually high: over 20x the median, likely a placeholder (e.g. 59999.99)
                others = [[float(o_['v']), labc(o_['modi'], o_['st'], o_['nt'], o_['tin'] != tin)] for o_ in [o_ for o_ in (ot or []) if o_['rp'] != hrp][:8]]
                row = [n, fee, t, float(v), (1 if isflat else 0) | (2 if islow else 0) | (8 if ishigh else 0), di_, ui_, npos - 1, others, zeros, labc(modi, st, nt, False)]
            else:
                row = [n, fee, t, 0, 4, di_, ui_, 0, [], zeros, -1]
            f.setdefault(str(pi), []).append(row)
    if curcode: put(curcode, f)
    for fu in futs: fu.result()
    c.close(); finish_dirs(u); shutil.rmtree(D / f'tmp/w{u}', ignore_errors=True)
    res = (u, nx, summ, {kk: sorted(v) for kk, v in scp.items()})
    s3.put_object(Bucket=B, Key=f'{WK}B/{u}.json', Body=json.dumps(res).encode())
    return res
# ---------- Stage B: buckets in parallel worker processes ----------
import multiprocessing as mp
summary, scope = {}, {}
buckets = sorted(int(p_.rsplit('=', 1)[1]) for p_ in glob.glob(f'{D}/xpart/bucket=*'))
if E.get('NOXPART'): buckets = list(range(NB))
done_units = set()
for k_, _ in ls(WK + 'B/'):
    kb, nx_, summ_, scp_ = json.loads(s3.get_object(Bucket=B, Key=k_)['Body'].read())
    done_units.add(str(kb))
    summary.update(summ_)
    for kk, v in scp_.items(): scope.setdefault(kk, set()).update(v)
def plan_units(buckets, done_units, split):
    """Whole buckets not yet done; with split>1, the pieces of each not-done bucket that aren't done yet."""
    out = []
    for b in buckets:
        if str(b) in done_units: continue
        if split > 1: out += [f'{b}_{s_}' for s_ in range(split) if f'{b}_{s_}' not in done_units]
        else: out.append(b)
    return out
def covered(done_units, nb, split):
    """Buckets fully done: whole, or all `split` pieces present."""
    return sum(1 for b in range(nb) if str(b) in done_units or (split > 1 and all(f'{b}_{s_}' in done_units for s_ in range(split))))
buckets = plan_units(buckets, done_units, SPLIT)
if E.get('BONLY'): buckets = [b for b in buckets if str(b) in E['BONLY'].split(',')]   # testing: just these buckets
if E.get('BORDER') == 'desc': buckets = buckets[::-1]
h_ = len(buckets) // 2   # 3rd/4th machines start in the middle and work outward; done buckets are skipped in work()
if E.get('BORDER') == 'mid': buckets = buckets[h_:] + buckets[:h_]
if E.get('BORDER') == 'middesc': buckets = buckets[:h_][::-1] + buckets[h_:][::-1]
if E.get('BSTART'): s_ = int(E['BSTART']); buckets = [b for b in buckets if unit_parts(b)[0] >= s_] + [b for b in buckets if unit_parts(b)[0] < s_]   # extra machines: start at a chosen bucket
if not buckets: log('all buckets already done')
log('stage B', len(buckets), 'buckets to do', len(summary), 'codes already done')
con.close()
# Oct 12, 2026: when a worker is killed (e.g. for memory), the pool starts a new one but the lost part never returns,
# so the machine waits forever (three Austin machines sat silent for an hour with every part already done). Watchdog: if no
# part finishes for STALL_MIN minutes (default 60, and at least 3x the slowest part so far), exit with an error so the
# machine's retry loop restarts this script; it skips finished parts and writes embed.json when all are in.
import multiprocessing.context as mpc
STALL = float(E.get('STALL_MIN', '60')) * 60
with mp.get_context('fork').Pool(int(E.get('WORKERS', '2')), maxtasksperchild=int(E.get('MAXTASKS', '4'))) as P:
    it, done, last, slowest = P.imap_unordered(work, buckets), 0, time.time(), 0.0
    while done < len(buckets):
        try: k, nx, summ, scp = it.next(timeout=60)
        except mpc.TimeoutError:
            if time.time() - last > max(STALL, 3 * slowest):
                log(f'no part finished for {round((time.time() - last) / 60)} min; a worker likely died. Restarting.'); LOGFLUSH(); P.terminate(); sys.exit(5)
            continue
        done += 1; slowest = max(slowest, time.time() - last); last = time.time()
        summary.update(summ)
        for kk, v in scp.items(): scope.setdefault(kk, set()).update(v)
        log(f'B {done}/{len(buckets)}', f'bucket {k}', f'{nx:,} rows', len(summary), 'codes so far')
# Oct 15 (BCLAIM): when this machine's list is done but units other machines claimed aren't finished yet, wait and take
# over any whose claim went stale (machine died) instead of exiting, so the last pieces are never left behind.
if E.get('BCLAIM'):
    base_ = list(range(NB)) if E.get('NOXPART') else sorted(int(p_.rsplit('=', 1)[1]) for p_ in glob.glob(f'{D}/xpart/bucket=*'))
    while True:
        left_ = plan_units(base_, {k_.rsplit('/', 1)[1][:-5] for k_, _ in ls(WK + 'B/') if k_.endswith('.json')}, SPLIT)
        if not left_: break
        log(f'{len(left_)} units not finished yet (claimed by other machines); checking again in 5 min'); LOGFLUSH(); time.sleep(300)
        with mp.get_context('fork').Pool(int(E.get('WORKERS', '2')), maxtasksperchild=int(E.get('MAXTASKS', '4'))) as P2:
            for r_ in P2.imap_unordered(work, left_):
                if r_[1]: log('took over', r_[0], f'{r_[1]:,} rows')
# another machine may have finished buckets meanwhile: reload them all, and write embed only when every bucket is in
summary, scope, done_units = {}, {}, set()
for k_, _ in ls(WK + 'B/'):
    kb, nx_, summ_, scp_ = json.loads(s3.get_object(Bucket=B, Key=k_)['Body'].read()); done_units.add(str(kb))
    summary.update(summ_)
    for kk, v in scp_.items(): scope.setdefault(kk, set()).update(v)
nb = covered(done_units, NB, SPLIT)
if nb < NB: log(f'{nb}/{NB} buckets in; another machine will write embed.json'); LOGFLUSH(); sys.exit(0)
if not summary: log('ERROR 0 codes across all buckets; not writing embed.json'); LOGFLUSH(); sys.exit(0)
codes = {}
for c_, n_ in summary.items():
    t_, nm = NAMES.get(c_, ('CPT', ''))
    if c_ in FEAT: codes[c_] = {'name': FEAT[c_]['plain_name'], 'cat': FEAT[c_]['category'], 'type': FEAT[c_]['code_type'], 'n': n_, 'f': None}
    else: codes[c_] = {'name': (nm or f'{t_} {c_}').strip(), 'cat': 'description as written in the insurer file', 'type': t_, 'n': n_, 'f': None, 'd': 1}
embed = {'codes': codes, 'fac': ptab, 'nets': nets, 'dates': dates, 'urls': urls, 'labs': labs,
         'scope': {k_: sorted(v) for k_, v in scope.items() if len(v) < len(codes) - 20}}
s3.put_object(Bucket=B, Key=TOUT + 'embed.json', Body=json.dumps(embed, separators=(',', ':')).encode())
s3.put_object(Bucket=B, Key=TOUT + 'npis.json', Body=json.dumps(npis).encode())
log('DONE', len(codes), 'codes', len(ptab), 'providers', len(nets), 'networks', sum(summary.values()), 'lines')
s3.put_object(Bucket=B, Key=OUTP + 'log.txt', Body='\n'.join(LOG).encode())
