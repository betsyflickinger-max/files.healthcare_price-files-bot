"""Hospital price files for the Texas city and metro Price Finder pages (Oct 13, 2026). Until now only DFW had them.

  python site/hosp_area.py run        GitHub runner (.github/workflows/hosp-areas.yml), every run moves the build one step
  python site/hosp_area.py h2 AREA..  on a rented machine: per-code hospital files for those areas

Build id hosp-tx-YYYY-MM; state in R2 site/builds/<id>/state.json. Stages:
  plan     every Texas hospital with a saved price file (data/hospitals.csv: last_key, last_sha256) is placed in a page's area
           by its ZIP code (Medicare's Hospital General Information file, by CCN): DFW/Houston/San Antonio/Austin/El Paso by
           3-digit ZIP (as tx_split.py), every other ZIP by reference/geo/tx_zip_metro.csv, else small-towns. DFW is skipped
           (the monthly refresh builds its hospitals). Files not parsed before go on the parse list.
  parse    hosp_every.py on rented machines (shared cache data/hosp_every/rows/<sha16>.parquet, same as the DFW refresh).
  h2       h2_build.py per area on rented machines, using the area's newest insurer build for its code list. Output next to
           that build: site/every-tx/<area>/<build>/hosp/h/<code>.txt and hosp/hosp_index.json.
  publish  city_page.py <area> --deploy, which now picks up hosp/hosp_index.json and serves hosp/h/ (one area per call).
Nothing is averaged; every hospital line keeps its file and line number (h2_build.py rules).
HOSP_SCOPE=s7 (state pages, Oct 13, 2026): build id hosp-st-YYYY-MM, one area per state of the first national batch (by the
hospital's state in data/hospitals.csv), next to each state's insurer build under site/every-st/<state>/.
"""
import csv, io, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
HGI = ('https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1785189955/'
       'Hospital_General_Information.csv')   # Medicare Hospital General Information, July 22, 2026 (Facility ID, ZIP Code)
BIG = [('750', '753', 'dfw'), ('760', '762', 'dfw'), ('770', '775', 'houston'), ('780', '782', 'san-antonio'),
       ('786', '787', 'austin'), ('798', '799', 'el-paso')]
SOLO = {'houston', 'san-antonio', 'austin', 'georgia', 'missouri', 'tennessee', 'north-carolina', 'connecticut', 'illinois'}   # big areas get a machine each; the rest share
SCOPE_STATES = {'s7': {'TN': 'tennessee', 'CO': 'colorado', 'OK': 'oklahoma', 'AL': 'alabama', 'MS': 'mississippi', 'MO': 'missouri', 'GA': 'georgia'},
                'nc': {'NC': 'north-carolina'},   # Oct 16, 2026: North Carolina has its own scope
                'ct': {'CT': 'connecticut'}}   # Oct 16, 2026: Connecticut has its own scope (data/ct/)

