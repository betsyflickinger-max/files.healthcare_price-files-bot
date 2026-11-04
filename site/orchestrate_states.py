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
import csv, io, json, os, subprocess, sys, time

# Oct 16, 2026: ST_SCOPE=nc builds North Carolina (its own insurer tables data/nc/, build id stnc-YYYY-MM); default s7.
SCOPE = os.environ.get('ST_SCOPE', 's7')
STB = 'st' if SCOPE == 's7' else 'st' + SCOPE   # no '-' inside, so '<STB>-<YYYY-MM>'.split('-', 1) still gives the month
# Nov 1, 2026: last month's build is finished first when it is still under way (site/build_month.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_month import month_for
MONTH = os.environ.get('ST_BUILD') or month_for(STB)
# Oct 16, 2026: rebuild some states only, after new insurer tables landed for them (Anthem's Colorado, Georgia and Missouri
# networks). Named in site/state_rebuild.json (this repo), e.g. {"st": {"base": "2026-10", "build": "2026-10b", "states":
# ["CO", "GA", "MO"]}}, and used while "base" is this month's build. It is a fresh build (its own folder, so its own stage-B
# work; the stage-A cache is shared, so unchanged tables aren't read again) that splits only tables not split before. The
# pages publisher (hosp_area.py) republishes a state whenever its newest build is newer than the one its page came from.
BASE, REBUILD = MONTH, {}
if not os.environ.get('ST_BUILD'):
    try:
        import json
        REBUILD = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_rebuild.json'))).get(STB) or {}
        # Oct 18, 2026: a rebuild with "paused" set is skipped entirely (its finished batches stay in R2 for when it resumes)
        if REBUILD.get('paused'): REBUILD = {}
        elif REBUILD.get('base') == MONTH and REBUILD.get('build') and REBUILD.get('states'): MONTH = REBUILD['build']
        else: REBUILD = {}
    except Exception: REBUILD = {}
os.environ['BUILD'] = STB + '-' + MONTH
try: open('/tmp/st_bid', 'w').write(os.environ['BUILD'])   # the workflow reads the build id from here
except Exception: pass
PAGES_WF = 'state-pages.yml' if SCOPE == 's7' else f'{SCOPE}-pages.yml' if SCOPE in ('nc', 'ct') else 'state-builds.yml'   # Oct 18: shared schedule
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestrate as O
from orchestrate import B, s3, log, exists, getj, putj, ls, ensure, free_slots

E = os.environ
SP = O.SP
SIZE = 's-8vcpu-32gb-amd'
SCOPE_STATES = {'s7': {'TN': 'tennessee', 'CO': 'colorado', 'OK': 'oklahoma', 'AL': 'alabama', 'MS': 'mississippi', 'MO': 'missouri', 'GA': 'georgia'},
                'nc': {'NC': 'north-carolina'},   # Oct 16, 2026: North Carolina has its own scope
                'ct': {'CT': 'connecticut'}}   # Oct 16, 2026: Connecticut has its own scope (data/ct/)

