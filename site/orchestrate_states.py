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
# Oct 14: STALL_MIN 180 (default 60): a Georgia batch takes 60-90 min, so the 60-min freeze check restarted nearly every
# new Georgia machine just before its first batch finished, over and over.
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


# Oct 14: while the state builds ran, the insurer queue was paused (hold.txt starting 'state-pages pause') so its machine
# slots went to the builds; files already being read finished. Lifted here as soon as every state is built.
PAUSE_KEYS = ['bot/insurers/tx/hold.txt', 'bot/insurers/hold.txt', 'bot/fleet/hold_hospitals.txt']
def lift_pause():
    for k in PAUSE_KEYS:
        try:
            if s3.get_object(Bucket=B, Key=k)['Body'].read().decode().startswith('state-pages pause'):
                s3.delete_object(Bucket=B, Key=k); log('insurer queue pause lifted:', k)
        except Exception: pass


# Oct 14: when a state finishes, its machines delete themselves and the free slots go to the states still building, so no
# slot sits empty (this was done by hand before). Each free slot goes to the state with the most stage-B buckets left per
# machine; a new machine spends ~30 min getting ready, so only where at least MIN_LEFT buckets per machine remain.
NB, MIN_LEFT, MAX_MACHINES = 256, 10, 12
def wk(slug): return f"work/every-st/{slug}/v{MONTH.replace('-', '')}/"
def rebalance(st, left, run):
    free = free_slots()
    if free < 1 or not left: return
    todo = {s: NB - sum(1 for k in ls(wk(s) + 'B/') if k.endswith('.json')) for s in left}
    while free > 0:
        room = [x for x in left if st['machines'][x] < MAX_MACHINES]
        if not room: break
        s = max(room, key=lambda x: todo[x] / (st['machines'][x] + 1))
        if todo[s] / (st['machines'][s] + 1) < MIN_LEFT: break
        st['machines'][s] += 1; free -= 1
        msg = f"{time.strftime('%b %d %H:%M')} UTC: free slot -> {s} ({st['machines'][s]} machines, {todo[s]} of {NB} buckets left)"
        log(msg); st.setdefault('log', []).append(msg)
        run(s, st['machines'][s] - 1)


# Oct 14: a GitHub notice (issue, which GitHub emails to Betsy) as each state finishes, naming where its machines went.
# Announced one run after the state is first seen done, so the freed slots' moves (written by rebalance) are included.
# States finished before this was added were already reported by hand.
ANNOUNCE_FROM = '2026-10-14 21:30'   # UTC
NAMES = {v: v.title() for v in STATES.values()}
def ct(t):   # a UTC datetime -> "Oct 14 5:03 PM CT"
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo('America/Chicago')).strftime('%b %d %-I:%M %p CT')
def finished_at(x): return ct(s3.head_object(Bucket=B, Key=tout(x) + 'embed.json')['LastModified'])
def announce(st, left):
    if 'announced' not in st:
        st['announced'] = [x for x in STATES.values() if x not in left and
                           s3.head_object(Bucket=B, Key=tout(x) + 'embed.json')['LastModified'].strftime('%Y-%m-%d %H:%M') < ANNOUNCE_FROM]
        st['announce_log_i'] = len(st.get('log', []))
    seen = st.setdefault('done_seen', [])
    new = [x for x in STATES.values() if x not in left and x not in st['announced']]
    if not new: return
    if left and not all(x in seen for x in new):
        seen.extend(x for x in new if x not in seen); return
    moves = st.get('log', [])[st['announce_log_i']:]
    still = [f"- {NAMES[x]}: {sum(1 for k in ls(wk(x) + 'B/') if k.endswith('.json'))} of {NB} batches done, {st['machines'][x]} machines"
             for x in left]
    title = ' + '.join(NAMES[x] for x in new) + (' done: all 7 states built' if not left else ' done; machines moved on')
    body = '\n'.join([' '.join(f"{NAMES[x]} finished its Price Finder data at {finished_at(x)}." for x in new), '',
                      '**Where the free machines went**', *(['- ' + m for m in moves] or ['- none yet (slots go out on the next runs)']), '',
                      '**Still building**', *(still or ['- nothing: every state is built; the hospital + publish step starts now'])])
    O.issue(title, body)
    st['announced'] += new; st['announce_log_i'] = len(st.get('log', []))


# Oct 14: when a state's page data is written (embed.json), its other machines can still be busy for up to an hour on
# batches another machine already finished (Missouri c1, Colorado c1/c2/c4/c5 held 5 slots this way). Shut them down so
# rebalance() hands the slots to the states still building in the same pass.
def release_finished(left):
    for d in O.droplets():
        for slug in STATES.values():
            if slug not in left and d['name'].startswith(f'upfront-site-{O.BID}-{slug}-c'):
                try: O.do('DELETE', f"/droplets/{d['id']}"); log('released', d['name'], '(its state is done)')
                except Exception as e: log('release failed', d['name'], repr(e)[:150])


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
        left = [slug for slug in STATES.values() if not exists(tout(slug) + 'embed.json')]
        def run(slug, i):
                n = st['machines'][slug]
                env = dict(RATES=f'data/s7/state/{slug}/rates/', NPIS=f'data/s7/state/{slug}/npis.parquet', TOUT=tout(slug),
                           OUTP=f'{SP}{slug}-c{i + 1}/', WK=f"work/every-st/{slug}/v{MONTH.replace('-', '')}/",
                           ACACHE=f'work/every-st/{slug}/Acache/', NOXPART='1', ACLAIM='1', PIECE_GB='0.4', MAXPIECES='3', THREADS='6',
                           MEM='18GB', WORK='/d', ASTART=str(i * 5), BSTART=str(i * NB // n), STALL_MIN='180', **W)
                ensure(st, f'{slug}-c{i + 1}', SIZE, O.RUN_INS, env, False)
        for slug in left:
            for i in range(st['machines'][slug]): run(slug, i)
        release_finished(left)
        rebalance(st, left, run)
        try: announce(st, left)   # a failed notice must never stop the build from saving its state
        except Exception as e: log('notice failed:', repr(e)[:200])
        log('states still building:', ', '.join(left) or 'none')
        if not left: st['stage'] = 'hosp'; lift_pause()
    if st['stage'] == 'hosp':
        lift_pause()
        log('insurer builds done; the hospital step (hosp_area.py, HOSP_SCOPE=s7) builds hospitals and publishes the pages')
    putj(SP + 'state.json', st)


if __name__ == '__main__':
    main()
