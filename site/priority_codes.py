"""Priority code list per state for "common codes first" builds (Oct 18, 2026, Betsy approved: 2,000 codes).

A state's Price Finder page goes live with these codes first; every other code is built when someone asks for it, or in
the background on spare machine time. The list, per state (two-letter code), in this order until it reaches N codes:
  1. the site's named procedures (site/site_codes.csv: all 70 CMS shoppable services and the rest of the 89)
  2. every MS-DRG (hospital stays; few rows each, so they cost little)
  3. CPT/HCPCS codes by how many Medicare patients got them in that state (CMS "Medicare Physician & Other
     Practitioners - by Geography and Service", data year 2024, state rows, office + facility added together)
How many insurer files list a code is NOT used: fee schedules list nearly every code for every doctor, so a
dermatologist has a price for brain surgery. Medicare use is a public measure of what people actually get.

Writes R2 site/priority/<ST>.json {"codes": [...], "n": N, "made": ..., "sources": ...}.
Run: python site/priority_codes.py [--states TX,IL,...] [--n 2000] [--report]   (--report: share of each built state's
price lines and codes that the list covers, i.e. what the first build costs compared with a full one)
"""
import argparse, csv, gzip, io, json, os, sys, time

E = os.environ
GEO_KEY = 'reference/2026-10-18/cms/MUP_PHY_R26_P05_V10_D24_Geo.csv'
STATES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut',
          'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
          'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
          'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
          'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
          'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
          'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
          'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'}


def s3c():
    import boto3
    g = lambda k: ''.join(E[k].split())
    return boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"), aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                        aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name=(os.environ.get('STORAGE_REGION') or 'auto')), g('R2_BUCKET')


def medicare_rank(geo_rows, state_name):
    """{code: patients} for one state, office and facility rows added together"""
    out = {}
    for r in geo_rows:
        if r['Rndrng_Prvdr_Geo_Lvl'] == 'State' and r['Rndrng_Prvdr_Geo_Desc'] == state_name:
            out[r['HCPCS_Cd'].strip().upper()] = out.get(r['HCPCS_Cd'].strip().upper(), 0) + float(r['Tot_Benes'] or 0)
    return out


def build_list(named, drgs, rank, n):
    """named + DRGs first (in that order), then Medicare's most-used codes, up to n codes"""
    out, seen = [], set()
    for c in list(named) + sorted(drgs, key=lambda x: int(x) if x.isdigit() else 0) + [c for c, _ in sorted(rank.items(), key=lambda kv: -kv[1])]:
        if c not in seen:
            seen.add(c); out.append(c)
        if len(out) >= n: break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--states', default=','.join(STATES))
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    s3, B = s3c()
    geo = list(csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key=GEO_KEY)['Body'].read().decode('utf-8', 'replace'))))
    named = [r['code'] for r in csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key='site/site_codes.csv')['Body'].read().decode()))]
    drgs = [str(d) for d in range(1, 1000)]   # every MS-DRG number; only the ones a state's files list ever get built
    lists = {}
    for st in [s.strip().upper() for s in a.states.split(',') if s.strip()]:
        rank = medicare_rank(geo, STATES[st])
        lst = build_list(named, [], rank, a.n)   # DRGs are added at build time (all of them, see header), not counted in n
        lists[st] = lst
        s3.put_object(Bucket=B, Key=f'site/priority/{st}.json', Body=json.dumps(dict(
            codes=lst, drgs='all', n=len(lst), made=time.strftime('%Y-%m-%d'),
            sources=['site/site_codes.csv', GEO_KEY + ' (data year 2024, state rows, Tot_Benes)'])).encode())
    print(len(lists), 'state lists written to site/priority/')
    if a.report:
        report(s3, B, lists)


def report(s3, B, lists):
    """for every built area: share of its price lines and codes covered by its state's list (+ all DRGs)"""
    areas = []
    for root, st_of in (('site/every-st/', None), ('site/every-tx/', 'TX')):
        for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=root, Delimiter='/'):
            for c in pg.get('CommonPrefixes', []):
                slug = c['Prefix'][len(root):-1]
                areas.append((slug, c['Prefix'], st_of))
    slug_state = {v.lower().replace(' ', '-'): k for k, v in STATES.items()}
    print('| Area | Codes in build | Priority codes found | Price lines covered by the first build | Left for later |')
    print('|---|---:|---:|---:|---:|')
    for slug, pre, st_of in sorted(areas):
        st = st_of or slug_state.get(slug)
        if not st or st not in lists: continue
        best = None
        for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pre, Delimiter='/'):
            for c in pg.get('CommonPrefixes', []):
                try: t = s3.head_object(Bucket=B, Key=c['Prefix'] + 'embed.json')['LastModified']
                except Exception: continue
                if best is None or t > best[0]: best = (t, c['Prefix'])
        if not best: continue
        codes = json.loads(s3.get_object(Bucket=B, Key=best[1] + 'embed.json')['Body'].read())['codes']
        want = set(lists[st])
        tot = sum(v['n'] for v in codes.values())
        hit = {c: v for c, v in codes.items() if c in want or v.get('type') == 'MS-DRG'}
        share = sum(v['n'] for v in hit.values()) / tot if tot else 0
        print(f"| {slug} | {len(codes):,} | {len(hit):,} | {100 * share:.0f}% | {100 * (1 - share):.0f}% |")


if __name__ == '__main__':
    main()