# Oct 18, 2026: states on the shared schedule (site/state_scopes.json) are added here, so a new state needs no code edits
try:
    import json as _j
    SCOPE_STATES.update({k: v for k, v in _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_scopes.json'))).items() if not k.startswith('_')})
except Exception: pass
STATES = {k: v for k, v in SCOPE_STATES[SCOPE].items() if not REBUILD or k in REBUILD['states']}
W = dict(WORKERS='4', WMEM='6GB', WTHREADS='2')
# Oct 14 8:20pm CT: Georgia's batches (90-150M rows) don't fit in 6 GB, so its machines spent 60-85% of their time waiting on
# disk (spilling). Georgia machines launched from now on run 2 batches at a time with 13 GB each instead of 4 with 6 GB.
# 10:05pm CT result: worse. The 2 x 13 GB machines were 5-9% busy with 42-67% iowait and landed no batch in 1.5 h, while 4 x 6 GB
# machines were 34-49% busy and landed 7. Back to 4 x 6 GB everywhere (kept as a per-state hook).
_BUNDLED = [False]   # Nov 3, 2026: code bundle refreshed at most once per orchestrator pass (see run())
WBIG = {'georgia': dict(SPLIT='4', WORKERS='1', WMEM='26GB', WTHREADS='8'),
        # Oct 16 11:40am CT (Betsy OK'd): North Carolina's batches are 165-210M rows (Georgia-size). Many took over 2 hours,
        # so the 120-min freeze check restarted 13 machines mid-batch and threw the work away. Split each unfinished batch
        # into 6 pieces (~30M rows, like Georgia's, which fit 4 x 6 GB workers) and allow 4 hours before the check fires.
        'north-carolina': dict(SPLIT='6', STALL_MIN='240'),
        # Oct 31, 2026 (Betsy OK'd): Ohio has Georgia's problem. Its insurer tables are 277 GB for 410k providers (Indiana
        # 120 GB / 157k), so its batches are ~90-100M rows and don't fit a worker's 6 GB: 6 machines landed 1.2 batches an
        # hour (Indiana ~1 a minute per machine) and the price check projected $303. Split each unfinished batch into 4
        # pieces (~25M rows, Indiana-size); finished batches are kept.
        'ohio': dict(SPLIT='4', STALL_MIN='240'),
        # Nov 1, 2026: every Washington helper died with "Out of Memory" (5.5 GB) loading the state's flat-rate list at the
        # start of its first batch (every_code.py FLAT), so 0 of 256 batches landed in 39 hours. One 26 GB worker per machine.
        # Nov 3, 2026: still 0 batches after the FLAT fixes: every machine at 0 GB free and workers killed before their first
        # batch's medians (11 re-claims in 40 min). A 26 GB worker plus the parent and download buffers doesn't fit 32 GB.
        # Smaller pieces (each batch in 4, like Georgia and Ohio) and a 16 GB limit (DuckDB spills the rest to disk).
        # Nov 3, 2026 7 AM CT (Betsy OK'd option 1): test on 2 x 64 GB machines (build_defaults.json "size") with a
        # once-a-minute memory log (every_code.py MEMLOG) to learn whether more memory is enough, and what fills it if not.
        'washington': dict(SPLIT='4', WORKERS='1', WMEM='40GB', WTHREADS='6', STALL_MIN='240', MEMLOG='1')}   # Oct 15 7:20am CT: last 5 pieces (one huge code each?) died twice with 4 x 6 GB workers   # 10:40pm CT: Georgia's unfinished batches split into 4 pieces each (every_code.py SPLIT),
# so each piece (~25-40M rows) fits in a worker's 6 GB like other states' batches. Finished whole batches are kept.
# Oct 14: STALL_MIN 360 (default 60; 180 was still too short: georgia-c5 went 3h12m without its first batch): a Georgia batch takes 60-90 min, so the 60-min freeze check restarted nearly every
# new Georgia machine just before its first batch finished, over and over.
GB_PER_MACHINE, MAX_PER_STATE = 20, 3
RUN_SPLIT = "for t in 1 2 3; do /root/v/bin/python /root/h/tx_split.py >> /root/run.log 2>&1 && break; sleep 5; done"
SPLIT_MACHINES = 4


def sizes(prefix):
    return {o['Key'].rsplit('/', 1)[1][:-8]: o['Size'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=prefix)
            for o in pg.get('Contents', []) if o['Key'].endswith('.parquet')}


# Nov 1, 2026 (Betsy: "do it"): insurers a scope's build doesn't wait for. Geisinger is 3,291 of the Northeast's 3,648 networks,
# its server allows only 2 machines at once (insurers/fleet.py HOST_CAPS), so 10 states sat waiting on one Pennsylvania insurer.
# The build uses every Geisinger network already read; the rest are added later as an update build (state_rebuild.json), the
# way Montana's Mountain Health was added in October.
WAIT_WITHOUT = {'c2': ('Geisinger Health Plan',)}


def s7_busy():
    try: m = s3.get_object(Bucket=B, Key=f'bot/insurers/{SCOPE}/manifest.csv')['Body'].read().decode()
    except Exception: return 1   # Oct 18, 2026: a new state whose files haven't been checked yet counts as busy
    rows = list(csv.DictReader(io.StringIO(m)))
    if not any(r.get('status') == 'processed' for r in rows): return max(1, len(rows))   # nothing read yet: never build empty
    skip = WAIT_WITHOUT.get(SCOPE, ())
    left = [r for r in rows if r.get('status') in ('running', 'queued')]
    n_skip = sum(1 for r in left if r.get('insurer') in skip)
    if n_skip:
        log(f'not waiting for {n_skip} {", ".join(skip)} files still queued or being read (added later as an update)')
    return len(left) - n_skip


def state_npis():
    import duckdb
    s3.download_file(B, f'data/scope/{SCOPE}_npis_all.parquet', '/tmp/s7_npis_all.parquet')
    c, out = duckdb.connect(), {}
    for st, slug in STATES.items():
        c.execute(f"copy (select * from read_parquet('/tmp/s7_npis_all.parquet') where upper(state) = '{st}') to '/tmp/npis_{slug}.parquet' (format parquet, compression zstd)")
        out[slug] = c.execute(f"select count(*) from read_parquet('/tmp/npis_{slug}.parquet')").fetchone()[0]
        if out[slug] < 1000: raise SystemExit(f'STOP: only {out[slug]} providers for {slug}; nothing changed')
    for slug in out: s3.upload_file(f'/tmp/npis_{slug}.parquet', B, f'data/{SCOPE}/state/{slug}/npis.parquet')
    return out


def tout(slug): return f'site/every-st/{slug}/{MONTH}/'
# Oct 18, 2026: "update" rebuilds (state_rebuild.json "mode": "update", "tables": R2 key of a JSON list of table names) build
# ONLY those tables into an add folder outside site/every-st/ (so no page ever picks it up by mistake), then merge_build.py
# merges it into the state's finished build ("from", default its newest) as a complete new build at tout(). The old way
# rebuilt every network of the state (the paused Oct 16 Anthem rebuild).
UPDATE = REBUILD.get('mode') == 'update'
def tadd(slug): return f'site/every-st-add/{slug}/{MONTH}/'
def base_rules(st, slug):
    """Nov 4, 2026: an update build uses the FIELDRULES of the build it merges into ("from", else the state's newest
    finished build), read from that build's build_env.json; '' when it had none. Kept in state.json per state."""
    br = st.setdefault('base_rules', {})
    if slug not in br:
        try:
            pre = f'site/every-st/{slug}/'
            ms = sorted(c['Prefix'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=pre, Delimiter='/') for c in pg.get('CommonPrefixes', []))
            ms = [m for m in ms if m != tout(slug)]
            fr = REBUILD.get('from')
            base = (pre + fr.strip('/') + '/') if fr else next((m for m in reversed(ms) if exists(m + 'embed.json')), None)
            br[slug] = (getj(base + 'build_env.json', {}) or {}).get('env', {}).get('FIELDRULES', '') if base else ''
        except Exception as e:
            log('base build rules not read for', slug, repr(e)[:120]); return ''
    return br[slug]
def tbuild(slug): return tadd(slug) if UPDATE else tout(slug)
def update_tables():
    if not UPDATE: return None
    tf = REBUILD.get('tables_from')
    if tf:   # Oct 25, 2026: the table list taken straight from an area's insurer manifest (no separate R2 file to write)
        import csv as _csv, io as _io
        rows = _csv.DictReader(_io.StringIO(s3.get_object(Bucket=B, Key=tf['manifest'])['Body'].read().decode()))
        tabs = sorted({r['table'] for r in rows if r.get('table') and r.get('status') == 'processed'
                       and r.get('insurer') == tf['insurer'] and (r.get('processed_on') or '') >= tf.get('processed_since', '')})
        # Oct 25, 2026: machines get the list by R2 key (ONLY_KEY), so write it once and point REBUILD['tables'] at it
        key = f"site/builds/{STB}-{MONTH}/update_tables.json"
        s3.put_object(Bucket=B, Key=key, Body=json.dumps(tabs).encode())
        REBUILD['tables'] = key
        return set(tabs)
    return set(json.loads(s3.get_object(Bucket=B, Key=REBUILD['tables'])['Body'].read()))
# Nov 1, 2026 (Betsy OK'd): networks kept off this scope's pages (site/pages_skip.json; Anthem pick list for s7). Read and
# stored as always; the split skips them and the build gets the rest as an ONLY_KEY list (every_code.py already filters by it).
try: PAGE_SKIP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pages_skip.json'))).get(SCOPE, {}).get('networks', [])
except Exception: PAGE_SKIP = []
def page_skip(t): return any(c in t for c in PAGE_SKIP)
def pages_tables_key(slug):
    """Full builds only: R2 list of the state's tables minus page_skip ones, or None when nothing is skipped."""
    if UPDATE or not PAGE_SKIP: return None
    tabs = sorted(sizes(f'data/{SCOPE}/state/{slug}/rates/'))
    keep = [t for t in tabs if not page_skip(t)]
    if len(keep) == len(tabs): return None
    key = f'{SP}{slug}_pages_tables.json'
    s3.put_object(Bucket=B, Key=key, Body=json.dumps(keep).encode())
    log(slug, ': leaving', len(tabs) - len(keep), 'tables off the page (pages_skip.json),', len(keep), 'used')
    return key
def big_waiting(wk):
    """Nov 2, 2026: True when another machine has marked a batch too big (work/.../Bbig/<batch>) and it isn't built yet."""
    try: return any(not exists(f'{wk}B/{k.rsplit("/", 1)[1]}.json') for k in ls(wk + 'Bbig/'))
    except Exception as e: log('big-batch check failed (starting the big machine to be safe):', repr(e)[:150]); return True
def stop_idle_big(st, slug):
    """Nov 2, 2026: shut a state's big-memory machine while no batch waits for it (it only waits, at 0% CPU, and bills).
    The orchestrator starts it again within the hour if a batch is marked too big; its launch count is reset, so these
    planned stops never count as failures."""
    name = f'upfront-site-{O.BID}-{slug}-big'
    for d in O.droplets():
        if d['name'] == name:
            try: O.do('DELETE', f"/droplets/{d['id']}"); log('stopped', name, '(no batch waiting for the big-memory machine)')
            except Exception as e: log('stop failed', name, repr(e)[:150]); return
    st['launches'][f'{slug}-big'] = 0
def pause_for_hold():
    """Nov 2, 2026 (Betsy OK'd): a scope listed in site/month_hold.json "pause_scopes" (the seven-state November rebuild,
    s7: every one of its states already has a live page) stops while the hold is on, even mid-build, so the states not
    live yet get its machines. Its machines are shut down; finished batches stay in R2, and ensure() starts the machines
    again when the hold lifts (only the batch each was on is redone). Returns the builds it is waiting for."""
    try: h = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'month_hold.json')))
    except Exception: return []
    if not h.get('hold') or SCOPE not in h.get('pause_scopes', []): return []
    held = month_hold()
    if not held: return []
    for d in O.droplets():
        if d['name'].startswith(f'upfront-site-{O.BID}-'):
            try: O.do('DELETE', f"/droplets/{d['id']}"); log('paused: stopped', d['name'])
            except Exception as e: log('pause stop failed', d['name'], repr(e)[:150])
    return held
