"""Build requested codes in minutes (Oct 18, 2026, Betsy approved "common codes first").

A state built "common codes first" lists its rare codes in embed.json "coming". When a visitor picks one, the page shows
"We're pulling these prices now, check back in a few minutes" and its Pages Function writes a request:
  R2 requests/<area>/<code>.json   {"code": "...", "area": "...", "at": "<when asked>"}   (area = the page's slug, e.g. illinois)
This job (GitHub, .github/workflows/request-codes.yml: every 10 minutes, or right away when the page dispatches it) reads
the requests, and for each area runs site/every_code.py with PHASE=codes against that area's newest finished build:
  - the build's own insurer tables and settings (build_env.json, written next to its embed.json), so the new files fit
    its lookup lists exactly (checked by fingerprint; it stops rather than write files that don't fit)
  - stage A is never redone (its saved work is in ACACHE); only the buckets the requested codes fall in are read
  - t/<code>.txt is written into the build's folder (the page's function serves it as soon as it exists) and the code
    moves from "coming" to the built codes in embed.json, marked "req": <date>
A handled request moves to requests/done/<area>/<code>.json with what happened. Nothing is estimated: a requested code
gets the same rows, flags and file links as if it had been built with the rest.

  python site/request_codes.py            handle waiting requests (MAXC codes per area per run, oldest asked first)
  python site/request_codes.py --list     show waiting requests only
"""
import json, os, subprocess, sys, time

E = os.environ
HERE = os.path.dirname(os.path.abspath(__file__))
MAXC = int(E.get('MAXC', '40'))
RQ = E.get('REQ_PREFIX', 'requests/')   # tests only: another prefix
ROOTS = tuple(E['REQ_ROOTS'].split(',')) if E.get('REQ_ROOTS') else ('site/every-st/', 'site/every-tx/')   # REQ_ROOTS: tests only


def s3c():
    import boto3
    g = lambda k: ''.join(E[k].split())
    return boto3.client('s3', endpoint_url=f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                        aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name='auto'), g('R2_BUCKET')


def ls(s3, B, pfx, delim=None):
    out, kw = [], dict(Bucket=B, Prefix=pfx, **({'Delimiter': delim} if delim else {}))
    for pg in s3.get_paginator('list_objects_v2').paginate(**kw):
        out += [(o['Key'], o['LastModified']) for o in pg.get('Contents', [])] if not delim else [c['Prefix'] for c in pg.get('CommonPrefixes', [])]
    return out


def newest_build(s3, B, area):
    """the area's newest folder with an embed.json, by when it was written (same rule as city_page.py and hosp_area.py)"""
    best = None
    for root in ROOTS:
        for d in ls(s3, B, f'{root}{area}/', '/'):
            try: t = s3.head_object(Bucket=B, Key=d + 'embed.json')['LastModified']
            except Exception: continue
            if best is None or t > best[0]: best = (t, d)
    return best[1] if best else None


def waiting(s3, B):
    """{area: [(asked_at, code, key)]} oldest first"""
    out = {}
    for k, t in ls(s3, B, RQ):
        parts = [''] + k[len(RQ):].split('/')   # ['', area, '<code>.json']
        if len(parts) != 3 or parts[1] in ('done', 'status') or not k.endswith('.json'): continue
        try: r = json.loads(s3.get_object(Bucket=B, Key=k)['Body'].read())
        except Exception: r = {}
        out.setdefault(parts[1], []).append((r.get('at') or t.isoformat(), parts[2][:-5], k))
    return {a: sorted(v) for a, v in out.items()}


def finish(s3, B, key, area, code, **what):
    """move a request to requests/done/ with what happened (the request itself is kept there)"""
    try: r = json.loads(s3.get_object(Bucket=B, Key=key)['Body'].read())
    except Exception: r = {}
    r.update(what, handled=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()))
    s3.put_object(Bucket=B, Key=f'{RQ}done/{area}/{code}.json', Body=json.dumps(r).encode())
    s3.delete_object(Bucket=B, Key=key)


