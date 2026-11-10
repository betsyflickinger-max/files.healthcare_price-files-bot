"""Hand-check sample for label d, "specialty mismatch" (Nov 9, 2026, Betsy OK'd: census first, 50-row check before any page shows it).

Draws doctor-fee lines at random from the published Price Finder pages (the 89 featured procedures), looks up each
clinician's specialty in the label d reference (reference/specialty/, utilization/build_specialty.py), and writes:
  - how many sampled doctor-fee lines have a specialty figure, and how many of those carry label d (share on live pages)
  - 50 labeled lines with the NPI Registry entry, for a person (or a fresh Claude) to judge: would this clinician really
    do this procedure? Answer in specialty_check.csv: plausible yes / no / can't tell, with a one-line note.
Same independence rule as the other audit layers: imports only audit/roundtrip.py (and evidence.npi_registry).

Output: reports/audit/<date>/specialty-check.md and specialty_check.csv. Usage: python audit/specialty_check.py [--lines 8000] [--n 50]
"""
import argparse, csv, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roundtrip as R      # noqa: E402
from evidence import npi_registry   # noqa: E402

MIN_TAX, MIN_CODE, MAX_SHARE = 200, 100, 0.002   # same as insurers/pipeline/rate_labels.py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lines', type=int, default=8000)
    ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--seed', type=int, default=int(R.TODAY.replace('-', '')) + 11)
    A = ap.parse_args()
    import duckdb
    rnd = random.Random(A.seed)
    W = '/tmp/spec-check'
    os.makedirs(W, exist_ok=True)
    for n in ('npi_taxonomy', 'taxonomy_n', 'code_n', 'code_taxonomy'):
        R.s3.download_file(R.B, f'reference/specialty/{n}.parquet', f'{W}/{n}.parquet')
    meta = json.loads(R.s3.get_object(Bucket=R.B, Key='reference/specialty/meta.json')['Body'].read())
    files = R.read_bundle()
    areas = json.loads(files['site/cities.json'])
    featured = [r['code'] for r in csv.DictReader(open(os.path.join(R.REPO, 'site', 'codes89.csv')))]
    ins, _ = R.sample(files, areas, A.lines, 0, rnd, featured)
    doc = [x for x in ins if x['fee'] == 'doctor' and str(x.get('npi') or '').isdigit()]
    con = duckdb.connect()
    con.execute('create table s (i int, npi varchar, code varchar)')
    con.executemany('insert into s values (?, ?, ?)', [(i, str(x['npi']), str(x['code']).upper()) for i, x in enumerate(doc)])
    rows = con.execute(f"""
        select s.i, st.taxonomy_1, tn.clinicians, cn.billers, coalesce(ct.billers, 0),
               tn.clinicians >= {MIN_TAX} and cn.billers >= {MIN_CODE} figure,
               tn.clinicians >= {MIN_TAX} and cn.billers >= {MIN_CODE} and coalesce(ct.billers, 0) <= {MAX_SHARE} * tn.clinicians
                   and not regexp_matches(s.code, '^99[2-4][0-9][0-9]$') d
        from s left join read_parquet('{W}/npi_taxonomy.parquet') st on st.npi = s.npi
        left join read_parquet('{W}/taxonomy_n.parquet') tn on tn.taxonomy_1 = st.taxonomy_1
        left join read_parquet('{W}/code_n.parquet') cn on cn.code = s.code
        left join read_parquet('{W}/code_taxonomy.parquet') ct on ct.code = s.code and ct.taxonomy_1 = st.taxonomy_1""").fetchall()
    with_fig = [r for r in rows if r[5]]
    hits = [r for r in rows if r[6]]
    rnd.shuffle(hits)
    by_area = {}
    pick = []
    for r in hits:   # spread over areas: at most 3 per area on the first pass
        a = doc[r[0]]['area']
        if by_area.get(a, 0) < 3:
            pick.append(r)
            by_area[a] = by_area.get(a, 0) + 1
    pick += [r for r in hits if r not in pick]
    pick = pick[:A.n]

    od = os.path.join(R.REPO, 'reports', 'audit', R.TODAY)
    os.makedirs(od, exist_ok=True)
    share = (len(hits) / len(with_fig)) if with_fig else 0
    md = [f'# Specialty-mismatch label (d): hand-check sample, {R.TODAY}', '',
          'Label only: "may never be used; unverified". Nothing is hidden or removed. Not shown on any page until this check is done.', '',
          f"Reference: Medicare physician + Medicaid professional records, data year {meta.get('data_year')}; "
          f"{meta.get('clinicians_with_records', 0):,} clinicians with records; {meta.get('specialties_used')} specialties with {MIN_TAX}+ "
          f"clinicians; {meta.get('codes_used'):,} codes with {MIN_CODE}+ billers. Rule: at most 1 in {round(1 / MAX_SHARE)} of the "
          'specialty\'s clinicians billed the code.', '',
          f'Sampled from the live pages: {len(ins):,} insurer lines, {len(doc):,} doctor-fee lines with an NPI, '
          f'{len(with_fig):,} with a specialty figure, **{len(hits):,} labeled ({share:.1%})**.', '',
          'For each line: would this clinician really do this procedure? Fill specialty_check.csv: plausible = yes / no / can\'t tell, '
          'note = one sentence. "No" means the label is right (rate likely never used); "yes" means the label is wrong.', '']
    with open(os.path.join(od, 'specialty_check.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'area', 'code', 'npi', 'taxonomy', 'specialty_billers', 'specialty_clinicians', 'plausible', 'note'])
        for k, r in enumerate(pick, 1):
            x = doc[r[0]]
            reg = npi_registry(x['npi'])
            md += [f"## S{k:02d} · {x['area']} · code {x['code']}", '',
                   f"- Provider on the page: {x['provider']} (NPI {x['npi']})",
                   f"- NPI Registry: {reg}",
                   f"- Taxonomy {r[1]}: {r[4]:,} of {r[2]:,} clinicians with this specialty billed {x['code']} "
                   f"(code billed by {r[3]:,} clinicians in all)",
                   f"- Rate: ${x['value']:,.2f} doctor fee, {x['net'].replace('|', ' / ')}; file date {x['file_date']}", '']
            w.writerow([f'S{k:02d}', x['area'], x['code'], x['npi'], r[1], r[4], r[2], '', ''])
    open(os.path.join(od, 'specialty-check.md'), 'w').write('\n'.join(md))
    print(f'{len(doc)} doctor-fee lines, {len(with_fig)} with a specialty figure, {len(hits)} labeled ({share:.1%}); wrote {len(pick)}', flush=True)


if __name__ == '__main__':
    main()
