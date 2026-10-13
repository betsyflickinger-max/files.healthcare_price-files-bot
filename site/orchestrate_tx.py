"""Monthly Texas city builds (added Oct 12, 2026). Run by .github/workflows/site-build.yml every 6 hours, right after orchestrate.py.

One build per month, id tx-YYYY-MM; state in R2 site/builds/tx-YYYY-MM/state.json. October 2026 was built by hand, so the
first automatic build is November 2026. Stages:
  wait     from the 8th: this month's DFW refresh is live (DFW gets the machines first), no Texas insurer file is still
           being read, and at least 2 machines are free
  split    tx_split.py on rented machines for every Texas insurer table not split by metro yet (insurers re-post monthly
           under new names, and the insurer bot retires last month's tables), plus one machine that re-splits the October
           "rest of Texas" tables into the metro-area pages (tx_split.py SRC=rest; once per table). Split tables whose insurer
           table was retired are moved to work/retired/<YYYY-MM>/tx_metro/, and each metro's provider list is rebuilt from the Texas list.
  build    every_code.py per metro on several machines that share the work (same settings as the October hand run,
           v2/v3 code). A metro is done when site/every-tx/<metro>/<YYYY-MM>/embed.json exists.
  publish  city_page.py --deploy for each page: El Paso, Austin, San Antonio, Houston, then the 18 metro areas and small towns
           (Oct 12, 2026: they replace the single "rest of Texas" build). A page that fails keeps its previous version and opens an issue.
Before November, "force_tx" starts build tx-YYYY-MM-metros: only the 18 metro areas + small towns (the four cities were built
by hand). Once started, it carries on by itself on the 6-hourly runs.
Dead machines are relaunched up to 3 times per role; machines delete themselves when done.
Env: as orchestrate.py, plus [FORCE_TX=1] (skip the 8th / DFW / insurer-bot waits) and [TX_BUILD=YYYY-MM]."""
import csv, io, os, subprocess, sys, time

MONTH = os.environ.get('TX_BUILD') or time.strftime('%Y-%m')
FIRST = '2026-11'
EARLY = MONTH < FIRST   # the four cities were built by hand: a forced run builds only the metro-area pages
os.environ['BUILD'] = 'tx-' + MONTH + ('-metros' if EARLY else '')   # orchestrate.py names machines, logs and the bundle after BUILD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestrate as O
from orchestrate import B, s3, log, exists, getj, putj, ls, ensure, free_slots, issue
from city_page import CITIES

E = os.environ
SP = O.SP                                     # site/builds/tx-YYYY-MM/
SIZE = 's-8vcpu-32gb-amd'                     # 400 GB disk: the biggest Texas tables are ~38 GB before splitting
# machines per city, biggest first, and stage B settings from the October run (Oct 12 v2 relaunch)
BIG = [('houston', 5, dict(WORKERS='2', WMEM='13GB', WTHREADS='4')),   # Oct 12 test: ~3x the parts per hour of 4 x 6 GB on Houston's 60-90M-row parts
       ('san-antonio', 2, dict(WORKERS='4', WMEM='6GB', WTHREADS='2')),
       ('austin', 2, dict(WORKERS='4', WMEM='6GB', WTHREADS='2')),
       ('el-paso', 1, dict(WORKERS='5', WMEM='5GB', WTHREADS='2'))]
ZIP3 = {'houston': ('770', '775'), 'san-antonio': ('780', '782'), 'austin': ('786', '787'), 'el-paso': ('798', '799')}  # as tx_split.py
DFW3 = [('750', '753'), ('760', '762')]
AREAS = [m for m in CITIES if m not in ZIP3]   # the rest of Texas: 18 metro areas + small-towns, by reference/geo/tx_zip_metro.csv
AREA_W = dict(WORKERS='4', WMEM='6GB', WTHREADS='2')   # as the October rest-of-Texas build
GB_PER_MACHINE, AREA_MAX = 20, 3              # metro-area machines: one per 20 GB of its split tables, 1 to 3
# Oct 12, 2026 (Betsy): small towns was the last page left, alone on one machine for hours. Put up to 15 machines on it so
# the build ends and the waiting Cigna file can start. Extra machines claim unread tables in stage A and skip finished
# buckets in stage B; any that don't fit the account's machine limit are simply not started.
BOOST = {'small-towns': 15}
GEO = os.path.join(O.HERE, '..', 'reference', 'geo', 'tx_zip_metro.csv')
CITY_PAGES = ['el-paso', 'austin', 'san-antonio', 'houston']
RUN_SPLIT = "for t in 1 2 3; do /root/v/bin/python /root/h/tx_split.py >> /root/run.log 2>&1 && break; sleep 5; done"
SPLIT_MACHINES = 4
REST_MACHINES = 8                             # extra machines for the one-time October re-split of the rest-of-Texas tables


