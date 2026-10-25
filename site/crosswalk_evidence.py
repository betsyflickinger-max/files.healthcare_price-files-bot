"""Crosswalk evidence from DFW hospital price files (Oct 25, 2026; Betsy asked for a real-file check of the CPT -> DRG crosswalk).

Question: do hospitals themselves put a surgeon/procedure code (CPT/HCPCS) and a hospital-stay code (MS-DRG) on the SAME line of
their federally required price file? When they do, that line is real-world evidence of the pairing.

Input:  reference/cpt_drg_anesthesia_crosswalk.csv (the draft crosswalk); live DFW build's hospital files
        (site/every/CURRENT -> site/builds/<BID>/hosp_index.json src) and their rows data/hosp_every/rows/<sha16>.parquet
        (column all_codes = every code on the line, "TYPE:code;TYPE:code").
Output: OUT/evidence.csv  one row per crosswalk surgery: hospital files with a line listing the row's CPT and a DRG from its family,
                          which DRGs, an example line (hospital, description, row, link)
        OUT/pairs.csv     every DRG + CPT pair found on one line: hospital files, lines, example
        OUT/drg_names.csv the hospitals' own descriptions for each crosswalk DRG (most common first)
        OUT/summary.md
Nothing is averaged or estimated; counts are of hospital files and lines. Env: R2_*; [OUT]; [BID]."""
import csv, json, os, re, shutil, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
import boto3, duckdb

E = os.environ
HERE = os.path.dirname(os.path.abspath(__file__))
g = lambda k: ''.join(E[k].split())
s3 = boto3.client('s3', endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                  aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name='auto')
B = g('R2_BUCKET')
OUT = E.get('OUT') or f"reports/crosswalk-evidence/{time.strftime('%Y-%m')}"
W = E.get('WORK', '/tmp/xw')
os.makedirs(OUT, exist_ok=True); shutil.rmtree(W, ignore_errors=True); os.makedirs(W, exist_ok=True)
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def getj(k): return json.loads(s3.get_object(Bucket=B, Key=k)['Body'].read())

XW = list(csv.DictReader(open(f'{HERE}/../reference/cpt_drg_anesthesia_crosswalk.csv', encoding='utf-8')))
def drgs_in(text):
    s = set()
    for a, b in re.findall(r'\b(\d{3})(?:-(\d{3}))?\b', text or ''):
        for d in range(int(a), int(b or a) + 1): s.add(str(d))
    return s
for r in XW:
    r['_fam'] = drgs_in(r['usual_drg'] + ' ' + r['other_drgs_and_when'])
    r['_cpt'] = r['surgeon_cpt'].strip()
ALL_DRG = set().union(*[r['_fam'] for r in XW])

BID = E.get('BID') or s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
src = getj(f'site/builds/{BID}/hosp_index.json')['src']   # [name, city, other locations, last updated, url, sha16, unit]
log('build', BID, '|', len(src), 'hospital files')

con = duckdb.connect(f'{W}/x.duckdb')
con.execute("set memory_limit='10GB'; set preserve_insertion_order=false")
con.execute("create table lines (sha16 varchar, hospital varchar, url varchar, all_codes varchar, description varchar, source_row varchar, n bigint)")
con.execute("create table dname (sha16 varchar, drg varchar, description varchar, n bigint)")
con.execute("create table diag (sha16 varchar, pattern varchar, n bigint)")
no_allcodes = []
def dl(x):
    k = f'data/hosp_every/rows/{x[5]}.parquet'; p = f'{W}/h_{x[5]}.parquet'
    try: s3.download_file(B, k, p); return p
    except Exception as e: log('missing rows', x[0], repr(e)[:80]); return None
with ThreadPoolExecutor(8) as P:
    for x, p in zip(src, P.map(dl, src)):
        if not p: continue
        cols = {r[0] for r in con.execute(f"describe select * from read_parquet('{p}')").fetchall()}
        nm, url = x[0].replace("'", "''"), (x[4] or '').replace("'", "''")
        if 'all_codes' in cols:
            con.execute(f"""insert into lines select '{x[5]}', '{nm}', '{url}', all_codes, any_value(description), min(source_row::varchar), count(*)
                from read_parquet('{p}') where all_codes ilike '%drg%' and (all_codes ilike '%cpt:%' or all_codes ilike '%hcpcs:%') group by all_codes""")
        else: no_allcodes.append(x[0])
        con.execute(f"""insert into diag select '{x[5]}', regexp_replace(coalesce(all_codes,''), ':[^;]*', '', 'g'), count(*) from read_parquet('{p}')
            where code_type ilike '%drg%' group by 2""")
        dl_list = ','.join(f"'{d}'" for d in ALL_DRG)
        con.execute(f"""insert into dname select '{x[5]}', ltrim(code,'0'), upper(trim(description)), count(*) from read_parquet('{p}')
            where code_type ilike '%drg%' and ltrim(code,'0') in ({dl_list}) group by all""")
        os.remove(p)
