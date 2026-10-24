"""Hand-check of the match pilot's biggest disagreements against the original files (Betsy OK'd Oct 24, 2026, 3:38am ET),
before anything goes on the Price File Watch.

For each case in reports/match-pilot/<month>/handcheck/cases.json (a row of the pilot's pairs.csv, picked by
hospital / insurer / code / prices):
  hospital side  every field of the cited row (data/hosp_every/rows/<sha16>.parquet, the parsed copy of the file), the
                 original line(s) from the raw file in R2 (raw_key, CSV files), and every other row in the file for the
                 same code and insurer
  insurer side   every row in the insurer's table (data/full/rates/ or history/insurers/, every field the reader keeps:
                 negotiated_type, negotiation_arrangement, billing_class, setting, service_code, modifier,
                 additional_information, expiration_date, NPI/TIN...) for that NPI and code, and its network name(s)
Output: <dir>/case_<n>.json and <dir>/sources.md (also printed). Verdicts are written by hand afterwards.
Env: R2_*; [DIR=reports/match-pilot/<YYYY-MM>/handcheck]."""
import csv, io, json, os, re, sys, time
import boto3, duckdb

E = os.environ
HERE = os.path.dirname(os.path.abspath(__file__))
g = lambda k: ''.join(E[k].split())
s3 = boto3.client('s3', endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                  aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name='auto')
B = g('R2_BUCKET')
D = E.get('DIR') or f"reports/match-pilot/{time.strftime('%Y-%m')}/handcheck"
W = E.get('WORK', '/tmp/hc'); os.makedirs(W, exist_ok=True)
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def getj(k): return json.loads(s3.get_object(Bucket=B, Key=k)['Body'].read())
def ls(pfx):
    out = []
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pfx): out += [(o['Key'], o['Size']) for o in pg.get('Contents', [])]
    return out
def stem(name):
    for ext in ('.gz', '.json', '.zip', '.7z'):
        if name.endswith(ext): name = name[:-len(ext)]
    return name[:180]

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute(f"CREATE SECRET r2 (TYPE R2, KEY_ID '{g('R2_ACCESS_KEY_ID')}', SECRET '{g('R2_SECRET_ACCESS_KEY')}', ACCOUNT_ID '{g('R2_ACCOUNT_ID')}')")
def q(sql, *a):
    cur = con.execute(sql, list(a)); cols = [c[0] for c in cur.description]
    return [dict(zip(cols, [str(x) if x is not None else None for x in r])) for r in cur.fetchall()]

cases = json.load(open(f'{D}/cases.json'))
pairs = list(csv.DictReader(open(f'{D}/../pairs.csv', encoding='utf-8')))
BID = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
src = getj(f'site/builds/{BID}/hosp_index.json')['src']
log('cases', len(cases), '| build', BID)
RATE_KEYS = ls('data/full/rates/') + [x for x in ls('history/insurers/') if '/rates/' in x[0]]
log('insurer tables known (current + history):', len(RATE_KEYS))
INS_WORDS = {'UnitedHealthcare': "(payer_name ilike '%united%' or payer_name ilike '%uhc%' or plan_name ilike '%united%' or plan_name ilike '%uhc%')",
             'Aetna': "(payer_name ilike '%aetna%' or plan_name ilike '%aetna%')", 'Cigna': "(payer_name ilike '%cigna%' or plan_name ilike '%cigna%')",
             'BCBSTX': "(payer_name ilike '%blue%' or payer_name ilike '%bcbs%' or plan_name ilike '%blue%' or plan_name ilike '%bcbs%')"}