def month_hold():
    """Nov 1, 2026 (Betsy: "pause the rebuild after the current states that are already live"): while the builds listed in
    site/month_hold.json (states not live yet) haven't finished their hospital step, a build that hasn't started ('wait')
    stays waiting. Builds already under way carry on. Releases itself when every listed build is done; returns what's left."""
    try: h = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'month_hold.json')))
    except Exception: return []
    if not h.get('hold') or O.BID in h.get('until_done', []): return []
    left = []
    for bid in h.get('until_done', []):
        try: done = getj(f'site/builds/hosp-{bid}/state.json', {}).get('stage') == 'done'
        except Exception: done = False
        if not done: left.append(bid)
    return left
MERGE_SIZE = 's-4vcpu-8gb'
RUN_MERGE = "for t in 1 2 3; do /root/v/bin/python /root/h/merge_build.py >> /root/run.log 2>&1 && break; sleep 5; done"
CODE_OF = {v: k for k, v in STATES.items()}
def build_defaults():
    """Oct 19, 2026: site/build_defaults.json, the standard settings for new state builds (practice view, batch slicing,
    big-memory machine). Tested on Mississippi, Colorado and Missouri, Oct 18-19."""
    try: return json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_defaults.json')))
    except Exception: return {}


def common_first():
    """Oct 18, 2026: scopes listed in site/common_first.json build their state's 2,000 priority codes (+ every MS-DRG) first;
    every other code is listed on the page as coming and built on request or by the background fill."""
    try: return SCOPE in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common_first.json')))['scopes']
    except Exception: return False


def label_tables(st):
    """Oct 18, 2026: the scope's catalog networks (insurers/networks_<scope>.csv finder "catalog": one network per file, e.g.
    Anthem's and Blue Cross's employer networks) are named by their file label, not split by each provider's product list.
    Table names come from the scope's manifest (they change with each month's file). Written once per build."""
    key = SP + 'label_tables.json'
    if st.get('label_tables_done'): return key
    try:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        nets = os.path.join(here, 'insurers', f'networks_{SCOPE}.csv')
        import re as re_
        blue = re_.compile(r'anthem|blue|bcbs|highmark|premera|regence|wellmark|excellus|carefirst|horizon|hcsc', re_.I)
        # only Blue plans' catalog files: their membership lists each provider's products (UnitedHealthcare's, Cigna's and
        # Aetna's already give one name per network, so they keep their saved stage-A work)
        slots = {r['slot'] for r in csv.DictReader(open(nets)) if r.get('finder') == 'catalog' and blue.search(r.get('insurer', ''))}
        man = s3.get_object(Bucket=B, Key=f'bot/insurers/{SCOPE}/manifest.csv')['Body'].read().decode()
        tabs = sorted({m['table'] for m in csv.DictReader(io.StringIO(man)) if m['slot'] in slots and m.get('table')})
        putj(key, tabs); st['label_tables_done'] = True; log(len(tabs), 'catalog tables named by their file label')
    except Exception as e: log('label table list not written:', repr(e)[:150]); putj(key, [])
    return key


def practice_for(st, slug):
    """Oct 22, 2026: a new build uses the practice view when build_defaults.json says so (st['practice']). An update build
    matches the build it will be merged into (merge_build.py stops on a mix): practice view if that build has a practice
    table. Decided once per state and kept in state.json."""
    if not UPDATE: return bool(st.get('practice'))
    bp = st.setdefault('base_practice', {})
    if slug not in bp:
        base = f"site/every-st/{slug}/{REBUILD['from']}/" if REBUILD.get('from') else None
        if not base:
            best = None
            for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=f'site/every-st/{slug}/', Delimiter='/'):
                for c in pg.get('CommonPrefixes', []):
                    try: t = s3.head_object(Bucket=B, Key=c['Prefix'] + 'embed.json')['LastModified']
                    except Exception: continue
                    if best is None or t > best[0]: best = (t, c['Prefix'])
            base = best[1] if best else None
        try: bp[slug] = bool(base) and 'prac' in json.loads(s3.get_object(Bucket=B, Key=base + 'embed.json')['Body'].read())
        except Exception as e: log(slug, ': could not read the base build to pick its mode:', repr(e)[:120]); return False
        log(slug, ': update build', 'with' if bp[slug] else 'without', 'the practice view, to match', base)
    return bp[slug]


