"""Price Finder pages for the first national batch: one page per state (TN, CO, OK, AL, MS, MO, GA). Added Oct 13, 2026.
Run by .github/workflows/state-pages.yml; every run moves the build one step. Build id st-YYYY-MM; state in R2
site/builds/st-YYYY-MM/state.json. Stages:
  wait     no seven-state insurer file is still being read (bot/insurers/s7/manifest.csv) and 2+ machines are free
  split    tx_split.py SCOPE=s7 on rented machines: every data/s7/rates/ table split by the provider's practice state into
           data/s7/state/<state>/rates|membership/; then each state's provider list data/s7/state/<state>/npis.parquet
  build    every_code.py per state (same settings as the Texas metro areas) -> site/every-st/<state>/<YYYY-MM>/embed.json
  hosp     hosp_area.py with HOSP_SCOPE=s7 (the workflow's next step): each state's hospital price files, then
           city_page.py --deploy per state (pages at /<state>/price-finder/, listed in the Area picker on every page)
Nothing is averaged; every rate keeps its insurer file. Machines delete themselves when done.
Env: as orchestrate.py, plus [ST_BUILD=YYYY-MM] [FORCE=1]."""
import csv, io, os, sys, time

MONTH = os.environ.get('ST_BUILD') or time.strftime('%Y-%m')
os.environ['BUILD'] = 'st-' + MONTH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestrate as O
from orchestrate import B, s3, log, exists, getj, putj, ls, ensure, free_slots

E = os.environ
SP = O.SP
SIZE = 's-8vcpu-32gb-amd'
STATES = {'TN': 'tennessee', 'CO': 'colorado', 'OK': 'oklahoma', 'AL': 'alabama', 'MS': 'mississippi', 'MO': 'missouri', 'GA': 'georgia'}
W = dict(WORKERS='4', WMEM='6GB', WTHREADS='2')
GB_PER_MACHINE, MAX_PER_STATE = 20, 3
RUN_SPLIT = "for t in 1 2 3; do /root/v/bin/python /root/h/tx_split.py >> /root/run.log 2>&1 && break; sleep 5; done"
SPLIT_MACHINES = 4


def sizes(prefix):
    return {o['Key'].rsplit('/', 1)[1][:-8]: o['Size'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=prefix)
            for o in pg.get('Contents', []) if o['Key'].endswith('.parquet')}


def s7_busy():
    m = s3.get_object(Bucket=B, Key='bot/insurers/s7/manifest.csv')['Body'].read().decode()
    return sum(1 for r in csv.DictReader(io.StringIO(m)) if r.get('status') in ('running', 'queued'))


def state_npis():
    import duckdb
    s3.download_file(B, 'data/scope/s7_npis_all.parquet', '/tmp/s7_npis_all.parquet')
    c, out = duckdb.connect(), {}
    for st, slug in STATES.items():
        c.execute(f"copy (select * from read_parquet('/tmp/s7_npis_all.parquet') where upper(state) = '{st}') to '/tmp/npis_{slug}.parquet' (format parquet, compression zstd)")
        out[slug] = c.execute(f"select count(*) from read_parquet('/tmp/npis_{slug}.parquet')").fetchone()[0]
        if out[slug] < 1000: raise SystemExit(f'STOP: only {out[slug]} providers for {slug}; nothing changed')
    for slug in out: s3.upload_file(f'/tmp/npis_{slug}.parquet', B, f'data/s7/state/{slug}/npis.parquet')
    return out


def tout(slug): return f'site/every-st/{slug}/{MONTH}/'


def main():
    st = getj(SP + 'state.json', {'stage': 'wait', 'launches': {}, 'problems': []})
    log('state pages build', MONTH, 'stage', st['stage'])
    if st['stage'] == 'wait':
        busy = s7_busy()
        if busy and not E.get('FORCE'): log(busy, 'seven-state insurer files still queued or being read; waiting'); return putj(SP + 'state.json', st)
        if free_slots() < 2: log('not enough free machines; waiting'); return putj(SP + 'state.json', st)
        O.bundle()
        st.update(stage='split', started=time.strftime('%Y-%m-%d %H:%M'))
    if st['stage'] == 'split':
        sz = sizes('data/s7/rates/')
        done = {k.rsplit('/', 1)[1][:-5] for k in ls('data/s7/state/_done/')}
        todo = sorted((t for t in sz if t not in done), key=lambda t: -sz[t])
        if 'split_jobs' not in st:
            jobs = [[] for _ in range(min(SPLIT_MACHINES, max(1, len(todo))))]
            for i, t in enumerate(todo): jobs[i % len(jobs)].append(t)
            st['split_jobs'] = [j for j in jobs if j]
        busy = 0
        for i, job in enumerate(st['split_jobs']):
            role = f'split-{i + 1}'
            left = [t for t in job if t not in done]
            finished = not left or (st['launches'].get(role, 0) >= 3 and not O.alive(role))
            ensure(st, role, SIZE, RUN_SPLIT, dict(SCOPE='s7', TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'), finished)
            busy += not finished
        if 'back_jobs' not in st:   # Oct 13: 530 GB on 4 machines is slow; a second machine per list works from the small end
            st['back_jobs'] = [list(reversed(j[1:])) for j in st['split_jobs'] if len(j) > 2]
        for i, job in enumerate(st['back_jobs']):
            role = f'split-{i + 1}b'
            left = [t for t in job if t not in done]
            finished = not left or (st['launches'].get(role, 0) >= 3 and not O.alive(role))
            ensure(st, role, SIZE, RUN_SPLIT, dict(SCOPE='s7', TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'), finished)
            busy += not finished
        log(len(todo), 'of', len(sz), 'seven-state tables left to split')
        if not busy:
            st['split_failed'] = todo
            st['providers'] = state_npis()
            st['machines'] = {s: min(MAX_PER_STATE, max(1, -(-sum(sizes(f'data/s7/state/{s}/rates/').values()) // int(GB_PER_MACHINE * 1e9))))
                              for s in STATES.values()}
            st['stage'] = 'build'
            log('providers per state', st['providers'], 'machines', st['machines'])
    if st['stage'] == 'build':
        left = []
        for slug in STATES.values():
            if exists(tout(slug) + 'embed.json'): continue
            left.append(slug); n = st['machines'][slug]
            for i in range(n):
                env = dict(RATES=f'data/s7/state/{slug}/rates/', NPIS=f'data/s7/state/{slug}/npis.parquet', TOUT=tout(slug),
                           OUTP=f'{SP}{slug}-c{i + 1}/', WK=f"work/every-st/{slug}/v{MONTH.replace('-', '')}/",
                           ACACHE=f'work/every-st/{slug}/Acache/', NOXPART='1', ACLAIM='1', PIECE_GB='0.4', MAXPIECES='3', THREADS='6',
                           MEM='18GB', WORK='/d', ASTART=str(i * 5), BSTART=str(i * 256 // n), **W)
                ensure(st, f'{slug}-c{i + 1}', SIZE, O.RUN_INS, env, False)
        log('states still building:', ', '.join(left) or 'none')
        if not left: st['stage'] = 'hosp'
    if st['stage'] == 'hosp':
        log('insurer builds done; the hospital step (hosp_area.py, HOSP_SCOPE=s7) builds hospitals and publishes the pages')
    putj(SP + 'state.json', st)


if __name__ == '__main__':
    main()
