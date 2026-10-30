"""Monthly website refresh, run by .github/workflows/site-build.yml every 6 hours.

One build per month (build id = YYYY-MM). State lives in R2 site/builds/<id>/state.json. Stages:
  wait     start once it is the 8th or later (insurers post early in the month; the insurer bot needs a few days),
           no DFW insurer file is still being read, and there are free machines (always leaves RESERVE free)
  build1   rented machines: every_code.py over data/full/rates (2 machines, opposite ends), and hosp_every.py over
           the DFW hospital files that changed since last month (unchanged files reuse last month's rows)
  build2   one machine: h2_build.py -> per-code hospital files + hosp_index.json
  publish  on the GitHub runner: merge into the page, run check_build.py against the live page, point
           site/every/CURRENT at the new build and deploy with wrangler. If a check fails: nothing goes live, an issue opens.
Dead machines are relaunched (up to 3 times per role). Machines delete themselves when done.
Env: R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET DIGITALOCEAN_TOKEN [CLOUDFLARE_API_TOKEN] [FORCE=1] [BUILD=YYYY-MM]"""
import csv, io, json, os, subprocess, sys, tarfile, time, urllib.request
import boto3

E = os.environ
for _k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET', 'DIGITALOCEAN_TOKEN', 'CLOUDFLARE_API_TOKEN'):
    if _k in E:  # pasted secrets can carry a line break; strip it (same as bot/store.env) so every step and machine gets clean values
        E[_k] = ''.join(E[_k].split())
B = E.get('R2_BUCKET', 'upfrontdfwdata')
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
HERE = os.path.dirname(os.path.abspath(__file__))
BID = E.get('BUILD') or time.strftime('%Y-%m')
# Oct 23, 2026 (Betsy: "set up the DFW update"): a mid-month DFW rebuild, so networks added after the month's build
# (UMR, NEXUS ACO, UnitedHealthcare Core / Core EPO / Select Plus / Navigate, Aetna's 4 national networks, Anthem Blue High
# Performance) reach the live page before open enrollment (Nov 1) instead of at the Nov 8 build. Named in
# site/dfw_rebuild.json and used only while "base" is this month and no build id was given by hand. Stage A results are
# cached per table, so it reads only tables it hasn't seen; the publish step's checks still run against the live page.
REBUILD = {}
if not E.get('BUILD'):
    try:
        REBUILD = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dfw_rebuild.json')))
        if REBUILD.get('paused') or REBUILD.get('base') != BID or not REBUILD.get('build'): REBUILD = {}
        else: BID = REBUILD['build']
    except Exception: REBUILD = {}
SP = f'site/builds/{BID}/'
TOUT = f'site/every/{BID}/'
HPFX = 'data/hosp_every/'
RESERVE = 1
SIZE_INS, SIZE_HOSP, SIZE_H2 = 's-8vcpu-16gb-amd', 's-4vcpu-8gb-intel', 's-8vcpu-16gb-amd'
REGIONS = ['nyc3', 'sfo3', 'nyc1']



def _names_file():
    """hand-written names (plain_names_cpt.tsv) override machine-written ones (plain_names_auto.tsv)"""
    out = '/tmp/pub/plain_names_all.tsv'
    rows = {}
    for f in (f'{HERE}/plain_names_auto.tsv', f'{HERE}/plain_names_cpt.tsv'):
        if os.path.exists(f):
            for l in open(f):
                if '\t' in l: c, n = l.rstrip('\n').split('\t', 1); rows[c] = n
    open(out, 'w').write(''.join(f'{c}\t{n}\n' for c, n in rows.items()))
    return out

def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def exists(k):
    try: s3.head_object(Bucket=B, Key=k); return True
    except Exception: return False
def getj(k, default=None):
    try: return json.loads(s3.get_object(Bucket=B, Key=k)['Body'].read())
    except Exception: return default
def putj(k, v): s3.put_object(Bucket=B, Key=k, Body=json.dumps(v, indent=1).encode())
def ls(p): return [o['Key'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])]