def merge_step(st, left):
    """update mode: one small machine per state whose add build is finished merges it into the state's finished build"""
    def newest(slug):   # same rule as hosp_area.newest_build: the newest folder whose embed.json exists
        best = None
        for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=f'site/every-st/{slug}/', Delimiter='/'):
            for c in pg.get('CommonPrefixes', []):
                try: t = s3.head_object(Bucket=B, Key=c['Prefix'] + 'embed.json')['LastModified']
                except Exception: continue
                if best is None or t > best[0]: best = (t, c['Prefix'])
        return best[1] if best else None
    for slug in left:
        if not exists(tadd(slug) + 'embed.json'): continue
        base = st.setdefault('merge_from', {}).get(slug)
        if not base:
            base = f"site/every-st/{slug}/{REBUILD['from']}/" if REBUILD.get('from') else newest(slug)
            if not base or base == tout(slug): st['problems'].append(f'{slug}: no finished build to merge into'); continue
            st['merge_from'][slug] = base
        # Oct 18, 2026: the merge runs on a free GitHub machine (merge-build.yml); a rented machine only after 2 tries
        md = st.setdefault('merge_dispatch', {}).setdefault(slug, {'n': 0, 'at': 0})
        if md['n'] < 2:
            if time.time() - md['at'] > 6.5 * 3600:   # GitHub ends a job at 6 hours, so a run older than that is over
                r = subprocess.run(['gh', 'workflow', 'run', 'merge-build.yml', '--ref', 'main', '-f', f'base={base}', '-f', f'add={tadd(slug)}',
                                    '-f', f'out={tout(slug)}'], capture_output=True, text=True, timeout=90,
                                   stdin=subprocess.DEVNULL, env=dict(os.environ, GH_PROMPT_DISABLED='1'))
                if r.returncode == 0: md.update(n=md['n'] + 1, at=time.time()); log('merge for', slug, 'started on GitHub (try', md['n'], ')')
                else: log('could not start the GitHub merge for', slug, (r.stderr or r.stdout)[:200]); md['n'] = 2
            continue
        ensure(st, f'{slug}-merge', MERGE_SIZE, RUN_MERGE, dict(BASE=base, ADD=tadd(slug), OUT=tout(slug), PROCS='6'), False)


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
NB, MIN_LEFT, MAX_MACHINES = 256, 10, 24   # Oct 14 11:35pm CT: 12 -> 20 so Tennessee's freed slots go to Georgia
def wk(slug): return f"work/every-st/{slug}/v{MONTH.replace('-', '')}/"
def batches_done(slug):
    """Whole batches done, counting a split batch (pieces k_s.json, every_code.py SPLIT) as done only in proportion."""
    names = [k.rsplit('/', 1)[1][:-5] for k in ls(wk(slug) + 'B/') if k.endswith('.json')]
    whole = {n for n in names if '_' not in n}
    split = int(WBIG.get(slug, {}).get('SPLIT', '1'))
    pieces = [n for n in names if '_' in n and n.split('_')[0] not in whole]
    return len(whole) + (len(pieces) // split if split > 1 else 0)
def rebalance(st, left, run, cap=10**9):
    free = min(free_slots(), cap - sum(st['machines'][x] for x in left))
    if free < 1 or not left: return
    # work left in units a machine takes one at a time: a split state's batches count as SPLIT pieces each
    todo = {s: units_left(s) for s in left}
    while free > 0:
        room = [x for x in left if st['machines'][x] < MAX_MACHINES]
        if not room: break
        s = max(room, key=lambda x: todo[x] / (st['machines'][x] + 1))
        if todo[s] / (st['machines'][s] + 1) < MIN_LEFT: break
        st['machines'][s] += 1; free -= 1
        msg = (f"{time.strftime('%b %d %H:%M')} UTC: free slot -> {s} ({st['machines'][s]} machines, {batches_done(s)} of {NB} batches done"
               f"{', ' + str(todo[s]) + ' pieces left' if int(WBIG.get(s, {}).get('SPLIT', '1')) > 1 else ''})")
        log(msg); st.setdefault('log', []).append(msg)
        run(s, st['machines'][s] - 1)


# Oct 14: a GitHub notice (issue, which GitHub emails to Betsy) as each state finishes, naming where its machines went.
# Announced one run after the state is first seen done, so the freed slots' moves (written by rebalance) are included.
# States finished before this was added were already reported by hand.
ANNOUNCE_FROM = '2026-10-14 21:30'   # UTC
NAMES = {v: v.replace('-', ' ').title() for v in STATES.values()}
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
    still = [f"- {NAMES[x]}: {batches_done(x)} of {NB} batches done, {st['machines'][x]} machines"
             for x in left]
    title = ' + '.join(NAMES[x] for x in new) + (f' done: all {len(STATES)} states built' if len(STATES) > 1 and not left else ' done' if not left else ' done; machines moved on')
    body = '\n'.join([' '.join(f"{NAMES[x]} finished its Price Finder data at {finished_at(x)}." for x in new), '',
                      '**Where the free machines went**', *(['- ' + m for m in moves] or ['- none yet (slots go out on the next runs)']), '',
                      '**Still building**', *(still or ['- nothing: every state is built']), '',
                      'Its Price Finder page goes live as soon as its hospital price files are added.'])
    O.issue(title, body)
    try:   # Oct 15: start the publishing job now (it runs beside this build) instead of at the next hourly run
        import subprocess
        subprocess.run(['gh', 'workflow', 'run', PAGES_WF, '--ref', 'main'], timeout=60, stdin=subprocess.DEVNULL, capture_output=True)
    except Exception as e: log('could not start the page publisher:', repr(e)[:150])
    st['announced'] += new; st['announce_log_i'] = len(st.get('log', []))


# Oct 14: when a state's page data is written (embed.json), its other machines can still be busy for up to an hour on
# batches another machine already finished (Missouri c1, Colorado c1/c2/c4/c5 held 5 slots this way). Shut them down so
# rebalance() hands the slots to the states still building in the same pass.
def release_finished(left):
    for d in O.droplets():
        for slug in STATES.values():
            if slug not in left and (d['name'].startswith(f'upfront-site-{O.BID}-{slug}-c') or d['name'] == f'upfront-site-{O.BID}-{slug}-big'):
                try: O.do('DELETE', f"/droplets/{d['id']}"); log('released', d['name'], '(its state is done)')
                except Exception as e: log('release failed', d['name'], repr(e)[:150])


# Oct 15 (Betsy): each state's page now goes live as soon as that state is built (hosp_area.py state_by_state), which needs a
# hospital machine per finished state. Georgia had every slot, so up to HOSP_SLOTS slots are kept free while finished states
# wait for their pages; the newest machines of the state with the most give them up (stage B has no claims: a stopped
# machine's unfinished pieces are simply done by the others, and every finished piece is kept). They come back afterwards.
HOSP_SLOTS = 3
# Oct 16, 2026: machines launched before a change to their settings (WBIG) keep the old settings until relaunched. A build
# listed here gets its machines created before the cutoff stopped once; ensure() then relaunches them with the new
# settings. Finished stage-B batches stay in R2; only the batch each machine was working on is redone.
RELAUNCH_BEFORE = {'stnc-2026-10': '2026-10-16T16:39:00Z', 'stc3-2026-10': '2026-11-03T06:52:53Z'}   # Nov 2-3, 2026: Washington machines restart on the every_code.py FLAT fixes
def relaunch_old(left):
    cut = RELAUNCH_BEFORE.get(O.BID)
    if not cut: return
    for d in O.droplets():
        if any(d['name'].startswith(f'upfront-site-{O.BID}-{s}-c') for s in left) and d.get('created_at', '9') < cut:
            try: O.do('DELETE', f"/droplets/{d['id']}"); log('relaunching with new settings:', d['name'])
            except Exception as e: log('relaunch stop failed', d['name'], repr(e)[:150])


def hosp_waiting(left):
    h = getj(f'site/builds/hosp-{STB}-{BASE}/state.json', {})   # a rebuild's pages are republished by the month's page build
    pub, frm = h.get('published', {}), h.get('published_from', {})
    return [x for x in STATES.values() if x not in left and (x not in pub or (REBUILD and frm.get(x) != tout(x)))]
def build_cap(left):
    """machines the state builds may use: the account limit, less the orchestrator's reserve and the hospital slots"""
    want = min(HOSP_SLOTS, len(hosp_waiting(left)))
    limit = int(O.do('GET', '/account')['account']['droplet_limit'])
    cap = limit - O.RESERVE - want
    # Oct 18, 2026: machine shares (machine_shares.py) - leave room for waiting insurer files; rebuilds get at most a quarter
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import machine_shares
        cap = min(cap, machine_shares.build_cap(O.BID, limit, O.RESERVE, [d['name'] for d in O.droplets()], s3, B, log) - want)
    except Exception as e: log('machine shares check failed (using the old cap):', repr(e)[:150])
    return max(cap, 1), want
def make_room(st, left, cap):
    while left and sum(st['machines'][x] for x in left) > cap:
        s = max(left, key=lambda x: st['machines'][x])
        if st['machines'][s] <= 1: break
        st['machines'][s] -= 1
        name = f"upfront-site-{O.BID}-{s}-c{st['machines'][s] + 1}"
        for d in O.droplets():
            if d['name'] == name:
                try: O.do('DELETE', f"/droplets/{d['id']}"); log('stopped', name, 'to free a slot for finished states\' hospital pages')
                except Exception as e: log('stop failed', name, repr(e)[:150])


# Oct 15 7:30am CT: Georgia had 24 machines (32 GB each, paid by the hour) for its last 5 pieces, so 19 sat waiting. Once a
# state has fewer units left than machines, its highest-numbered machines are shut down, but only one with no live claim
# (a machine on a piece keeps going; the others would only wait). Units = whole batches, or pieces for a split state.
def units_left(slug):
    names = {k.rsplit('/', 1)[1][:-5] for k in ls(wk(slug) + 'B/') if k.endswith('.json')}
    split = int(WBIG.get(slug, {}).get('SPLIT', '1'))
    if split == 1: return NB - len({n for n in names if '_' not in n})
    return sum(0 if str(k) in names else sum(f'{k}_{s}' not in names for s in range(split)) for k in range(NB))
def live_claims(slug):
    """machines holding a claim under 1.5 h old (BCLAIM_H) on a unit that isn't finished yet"""
    names = {k.rsplit('/', 1)[1][:-5] for k in ls(wk(slug) + 'B/') if k.endswith('.json')}
    fresh, hold = time.time() - 1.5 * 3600, set()
    for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=wk(slug) + 'Bclaim/'):
        for o in pg.get('Contents', []):
            u = o['Key'].rsplit('/', 1)[1]
            if o['LastModified'].timestamp() > fresh and u not in names and u.split('_')[0] not in names:
                hold.add(s3.get_object(Bucket=B, Key=o['Key'])['Body'].read().decode())
    return hold
