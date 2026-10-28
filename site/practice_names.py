"""Practice names for the practice view (Oct 18, 2026). A practice is the tax ID (TIN) its doctors bill under, and insurer
files never name it. Names come only from public records, in this order:
  'i' IRS: the tax ID is in the IRS list of tax-exempt organizations (eo1-eo4.csv, the legal owner of that tax ID).
  'b' both: an organization NPI listed under the same tax ID in the insurer files, AND the group most of these doctors are
      listed with in Medicare's clinician directory (CMS "Doctors and Clinicians" National Downloadable File) share a
      distinctive word. Two independent sources agreeing.
  'm' Medicare: more than half of the practice's doctors are listed with the same group in Medicare's directory, and no
      organization NPI under the tax ID says otherwise (when the two disagree, the practice gets no name).
  's' solo: one doctor; shown as the doctor.
  'n' no public name: the page says "Group of N doctors" and lists them.
Tested on Mississippi (Oct 18): the organization NPI alone disagreed with Medicare's directory 40% of the time, so it is
never used by itself.

  python practice_names.py sources   -> refresh R2 data/names/dac_npi_org.parquet and data/names/irs_eo.parquet
  name_all(prac_raw, ptab, npis, con) -> {practice id: [name, city, how, doctor ids]}  (used by every_code.py)
"""
import collections, os, re, sys

DAC_URL_META = 'https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/mj5m-pzi6'
IRS_URLS = [f'https://www.irs.gov/pub/irs-soi/eo{i}.csv' for i in (1, 2, 3, 4)]
K_DAC, K_IRS = 'data/names/dac_npi_org.parquet', 'data/names/irs_eo.parquet'
_W = re.compile(r'\b(llc|pllc|pa|inc|pc|ltd|of|the|and|corp|corporation|co|llp|lp)\b')
STOP = {'medical', 'health', 'center', 'clinic', 'clinics', 'group', 'services', 'physicians', 'associates', 'care',
        'state', 'hospital', 'regional', 'family', 'healthcare', 'practice', 'partners', 'specialists', 'physician'}


def words(s): return set(_W.sub('', re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())).split())
def sig(s): return {w for w in words(s) if w not in STOP and len(w) > 2}
def ein(t):
    d = re.sub(r'\D', '', t or '')
    return d if len(d) == 9 else None
def top1(c):
    """Most common item, ties broken by the item itself, so every machine names a practice the same way (Oct 21, 2026: two
    machines building Georgia disagreed on ~17 names because Counter.most_common breaks ties by insertion order, and that
    order came from set iteration, which changes with each process's string hashing)."""
    return min(c.items(), key=lambda kv: (-kv[1], str(kv[0]))) if c else None
def spell_key(name): return re.sub(r'[^a-z0-9]', '', (name or '').lower())
def same_spelling(prac):
    """One spelling per name (Oct 21, 2026, Betsy): "Northland Hearing Centers Inc", "..., Inc" and "..., Inc." differ only in
    punctuation, spacing or capitals, so every practice gets the spelling most of them use (ties: the longest, then A-Z).
    Different words (Inc vs LLC) stay as they are: those can be different legal companies. Changes prac in place."""
    by = collections.defaultdict(collections.Counter)
    for v in prac.values():
        if v[0] and v[2] != 's': by[spell_key(v[0])][v[0]] += 1
    pick = {k: min(c.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0] for k, c in by.items() if len(c) > 1}
    n = 0
    for v in prac.values():
        if v[0] and v[2] != 's' and (w := pick.get(spell_key(v[0]))) and w != v[0]: v[0] = w; n += 1
    return n
def same_spelling_fac(fac):
    """Same rule for the page's place list (D.fac: [name, city, kind]): organizations only (kinds G, A, H), never people.
    Oct 21, 2026: the Compare table's rows are organization NPIs, so "Northland Hearing Centers Inc / , Inc / , Inc." showed
    there even after the practice list was fixed. Changes fac in place; returns how many names changed."""
    by = collections.defaultdict(collections.Counter)
    for v in fac:
        if v and v[0] and len(v) > 2 and v[2] != 'P': by[spell_key(v[0])][v[0]] += 1
    pick = {k: min(c.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0] for k, c in by.items() if len(c) > 1}
    n = 0
    for v in fac:
        if v and v[0] and len(v) > 2 and v[2] != 'P' and (w := pick.get(spell_key(v[0]))) and w != v[0]: v[0] = w; n += 1
    return n
def merge_prac(base, add, pmap=None):
    """Oct 22, 2026: one practice table from two builds' tables (merge_build.py; requested codes). A practice is its tax ID
    (the same hashed id in every build), so the same id is the same practice: its doctors are combined (ADD's doctor ids
    renumbered through pmap). BASE's name stays unless BASE had none ('n') or only a solo doctor ('s') and ADD has a public
    name ('i', 'b', 'm'). A solo practice that gains doctors and has no public name becomes 'n'. Then one spelling per name."""
    out = {pid: [v[0], v[1], v[2], list(v[3])] for pid, v in (base or {}).items()}
    for pid, (nm, city, how, docs) in (add or {}).items():
        docs = sorted(pmap[i] for i in docs) if pmap is not None else sorted(docs)
        if pid not in out: out[pid] = [nm, city, how, docs]; continue
        b = out[pid]; u = sorted(set(b[3]) | set(docs))
        if b[2] in ('n', 's') and how in ('i', 'b', 'm'): b[0], b[2] = nm, how
        elif b[2] == 's' and len(u) > 1: b[0], b[2] = '', 'n'
        b[1] = b[1] or city; b[3] = u
    same_spelling(out)
    return out
