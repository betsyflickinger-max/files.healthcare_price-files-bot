"""Medicare's facility rate for each hospital and surgery center, after CMS's local wage adjustment (CY2026).

Writes R2 site/med_local/2026.json: {"src": {...}, "npi": {npi: [kind, wage_index, ccn, cbsa]}} for hospitals ("H") and
surgery centers ("A"). procedure_pages.py multiplies the national OPPS / ASC rate by that provider's factor:
  hospital outpatient (OPPS): national x (0.60 x wage index + 0.40); the CY2026 OPPS uses the FY2026 IPPS wage index
      "including all reclassifications" (CY2026 OPPS final rule) -> FY2026 IPPS Final Rule Impact File, column "FY 2026 Wage Index"
      (after reclassification, floors, the Sec. 505 out-migration adjustment, the 5% cap and the low-wage transition).
  surgery centers (ASC): national x (0.50 x wage index + 0.50) (MedPAC ASC Payment Basics, Oct 2026); ASCs use the
      pre-floor, pre-reclassified hospital wage index of the CBSA where they are -> FY2026 IPPS Table 3, the pre-floor
      column where CMS gives one, otherwise "Wage Index".
Matching an NPI to its Medicare facility (CCN): the NPI's practice address in NPPES (Sept 2026) and the facility's address in
CMS's Provider of Services file (Q3 2026) must share the ZIP and the street number and street name. A hospital NPI matches
hospitals only, a surgery-center NPI surgery centers only. More than one possible match with different wage indexes, or none,
means no local figure: the page then shows only the national rate. Nothing is estimated.

  python site/med_local.py WORKDIR          (needs R2_* env; downloads the CMS files into WORKDIR)
"""
import csv
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from collections import defaultdict

SRC = {
    'impact': ['FY 2026 IPPS Final Rule Impact File', 'https://www.cms.gov/files/zip/fy2026-ipps-fr-impact-file.zip'],
    'tables': ['FY 2026 IPPS Final Rule Tables 2, 3, 4A, 4B', 'https://www.cms.gov/files/zip/fy2026-ipps-fr-tables-2-3-4a-4b.zip'],
    'pos_h': ['Provider of Services file, hospitals, Q3 2026',
              'https://data.cms.gov/sites/default/files/2026-10/e5a8afbb-a1f4-4d3b-bdb9-3968e194da0e/Hospital_and_other.DATA.Q3_2026.csv'],
    'pos_a': ['Provider of Services file (iQIES), surgery centers, Q3 2026',
              'https://data.cms.gov/sites/default/files/2026-10/d7e32873-6bf0-4719-9048-376972900d5c/POS_iQIES.DATA.Q3_2026.csv'],
    'rule_opps': ['CY 2026 OPPS final rule: FY2026 IPPS wage index incl. reclassifications, 60% labor share',
                  'https://www.team-iha.org/getmedia/0ac1a3dd-fdba-4a75-b218-1801387c9720/CY-2026-Medicare-OPPS-FR-Rule-Summary.pdf?ext=.pdf'],
    'rule_asc': ['MedPAC ASC Payment Basics (Oct 2026): labor and non-labor portions 50% each',
                 'https://www.medpac.gov/wp-content/uploads/2026/10/MedPAC_Payment_Basics_26_ASC_FINAL_SEC.pdf'],
}
NPI_SCOPE = 'data/scope/'   # <st>_npis_all.parquet: NPPES rows (npi, taxonomy_1, address, zip5) per state


def fetch(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=600) as r, open(path, 'wb') as f:
            f.write(r.read())
    return path


def street_key(adr, zip5):
    a = re.sub(r'[^A-Z0-9 ]', ' ', (adr or '').upper())
    t = [x for x in a.split() if x not in ('N', 'S', 'E', 'W', 'NORTH', 'SOUTH', 'EAST', 'WEST')]
    if len(t) < 2 or not t[0][0].isdigit():
        return None
    return (str(zip5)[:5], t[0], t[1][:6])


