"""One site deploy at a time (Nov 8, 2026; Betsy: "I do not want them to conflict").

Every job that saves the live site (R2 site/deploy/current.tgz) downloads the whole site, changes its part, deploys it and
uploads it again. Two at once meant the second either refused to save (procedure pages, one-off fixes) or quietly erased
the first one's change (the monthly refresh and the state Price Finder builds had no check at all). Now each holds this
lock from the moment it downloads the site until it has saved it, and the others wait their turn.

The lock is a small file, site/deploy/LOCK.json, with an owner token and an expiry. The holder renews it every 2 minutes
from a background thread, so a job that crashes or is cancelled frees it within LEASE minutes. A waiting job checks every
20 seconds and gives up (without deploying anything) after WAIT minutes.

Use:
    import deploy_lock
    deploy_lock.acquire(s3, bucket, 'procedure pages')   # before downloading current.tgz to deploy from it
    ...                                                 # change, deploy, upload current.tgz
    deploy_lock.release()                                # also released automatically when the process exits
For a pull in one step and a push in another (site_files.py): acquire(..., hand_off=path) writes the token to a file
and leaves the lock held when this process exits; adopt(s3, bucket, path) in the later process takes it over.
"""
import atexit
import json
import os
import sys
import threading
import time
import uuid

KEY = 'site/deploy/LOCK.json'
LEASE = 10          # minutes a lock lives without renewal
HAND_OFF_LEASE = 120  # minutes, for a pull/push split across steps (no renewal in between)
WAIT = 300          # minutes to wait for another deploy before giving up

_s3 = _b = _token = _who = None
_beat = None
_stop = threading.Event()
_keep_on_exit = False


def _now():
    return time.time()


def _read():
    try:
        return json.loads(_s3.get_object(Bucket=_b, Key=KEY)['Body'].read())
    except Exception:
        return None


def _write(lease_min):
    run = os.environ.get('GITHUB_RUN_ID', '')
    body = {'token': _token, 'who': _who, 'run': run, 'workflow': os.environ.get('GITHUB_WORKFLOW', ''),
            'since': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()), 'until': _now() + lease_min * 60}
    _s3.put_object(Bucket=_b, Key=KEY, Body=json.dumps(body).encode(), ContentType='application/json')


def _heartbeat():
    while not _stop.wait(120):
        try:
            cur = _read()
            if cur and cur.get('token') == _token:
                _write(LEASE)
            else:
                print('deploy lock: lost the lock (expired or taken); stopping before anything else is saved', flush=True)
                os._exit(3)
        except Exception as e:
            print('deploy lock: renewal failed:', e, flush=True)


def _start_beat():
    global _beat
    _stop.clear()
    _beat = threading.Thread(target=_heartbeat, daemon=True)
    _beat.start()


def acquire(s3, bucket, who, hand_off=None, wait_min=WAIT):
    """Wait for any other deploy to finish, then take the lock. Exits the process (nothing deployed) after wait_min."""
    global _s3, _b, _token, _who, _keep_on_exit
    if _token:
        return _token
    _s3, _b, _who = s3, bucket, who
    _token = uuid.uuid4().hex
    t0, said = _now(), 0
    while True:
        cur = _read()
        if cur and cur.get('until', 0) > _now() and cur.get('token') != _token:
            if _now() - said > 300:
                print(f"deploy lock: waiting for '{cur.get('who')}' ({cur.get('workflow')} run {cur.get('run')}, since {cur.get('since')})", flush=True)
                said = _now()
            if _now() - t0 > wait_min * 60:
                _token = None
                sys.exit(f"STOP: waited {wait_min} minutes for '{cur.get('who')}' to finish deploying; nothing deployed. Try again later.")
            time.sleep(20)
            continue
        _write(HAND_OFF_LEASE if hand_off else LEASE)
        time.sleep(3)                       # two jobs that wrote at the same moment: the last write wins, the other waits
        cur = _read()
        if cur and cur.get('token') == _token:
            break
    waited = int(_now() - t0)
    print(f"deploy lock: taken by '{who}'" + (f' after waiting {waited // 60} min' if waited > 60 else ''), flush=True)
    if hand_off:
        open(hand_off, 'w').write(_token)
        _keep_on_exit = True                # the push step takes it over
    else:
        _start_beat()
    atexit.register(_at_exit)
    return _token


def adopt(s3, bucket, hand_off, who):
    """Take over a lock acquired with hand_off= in an earlier step. Exits if it expired or someone else holds it."""
    global _s3, _b, _token, _who, _keep_on_exit
    _s3, _b, _who = s3, bucket, who
    tok = open(hand_off).read().strip() if os.path.isfile(hand_off) else ''
    cur = _read()
    if not tok or not cur or cur.get('token') != tok:
        sys.exit("STOP: this job's deploy lock expired or another deploy took it since the pull; nothing deployed. Pull again.")
    _token, _keep_on_exit = tok, False
    _write(LEASE)
    _start_beat()
    atexit.register(_at_exit)
    print(f"deploy lock: '{who}' took over the lock from the pull", flush=True)


def release():
    global _token
    _stop.set()
    if not _token:
        return
    try:
        cur = _read()
        if cur and cur.get('token') == _token:
            _s3.delete_object(Bucket=_b, Key=KEY)
            print(f"deploy lock: released by '{_who}'", flush=True)
    except Exception as e:
        print('deploy lock: release failed (it expires on its own):', e, flush=True)
    _token = None


def _at_exit():
    if not _keep_on_exit:
        release()