def fit_to_work(st, left):
    for s in left:
        need = max(1, units_left(s))
        if st['machines'][s] <= need: continue
        hold = live_claims(s)
        while st['machines'][s] > need and f"{s}-c{st['machines'][s]}" not in hold:
            name = f"upfront-site-{O.BID}-{s}-c{st['machines'][s]}"
            st['machines'][s] -= 1
            for d in O.droplets():
                if d['name'] == name:
                    try: O.do('DELETE', f"/droplets/{d['id']}"); log('stopped', name, f'({need} units left for {s})')
                    except Exception as e: log('stop failed', name, repr(e)[:150])


# Oct 18, 2026 (Betsy OK'd): price check (cost_check.py). After 2 hours of building, the build's real speed projects the
# hours and dollars still needed; over $100 or a day without an OK in build_approvals.json, its machines are stopped
# (finished batches stay in R2), a GitHub issue goes out, and the build waits.
def units_total(slug): return NB * int(WBIG.get(slug, {}).get('SPLIT', '1'))
def usd_hour(size):
    try: return float(next(z['price_hourly'] for z in O.do('GET', '/sizes?per_page=200')['sizes'] if z['slug'] == size))
    except Exception: return 0.25
_SIZES = {}
def usd_size(slug):
    if not _SIZES:
        try: _SIZES.update({z['slug']: float(z['price_hourly']) for z in O.do('GET', '/sizes?per_page=200')['sizes']})
        except Exception: pass
    return _SIZES.get(slug, 0.25)
def fleet_rate(st, left):
    """Nov 4, 2026 (code review B3, Betsy OK'd): (machines, dollars per hour) of the build's machines as they really are.
    The check priced every machine at SIZE's rate (32 GB, ~$0.24/h), but Washington's and the big-memory machines are
    64 GB (~$0.59/h), so real spend ran ~2.4-3x what it thought. Live machines are priced by their own size; with none
    running, the plan (st['machines'] per state at that state's size, plus one big-memory machine each) is priced."""
    try:
        ds = [d for d in O.droplets() if d['name'].startswith(f'upfront-site-{O.BID}-')]
        if ds: return len(ds), sum(float((d.get('size') or {}).get('price_hourly') or usd_size(d.get('size_slug'))) for d in ds)
    except Exception: pass
    bd = build_defaults(); n_, usd_ = 0, 0.0
    for s_ in left:
        ps = bd.get('per_state', {}).get(s_, {}); k_ = st['machines'][s_]
        n_ += k_; usd_ += k_ * usd_size(ps.get('size', SIZE))
        if practice_for(st, s_) and bd.get('big_machine', True):
            n_ += 1; usd_ += usd_size(ps.get('big_size', SIZE))
    return n_, usd_
