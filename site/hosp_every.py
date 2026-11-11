"""Every-code extraction of DFW hospital price files (monthly site build; first run Oct 10, 2026). For each job: download raw .zst from R2,
decompress (strip BOM), parse with reader.py (CMS 45 CFR 180 CSV tall/wide + JSON) keeping EVERY CPT/HCPCS/MS-DRG
row, write rows to parquet and upload to R2 data/2026-10-10/hosp_every/rows/<sha16>.parquet. Resumable via done markers.

Nov 11, 2026 (hospital rows v2, docs/hospital-rows-v2.md):
  - storage goes through bot/store.py (R2 now, Backblaze after the move); the site bundle carries store.py next to this file
  - v2 rows (ROWS_VERSION=v2, or HPFX is the v2 folder in site/hosp_rows.json) also carry the 2026 allowed-amount fields
    p10_amount, p90_amount, allowed_count and the file's CMS template version (file_version), at the end. v1 rows (the live
    site's, the default) are written with exactly the same columns as before.
  - v2 runs stop between files while the hospital queue is on hold (bot/fleet/hold_hospitals.txt, the maintenance pause)
  - the per-file steps are functions (parse_to_csv, to_parquet) so tests can run them on small files without storage."""
import sys, os, re, json, csv, time, hashlib, zstandard, duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, '..', 'bot'), HERE):   # store.py: bot/ in the repo, next to this file in the site bundle
    if _p not in sys.path: sys.path.insert(0, _p)
src = open(f'{HERE}/reader.py').read().split('def main():')[0]
_argv = sys.argv
sys.argv = ['x', f'{HERE}/codes89.csv', 'x', f'{HERE}/out']
exec(src)
sys.argv = _argv
LINE_RE = re.compile(r'')   # pass every line
CODE5 = re.compile(r'^[0-9A-Z]{5}$')
HOLD = 'bot/fleet/hold_hospitals.txt'   # board/maintenance.py HOSPITAL_HOLD: machines check it between files
def match(codes):
    for c, t in codes:
        c, t = str(c).strip().upper(), str(t).strip().upper()
        if t in ('CPT', 'HCPCS') and CODE5.match(c[:5]) and (len(c) == 5 or not c[5:].isalnum()):
            return c[:5], t
        if t in ('MS-DRG', 'MSDRG') and c.lstrip('0').isdigit() and len(c.lstrip('0')) <= 3:
            return c.lstrip('0'), 'MS-DRG'
    return None
E = os.environ
def parse_codecols(path):
    """CSV with columns description, CPT, HCPCS, MS-DRG, ..., payer_name, plan_name, standard_charge, standard_charge_percent
    and no CMS header rows (Children's Health, Sept 2026). Line numbers count the header as line 1."""
    with open(path, encoding='utf-8', errors='replace', newline='') as fh:
        for n, r in enumerate(csv.DictReader(fh), 2):
            code = ct = None
            for col in ('CPT', 'HCPCS'):
                c = (r.get(col) or '').strip().upper()
                if CODE5.match(c[:5]) and (len(c) == 5 or not c[5:].isalnum()): code, ct = c[:5], col; break
            if not code:
                c = (r.get('MS-DRG') or '').strip().lstrip('0')
                if c.isdigit() and len(c) <= 3: code, ct = c, 'MS-DRG'
            if not code: continue
            yield dict(source_row=str(n), description=r.get('description', ''), code=code, code_type=ct, modifiers=r.get('modifiers', ''),
                       setting=r.get('setting', ''), billing_class=r.get('billing_class', ''), gross_charge=r.get('gross_charge', ''),
                       discounted_cash=r.get('discounted_cash', ''), min_charge=r.get('minimum', ''), max_charge=r.get('maximum', ''),
                       payer_name=r.get('payer_name', ''), plan_name=r.get('plan_name', ''), negotiated_dollar=r.get('standard_charge', ''),
                       negotiated_percentage=r.get('standard_charge_percent', ''), negotiated_algorithm=r.get('standard_charge_algorithm', ''),
                       methodology=r.get('methodology', ''), median_amount=r.get('50th_percentile', ''), notes=r.get('additional_generic_notes', ''),
                       payer_notes=r.get('additional_payer_notes', ''), hospital_name=E.get('HNAME_' + os.path.basename(path), ''),
                       p10_amount=r.get('10th_percentile', ''), p90_amount=r.get('90th_percentile', ''), allowed_count=r.get('count', ''))


def pick_parser(raw):
    parser = parse_json if is_json(raw) else parse_csv
    with open(raw, encoding='utf-8', errors='replace') as fh: first = fh.readline()
    cols = [x.strip().strip('"') for x in first.split(',')]
    if not is_json(raw) and 'CPT' in cols and 'payer_name' in cols and 'standard_charge' in cols: parser = parse_codecols
    return parser