# ---------- DigitalOcean ----------
def do(method, path, body=None):
    req = urllib.request.Request('https://api.digitalocean.com/v2' + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={'Authorization': 'Bearer ' + E['DIGITALOCEAN_TOKEN'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r: return json.loads(r.read() or b'{}')
def droplets(): return do('GET', '/droplets?per_page=200')['droplets']
def over_card_cap():
    """Oct 29, 2026: this month's spend beyond the DigitalOcean credit has reached the cap Betsy OK'd
    (build_approvals.json "_card_cap"): start no new machines. An API hiccup never stops a build."""
    try:
        b = do('GET', '/customers/my/balance')
        mtd, bal = float(b.get('month_to_date_usage') or 0), float(b.get('account_balance') or 0)
        cap = float(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build_approvals.json')))['_card_cap']['usd'])
        return mtd - (-bal if bal < 0 else 0.0) >= cap
    except Exception:
        return False
def free_slots():
    if over_card_cap():
        print('card spending cap reached for this month: no new machines (build_approvals.json _card_cap)')
        return 0
    return int(do('GET', '/account')['account']['droplet_limit']) - RESERVE - len(droplets())

ENV_KEYS = ['R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY']
# Oct 28, 2026: where storage lives (blank = Cloudflare R2). Set as repo variables to move to another S3-style store.
STORAGE_KEYS = ['STORAGE_ENDPOINT', 'STORAGE_REGION']
def userdata(script, env):
    envs = '\n'.join(f"export {k}='{E.get(k, '')}'" for k in ENV_KEYS + STORAGE_KEYS) + f"\nexport R2_BUCKET={B} DO_TOKEN='{E['DIGITALOCEAN_TOKEN']}'\n" + \
        '\n'.join(f"export {k}='{v}'" for k, v in env.items())
    return f"""#!/bin/bash
exec > /root/boot.log 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y python3-venv curl
python3 -m venv /root/v && /root/v/bin/pip install -q duckdb==1.1.3 boto3 ijson zstandard
cat > /root/env.sh <<'ENV'
{envs}
ENV
cat > /root/run.sh <<'RUN'
#!/bin/bash
. /root/env.sh
mkdir -p /root/h /d && cd /root/h
/root/v/bin/python -c "
import boto3,os
s3=boto3.client('s3',endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or 'https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com'),aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
s3.download_file(os.environ['R2_BUCKET'],'{SP}bundle.tgz','/root/b.tgz')"
tar xzf /root/b.tgz -C /root/h
{script}
/root/v/bin/python -c "
import boto3,os
s3=boto3.client('s3',endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or 'https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com'),aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
s3.upload_file('/root/run.log',os.environ['R2_BUCKET'],'{SP}logs/'+os.environ['ROLE']+'.log')"
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DO_TOKEN" https://api.digitalocean.com/v2/droplets/$ID
RUN
chmod +x /root/run.sh
setsid nohup /root/run.sh < /dev/null > /root/run.out 2>&1 &
"""
def launch(role, size, script, env):
    name = f'upfront-site-{BID}-{role}'
    ud = userdata(script, dict(env, ROLE=role))
    for region in REGIONS:
        try:
            d = do('POST', '/droplets', {'name': name, 'region': region, 'size': size, 'image': 'ubuntu-24-04-x64', 'user_data': ud, 'tags': ['site-build'], 'monitoring': True})
            log('launched', name, region, d['droplet']['id']); return True
        except urllib.error.HTTPError as e:
            log('launch failed', name, region, e.read()[:150])
    return False


RUN_INS = "for t in $(seq 1 40); do /root/v/bin/python /root/h/every_code.py >> /root/run.log 2>&1 && break; sleep 5; done"
RUN_HOSP = "for t in 1 2 3; do /root/v/bin/python /root/h/hosp_every.py >> /root/run.log 2>&1 && break; sleep 5; done"
RUN_H2 = """/root/v/bin/python - >> /root/run.log 2>&1 <<'PY'
import boto3, os, json
from concurrent.futures import ThreadPoolExecutor
E = os.environ
s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or 'https://' + E['R2_ACCOUNT_ID'] + '.r2.cloudflarestorage.com'), aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
jobs = json.loads(s3.get_object(Bucket=E['R2_BUCKET'], Key=E['JOBS_KEY'])['Body'].read())
os.makedirs('/root/rows', exist_ok=True)
with ThreadPoolExecutor(16) as P: list(P.map(lambda j: s3.download_file(E['R2_BUCKET'], E['HPFX'] + 'rows/' + j['id'] + '.parquet', '/root/rows/' + j['id'] + '.parquet'), jobs))
s3.download_file(E['R2_BUCKET'], E['PAGE_KEY'], '/root/page.html')
PY
/root/v/bin/python /root/h/h2_build.py '/root/rows/*.parquet' /root/h/payer_name_mapping.csv /root/page.html /d >> /root/run.log 2>&1
/root/v/bin/python -c "
import boto3,os
s3=boto3.client('s3',endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or 'https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com'),aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
s3.upload_file('/d/hosp_index.json',os.environ['R2_BUCKET'],os.environ['SP']+'hosp_index.json')" >> /root/run.log 2>&1"""


# ---------- hospital jobs: newest file per DFW hospital, reuse rows when unchanged ----------
def hospital_jobs():
    base = getj('site/builds/hosp_jobs_base.json', [])
    latest = {}
    for k in sorted(x for x in ls('bot/status/') if x.endswith('/TX.csv')):
        for r in csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key=k)['Body'].read().decode())):
            if r.get('r2_key') and r.get('sha256'): latest[r['mrf_url']] = r
    jobs = []
    for j in base:
        r = latest.get(j['url'])
        jobs.append(dict(j, id=r['sha256'][:16], key=r['r2_key'], size=int(r.get('size') or 0)) if r else j)
    cached = {k.rsplit('/', 1)[1][:-8] for k in ls(HPFX + 'rows/')}
    todo = [j for j in jobs if j['id'] not in cached]
    return jobs, todo


def bundle():
    p = '/tmp/site_bundle.tgz'
    with tarfile.open(p, 'w:gz') as t:
        for f in os.listdir(HERE):
            # Oct 22, 2026: .json too. state_scopes.json (which states each new area has) was left out, so tx_split.py on
            # the machines fell back to Texas tables (404) and Arkansas and Illinois never split (builds stuck since Oct 19-20)
            if f.endswith(('.py', '.csv', '.tsv', '.json')): t.add(os.path.join(HERE, f), arcname=f)
        t.add(os.path.join(HERE, '..', 'reference', 'geo', 'tx_zip_metro.csv'), arcname='tx_zip_metro.csv')   # Texas metro areas (tx_split.py)
    s3.upload_file(p, B, SP + 'bundle.tgz')


def insurer_bot_busy():
    m = s3.get_object(Bucket=B, Key='bot/insurers/manifest.csv')['Body'].read().decode()
    return sum(1 for r in csv.DictReader(io.StringIO(m)) if r.get('status') == 'running')


def alive(role): return any(d['name'] == f'upfront-site-{BID}-{role}' for d in droplets())


def ensure(st, role, size, script, env, done):
    """keep one machine per role running until its work is done; relaunch dead ones up to 3 times"""
    if done or alive(role): return
    n = st['launches'].get(role, 0)
    if n >= 8: st['problems'].append(f'{role} failed 8 times'); return   # Oct 14: 4 -> 6 (hand relaunches during the Georgia fixes used up tries)
    if free_slots() < 1:
        # Oct 22, 2026: ask the insurer reader for room at every step, not only when a build starts (Arkansas and Illinois
        # sat in their build step for 30+ hours while the reader's machines held all 25 slots). insurers/bot.py fill()
        # leaves fleet.ST_ROOM slots free for 2 hours after this note.
        try: putj('bot/fleet/build_wants_room.json', {'build': f'{BID} {role}', 'at': time.time()})
        except Exception: pass
        log('no free machine for', role, '(asked the insurer reader to leave room)'); return
    if launch(role, size, script, env): st['launches'][role] = n + 1


def issue(title, body):
    try:
        # Oct 14: time limit + no prompts, so a stuck gh call can't freeze the 5-minute build loop
        r = subprocess.run(['gh', 'issue', 'create', '--title', title, '--body', body], check=False, timeout=90,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, env=dict(os.environ, GH_PROMPT_DISABLED='1'))
        log('issue:', (r.stdout or r.stderr).strip()[:200])
    except Exception as e: log('issue failed', e)


def main():
    st = getj(SP + 'state.json', {'stage': 'wait', 'launches': {}, 'problems': [], 'log': []})
    log('build', BID, 'stage', st['stage'])
    if st['stage'] == 'wait':
        if int(time.strftime('%d')) < 8 and not E.get('FORCE'): log('waiting for the 8th'); return
        busy = insurer_bot_busy()
        if busy and not E.get('FORCE'): log(busy, 'insurer files still being read; waiting'); return
        if REBUILD and not E.get('FORCE'):
            # wait until every network named in dfw_rebuild.json is read (or has failed), or until "go_by" (UTC)
            man = {r['slot']: r for r in csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key='bot/insurers/manifest.csv')['Body'].read().decode()))}
            left = [n for n in REBUILD.get('wait_for', []) if man.get(n, {}).get('status', 'new') in ('new', 'queued', 'running')]
            if left and time.strftime('%Y-%m-%dT%H:%M', time.gmtime()) < REBUILD.get('go_by', '9999'):
                log(len(left), 'new networks not read yet; waiting (or until', REBUILD.get('go_by'), 'UTC):', ', '.join(left)); return
            if left: log('go_by reached: building without', ', '.join(left))
        if free_slots() < 2: log('not enough free machines; waiting'); return
        jobs, todo = hospital_jobs()
        putj(SP + 'hosp_jobs.json', jobs); putj(SP + 'hosp_todo.json', todo)
        s3.copy_object(Bucket=B, Key=SP + 'page_before.html', CopySource={'Bucket': B, 'Key': 'site/deploy/price-finder.html'})
        bundle()
        st.update(stage='build1', started=time.strftime('%Y-%m-%d %H:%M'), hosp_changed=len(todo), hosp_total=len(jobs))
        log(len(todo), 'of', len(jobs), 'hospital files changed')
    if st['stage'] == 'build1':
        common = dict(TOUT=TOUT, OUTP=SP, WK=f'work/every/{BID}/', ACACHE='work/every/Acache/', NOXPART='1', PIECE_GB='0.4',
                      MAXPIECES='3', THREADS='4', MEM='9GB', WORKERS='3', WTHREADS='1', WMEM='2500MB', WORK='/d')
        ins_done = exists(TOUT + 'embed.json')
        ensure(st, 'ins1', SIZE_INS, RUN_INS, common, ins_done)
        ensure(st, 'ins2', SIZE_INS, RUN_INS, dict(common, AORDER='desc', BORDER='desc'), ins_done)
        todo = getj(SP + 'hosp_todo.json', [])
        hdone = {k.rsplit('/', 1)[1][:-5] for k in ls(HPFX + 'done/')}
        left = [j for j in todo if j['id'] not in hdone]
        if todo:
            for sh in range(2 if len(todo) > 10 else 1):
                ensure(st, f'hosp{sh}', SIZE_HOSP, RUN_HOSP, dict(JOBS_KEY=SP + 'hosp_todo.json', SHARD=str(sh), SHARDS='2' if len(todo) > 10 else '1', HPFX=HPFX), not left)
        log('insurer part', 'done' if ins_done else 'running', '| hospital files left', len(left))
        if ins_done and not left: st['stage'] = 'build2'
    if st['stage'] == 'build2':
        done = exists(SP + 'hosp_index.json')
        ensure(st, 'h2', SIZE_H2, RUN_H2, dict(JOBS_KEY=SP + 'hosp_jobs.json', HPFX=HPFX, PAGE_KEY=SP + 'page_before.html', SP=SP,
                                                UPLOAD='1', HKEY=TOUT + 'h/', NP='8', MEM='11GB'), done)
        if done: st['stage'] = 'publish'
    if st['stage'] == 'publish':
        publish(st)
    putj(SP + 'state.json', st)