def raw_lines(raw_key, row, unit):
    """the original line(s) of a CSV hospital file: row = the line number the reader recorded (header counted)"""
    if not raw_key or 'json' in unit or raw_key.lower().endswith('.json.zst'): return {'note': 'JSON file: the fields above are the parsed entry'}
    try:
        n = int(row)
        sz = s3.head_object(Bucket=B, Key=raw_key)['ContentLength']
        if sz > 8e9: return {'note': f'raw file too big to stream here ({sz/1e9:.1f} GB)'}
        body = s3.get_object(Bucket=B, Key=raw_key)['Body']
        if raw_key.endswith('.zst'):
            import zstandard
            stream = zstandard.ZstdDecompressor().stream_reader(body)
        else: stream = body
        txt = io.TextIOWrapper(stream, encoding='utf-8', errors='replace', newline='')
        out, hdr = {}, []
        for i, l in enumerate(txt, 1):
            if i <= 3: hdr.append(l.rstrip('\r\n')[:3000])
            if n - 1 <= i <= n + 1: out[str(i)] = l.rstrip('\r\n')[:3000]
            if i > n + 1: break
        return {'raw_key': raw_key, 'first_lines': hdr, 'lines': out}
    except Exception as e: return {'note': 'raw line not read: ' + repr(e)[:200]}