def cost_hold(st, left):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import cost_check as C
    lefts = {s: units_left(s) for s in left}
    # Oct 30, 2026: done counts every state in the build, finished ones included. It used to count only the states still
    # building, so when Wisconsin finished (stn5, Oct 30 00:19 UTC) its 35 batches left the count, California's 53 new
    # batches looked like 18, and the check projected $752 / 231 h (2 batches an hour) while California was really landing
    # ~50 an hour. Finished states add a constant, so they no longer distort the speed.
    done_now = sum(units_total(s) - lefts[s] for s in left) + sum(units_total(s) for s in STATES.values() if s not in left)
    ck = st.setdefault('cost_check', {})
    if 't0' not in ck: ck.update(t0=time.time(), done0=done_now); return False
    h = ck.get('hold')
    # Oct 24, 2026: a hold resumes only when the OK is raised above what it was at the hold (before, any OK on file resumed it
    # at once, so a build held for going over its OK was stopped and restarted in a loop)
    # Oct 30, 2026: ...or when a new OK was given after the hold ("ok_at" in build_approvals.json), even a lower one
    hold_at = ck.get('hold_at') or (ck.get('last') or {}).get('at', '')
    if h and C.approved_usd(O.BID) <= ck.get('hold_ok', 0) and not (C.approved_at(O.BID) > hold_at > ''):
        log('price check: waiting for Betsy\'s OK:', h); return True
    # Oct 18, 2026: the first step (reading the insurer tables, stage A) finishes no batches, so a build still reading at
    # 2 hours looked like "no progress" and was held (st-2026-10c). Now the 2-hour measurement starts with the first
    # finished batch; only a reading step longer than READ_LIMIT_H hours is held.
    # Oct 24, 2026 (Betsy OK'd): until the first batch finishes, wait (no time limit). A build still reading after 6 hours
    # used to be projected at "$inf" and stopped (stn5, stb1); now it is held only if the money already spent passes the OK.
    machines = sum(st['machines'][s] for s in left)
    # Oct 24, 2026: money already spent counts the machines that really exist (the plan in st['machines'] can be far
    # more than machine shares let the build run: stn5 planned 14 and had 1)
    live, rate_ = fleet_rate(st, left)   # Nov 4: dollars per hour of the real machines (sizes differ)
    since = ck.get('spend_t0', ck['t0'])
    v = None
    if not h and not ck.get('b0'):
        if done_now > ck['done0']: ck.update(t0=time.time(), done0=done_now, b0=True); log('price check: first batches in, measuring from now'); return False
        v = C.spent_hold(O.BID, (time.time() - since) / 3600, 1, rate_)
        if not v: return False
    if h:   # approved: start again with fresh launch counts and a fresh measurement
        log('price check: approved for $', C.approved_usd(O.BID), '- resuming')
        st['cost_check'] = {'t0': time.time(), 'done0': done_now, 'approved_after': h, 'spend_t0': time.time()}
        for k in [k for k in st['launches'] if any(k.startswith(s + '-c') for s in left)]: st['launches'].pop(k)
        return False
    proj = None
    if not v:
        proj = C.projection(ck['t0'], ck['done0'], done_now, sum(lefts.values()), 1, rate_)
        v = C.verdict(O.BID, proj)
        if proj is None and v == 'ok' and ck.get('b0'):   # no new batch since the first: hold only on money already spent
            v = C.spent_hold(O.BID, (time.time() - since) / 3600, 1, rate_) or 'ok'
    if proj: ck['last'] = dict(at=time.strftime('%Y-%m-%d %H:%M'), hours_left=round(proj[0], 1) if proj[0] != float('inf') else None,
                               usd_left=round(proj[1]) if proj[1] != float('inf') else None, units_per_hour=round(proj[2], 2))
    if v == 'ok': return False
    ck['hold'] = v; ck['hold_ok'] = C.approved_usd(O.BID); ck['hold_at'] = time.strftime('%Y-%m-%d %H:%M', time.gmtime())
    for d in O.droplets():
        if d['name'].startswith(f'upfront-site-{O.BID}-'):
            try: O.do('DELETE', f"/droplets/{d['id']}"); log('price check: stopped', d['name'])
            except Exception as e: log('stop failed', d['name'], repr(e)[:150])
    per = ', '.join(f"{NAMES.get(s, s)} {units_total(s) - lefts[s]} of {units_total(s)}" for s in left)
    O.issue(f"Price check: {O.BID} paused, needs your OK",
            f"The {O.BID} Price Finder build was stopped: {v}.\n\n"
            f"Work done so far (kept in storage): {per}.\n\n"
            f"To let it finish, tell Claude a new, higher most it may spend (it updates build_approvals.json). "
            f"Or ask Claude to make the data smaller first.")
    log('price check: HOLD', v); return True