def cleanup(prev):
    """After a build is live: delete only build leftovers. Kept forever: raw/ (original price files), data/ insurer and
    hospital tables, history/insurers/ and work/retired/ (replaced insurer tables, every month), site/deploy/, site/builds/ (state + logs), the A cache.
    Kept: the live build and the one before it (rollback). Deleted: older site/every/<build>/ folders and
    work/every/<build>/ scratch for builds other than the live one."""
    import re
    keep = {BID, prev}
    gone = 0
    for k in ls('site/every/') + ls('work/every/'):
        m = re.match(r'^(site|work)/every/([0-9]{4}-[0-9]{2}(?:-[0-9]{2})?)/', k)
        if not m: continue                       # CURRENT, Acache/ and anything unexpected are left alone
        b = m.group(2)
        if (m.group(1) == 'site' and b not in keep) or (m.group(1) == 'work' and b != BID):
            s3.delete_object(Bucket=B, Key=k); gone += 1
    for k in ls('data/2026-10-10/hosp_every/rows/'):   # copied to data/hosp_every/rows/ on Oct 11
        if exists('data/hosp_every/rows/' + k.rsplit('/', 1)[1]): s3.delete_object(Bucket=B, Key=k); gone += 1
    log('cleanup: deleted', gone, 'leftover build files')
    return gone


