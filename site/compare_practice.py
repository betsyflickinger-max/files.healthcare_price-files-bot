"""Oct 18, 2026: check a practice-view build (every_code.py PRACTICE=1) against the normal build of the same data.
Betsy's rule: no doctor missing, no doctor mispriced. For every code:
- organizations (hospitals, surgery centers, labs, groups): rows must match the normal build (network, fee type, price,
  $0 count, other-rate count, date, source file, label). The flags field is reported separately.
- doctors: every (doctor, network, fee type, rate type) in the normal build must be in at least one of the doctor's practice
  entries, and the normal build's headline price must be one of those entries' prices; no doctor may appear in the practice
  build where the normal build doesn't have them.
Usage: LIVE=<build prefix> TEST=<build prefix> [CODES=a,b,c] python compare_practice.py   (R2_* env as usual)
Writes TEST/compare_practice.json and prints a summary. Exit 0 = PASS."""
import os, sys, json, gzip, base64, boto3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
E = os.environ
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = E['R2_BUCKET']; LIVE = E['LIVE']; TEST = E['TEST']
def j(key): return json.loads(s3.get_object(Bucket=B, Key=key)['Body'].read())
_S3 = {}
def cli():   # one client per process (the check forks worker processes)
    pid = os.getpid()
    if pid not in _S3:
        _S3[pid] = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                                aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
    return _S3[pid]
def page(prefix, code):
    try: return json.loads(gzip.decompress(base64.b64decode(cli().get_object(Bucket=B, Key=f'{prefix}t/{code}.txt')['Body'].read())))
    except cli().exceptions.NoSuchKey: return None
el, nl = j(LIVE + 'embed.json'), j(LIVE + 'npis.json')
try: et, nt = j(TEST + 'embed.json'), j(TEST + 'npis.json')
except Exception: et, nt = el, nl; print('test build has no embed.json yet (partial test): using the live lookup lists')
KIND = {nl[i]: p[2] for i, p in enumerate(el['fac'])}
codes = E['CODES'].split(',') if E.get('CODES') else sorted(set(el['codes']) | set(et['codes']))
# SHARD=i/n: this machine checks every n-th code (several machines split the work); PROCS: parallel processes
SH = E.get('SHARD', '0/1'); si, sn = (int(x) for x in SH.split('/')); codes = codes[si::sn]
C = Counter(); EX = {}
def ex(kind, x):
    C[kind] += 1
    if len(EX.setdefault(kind, [])) < 10: EX[kind].append(x)
def one(code):
    a, b = page(LIVE, code), page(TEST, code)
    if a is None or b is None:
        return [('code_missing_live' if a is None else 'code_missing_test', code)] if (a or b) else []
    out = []
    def key(nets, n, fee, t): return (nets[n], fee, t)
    # organizations
    fa = {nl[int(p)]: rows for p, rows in a['f'].items() if KIND.get(nl[int(p)]) != 'P'}
    fb = {nt[int(p)]: rows for p, rows in b['f'].items()}
    for npi in set(fa) | set(fb):
        ra = sorted((key(el['nets'], r[0], r[1], r[2]), r[3], r[7], r[9], el['dates'][r[5]], el['urls'][r[6]], el['labs'][r[10]] if r[10] >= 0 else '') for r in fa.get(npi, []))
        rb = sorted((key(et['nets'], r[0], r[1], r[2]), r[3], r[7], r[9], et['dates'][r[5]], et['urls'][r[6]], et['labs'][r[10]] if r[10] >= 0 else '') for r in fb.get(npi, []))
        if ra != rb: out.append(('org_rows_differ', (code, npi, ra[:2], rb[:2])))
        else:
            out.append(('org_rows_ok', len(ra)))
            fla = sorted((key(el['nets'], r[0], r[1], r[2]), r[3], r[4]) for r in fa[npi]); flb = sorted((key(et['nets'], r[0], r[1], r[2]), r[3], r[4]) for r in fb[npi])
            if fla != flb: out.append(('org_flags_only_differ', (code, npi)))
    # doctors
    L = {}
    for p, rows in a['f'].items():
        npi = nl[int(p)]
        if KIND.get(npi) != 'P': continue
        for r in rows: L[(npi,) + key(el['nets'], r[0], r[1], r[2])] = r[3]
    T = {}
    for pid, ents in b.get('p', {}).items():
        for r, docs in ents:
            for d in docs: T.setdefault((nt[d],) + key(et['nets'], r[0], r[1], r[2]), set()).add(r[3])
    for k, v in L.items():
        if k not in T: out.append(('doctor_missing', (code,) + k))
        elif v not in T[k]: out.append(('doctor_mispriced', (code,) + k + (v, sorted(T[k])[:5])))
        else: out.append(('doctor_ok', 1))
    for k in T.keys() - L.keys(): out.append(('doctor_extra', (code,) + k))
    out.append(('lines_live', sum(len(r) for r in a['f'].values())))
    out.append(('lines_test', sum(len(r) for r in b['f'].values()) + sum(len(e) for e in b.get('p', {}).values())))
    return out
import multiprocessing as mp
def one_safe(code):
    for t in range(3):
        try: return one(code)
        except Exception as e: err = repr(e)[:200]
    return [('check_error', (code, err))]
with mp.get_context('fork').Pool(int(E.get('PROCS', '8'))) as P:
    for i, res in enumerate(P.imap_unordered(one_safe, codes, chunksize=20)):
        for kind, x in res:
            if kind in ('org_rows_ok', 'lines_live', 'lines_test', 'doctor_ok'): C[kind] += x
            else: ex(kind, x)
        if i % 2000 == 0: print(i, 'of', len(codes), dict(C), flush=True)
bad = sum(C[k] for k in ('code_missing_live', 'code_missing_test', 'org_rows_differ', 'doctor_missing', 'doctor_mispriced', 'doctor_extra', 'check_error'))
rep = {'codes': len(codes), 'counts': dict(C), 'examples': EX, 'result': 'PASS' if bad == 0 else 'FAIL',
       'practices': len(et.get('prac', {})), 'npis_identical': nl == nt}
s3.put_object(Bucket=B, Key=TEST + f"compare_practice_{si}of{sn}.json", Body=json.dumps(rep, indent=1, default=str).encode())
print(json.dumps(rep, indent=1, default=str)[:4000])
sys.exit(0 if bad == 0 else 1)
