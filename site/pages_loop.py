"""Oct 30, 2026 (Betsy): ONE job publishes every state's page, one scope after another, instead of one waiting job per scope.

Why: publishing deploys the site, so it holds the website build's shared lock (site-build-v2). GitHub keeps only ONE job
waiting on a lock: each newly waiting job cancels the one that was waiting before. With a waiting `pages` job per scope
(state-builds.yml's 10-scope matrix, state-pages.yml for the seven states, ct-pages.yml, nc-pages.yml), the jobs kept
cancelling each other, and on Oct 30 no state page except Ohio/Indiana/Kentucky got a turn for hours. Now every waiting
job does the same thing (all scopes), so when a newer one replaces an older one nothing is lost.

Each pass runs `hosp_area.py run` once per scope (round robin, so a scope whose hospital machines are still working
doesn't hold up the others), skipping scopes that are finished or have nothing to do yet. It stops, freeing the lock, when
no scope has work in progress; the next run (hourly, or started by a build) picks the rest up. Out of time: it starts a
fresh run of state-builds.yml.
Usage: python site/pages_loop.py
"""
import json, os, subprocess, sys, time
import boto3

HERE = os.path.dirname(os.path.abspath(__file__))
IDLE = '/tmp/hosp_idle'                        # hosp_area.py writes this when its scope has nothing to do for now
OWN = ['s7', 'nc', 'ct']                       # scopes from before state_scopes.json (no insurer-build pre-check, as before)
SHARED = [k for k in json.load(open(f'{HERE}/state_scopes.json')) if not k.startswith('_')]
MAX_SECONDS = 320 * 60                         # the job's timeout is 350 minutes
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                  region_name=(os.environ.get('STORAGE_REGION') or 'auto'))


def stage(key):
    try: return json.loads(s3.get_object(Bucket=E['R2_BUCKET'], Key=key)['Body'].read()).get('stage', '')
    except Exception: return ''


def stb(scope): return 'st' if scope == 's7' else 'st' + scope


def main():
    t0 = time.time()
    while True:
        month = time.strftime('%Y-%m'); working = []
        for scope in OWN + SHARED:
            if scope in SHARED and stage(f'site/builds/{stb(scope)}-{month}/state.json') not in ('build', 'hosp'):
                continue   # no insurer build for this state yet (same check the per-scope jobs made)
            if os.path.exists(IDLE): os.remove(IDLE)
            print(f'--- {scope}', flush=True)
            r = subprocess.run([sys.executable, f'{HERE}/hosp_area.py', 'run'], env={**os.environ, 'HOSP_SCOPE': scope})
            if r.returncode: print(f'{scope}: hosp_area.py stopped with code {r.returncode}', flush=True)
            elif stage(f'site/builds/hosp-{stb(scope)}-{month}/state.json') != 'done' and not os.path.exists(IDLE):
                working.append(scope)   # hospital machines still working: come back to it next pass
        if not working:
            print('every scope finished or waiting on its insurer build: freeing the lock', flush=True); return
        if time.time() - t0 > MAX_SECONDS:
            print('out of time with work left for', ', '.join(working), ': starting a fresh run', flush=True)
            subprocess.run(['gh', 'workflow', 'run', 'state-builds.yml', '--ref', 'main']); return
        print('still working:', ', '.join(working), '- next pass in 3 minutes', flush=True)
        time.sleep(180)


if __name__ == '__main__':
    main()