def tx_bot_busy():
    m = s3.get_object(Bucket=B, Key='bot/insurers/tx/manifest.csv')['Body'].read().decode()
    return sum(1 for r in csv.DictReader(io.StringIO(m)) if r.get('status') == 'running')


def tables(prefix):
    return {k.rsplit('/', 1)[1][:-8]: k for k in ls(prefix) if k.endswith('.parquet')}


def sizes(prefix):
    return {o['Key'].rsplit('/', 1)[1][:-8]: o['Size'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=prefix)
            for o in pg.get('Contents', []) if o['Key'].endswith('.parquet')}


def metros():
    """(metro, machines, stage B settings) built this month; metro-area machine counts are set after the split"""
    return ([] if EARLY else BIG) + [(m, None, AREA_W) for m in AREAS]


def retire_stale():
    """split tables whose Texas insurer table is gone (retired by the insurer bot) leave the metro inputs"""
    current, moved = set(tables('data/tx/rates/')), 0
    for m in [m for m, _, _ in metros()] + ['rest']:
        for sub in ('rates', 'membership'):
            for t, k in tables(f'data/tx/metro/{m}/{sub}/').items():
                if t not in current:
                    s3.copy_object(Bucket=B, Key=f'work/retired/{MONTH}/tx_metro/{m}/{sub}/{t}.parquet', CopySource={'Bucket': B, 'Key': k})
                    s3.delete_object(Bucket=B, Key=k); moved += 1
    return moved


def metro_npis():
    """each metro's provider list = the Texas list (data/scope/tx_npis_all.parquet) cut by practice ZIP, as tx_split.py does"""
    import duckdb
    s3.download_file(B, 'data/scope/tx_npis_all.parquet', '/tmp/tx_npis_all.parquet')
    c = duckdb.connect(); out = {}
    c.execute(f"create table g as select zip5, slug from read_csv('{GEO}', all_varchar=true)")
    city = ' or '.join(f"left(n.zip5, 3) between '{a}' and '{b}'" for a, b in list(ZIP3.values()) + DFW3)
    for m, _, _ in metros():
        if m in ZIP3:
            a, b = ZIP3[m]; cond = f"left(n.zip5, 3) between '{a}' and '{b}'"
        else:
            cond = f"not ({city}) and coalesce(g.slug, 'small-towns') = '{m}'"
        c.execute(f"""copy (select n.* from read_parquet('/tmp/tx_npis_all.parquet') n left join g on g.zip5 = left(n.zip5, 5) where {cond})
                      to '/tmp/npis_{m}.parquet' (format parquet, compression zstd)""")
        out[m] = c.execute(f"select count(*) from read_parquet('/tmp/npis_{m}.parquet')").fetchone()[0]
        if out[m] < (1000 if m in ZIP3 else 100): raise SystemExit(f'STOP: only {out[m]} providers for {m}; nothing changed')
    for m in out: s3.upload_file(f'/tmp/npis_{m}.parquet', B, f'data/tx/metro/{m}/npis.parquet')
    return out