def tidy(name):
    """IRS and CMS names are upper case: title-case them the way the page does provider names."""
    if not name or not name.isupper(): return name
    nm = name.title()
    for a, b in ((' Llc', ' LLC'), (' Pllc', ' PLLC'), (' Pa', ' PA'), (' Pc', ' PC'), (' Llp', ' LLP'), (' Lp', ' LP'), (' Md', ' MD'), (' Ms ', ' MS ')):
        nm = re.sub(re.escape(a) + r'\b', b, nm)
    return nm


def name_all(raw, ptab, npis, con, s3=None, bucket=None, workdir='/tmp'):
    """raw: {pid: {'d': doctor ids, 'o': Counter(org ids), 't': tax ID or None}}. Returns the embed 'prac' table."""
    dac, irs = {}, {}
    try:
        for k, p in ((K_DAC, f'{workdir}/dac.parquet'), (K_IRS, f'{workdir}/irs.parquet')):
            if s3 and not os.path.exists(p): s3.download_file(bucket, k, p)
        need = sorted({npis[i] for v in raw.values() for i in v['d']})
        con.execute('create or replace temp table need_ as select unnest(?::varchar[]) npi', [need])
        for n, org in con.execute(f"select d.npi, d.org from read_parquet('{workdir}/dac.parquet') d join need_ using (npi) order by 1, 2").fetchall():
            dac.setdefault(n, set()).add(org)
        eins = sorted({e for v in raw.values() for e in [ein(v.get('t'))] if e})
        con.execute('create or replace temp table eins_ as select unnest(?::varchar[]) ein', [eins])
        irs = dict(con.execute(f"select i.ein, min(i.nm) from read_parquet('{workdir}/irs.parquet') i join eins_ using (ein) group by 1").fetchall())
    except Exception as e:
        print('practice names: public name lists not available, using solo/no-name only:', repr(e)[:150], flush=True)
    out = {}
    for pid, v in raw.items():
        d = sorted(v['d']); cities = collections.Counter(ptab[i][1] for i in d if ptab[i][1])
        city = top1(cities)[0] if cities else ''
        orgs = v.get('o') or collections.Counter()
        org_name = ptab[top1(orgs)[0]][0] if orgs else ''
        med = collections.Counter(o for i in d for o in sorted(dac.get(npis[i], ())))
        top = top1(med)
        e = ein(v.get('t'))
        if len(d) == 1 and not (e and e in irs): out[pid] = [ptab[d[0]][0], ptab[d[0]][1], 's', d]
        elif e and e in irs: out[pid] = [tidy(irs[e]), city, 'i', d]
        elif org_name and top and sig(org_name) & sig(top[0]): out[pid] = [org_name, city, 'b', d]
        elif top and top[1] / len(d) > 0.5 and not org_name: out[pid] = [tidy(top[0]), city, 'm', d]   # an organization NPI that disagrees = conflicting sources: no name
        else: out[pid] = ['', city, 'n', d]
    same_spelling(out)
    return out


def refresh_sources():
    """Download the two public lists and store compact copies in R2 (run monthly; both sources update monthly)."""
    import json, urllib.request, boto3, duckdb
    E = os.environ
    s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
    d = E.get('WORK', '/tmp/names'); os.makedirs(d, exist_ok=True)
    meta = json.loads(urllib.request.urlopen(DAC_URL_META, timeout=60).read())
    url = meta['distribution'][0]['data']['downloadURL']
    urllib.request.urlretrieve(url, f'{d}/dac.csv')
    for u in IRS_URLS: urllib.request.urlretrieve(u, f"{d}/{u.rsplit('/', 1)[1]}")
    con = duckdb.connect()
    con.execute(f"""copy (select distinct NPI npi, "Facility Name" org from read_csv_auto('{d}/dac.csv', all_varchar=true)
                    where "Facility Name" <> '') to '{d}/dac.parquet' (format parquet)""")
    con.execute(f"""copy (select EIN ein, min(NAME) nm from read_csv_auto('{d}/eo*.csv', all_varchar=true, union_by_name=true)
                    group by EIN) to '{d}/irs.parquet' (format parquet)""")
    s3.upload_file(f'{d}/dac.parquet', E['R2_BUCKET'], K_DAC); s3.upload_file(f'{d}/irs.parquet', E['R2_BUCKET'], K_IRS)
    # CMS Hospital Enrollments (each hospital's NPIs and CMS number), for the list-price math's hospital links
    cat = json.loads(urllib.request.urlopen('https://data.cms.gov/data.json', timeout=300).read())
    hu = max(((x.get('title', ''), x['downloadURL']) for d_ in cat['dataset'] for x in d_.get('distribution', [])
              if x.get('title', '').startswith('Hospital Enrollments :') and str(x.get('downloadURL', '')).endswith('.csv')))[1]
    urllib.request.urlretrieve(hu, f'{d}/hospital_enrollments.csv')
    s3.upload_file(f'{d}/hospital_enrollments.csv', E['R2_BUCKET'], 'data/names/hospital_enrollments.csv')
    s3.put_object(Bucket=E['R2_BUCKET'], Key='data/names/sources.json', Body=json.dumps(
        {'dac': url, 'dac_modified': meta.get('modified'), 'irs': IRS_URLS}).encode())
    print('practice name sources refreshed', url, meta.get('modified'))


if __name__ == '__main__' and sys.argv[1:] == ['sources']:
    refresh_sources()