def main(work):
    os.makedirs(work, exist_ok=True)
    # wage indexes
    z = zipfile.ZipFile(fetch(SRC['impact'][1], os.path.join(work, 'impact.zip')))
    txt = z.read(next(n for n in z.namelist() if n.endswith('Impact File.txt'))).decode('latin-1').splitlines()
    h = txt[1].split('\t')
    iw = h.index('FY 2026 Wage Index')
    wi_ccn = {l.split('\t')[0].strip().zfill(6): float(l.split('\t')[iw]) for l in txt[2:] if l.split('\t')[0].strip() and len(l.split('\t')) > iw}
    z = zipfile.ZipFile(fetch(SRC['tables'][1], os.path.join(work, 'tables.zip')))
    t3 = z.read(next(n for n in z.namelist() if n.endswith('Tables 3.txt'))).decode('latin-1').splitlines()
    h = [x.strip('"') for x in t3[1].split('\t')]
    iw, ipre = h.index('Wage Index'), next(i for i, x in enumerate(h) if x.startswith('3Pre-Frontier'))
    wi_cbsa = {}
    for l in t3[2:]:
        c = [x.strip('"') for x in l.split('\t')]
        v = (c[ipre] if len(c) > ipre else '') or (c[iw] if len(c) > iw else '')
        if c[0] and re.fullmatch(r'[\d.]+', v or ''):
            wi_cbsa[c[0]] = float(v)
    print(f'wage indexes: {len(wi_ccn):,} IPPS hospitals, {len(wi_cbsa):,} CBSAs', flush=True)
    # Medicare facilities by street address
    fac = defaultdict(list)   # key -> [(kind, ccn, cbsa)]
    r = csv.reader(open(fetch(SRC['pos_h'][1], os.path.join(work, 'pos_h.csv')), encoding='latin-1'))
    h = next(r)
    I = {k: h.index(k) for k in ('PRVDR_NUM', 'ST_ADR', 'ZIP_CD', 'CBSA_CD', 'PGM_TRMNTN_CD', 'PRVDR_CTGRY_CD')}
    for row in r:
        if row[I['PRVDR_CTGRY_CD']] == '01' and row[I['PGM_TRMNTN_CD']].strip() == '00':
            k = street_key(row[I['ST_ADR']], row[I['ZIP_CD']])
            if k:
                fac[k].append(('H', row[I['PRVDR_NUM']].strip(), row[I['CBSA_CD']].strip()))
    r = csv.reader(open(fetch(SRC['pos_a'][1], os.path.join(work, 'pos_a.csv')), encoding='latin-1'))
    h = next(r)
    I = {k: h.index(k) for k in ('prvdr_num', 'st_adr', 'zip_cd', 'cbsa_cd', 'pgm_trmntn_cd', 'prvdr_type_id')}
    for row in r:
        if row[I['prvdr_type_id']] == '11' and row[I['pgm_trmntn_cd']].strip() == '00':
            k = street_key(row[I['st_adr']], row[I['zip_cd']])
            if k:
                fac[k].append(('A', row[I['prvdr_num']].strip(), row[I['cbsa_cd']].strip()))
    print(f'Medicare facilities by address: {len(fac):,}', flush=True)
    # NPIs (hospital and surgery-center taxonomies) -> facility
    import duckdb
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bot'))
    import store
    s3, B = store.r2()
    keys = [o['Key'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=NPI_SCOPE)
            for o in pg.get('Contents', []) if re.search(r'/[a-z]{2}_npis_all\.parquet$', o['Key'])]
    out, why = {}, defaultdict(int)
    con = duckdb.connect()
    for k in keys:
        p = os.path.join(work, os.path.basename(k))
        if not os.path.exists(p):
            s3.download_file(B, k, p)
        rows = con.execute(f"""select npi, taxonomy_1, address, zip5 from read_parquet('{p}')
                               where taxonomy_1 like '28%' or taxonomy_1 like '27%' or taxonomy_1 = '261QA1903X'""").fetchall()
        for npi, tax, adr, z5 in rows:
            kind = 'A' if tax == '261QA1903X' else 'H'
            key = street_key(adr, z5)
            cands = [c for c in fac.get(key, []) if c[0] == kind] if key else []
            if not cands:
                why['no address match'] += 1
                continue
            vals = set()
            for _, ccn, cbsa in cands:
                if kind == 'H':
                    w = wi_ccn.get(ccn.zfill(6))
                    vals.add((round(w, 4), ccn, cbsa) if w is not None else None)
                else:
                    w = wi_cbsa.get(cbsa[3:] if re.fullmatch(r'999\d\d', cbsa) else cbsa)   # POS rural '99945' = Table 3 '45'
                    vals.add((round(w, 4), ccn, cbsa) if w is not None else None)
            vals.discard(None)
            if not vals:
                why['facility not paid under the wage-index file (e.g. critical access, children\'s, cancer)' if kind == 'H' else 'CBSA not in Table 3'] += 1
                continue
            if len({v[0] for v in vals}) > 1:
                why['more than one facility at the address'] += 1
                continue
            v = sorted(vals)[0]
            out[npi] = [kind, v[0], v[1], v[2]]
    print(f'mapped {len(out):,} NPIs; not mapped: {dict(why)}', flush=True)
    doc = {'src': SRC, 'built': __import__('datetime').date.today().isoformat(), 'npi': out}
    s3.put_object(Bucket=B, Key='site/med_local/2026.json', Body=json.dumps(doc, separators=(',', ':')).encode(), ContentType='application/json')
    print('wrote R2 site/med_local/2026.json', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