def publish(st):
    os.makedirs('/tmp/pub', exist_ok=True)
    for k, f in [(SP + 'page_before.html', 'old.html'), (TOUT + 'embed.json', 'embed.json'), (SP + 'hosp_index.json', 'hosp.json'),
                 ('reference/site/med_all.json', 'med.json'), ('reference/site/msdrg_table5.txt', 't5.txt')]:
        s3.download_file(B, k, '/tmp/pub/' + f)
    try: s3.download_file(B, TOUT + 'npis.json', '/tmp/pub/npis.json')   # merge_page.py re-keys the arbitration provider lines with it
    except Exception as e: print('no npis.json for this build; arbitration provider lines dropped:', e)
    import shutil; shutil.copy('/tmp/pub/old.html', '/tmp/pub/new.html')
    py = sys.executable
    subprocess.run([py, f'{HERE}/merge_page.py', '/tmp/pub/new.html', '/tmp/pub/embed.json', '/tmp/pub/hosp.json'], check=True)
    subprocess.run([py, f'{HERE}/apply_names_med.py', '/tmp/pub/new.html', '/tmp/pub/med.json', _names_file(), '/tmp/pub/t5.txt'], check=True)
    chk = subprocess.run([py, f'{HERE}/check_build.py', '/tmp/pub/old.html', '/tmp/pub/new.html'], capture_output=True, text=True)
    print(chk.stdout)
    s3.upload_file('/tmp/pub/new.html', B, SP + 'page_new.html')
    if chk.returncode != 0:
        st['stage'] = 'held'
        issue(f'Website refresh {BID} held: checks failed', f'Nothing went live.\n\n```\n{chk.stdout}\n```\nNew page saved to R2 `{SP}page_new.html`.')
        return
    # map locations for this build (site/every/<BID>/geo.json). Never blocks the refresh: if it fails, the map
    # says it is being updated and the rest of the Price Finder works as before.
    try: g = subprocess.run([py, f'{HERE}/geo_build.py', '/tmp/pub/new.html', BID], capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired as e: g = subprocess.CompletedProcess(e.cmd, 1, '', 'timed out after 25 minutes')
    print(g.stdout[-1500:], g.stderr[-1500:])
    if g.returncode != 0: issue(f'Website refresh {BID}: map locations not built', 'The prices will still go live; the map will show "being updated" until this is fixed.\n\n```\n' + g.stderr[-3000:] + '\n```')
    if not E.get('CLOUDFLARE_API_TOKEN'):
        st['stage'] = 'ready'
        issue(f'Website refresh {BID} ready, not deployed', 'Checks passed but the CLOUDFLARE_API_TOKEN secret is not set, so it could not deploy.\n\n```\n' + chk.stdout + '\n```')
        return
    # deploy: site files come from R2 (the site is not in this public repo)
    s3.download_file(B, 'site/deploy/current.tgz', '/tmp/pub/site.tgz')
    shutil.rmtree('/tmp/pub/deploy', ignore_errors=True)
    with tarfile.open('/tmp/pub/site.tgz') as t: t.extractall('/tmp/pub/deploy')
    shutil.copy('/tmp/pub/new.html', '/tmp/pub/deploy/site/price-finder/index.html')
    # quality ratings are matched by provider position: re-place them for this build's provider order (Oct 18, 2026 fix;
    # the old file kept last build's positions and showed ratings on the wrong providers)
    subprocess.run([sys.executable, f'{HERE}/quality_rekey.py', 'render', '/tmp/pub/npis.json', '/tmp/pub/new.html',
                    '/tmp/pub/deploy/site/price-finder/pf/q/quality.txt'], check=True)
    try: prev = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
    except Exception: prev = '2026-10-08'
    s3.put_object(Bucket=B, Key='site/every/CURRENT', Body=BID.encode())
    env = dict(os.environ, CLOUDFLARE_ACCOUNT_ID=E['R2_ACCOUNT_ID'])
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sitewide.py'), '/tmp/pub/deploy'], check=True)   # name, Units look, share image (Oct 18)
    r = subprocess.run(['npx', '--yes', 'wrangler@3.114.0', 'pages', 'deploy', 'site', '--project-name', 'upfront-dfw-preview', '--branch', 'main', '--commit-dirty=true'],
                       cwd='/tmp/pub/deploy', env=env, capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode != 0:
        s3.put_object(Bucket=B, Key='site/every/CURRENT', Body=prev.encode())
        st['stage'] = 'held'; issue(f'Website refresh {BID}: deploy failed', '```\n' + r.stderr[-3000:] + '\n```'); return
    s3.upload_file('/tmp/pub/new.html', B, 'site/deploy/price-finder.html')
    with tarfile.open('/tmp/pub/site.tgz', 'w:gz') as t: t.add('/tmp/pub/deploy', arcname='.')
    s3.upload_file('/tmp/pub/site.tgz', B, 'site/deploy/current.tgz')
    st['stage'] = 'live'; st['live_at'] = time.strftime('%Y-%m-%d %H:%M')
    st['cleanup'] = cleanup(prev)
    putj(SP + 'state.json', st)   # DFW is live; with 23 Texas pages the rebuilds below can outlast the workflow's time limit
    st['cities'] = refresh_cities('/tmp/pub/deploy/site/cities.json')
    issue(f'Website refresh {BID} is live', '```\n' + chk.stdout + '\n```' + ''.join(f'\n{c}: {v}' for c, v in st['cities'].items()))


def refresh_cities(cities_json):
    """After DFW goes live, rebuild every live Texas city page on the new layout, names and Medicare figures, with that city's
    newest finished insurer build. One at a time (each deploy adds to the site DFW just published). A city that fails keeps
    last month's page and opens an issue; it never touches the DFW page."""
    try: live = [c for c in json.load(open(cities_json, encoding='utf-8')) if c['slug'] != 'dfw']
    except Exception: live = []
    out = {}
    for c in live:
        try: r = subprocess.run([sys.executable, f'{HERE}/city_page.py', c['slug'], '--deploy', '--out', f"/tmp/city-{c['slug']}"],
                                capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired: r = subprocess.CompletedProcess([], 1, '', 'timed out after 20 minutes')
        print(r.stdout[-1500:], r.stderr[-1500:])
        out[c['slug']] = 'rebuilt' if r.returncode == 0 else 'kept last version (failed)'
        if r.returncode != 0:
            issue(f"Website refresh {BID}: {c['name']} page not rebuilt", "The page keeps its previous version.\n\n```\n" + (r.stdout + r.stderr)[-3000:] + "\n```")
    return out


if __name__ == '__main__':
    main()