md = [f'# Match pilot hand-check: original rows ({time.strftime("%b %d, %Y")})', '']
for k, c in enumerate(cases, 1):
    # the pilot row
    p = next((r for r in pairs if r['hospital'] == c['hospital'] and r['insurer'] == c['insurer'] and r['code'] == c['code']
              and (not c.get('hospital_price') or abs(float(r['hospital_price'] or 0) - c['hospital_price']) < 0.01)
              and (not c.get('insurer_price') or abs(float(r['insurer_price'] or 0) - c['insurer_price']) < 0.01)), None)
    if not p: log('case', k, 'not found in pairs.csv', c); continue
    out = {'case': k, 'label': c.get('label', ''), 'pilot_row': p}
    # ---- hospital side
    cand = [x for x in src if x[4] == p['hospital_file'] and x[0] == p['hospital']] or [x for x in src if x[4] == p['hospital_file']]
    hs = []
    for x in cand:
        key = f'data/hosp_every/rows/{x[5]}.parquet'
        try:
            r = q(f"select * from read_parquet('r2://{B}/{key}') where source_row::varchar = ? and upper(trim(code)) = ?", p['hospital_row'], p['code'])
        except Exception as e: r = []; log('hospital rows not read', key, repr(e)[:120])
        if r:
            hs.append((x, key, r)); break
    if hs:
        x, key, r = hs[0]
        cited = [y for y in r if (y.get('negotiated_dollar') or '').replace(',', '').replace('$', '').strip() not in ('',) ] or r
        same = q(f"""select source_row, payer_name, plan_name, code, code_type, modifiers, setting, billing_class, methodology, negotiated_dollar,
             negotiated_percentage, negotiated_algorithm, gross_charge, discounted_cash, description, notes, payer_notes
             from read_parquet('r2://{B}/{key}') where upper(trim(code)) = ? and {INS_WORDS.get(p['insurer'], 'true')} order by try_cast(source_row as bigint) limit 60""", p['code'])
        out['hospital'] = {'file': x[4], 'name': x[0], 'sha16': x[5], 'unit': x[6], 'rows_key': key, 'cited_rows': r,
                           'raw': raw_lines(r[0].get('raw_key'), p['hospital_row'], x[6]), 'same_code_and_insurer': same}
        log('case', k, 'hospital rows', len(r), '| same code + insurer', len(same))
    else:
        out['hospital'] = {'note': 'cited row not found', 'candidates': [x[5] for x in cand]}
    # ---- insurer side
    st = stem(p['insurer_file'].rsplit('/', 1)[-1].split('?')[0])
    tk = [kk for kk, _ in RATE_KEYS if kk.rsplit('/', 1)[1].startswith(st[:60])]
    if not tk:   # name not derived from the file (catalog tables): try tables whose name shares the file's longest word run
        words = [w for w in re.split(r'[^A-Za-z0-9]+', st) if len(w) > 3]
        tk = [kk for kk, _ in RATE_KEYS if sum(w.lower() in kk.lower() for w in words) >= max(2, len(words) - 1)]
    ins_rows, used = [], []
    code_sql = "ltrim(trim(billing_code), '0')" if p['code'].isdigit() and len(p['code']) <= 3 else "upper(trim(billing_code))"
    for kk in tk[:12]:
        try:
            r = q(f"select * from read_parquet('r2://{B}/{kk}', union_by_name=true) where npi = ? and {code_sql} = ?", p['insurer_npi'], p['code'])
        except Exception as e: log('insurer table not read', kk, repr(e)[:150]); continue
        used.append(kk)
        if r:
            for y in r: y['_table'] = kk
            ins_rows += r
            try:
                mk = kk.replace('/rates/', '/membership/')
                m = q(f"select distinct network_name, tin from read_parquet('r2://{B}/{mk}') where npi = ?", p['insurer_npi'])
                for y in r: y['_networks_for_npi'] = m
            except Exception: pass
    out['insurer'] = {'file': p['insurer_file'], 'file_date': p['insurer_file_date'], 'network': p['insurer_network'], 'npi': p['insurer_npi'],
                      'tables_tried': tk[:12], 'tables_read': used, 'rows': ins_rows}
    log('case', k, 'insurer tables', len(tk), 'read', len(used), '| rows for NPI + code', len(ins_rows))
    json.dump(out, open(f'{D}/case_{k:02d}.json', 'w'), indent=1)
    # ---- summary lines
    md += [f"## Case {k}: {p['hospital']} × {p['insurer']} · {p['code']} {p['procedure']}", '',
           f"Pilot: hospital ${float(p['hospital_price']):,.2f} vs insurer ${float(p['insurer_price']):,.2f} ({p['result']})", '']
    h = out['hospital']
    for y in h.get('cited_rows', [])[:3]:
        md.append(f"- Hospital row {y.get('source_row')}: payer `{y.get('payer_name')}` · plan `{y.get('plan_name')}` · {y.get('code_type')} {y.get('code')} "
                  f"· setting `{y.get('setting')}` · class `{y.get('billing_class')}` · methodology `{y.get('methodology')}` · $ `{y.get('negotiated_dollar')}` "
                  f"· % `{y.get('negotiated_percentage')}` · algorithm `{(y.get('negotiated_algorithm') or '')[:120]}` · modifiers `{y.get('modifiers')}` "
                  f"· description `{(y.get('description') or '')[:90]}` · notes `{(y.get('notes') or '')[:120]}` / `{(y.get('payer_notes') or '')[:120]}` · file date {y.get('last_updated_on')}")
    md.append(f"- Same code + insurer in the hospital file: {len(h.get('same_code_and_insurer', []))} rows: " + '; '.join(
        f"{y['plan_name'][:40]} {y['setting']} {y['methodology']} ${y['negotiated_dollar']}{' %'+y['negotiated_percentage'] if y.get('negotiated_percentage') else ''}"
        for y in h.get('same_code_and_insurer', [])[:12]))
    if h.get('raw', {}).get('lines'): md.append(f"- Raw line {p['hospital_row']}: `{h['raw']['lines'].get(str(p['hospital_row']), '')[:600]}`")
    elif h.get('raw'): md.append(f"- Raw: {h['raw'].get('note')}")
    for y in ins_rows[:8]:
        md.append(f"- Insurer row: type `{y.get('negotiated_type')}` · arrangement `{y.get('negotiation_arrangement')}` · class `{y.get('billing_class')}` · setting `{y.get('setting')}` "
                  f"· {y.get('billing_code_type')} {y.get('billing_code')} · rate ${y.get('negotiated_rate')} · service codes `{(y.get('service_code') or '')[:60]}` "
                  f"· modifier `{y.get('billing_code_modifier')}` · additional info `{(y.get('additional_information') or '')[:150]}` · expires {y.get('expiration_date')} "
                  f"· NPI {y.get('npi')} TIN {y.get('tin')} ({y.get('tin_type')}) · table {y['_table'].rsplit('/', 1)[1]}")
    if not ins_rows: md.append(f"- Insurer rows: none found (tables tried: {len(tk)})")
    md.append('')
open(f'{D}/sources.md', 'w').write('\n'.join(md) + '\n')
print('\n'.join(md))