def area_machines():
    return {m: min(AREA_MAX, max(1, -(-sum(sizes(f'data/tx/metro/{m}/rates/').values()) // int(GB_PER_MACHINE * 1e9)))) for m in AREAS}


def tout(m): return f'site/every-tx/{m}/{MONTH}/'


def main():
    force = E.get('FORCE_TX')
    if EARLY and not force and not exists(SP + 'state.json'):
        log('Texas', MONTH, 'was built by hand; automatic builds start', FIRST, '("force_tx" builds the metro-area pages now)'); return
    st = getj(SP + 'state.json', {'stage': 'wait', 'launches': {}, 'problems': [], 'log': []})
    log('Texas build', MONTH, 'stage', st['stage'])
    if st['stage'] == 'wait':
        if int(time.strftime('%d')) < 8 and not force: log('waiting for the 8th'); return
        dfw = getj(f'site/builds/{MONTH}/state.json', {}).get('stage')
        if dfw not in ('live', 'held', 'ready') and not force: log('waiting for the DFW refresh first (stage', dfw, ')'); return
        busy = tx_bot_busy()
        if busy and not force: log(busy, 'Texas insurer files still being read; waiting'); return
        if free_slots() < 2: log('not enough free machines; waiting'); return
        O.bundle()
        st.update(stage='split', started=time.strftime('%Y-%m-%d %H:%M'))
    if st['stage'] == 'split':
        sz = sizes('data/tx/rates/')
        done = {k.rsplit('/', 1)[1][:-5] for k in ls('data/tx/metro/_done/')}
        todo = sorted((t for t in sz if t not in done), key=lambda t: -sz[t])
        if 'split_jobs' not in st:   # fixed once, biggest tables spread across the machines
            jobs = [[] for _ in range(min(SPLIT_MACHINES, max(1, len(todo))))]
            for i, t in enumerate(todo): jobs[i % len(jobs)].append(t)
            st['split_jobs'] = [j for j in jobs if j]
            st['rest_job'] = [t for t in tables('data/tx/metro/rest/rates/') if t in sz]   # October "rest" tables still current
        for i, job in enumerate(st['split_jobs']):
            left = [t for t in job if t not in done]
            ensure(st, f'split-{i + 1}', SIZE, RUN_SPLIT, dict(TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'), not left)
        rdone = {k.rsplit('/', 1)[1][:-5] for k in ls('data/tx/metro/_done_rest/')}
        rleft = [t for t in st.get('rest_job', []) if t not in rdone]
        if st.get('rest_job'):
            ensure(st, 'split-rest', SIZE, RUN_SPLIT, dict(SRC='rest', TABLES=','.join(st['rest_job']), MEM='24GB', THREADS='8', WORK='/d'), not rleft)
            if 'rest_jobs' not in st:   # Oct 12: one machine was ~25 min per table; spread the rest over more machines.
                # split-rest works through rest_job front to back; the extra machines take the tables from the back, so the
                # two only meet near the end (a table done twice is harmless: same output, and done markers are skipped)
                back = [t for t in reversed(st['rest_job']) if t not in rdone][:-1]
                jobs = [[] for _ in range(min(REST_MACHINES, len(back)))]
                for i, t in enumerate(back): jobs[i % len(jobs)].append(t)
                st['rest_jobs'] = [j for j in jobs if j]
            for i, job in enumerate(st['rest_jobs']):
                ensure(st, f'split-rest-{i + 2}', SIZE, RUN_SPLIT, dict(SRC='rest', TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'),
                       not [t for t in job if t not in rdone])
        log(len(todo), 'Texas tables left to split;', len(rleft), 'rest-of-Texas tables left to re-split')
        if not todo and not rleft:
            st['retired_split_tables'] = retire_stale()
            st['providers'] = metro_npis()
            st['machines'] = area_machines()
            st['stage'] = 'build'
    if st['stage'] == 'build':
        left = []
        for m, n, w in metros():
            if exists(tout(m) + 'embed.json'): continue
            left.append(m); n = max(n or st['machines'][m], BOOST.get(m, 0))
            for i in range(n):
                env = dict(RATES=f'data/tx/metro/{m}/rates/', NPIS=f'data/tx/metro/{m}/npis.parquet', TOUT=tout(m), OUTP=f'{SP}{m}-c{i + 1}/',
                           WK=f"work/every-tx/{m}/v{MONTH.replace('-', '')}/", ACACHE=f'work/every-tx/{m}/Acache/', NOXPART='1', ACLAIM='1',
                           PIECE_GB='0.4', MAXPIECES='3', THREADS='6', MEM='18GB', WORK='/d', ASTART=str(i * 5), BSTART=str(i * 256 // n), **w)
                ensure(st, f'{m}-c{i + 1}', SIZE, O.RUN_INS, env, False)
        log('metros still building:', ', '.join(left) or 'none')
        if not left: st['stage'] = 'publish'
    if st['stage'] == 'publish':
        res = st.setdefault('cities', {})
        for m in ([] if EARLY else CITY_PAGES) + AREAS:
            if m in res: continue   # a run stopped by the workflow's time limit carries on with the next page
            r = subprocess.run([sys.executable, f'{O.HERE}/city_page.py', m, '--deploy', '--out', f'/tmp/txcity-{m}'], capture_output=True, text=True, timeout=3600)
            print(r.stdout[-1500:], r.stderr[-1500:])
            res[m] = 'live' if r.returncode == 0 else 'kept previous page (failed)'
            if r.returncode: issue(f'Texas {MONTH}: {m} page not rebuilt', 'The page keeps its previous version.\n\n```\n' + (r.stdout + r.stderr)[-3000:] + '\n```')
            putj(SP + 'state.json', st)
        st.update(stage='live', live_at=time.strftime('%Y-%m-%d %H:%M'))
        issue(f'Texas city pages {MONTH} are live', '\n'.join(f'{m}: {v}' for m, v in res.items()))
    putj(SP + 'state.json', st)


if __name__ == '__main__':
    main()