# Oct 18, 2026: states on the shared schedule (site/state_scopes.json) are added here, so a new state needs no code edits
try:
    import json as _j
    SCOPE_STATES.update({k: v for k, v in _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_scopes.json'))).items() if not k.startswith('_')})
except Exception: pass
HSCOPE = os.environ.get('HOSP_SCOPE', '')
S7 = HSCOPE in SCOPE_STATES   # a state scope (s7 or nc), not the Texas areas
STATES = SCOPE_STATES.get(HSCOPE, SCOPE_STATES['s7'])
STATE_SLUGS = {v for d in SCOPE_STATES.values() for v in d.values()}
STB = 'st' if HSCOPE in ('', 's7') else 'st' + HSCOPE   # build ids: st-YYYY-MM / hosp-st-YYYY-MM, stnc-YYYY-MM / hosp-stnc-YYYY-MM


def s3c():
    import boto3
    E = os.environ
    return boto3.client('s3', endpoint_url=f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com",
                        aws_access_key_id=''.join(E['R2_ACCESS_KEY_ID'].split()),
                        aws_secret_access_key=''.join(E['R2_SECRET_ACCESS_KEY'].split()), region_name='auto')


def newest_build(s3, B, area):
    """same rule as city_page.py: the newest site/every-tx/<area>/<build>/ whose embed.json exists"""
    root = 'site/every-st/' if area in STATE_SLUGS else 'site/every-tx/'
    dirs = [c['Prefix'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=f'{root}{area}/', Delimiter='/')
            for c in pg.get('CommonPrefixes', [])]
    best = None
    for d in dirs:
        try: t = s3.head_object(Bucket=B, Key=d + 'embed.json')['LastModified']
        except Exception: continue
        if best is None or t > best[0]: best = (t, d)
    return best[1] if best else None


# ---------------------------------------------------------------- rented machine
def h2(areas):
    s3, B = s3c(), os.environ['R2_BUCKET']
    SP = os.environ['SP']
    plan = json.loads(s3.get_object(Bucket=B, Key=SP + 'areas.json')['Body'].read())
    for area in areas:
        t0 = time.time()
        a = plan[area]
        d = f'/d/{area}'; os.makedirs(f'{d}/rows', exist_ok=True)
        have = 0
        for j in a['jobs']:
            try: s3.download_file(B, 'data/hosp_every/rows/' + j['id'] + '.parquet', f"{d}/rows/{j['id']}.parquet"); have += 1
            except Exception: print(area, 'no parsed rows for', j['name'], flush=True)
        if not have:   # no hospital files left (Oct 15: e.g. its only file was another hospital's): drop the old index too
            try: s3.delete_object(Bucket=B, Key=a['prefix'] + 'hosp/hosp_index.json')
            except Exception: pass
            s3.put_object(Bucket=B, Key=SP + f'h2/{area}.done', Body=json.dumps({'files': 0}).encode()); continue
        s3.download_file(B, a['prefix'] + 'embed.json', f'{d}/embed.json')
        codes = json.load(open(f'{d}/embed.json'))['codes']
        open(f'{d}/page.html', 'w').write('<script type="application/json" id="data">' +
                                          json.dumps({'codes': codes, 'hosp': {'src': []}}) + '</script>')
        env = dict(os.environ, AREA=area, UPLOAD='1', HKEY=a['prefix'] + 'hosp/h/', NP=os.environ.get('NP', '8'), MEM=os.environ.get('MEM', '11GB'))
        r = subprocess.run([sys.executable, f'{HERE}/h2_build.py', f'{d}/rows/*.parquet', f'{HERE}/payer_name_mapping.csv',
                            f'{d}/page.html', f'{d}/out'], env=env)
        if r.returncode:
            print(area, 'h2_build failed', flush=True); continue
        s3.upload_file(f'{d}/out/hosp_index.json', B, a['prefix'] + 'hosp/hosp_index.json')
        n = len(json.load(open(f'{d}/out/hosp_index.json'))['src'])
        s3.put_object(Bucket=B, Key=SP + f'h2/{area}.done', Body=json.dumps({'files': n, 'secs': round(time.time() - t0)}).encode())
        subprocess.run(['rm', '-rf', d])
        print(area, 'done', n, 'hospital files', round(time.time() - t0), 's', flush=True)


# ---------------------------------------------------------------- GitHub runner
def plan_areas(O):
    import requests
    zips = {r['Facility ID']: r['ZIP Code'].strip()[:5]
            for r in csv.DictReader(io.StringIO(requests.get(HGI, timeout=300).content.decode('utf-8-sig')))}
    metro = {r['zip5']: r['slug'] for r in csv.DictReader(open(f'{HERE}/../reference/geo/tx_zip_metro.csv'))}
    def area(z):
        for lo, hi, a in BIG:
            if lo <= z[:3] <= hi: return a
        return metro.get(z, 'small-towns')
    # Oct 15, 2026: each hospital's file is the one the daily run has now (R2 bot/manifest/hospitals + files), else the
    # October file in data/hospitals.csv; a file ruled another hospital's (bot/identity.py) is left off.
    sys.path.insert(0, f'{HERE}/../bot')
    import identity
    wrong = identity.load(O.s3, O.B)
    cur, nfix, nnew = {}, 0, 0
    for st_ in (['TX'] if not S7 else list(STATES)):
        def rd(k):
            try: return list(csv.DictReader(io.StringIO(O.s3.get_object(Bucket=O.B, Key=k)['Body'].read().decode())))
            except Exception: return []
        files = {f['url']: f for f in rd(f'bot/manifest/files/{st_}.csv')}
        for m in rd(f'bot/manifest/hospitals/{st_}.csv'):
            f = files.get(m.get('mrf_url', ''))
            if f and f.get('sha256') and f.get('r2_key') and m.get('status') != identity.WRONG_STATUS:
                cur[m['ccn']] = (m['mrf_url'], f['r2_key'], f['sha256'])
    areas, nozip = {}, 0
    for r in csv.DictReader(open(f'{HERE}/../data/hospitals.csv')):
        if (r['state'] == 'TX') == S7 or r['state'] != 'TX' and not (S7 and r['state'] in STATES): continue
        if r['ccn'] in cur:
            u_, k_, h_ = cur[r['ccn']]
            if h_[:16] != (r.get('last_sha256') or '')[:16]: nnew += 1
            r = dict(r, mrf_url=u_, last_key=k_, last_sha256=h_)
        if not r['last_key'] or not r['last_sha256']: continue
        if identity.is_wrong(wrong, r['ccn'], r['mrf_url']): nfix += 1; continue
        z = zips.get(r['ccn'], '')
        if not z and not S7: nozip += 1; continue
        a = STATES[r['state']] if S7 else area(z)
        if a == 'dfw': continue
        j = dict(id=r['last_sha256'][:16], key=r['last_key'], url=r['mrf_url'], name=r['name'].title(), ccn=r['ccn'], zip=z)
        if all(x['id'] != j['id'] for x in areas.setdefault(a, [])): areas[a].append(j)
    out = {}
    for a, jobs in sorted(areas.items()):
        p = newest_build(O.s3, O.B, a)
        if not p and S7: p = f"site/every-st/{a}/{O.BID.split('-', 2)[2]}/"   # the state's insurer build is still running; same folder
        if p: out[a] = dict(prefix=p, jobs=jobs)
        else: O.log('no insurer build for', a, '- skipped')
    O.log(sum(len(v['jobs']) for v in out.values()), 'hospital files in', len(out), 'areas;', nozip, 'saved files with no Medicare ZIP;',
          nnew, 'newer than October;', nfix, "left off as another hospital's file")
    return out


def fix_names(O, prefix):
    """Hospital names as the page shows them. Some systems put only the system name in every file (six Austin files said just
    "Ascension Seton", no city). When a file's name is shared by another file in the area, or it has no city, use Medicare's
    name and city for that hospital (data/hospitals.csv, matched by the file's fingerprint). Safe to run again."""
    key = prefix + 'hosp/hosp_index.json'
    try: H = json.loads(O.s3.get_object(Bucket=O.B, Key=key)['Body'].read())
    except Exception: return
    # Oct 15, 2026: never name a file after a hospital it was ruled not to belong to (bot/identity.py); when several hospitals
    # share a file, the one the build planned it for (its job's CCN) wins
    sys.path.insert(0, f'{HERE}/../bot')
    import identity
    wrong = identity.load(O.s3, O.B)
    plan = {j['id']: j['ccn'] for a in O.getj(O.SP + 'areas.json', {}).values() for j in a['jobs']}
    cms = {}
    for r in csv.DictReader(open(f'{HERE}/../data/hospitals.csv')):
        k = r['last_sha256'][:16]
        if not k or identity.is_wrong(wrong, r['ccn'], r['mrf_url']): continue
        if k not in cms or plan.get(k) == r['ccn']: cms[k] = (r['name'], r['city'])
    from collections import Counter
    n = Counter((x[0] or '').strip().lower() for x in H['src'])
    fixed = 0
    for x in H['src']:
        if x[5] in cms and (not x[1] or n[(x[0] or '').strip().lower()] > 1):
            nm, ct = cms[x[5]]
            if nm:
                t = ' '.join(nm.split()).title().replace("'S ", "'s ")
                for w in (' Of ', ' At ', ' The ', ' And ', ' For '): t = t.replace(w, w.lower())
                x[0], x[1] = t.replace(' Tx', ' TX').replace('Llc', 'LLC'), ' '.join((ct or '').split()).title(); fixed += 1
    if fixed:
        O.s3.put_object(Bucket=O.B, Key=key, Body=json.dumps(H, separators=(',', ':')).encode())
        O.log('hospital names:', fixed, 'of', len(H['src']), 'files named from Medicare\'s list in', prefix)


def run():
    os.environ.setdefault('BUILD', (f'hosp-{STB}-' if S7 else 'hosp-tx-') + time.strftime('%Y-%m'))
    sys.path.insert(0, HERE)
    import orchestrate as O
    SP = O.SP
    # Oct 13: the state pages' hospital files are parsed while the insurer builds still run (plan + parse need no insurer
    # build); h2 and publish wait for orchestrate_states.py to reach its 'hosp' stage
    ready = not S7 or O.getj(f"site/builds/{STB}-{O.BID.split('-', 2)[2]}/state.json", {}).get('stage') == 'hosp'
    st = O.getj(SP + 'state.json', {'stage': 'plan', 'launches': {}, 'problems': [], 'published': {}})
    O.log('hospital build', O.BID, 'stage', st['stage'], '' if ready else '(insurer builds still running: parse only)')
    if st['stage'] == 'plan':
        areas = plan_areas(O)
        O.putj(SP + 'areas.json', areas)
        cached = {k.rsplit('/', 1)[1][:-8] for k in O.ls(O.HPFX + 'rows/')}
        todo, seen = [], set()
        for a in areas.values():
            for j in a['jobs']:
                if j['id'] not in cached and j['id'] not in seen: seen.add(j['id']); todo.append(j)
        todo.sort(key=lambda j: j['id'])
        O.putj(SP + 'todo.json', todo)
        O.bundle()
        st.update(stage='parse', shards=min(8, max(1, len(todo) // 20)), todo=len(todo), areas=sorted(areas))
        O.log(len(todo), 'hospital files to parse on', st['shards'], 'machines')
    if st['stage'] == 'parse':
        todo = O.getj(SP + 'todo.json', [])
        hdone = {k.rsplit('/', 1)[1][:-5] for k in O.ls(O.HPFX + 'done/')}
        busy = 0
        for sh in range(st['shards']):
            role = f'hosp{sh}'
            left = [j for j in todo[sh::st['shards']] if j['id'] not in hdone]
            finished = not left or (st['launches'].get(role) and not O.alive(role))   # a machine that ended leaves its failures
            O.ensure(st, role, O.SIZE_HOSP, O.RUN_HOSP, dict(JOBS_KEY=SP + 'todo.json', SHARD=str(sh), SHARDS=str(st['shards']),
                                                             HPFX=O.HPFX), finished)
            busy += not finished
        failed = [j['name'] for j in todo if j['id'] not in hdone]
        O.log('parse:', len(todo) - len(failed), 'of', len(todo), 'files parsed;', busy, 'machines working')
        if not busy:
            st['parse_failed'] = failed; st['stage'] = 'h2'
    if S7 and st['stage'] in ('h2', 'publish', 'done'):   # 'done': still checks for a newer insurer build to republish
        return state_by_state(O, st)
    if st['stage'] == 'h2' and not ready:
        O.log('hospital files parsed; waiting for the state insurer builds before building each state\'s hospital pages')
    if st['stage'] == 'h2' and ready:
        areas = st['areas']
        small = [a for a in areas if a not in SOLO]
        groups = [[a] for a in areas if a in SOLO] + [small[i::4] for i in range(4) if small[i::4]]
        done = {k.rsplit('/', 1)[1][:-5] for k in O.ls(SP + 'h2/')}
        busy = 0
        for i, g in enumerate(groups):
            role = f'h2-{i}'
            finished = all(a in done for a in g) or (st['launches'].get(role) and not O.alive(role))
            O.ensure(st, role, O.SIZE_H2, f"/root/v/bin/python /root/h/hosp_area.py h2 {' '.join(g)} >> /root/run.log 2>&1",
                     dict(SP=SP, NP='8', MEM='11GB'), finished)
            busy += not finished
        O.log('h2:', len([a for a in areas if a in done]), 'of', len(areas), 'areas built;', busy, 'machines working')
        if not busy: st['stage'] = 'publish'
    if st['stage'] == 'done' and not st.get('names_fixed'): st['stage'] = 'publish'
    if st['stage'] == 'publish':
        if not st.get('names_fixed'):   # Oct 13: pages published before the name fix go out again
            st['published'], st['names_fixed'] = {}, True
        done = {k.rsplit('/', 1)[1][:-5]: k for k in O.ls(SP + 'h2/')}
        t0 = time.time()
        for a in st['areas']:
            if a in st['published'] or a not in done: continue
            if time.time() - t0 > 3 * 3600: break   # the rest go on the next run
            fix_names(O, st['plan_prefix'][a] if 'plan_prefix' in st else O.getj(SP + 'areas.json', {})[a]['prefix'])
            r = subprocess.run([sys.executable, f'{HERE}/city_page.py', a, '--deploy', '--out', f'/tmp/city-{a}'],
                               capture_output=True, text=True, timeout=3600)
            print(r.stdout[-1200:], r.stderr[-1200:], flush=True)
            st['published'][a] = 'live with hospitals' if r.returncode == 0 else 'failed: kept the page without hospitals'
            O.putj(SP + 'state.json', st)
        if all(a in st['published'] for a in st['areas'] if a in done):
            st['stage'] = 'done'
            O.log('published:', st['published'])
    O.putj(SP + 'state.json', st)


def redo(areas):
    """Oct 15, 2026: take files ruled another hospital's (bot/identity.py) off some areas' pages now, without waiting for the
    next monthly build. Drops those files from the build's areas.json and clears the areas' h2 and publish marks, so the
    next runs of hosp-areas.yml (same BUILD / HOSP_SCOPE) rebuild and republish just them. New files come with the next build.
    Usage: BUILD=hosp-tx-2026-10 python site/hosp_area.py redo houston odessa ...   (HOSP_SCOPE=s7 for state pages)"""
    os.environ.setdefault('BUILD', (f'hosp-{STB}-' if S7 else 'hosp-tx-') + time.strftime('%Y-%m'))
    sys.path.insert(0, HERE); sys.path.insert(0, f'{HERE}/../bot')
    import orchestrate as O, identity
    wrong = identity.load(O.s3, O.B)
    plan, st = O.getj(O.SP + 'areas.json', {}), O.getj(O.SP + 'state.json', {})
    for a in areas:
        if a not in plan: O.log(a, 'is not in build', O.BID); continue
        before = len(plan[a]['jobs'])
        plan[a]['jobs'] = [j for j in plan[a]['jobs'] if not identity.is_wrong(wrong, j['ccn'], j['url'])]
        O.log(a, before - len(plan[a]['jobs']), "file(s) taken off as another hospital's;", len(plan[a]['jobs']), 'left')
        try: O.s3.delete_object(Bucket=O.B, Key=O.SP + f'h2/{a}.done')
        except Exception: pass
        st.get('published', {}).pop(a, None)
        st.get('launches', {}).pop(f'h2-{a}', None)
    if not S7:   # Texas areas share machines in groups: let every group whose areas are all still built count as finished
        st['launches'] = {k: v for k, v in st.get('launches', {}).items() if not k.startswith('h2-')}
    st['stage'] = 'h2'
    O.putj(O.SP + 'areas.json', plan); O.putj(O.SP + 'state.json', st)
    O.log('next hosp-areas.yml runs with BUILD', O.BID, 'rebuild and republish', ', '.join(areas))


IDLE = '/tmp/hosp_idle'   # the workflow stops looping (and frees the site-build lock) when this exists


def publish_one(O, st, a, how):
    fix_names(O, O.getj(O.SP + 'areas.json', {})[a]['prefix'])
    r = subprocess.run([sys.executable, f'{HERE}/city_page.py', a, '--deploy', '--out', f'/tmp/city-{a}'],
                       capture_output=True, text=True, timeout=3600)
    print(r.stdout[-1200:], r.stderr[-1200:], flush=True)
    st['published'][a] = how if r.returncode == 0 else 'failed: page not published (see this run\'s log)'
    st.setdefault('published_from', {})[a] = newest_build(O.s3, O.B, a)
    O.log('published', a, '->', st['published'][a])
    O.putj(O.SP + 'state.json', st)


def state_by_state(O, st):
    """Oct 15, 2026 (Betsy): each state's page goes live as soon as that state's insurer build is done, instead of all seven
    waiting for the slowest (Georgia). A state is ready when site/every-st/<state>/<YYYY-MM>/embed.json exists. Each ready
    state gets its own hospital machine (h2-<state>, 2 tries); when its hospital files are built it is published at once. If
    its hospital machine fails twice, the page still goes live with insurer rates only and the run says so."""
    SP, month = O.SP, O.BID.split('-', 2)[2]
    st['names_fixed'] = True   # state pages were never published before the name fix; fix_names runs before each publish
    areas = st['areas']
    # Oct 16, 2026: a state rebuilt after the month's build (orchestrate_states.py rebuild, e.g. new Anthem tables) has a newer
    # insurer build than the one its page was published from: rebuild its hospital files next to it and publish it again.
    # Pages published before this was added count as published from their newest build at the first check.
    frm = st.setdefault('published_from', {})
    for a in areas:
        if a not in st['published']: continue
        nb = newest_build(O.s3, O.B, a)
        if a not in frm: frm[a] = nb; continue
        if nb and nb != frm[a]:
            O.log(a, 'has a newer insurer build', nb, 'than its page (', frm[a], '): rebuilding its hospital files and publishing it again')
            st['published'].pop(a, None); st['launches'].pop(f'h2-{a}', None); st['stage'] = 'h2'
            try: O.s3.delete_object(Bucket=O.B, Key=SP + f'h2/{a}.done')
            except Exception: pass
    ready = [a for a in areas if O.exists(f'site/every-st/{a}/{month}/embed.json')]
    done = {k.rsplit('/', 1)[1][:-5] for k in O.ls(SP + 'h2/')}
    busy = 0
    for a in ready:
        if a in st['published']: continue
        role = f'h2-{a}'
        gave_up = st['launches'].get(role, 0) >= 2 and not O.alive(role)
        O.ensure(st, role, O.SIZE_H2, f"/root/v/bin/python /root/h/hosp_area.py h2 {a} >> /root/run.log 2>&1",
                 dict(SP=SP, NP='8', MEM='11GB'), a in done or gave_up)
        if a in done: publish_one(O, st, a, 'live with hospitals')
        elif gave_up: publish_one(O, st, a, 'live, insurer rates only: its hospital machine failed twice')
        else: busy += 1
    waiting = [a for a in areas if a not in ready]
    O.log('state pages:', len(st['published']), 'of', len(areas), 'published;', busy, 'hospital machines working;',
          'insurer build still running for ' + ', '.join(waiting) if waiting else 'every state built')
    if all(a in st['published'] for a in areas):
        st['stage'] = 'done'; O.log('published:', st['published'])
    elif not busy:
        open(IDLE, 'w').write('waiting for ' + ', '.join(waiting))   # nothing to do until another state's build finishes
    O.putj(SP + 'state.json', st)


if __name__ == '__main__':
    if sys.argv[1] == 'redo': redo(sys.argv[2:])
    elif sys.argv[1] == 'h2': h2(sys.argv[2:])
    else: run()