def main():
    st = getj(SP + 'state.json', {'stage': 'wait', 'launches': {}, 'problems': []})
    log('state pages build', MONTH, 'stage', st['stage'])
    if st['stage'] == 'wait' and not E.get('FORCE'):
        held = month_hold()
        if held:
            log('new-month build held (site/month_hold.json) until these finish publishing:', ', '.join(held))
            open('/tmp/st_waiting', 'w').write('hold')
            return putj(SP + 'state.json', st)
    if st['stage'] in ('split', 'build') and not E.get('FORCE'):
        held = pause_for_hold()
        if held:
            log('build paused (site/month_hold.json pause_scopes) until these finish publishing:', ', '.join(held))
            st['paused_for_hold'] = True
            open('/tmp/st_waiting', 'w').write('hold')
            return putj(SP + 'state.json', st)
        if st.pop('paused_for_hold', None) or st.get('cost_check', {}).get('resume_reset') is None and '2026-11-03 23:40' <= st.get('cost_check', {}).get('hold_at', '') < '2026-11-04 01:00':
            # Nov 3, 2026: a build paused by the November hold (machines stopped, hours or days) is measured again from
            # the moment it resumes. The price check had counted the paused time as slow progress and as money spent:
            # the seven-state rebuild was held at "$3,571 / 2,041 h" and North Carolina at "$150 over 54.6 h", minutes
            # after the hold lifted. A hold already given for that reason is cleared too (once, resume_reset).
            st['cost_check'] = {'resume_reset': time.strftime('%Y-%m-%d %H:%M')}
            log('price check: measuring again from now (the build was paused by the November hold)')
    if st['stage'] == 'wait':
        busy = s7_busy()
        if busy and not E.get('FORCE'):
            log(busy, SCOPE, 'insurer files still queued or being read; waiting')
            open('/tmp/st_waiting', 'w').write(str(busy))   # Oct 18: the shared schedule ends its run instead of looping for hours
            return putj(SP + 'state.json', st)
        if free_slots() < 2:
            # Oct 18, 2026 (machine shares): tell the insurer reader a build is waiting, so it leaves ST_ROOM slots as its
            # machines finish files (before, a build couldn't start while the reader held every slot)
            putj('bot/fleet/build_wants_room.json', {'build': O.BID, 'at': time.time()})
            log('not enough free machines; waiting (asked the insurer reader to leave room)'); return putj(SP + 'state.json', st)
        O.bundle()
        st.update(stage='split', started=time.strftime('%Y-%m-%d %H:%M'))
        # Oct 19, 2026 (Betsy OK'd): the standard way to build a state, fixed when the build starts so a build in flight keeps
        # its mode (site/build_defaults.json): practice view, big batches sized up front, one big-memory machine per state
        st['practice'] = bool(build_defaults().get('practice')) and not UPDATE
        # Nov 4, 2026: price-field rules (every_code.py FIELDRULES), fixed at the start like the practice view; the value is
        # the build's date, the cutoff for expired rates on every machine. An update build takes its base build's setting
        # per state (base_rules), so the networks it adds follow the same rules as the build they merge into.
        st['fieldrules'] = time.strftime('%Y-%m-%d') if build_defaults().get('fieldrules') and not UPDATE else False
    if st['stage'] == 'split':
        sz = sizes(f'data/{SCOPE}/rates/')
        done = {k.rsplit('/', 1)[1][:-5] for k in ls(f'data/{SCOPE}/state/_done/')}
        # Oct 18, 2026 (Betsy OK'd): an update build splits only its own tables. Before, it split every table not split yet,
        # so st-2026-10c (CO/MO Anthem) spent hours on GA_POHMMED0000, a 44 GB table it doesn't use. Other tables wait for a
        # build that needs them (or a full rebuild).
        need = update_tables()
        def use(t): return (need is None or t in need) and not page_skip(t)   # Nov 1: pages_skip.json tables aren't split either
        if need is not None or PAGE_SKIP:
            todo_all = [t for t in sz if t not in done]
            todo_all and log('not splitting', len([t for t in todo_all if not use(t)]), 'tables this build does not use')
            for key in ('split_jobs', 'back_jobs'):
                for i, job in enumerate(st.get(key, [])):
                    keep = [t for t in job if use(t)]
                    if keep == job: continue
                    log('dropped', [t for t in job if not use(t)], 'from', key)
                    st[key][i] = keep
                    if not [t for t in keep if t not in done]:   # nothing left for that machine: stop it now (it holds a slot)
                        name = f"upfront-site-{O.BID}-split-{i + 1}{'b' if key == 'back_jobs' else ''}"
                        for d in O.droplets():
                            if d['name'] == name:
                                try: O.do('DELETE', f"/droplets/{d['id']}"); log('stopped', name)
                                except Exception as e: log('stop failed', name, repr(e)[:150])
        todo = sorted((t for t in sz if t not in done and use(t)), key=lambda t: -sz[t])
        if 'split_jobs' not in st:
            jobs = [[] for _ in range(min(SPLIT_MACHINES, max(1, len(todo))))]
            for i, t in enumerate(todo): jobs[i % len(jobs)].append(t)
            st['split_jobs'] = [j for j in jobs if j]
        busy = 0
        for i, job in enumerate(st['split_jobs']):
            role = f'split-{i + 1}'
            left = [t for t in job if t not in done]
            finished = not left or (st['launches'].get(role, 0) >= 3 and not O.alive(role))
            ensure(st, role, SIZE, RUN_SPLIT, dict(SCOPE=SCOPE, TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'), finished)
            busy += not finished
        if 'back_jobs' not in st:   # Oct 13: 530 GB on 4 machines is slow; a second machine per list works from the small end
            st['back_jobs'] = [list(reversed(j[1:])) for j in st['split_jobs'] if len(j) > 2]
        for i, job in enumerate(st['back_jobs']):
            role = f'split-{i + 1}b'
            left = [t for t in job if t not in done]
            finished = not left or (st['launches'].get(role, 0) >= 3 and not O.alive(role))
            ensure(st, role, SIZE, RUN_SPLIT, dict(SCOPE=SCOPE, TABLES=','.join(job), MEM='24GB', THREADS='8', WORK='/d'), finished)
            busy += not finished
        log(len(todo), 'of', len(sz), SCOPE, 'tables left to split')
        if not busy:
            st['split_failed'] = todo
            st['providers'] = state_npis()
            only_ = update_tables()   # update mode: size the machines by the new tables only
            st['machines'] = {s: min(MAX_PER_STATE, max(1, -(-sum(v for t, v in sizes(f'data/{SCOPE}/state/{s}/rates/').items() if (only_ is None or t in only_) and not page_skip(t)) // int(GB_PER_MACHINE * 1e9))))
                              for s in STATES.values()}
            st['stage'] = 'build'
            log('providers per state', st['providers'], 'machines', st['machines'])
    if st['stage'] == 'build' and st.get('split_failed') and st.get('split_restarts', 0) < 1 and \
            not any(sizes(f'data/{SCOPE}/state/{s}/rates/') for s in STATES.values()):
        # Oct 24, 2026 (Betsy): n5's split failed on Oct 22 (every table in its job list had been replaced) and every state
        # machine then found no tables and failed 8 times. Start the split again from a fresh listing, once.
        log('split produced no state tables (', len(st['split_failed']), 'failed): splitting again from a fresh table list')
        st['split_restarts'] = st.get('split_restarts', 0) + 1
        for k in ('split_jobs', 'back_jobs', 'split_failed', 'machines'): st.pop(k, None)
        for r in [r for r in st.get('launches', {}) if r.startswith(('split-',) + tuple(f'{s}-' for s in STATES.values()))]:
            st['launches'].pop(r)
        st['problems'] = [p for p in st.get('problems', []) if not any(p.startswith(s + '-') for s in STATES.values())]
        O.bundle()   # n5's Oct 22 bundle lacked state_scopes.json (fixed e08cb5f): machines get today's code
        st['stage'] = 'split'
    if st['stage'] == 'build':
        left = [slug for slug in STATES.values() if not exists(tout(slug) + 'embed.json')]
        final_left = left
        if UPDATE:   # states whose add build is done move to the merge step; the batch machinery below sees the rest
            merge_step(st, left)
            left = [slug for slug in left if not exists(tadd(slug) + 'embed.json')]
        try:
            if left and cost_hold(st, left): return putj(SP + 'state.json', st)
        except Exception as e: log('price check failed (build goes on):', repr(e)[:200])
        # Oct 16: AORDER=desc: biggest tables first, so the machines share them early. North Carolina's build read them
        # last (smallest first), and its last ~2 hours went to the two Blue Cross NC tables (75 and 95 pieces).
        def run(slug, i):
                n = st['machines'][slug]
                env = dict(RATES=f'data/{SCOPE}/state/{slug}/rates/', NPIS=f'data/{SCOPE}/state/{slug}/npis.parquet', TOUT=tbuild(slug),
                           OUTP=f'{SP}{slug}-c{i + 1}/', WK=f"work/every-st/{slug}/v{MONTH.replace('-', '')}/",
                           ACACHE=f'work/every-st/{slug}/Acache/', NOXPART='1', ACLAIM='1', PIECE_GB='0.4', MAXPIECES='3', THREADS='6',
                           MEM='18GB', WORK='/d', AORDER='desc', ASTART=str(i * 5), BSTART=str(i * NB // n), STALL_MIN='120', BCLAIM='1', BCLAIM_H='1.5',   # Oct 15 6am: pieces take 20-50 min, so 120 min / 1.5 h catch lost work (360 left 28 pieces waiting)
)
                env.update({**W, **WBIG.get(slug, {})})   # per-state settings win (STALL_MIN, SPLIT, workers)
                env['LABEL_TABLES_KEY'] = label_tables(st)
                fr_ = base_rules(st, slug) if UPDATE else st.get('fieldrules')
                if fr_: env['FIELDRULES'] = fr_ if isinstance(fr_, str) else '1'
                if common_first() and not UPDATE:   # Oct 18: common codes first (priority list + DRGs, the rest listed as coming)
                    env.update(PHASE='1', PRIORITY_KEY=f'site/priority/{CODE_OF[slug]}.json')
                if not UPDATE:   # Nov 1: pages_skip.json networks left out (the list is written once per state)
                    pk = st.setdefault('pages_tables', {}).get(slug)
                    if pk is None: pk = st['pages_tables'][slug] = pages_tables_key(slug) or ''
                    if pk: env['ONLY_KEY'] = pk
                if UPDATE:
                    if 'tables' not in REBUILD: update_tables()   # tables_from: writes the list to R2 first
                    env['ONLY_KEY'] = REBUILD['tables']
                    if REBUILD.get('nets_from_label'): env['NETS_FROM_LABEL'] = '1'
                bd = build_defaults(); ps = bd.get('per_state', {}).get(slug, {})   # per-state settings win
                if practice_for(st, slug):
                    env.update(PRACTICE='1', SLICE_ROWS=str(ps.get('slice_rows', bd.get('slice_rows', 30000000))))
                # Nov 3, 2026 (Betsy OK'd, Washington option 1): a state can ask for a different machine size
                # (build_defaults.json per_state "size"). A running machine of the old size is stopped once, so
                # the next step relaunches it at the new size; the planned swap never counts as a failure.
                want = ps.get('size', SIZE); name = f'upfront-site-{O.BID}-{slug}-c{i + 1}'
                # Nov 3, 2026: a new size gives every slot a clean start once. washington-c3..c6 had "failed 8 times"
                # on 32 GB machines, so ensure() refused them even after the 64 GB fix and the state stayed at 2.
                sz = st.setdefault('size_reset', {})
                if want != SIZE and sz.get(f'{slug}-c{i + 1}') != want:
                    sz[f'{slug}-c{i + 1}'] = want; st['launches'][f'{slug}-c{i + 1}'] = 0
                    st['problems'] = [p for p in st.get('problems', []) if not p.startswith(f'{slug}-c{i + 1} ')]
                for d in O.droplets():
                    if d['name'] == name and d.get('size_slug') and d['size_slug'] != want:
                        try: O.do('DELETE', f"/droplets/{d['id']}"); log('resized', name, d['size_slug'], '->', want, '(stopped; relaunching)')
                        except Exception as e: log('resize stop failed', name, repr(e)[:150])
                        st['launches'][f'{slug}-c{i + 1}'] = 0
                # Nov 3, 2026: the machines' code bundle was only made when the build started, so code fixes pushed
                # mid-build (Washington's two flat-rate fixes overnight) never reached relaunched machines. Like
                # hosp_area.py: refresh it once per pass before (re)launching a machine, so it runs today's code.
                if not _BUNDLED[0] and not O.alive(f'{slug}-c{i + 1}'): O.bundle(); _BUNDLED[0] = True
                ensure(st, f'{slug}-c{i + 1}', want, O.RUN_INS, env, False)
                if practice_for(st, slug) and i == 0 and build_defaults().get('big_machine', True):
                    # one big-memory machine per state: it builds only the batches the others mark as too big (one huge code)
                    big = {k_: v_ for k_, v_ in env.items() if k_ not in ('BCLAIM', 'BCLAIM_H', 'SPLIT')}
                    big.update(BIG='1', WORKERS='1', WMEM=ps.get('big_mem', '24GB'), WTHREADS='8', STALL_MIN='240', OUTP=f'{SP}{slug}-big/')
                    # Nov 2, 2026 (Betsy OK'd): start it only when a batch is actually waiting for it. Before, it sat idle
                    # for days (Washington's 62 hours at 0% CPU), billing and holding a machine slot the state needed.
                    if big_waiting(env['WK']): ensure(st, f'{slug}-big', ps.get('big_size', SIZE), O.RUN_INS, big, False)
                    else: stop_idle_big(st, slug)
        release_finished(left)
        relaunch_old(left)
        # Oct 24, 2026 (Betsy OK'd): a build with a floor (site/build_floors.json) tells the insurer machines how many
        # slots it is still short; they step aside between files (insurers/worker.py) and fill() leaves those slots free.
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import machine_shares
            fl = machine_shares.floor(O.BID)
            if fl:
                live = sum(1 for d in O.droplets() if d['name'].startswith(f'upfront-site-{O.BID}-'))
                fs = getj('bot/fleet/build_floor.json', {})
                fs[O.BID] = {'floor': fl, 'live': live, 'short': max(0, fl - live - max(free_slots(), 0)),
                             'at': time.time(), 'gen': int(time.time() // 1800)}
                putj('bot/fleet/build_floor.json', fs)
                log(f'floor: {live} of {fl} machines; asking insurer machines for {fs[O.BID]["short"]} slot(s)')
        except Exception as e: log('floor note failed:', repr(e)[:150])
        cap, held = build_cap(left)
        make_room(st, left, cap)
        fit_to_work(st, left)
        if held: log(held, 'slot(s) kept for finished states\' hospital pages')
        for slug in left:
            for i in range(st['machines'][slug]): run(slug, i)
        rebalance(st, left, run, cap)
        try: announce(st, left)   # a failed notice must never stop the build from saving its state
        except Exception as e: log('notice failed:', repr(e)[:200])
        log('states still building:', ', '.join(left) or 'none', '| merging:', ', '.join(x for x in final_left if x not in left) or 'none')
        if not final_left: st['stage'] = 'hosp'; lift_pause()
    if st['stage'] == 'hosp':
        lift_pause()
        log('insurer builds done; the hospital step (hosp_area.py, HOSP_SCOPE=s7 or nc) builds hospitals and publishes the pages')
    putj(SP + 'state.json', st)


if __name__ == '__main__':
    main()