log('lines with a DRG and a CPT/HCPCS together:', con.execute('select count(*) from lines').fetchone()[0], '| files without all_codes:', len(no_allcodes))

# ---- parse each line's codes into DRG x CPT pairs
pairs = defaultdict(lambda: {'files': set(), 'lines': 0, 'ex': None})
for sha, hosp, url, ac, desc, row, n in con.execute('select * from lines').fetchall():
    d_set, c_set = set(), set()
    for part in (ac or '').split(';'):
        if ':' not in part: continue
        t, c = part.split(':', 1); t, c = t.strip().upper(), c.strip().upper()
        if 'DRG' in t and c.lstrip('0').isdigit(): d_set.add(c.lstrip('0'))
        elif t in ('CPT', 'HCPCS') and re.fullmatch(r'[0-9A-Z]{5}', c[:5]): c_set.add(c[:5])
    for d in d_set:
        for c in c_set:
            k = pairs[(d, c)]; k['files'].add(sha); k['lines'] += n
            if not k['ex']: k['ex'] = (hosp, desc, row, url)
with open(f'{OUT}/pairs.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['drg', 'cpt_or_hcpcs', 'hospital_files', 'lines', 'example_hospital', 'example_description', 'example_row', 'example_file'])
    for (d, c), v in sorted(pairs.items(), key=lambda kv: -len(kv[1]['files'])):
        w.writerow([d, c, len(v['files']), v['lines'], *v['ex']])

# ---- per crosswalk row
ev = []
for r in XW:
    hits = {(d, c): v for (d, c), v in pairs.items() if c == r['_cpt'] and d in r['_fam']}
    files = set().union(*[v['files'] for v in hits.values()]) if hits else set()
    usual = r['usual_drg'].split(' ')[0]
    other_cpts = Counter()
    for (d, c), v in pairs.items():
        if d in r['_fam'] and c != r['_cpt']: other_cpts[c] += len(v['files'])
    ex = next(iter(hits.values()))['ex'] if hits else ('', '', '', '')
    ev.append(dict(surgery=r['surgery'], cpt=r['_cpt'], usual_drg=r['usual_drg'], hospital_files_pairing_cpt_with_family=len(files),
                   drgs_seen_with_this_cpt='|'.join(sorted({d for d, c in hits}, key=int)),
                   other_codes_on_same_drg_lines='|'.join(f'{c}:{n}' for c, n in other_cpts.most_common(8)),
                   example_hospital=ex[0], example_description=ex[1], example_row=ex[2], example_file=ex[3]))
with open(f'{OUT}/evidence.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, list(ev[0].keys())); w.writeheader(); w.writerows(ev)

dn = con.execute("select drg, description, count(distinct sha16) files, sum(n) lines from dname group by drg, description order by cast(drg as int), files desc").fetchall()
with open(f'{OUT}/drg_names.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['drg', 'hospital_description', 'hospital_files', 'lines']); w.writerows(dn)

dg = con.execute("select pattern, count(distinct sha16), sum(n) from diag group by pattern order by 2 desc limit 25").fetchall()
with open(f'{OUT}/drg_line_code_types.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['code_types_on_drg_lines', 'hospital_files', 'lines']); w.writerows(dg)
with open(f'{OUT}/summary.md', 'w') as f:
    f.write(f"# Crosswalk evidence from DFW hospital price files ({time.strftime('%Y-%m-%d')})\n\nBuild {BID}: {len(src)} hospital files; "
            f"{len(no_allcodes)} had no all_codes column. Lines listing a DRG and a CPT/HCPCS together: "
            f"{con.execute('select count(*) from lines').fetchone()[0]:,} distinct code sets; DRG+CPT pairs: {len(pairs):,}.\n\n"
            "| Surgery | CPT | Usual DRG | Hospital files pairing them | DRGs seen | Other codes on those DRG lines (files) |\n|---|---|---|---|---|---|\n")
    f.write("\n\nCode types that appear on hospitals' DRG lines (top patterns):\n\n| Code types on the line | Hospital files | Lines |\n|---|---|---|\n")
    for pat, nf, nl in dg: f.write(f"| {pat or '(blank)'} | {nf} | {nl:,} |\n")
    f.write("\n")
    for e in ev:
        f.write(f"| {e['surgery']} | {e['cpt']} | {e['usual_drg']} | {e['hospital_files_pairing_cpt_with_family']} | {e['drgs_seen_with_this_cpt']} | {e['other_codes_on_same_drg_lines'][:80]} |\n")
log('done', OUT)