def run_area(s3, B, area, reqs, log):
    pre = newest_build(s3, B, area)
    if not pre:
        log(area, ': no finished build yet; requests wait'); return
    emb = json.loads(s3.get_object(Bucket=B, Key=pre + 'embed.json')['Body'].read())
    coming = emb.get('coming', {})
    todo = []
    for at, code, key in reqs:
        if code in coming or emb['codes'].get(code, {}).get('carried'):
            todo.append((at, code, key))
        elif code in emb['codes']:
            finish(s3, B, key, area, code, result='already built', build=pre)
        else:
            finish(s3, B, key, area, code, result="not in this area's insurer files", build=pre)
    if not todo: return
    if emb.get('coming_adds'):
        # networks were added to this build by update mode after it was built; a requested code needs their rows too,
        # which this job doesn't merge yet. The background fill (or a full build) builds these. Requests stay waiting.
        log(area, f': {len(todo)} requested codes wait: build {pre} had networks added later (coming_adds); not built here'); return
    try: benv = json.loads(s3.get_object(Bucket=B, Key=pre + 'build_env.json')['Body'].read())
    except Exception:
        log(area, f': {pre} has no build_env.json (built before Oct 18, 2026); requests wait for the next build'); return
    todo = todo[:MAXC]
    codes = [c for _, c, _ in todo]
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    work = E.get('REQ_WORK', '/tmp/reqwork')
    env = {**E, **benv['env'], 'PHASE': 'codes', 'CODES': ','.join(codes), 'TOUT': pre, 'FILES_KEY': pre + 'build_env.json',
           'WK': f"{benv['wk']}req/{stamp}/", 'FP_WK': benv['wk'], 'OUTP': f'{pre}req/{stamp}/', 'WORK': work, 'NOXPART': '1',
           'SPLIT': '1', 'MEM': E.get('REQ_MEM', '8GB'), 'THREADS': '4', 'WORKERS': '2', 'WMEM': E.get('REQ_WMEM', '4GB'), 'WTHREADS': '2',
           'ROLE': f'req-{stamp}'}
    for k in ('ACLAIM', 'BCLAIM', 'ALSO_WK', 'PRIORITY_KEY', 'ONLY', 'ONLY_KEY', 'ASTART', 'BSTART', 'BORDER', 'AORDER', 'MAXPIECES'):
        env.pop(k, None)
    log(area, f': building {len(codes)} requested codes into {pre}:', ', '.join(codes))
    t0 = time.time()
    r = subprocess.run([sys.executable, f'{HERE}/every_code.py'], env=env)
    emb2 = json.loads(s3.get_object(Bucket=B, Key=pre + 'embed.json')['Body'].read())
    for at, code, key in todo:
        e = emb2['codes'].get(code)
        if r.returncode == 0 and e and e.get('req') and not e.get('carried'):
            finish(s3, B, key, area, code, result='built', build=pre, n=e.get('n'), seconds=round(time.time() - t0))
        else:
            log(area, code, f': not built (exit {r.returncode}); request stays waiting')
    if r.returncode: raise SystemExit(f'{area}: every_code.py exit {r.returncode} (log: {pre}req/{stamp}/log.txt)')


def main():
    s3, B = s3c()
    lines = []
    def log(*a):
        m = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(m, flush=True); lines.append(m)
    w = waiting(s3, B)
    log(sum(len(v) for v in w.values()), 'requests waiting:', {a: len(v) for a, v in w.items()} or 'none')
    if '--list' in sys.argv:
        for a, v in w.items():
            for at, c, _ in v: print(f'  {a} {c} asked {at}')
        return
    failed = []
    for area, reqs in w.items():
        try: run_area(s3, B, area, reqs, log)
        except SystemExit as e: failed.append(str(e)); log('FAILED', e)
    s3.put_object(Bucket=B, Key=f'{RQ}status/last_run.json', Body=json.dumps(dict(
        at=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), waiting={a: len(v) for a, v in w.items()}, failed=failed, log=lines), indent=1).encode())
    if failed: sys.exit(1)


if __name__ == '__main__':
    main()