def parse_to_csv(raw, j, sha, rows_csv, fields=None):
    """One decompressed hospital file -> rows CSV with `fields` (FIELDS = v1, the live site's; FIELDS_V2 = v2). Returns rows."""
    parser, c = pick_parser(raw), 0
    with open(rows_csv, 'w', newline='') as fo:
        w = csv.DictWriter(fo, fields or FIELDS, extrasaction='ignore'); w.writeheader()
        for row in parser(raw):
            w.writerow(dict(row, raw_key=j['key'], source_url=j['url'], sha256=sha, hospital_name=row.get('hospital_name') or j.get('name', ''))); c += 1
    return c


def to_parquet(rows_csv, pq):
    duckdb.sql(f"copy (select * from read_csv('{rows_csv}', all_varchar=true, header=true, max_line_size=20000000)) to '{pq}' (format parquet, compression zstd)")


def is_v2(pfx):
    if E.get('ROWS_VERSION') == 'v2': return True
    try:
        import hosp_rows
        return pfx.rstrip('/') == hosp_rows.v2_prefix().rstrip('/')
    except Exception:
        return False


def main():
    import store
    s3, B = store.r2()
    PFX = E.get('HPFX', 'data/hosp_every/')   # rows/<sha16>.parquet is a cache shared across months
    V2 = is_v2(PFX)
    fields = FIELDS_V2 if V2 else FIELDS
    print('rows', 'v2 (with the 2026 allowed-amount fields)' if V2 else 'v1', 'to', PFX, flush=True)
    jobs = json.loads(s3.get_object(Bucket=B, Key=E['JOBS_KEY'])['Body'].read()) if E.get('JOBS_KEY') else json.load(open(E.get('JOBS', f'{HERE}/jobs.json')))
    if E.get('SHARDS'): jobs = jobs[int(E.get('SHARD', '0'))::int(E['SHARDS'])]
    os.makedirs(f'{HERE}/out', exist_ok=True)
    done = {o['Key'].rsplit('/', 1)[1][:-5] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=PFX + 'done/') for o in pg.get('Contents', [])}
    logf = open(f'{HERE}/out/log.jsonl', 'a')
    for k, j in enumerate(jobs, 1):
        tag = j['id']
        if tag in done: continue
        if V2 and store.exists(s3, B, HOLD):
            print('hospital queue on hold (', HOLD, '): stopping between files; finished files stay done', flush=True)
            break
        t0 = time.time(); raw = f'{HERE}/out/f.raw'; rec = dict(j)
        try:
            s3.download_file(B, j['key'], raw + '.zst')
            h = hashlib.sha256()
            with open(raw + '.zst', 'rb') as fi, open(raw, 'wb') as fo2:
                r = zstandard.ZstdDecompressor().stream_reader(fi)
                while True:
                    ch = r.read(1 << 24)
                    if not ch: break
                    h.update(ch); fo2.write(ch)
            os.remove(raw + '.zst'); sha = h.hexdigest()
            with open(raw, 'rb') as fh: head = fh.read(3)
            if head == b'\xef\xbb\xbf':
                with open(raw, 'rb') as fi, open(raw + '.nb', 'wb') as fo3:
                    fi.seek(3)
                    while True:
                        ch = fi.read(1 << 24)
                        if not ch: break
                        fo3.write(ch)
                os.replace(raw + '.nb', raw)
            rows_csv = f'{HERE}/out/rows.csv'
            c = parse_to_csv(raw, j, sha, rows_csv, fields)
            os.remove(raw)
            pq = f'{HERE}/out/{tag}.parquet'
            to_parquet(rows_csv, pq)
            s3.upload_file(pq, B, PFX + f'rows/{tag}.parquet'); os.remove(pq); os.remove(rows_csv)
            s3.put_object(Bucket=B, Key=PFX + f'done/{tag}.done', Body=b'1')
            rec.update(ok=True, rows=c, secs=round(time.time() - t0), sha256=sha)
        except Exception as e:
            rec.update(ok=False, err=f'{type(e).__name__}: {str(e)[:300]}', secs=round(time.time() - t0))
            for p in (raw, raw + '.zst', raw + '.nb'):
                if os.path.exists(p): os.remove(p)
        logf.write(json.dumps(rec) + '\n'); logf.flush()
        s3.upload_file(f'{HERE}/out/log.jsonl', B, PFX + f"log_{E.get('SHARD','0')}.jsonl")
        print(k, len(jobs), rec.get('ok'), rec.get('rows'), rec.get('secs'), j['name'], flush=True)
    print('ALL DONE', flush=True)


if __name__ == '__main__':
    main()
