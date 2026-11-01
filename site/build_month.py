"""Which month's build a state scope should work on (Nov 1, 2026).

Build ids carry the month (stb4-2026-10). Every part of the state-page pipeline used the calendar month, so at midnight on
Nov 1 the October builds still running (Ohio's last step, Washington, Michigan, Minnesota) were dropped mid-way: their
finished work sat unpublished, their main machines kept billing, and November builds started over from "wait".

Rule: keep working on last month's build while it is under way (split or build stage), or while its insurer part is done
('hosp') but its hospital part (hosp-<stb>-<month>) isn't. A last-month build that never started ('wait' or none) is
skipped, so a scope with nothing in flight moves on to the new month as before.
Usage: python site/build_month.py <stb>   (prints the month, e.g. 2026-10)
"""
import json, os, sys, time


def _prev(m):
    y, mo = map(int, m.split('-'))
    return f'{y - 1}-12' if mo == 1 else f'{y}-{mo - 1:02d}'


def _s3():
    import boto3
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    return boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                        aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                        region_name=(os.environ.get('STORAGE_REGION') or 'auto')), E['R2_BUCKET']


def _stage(s3, b, key):
    try: return json.loads(s3.get_object(Bucket=b, Key=key)['Body'].read()).get('stage', '')
    except Exception: return ''


def month_for(stb, s3=None, bucket=None):
    cur = time.strftime('%Y-%m')
    try:
        if s3 is None: s3, bucket = _s3()
        prev = _prev(cur)
        ins = _stage(s3, bucket, f'site/builds/{stb}-{prev}/state.json')
        if ins in ('split', 'build'): return prev
        if ins == 'hosp' and _stage(s3, bucket, f'site/builds/hosp-{stb}-{prev}/state.json') != 'done': return prev
    except Exception as e:
        print('build_month: check failed, using this month:', repr(e)[:120], flush=True)
    return cur


if __name__ == '__main__':
    print(month_for(sys.argv[1]))
