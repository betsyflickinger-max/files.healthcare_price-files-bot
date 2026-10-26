"""Storage (Cloudflare R2) cost check, every 3 hours (Oct 26, 2026, Betsy OK'd).

Why: R2 charges per request, not per gigabyte. In late October the state builds made 276 million reads and 8 million
writes in two weeks ($165) and nobody saw it until the Cloudflare bill. cost_check.py only watched the rented machines.

What: asks Cloudflare's analytics API how many storage requests the account made each day and how much is stored, prices
them, and writes:
  alert.txt  - one line per problem (empty = all fine); the workflow turns it into a GitHub issue that emails Betsy
  r2_cost.md - a small table for the run summary
Needs a Cloudflare API token that can read account analytics (secret CF_ANALYTICS_TOKEN; falls back to
CLOUDFLARE_API_TOKEN). If the token can't read analytics, alert.txt says how to make one.

Prices (Cloudflare R2 standard storage, as on the October 2026 bill): writes/lists ("Class A") $4.50 per million,
reads ("Class B") $0.36 per million, storage $0.015 per GB-month. Deletes are free. The monthly free allowance
(1M writes, 10M reads, 10 GB) is ignored here, so these numbers run slightly high, never low.
"""
import datetime as dt
import json
import os
import urllib.request

LIMIT_DAY_USD = float(os.environ.get('R2_LIMIT_DAY_USD', '10'))   # one day's request cost that's worth a look
A_PRICE, B_PRICE, GB_MONTH = 4.50 / 1e6, 0.36 / 1e6, 0.015
CLASS_A = {'ListBuckets', 'PutBucket', 'ListObjects', 'ListObjectsV2', 'PutObject', 'CopyObject', 'CompleteMultipartUpload',
           'CreateMultipartUpload', 'UploadPart', 'UploadPartCopy', 'ListMultipartUploads', 'ListParts', 'PutBucketEncryption',
           'PutBucketCors', 'PutBucketLifecycleConfiguration', 'LifecycleStorageTierTransition', 'PutBucketPolicy'}
FREE = {'DeleteObject', 'DeleteObjects', 'DeleteBucket', 'AbortMultipartUpload'}

acct = ''.join(os.environ['R2_ACCOUNT_ID'].split())
tok = ''.join((os.environ.get('CF_ANALYTICS_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN') or '').split())
today = dt.datetime.now(dt.timezone.utc).date()
start = today - dt.timedelta(days=7)

Q = """query($a: String!, $s: Time!, $e: Time!, $sd: Date!) { viewer { accounts(filter: {accountTag: $a}) {
  ops: r2OperationsAdaptiveGroups(limit: 10000, filter: {datetime_geq: $s, datetime_lt: $e}) {
    sum { requests } dimensions { actionType date } }
  st: r2StorageAdaptiveGroups(limit: 1000, filter: {date_geq: $sd}) {
    max { payloadSize objectCount } dimensions { date bucketName } } } } }"""


def ask():
    body = json.dumps({'query': Q, 'variables': {'a': acct, 's': f'{start}T00:00:00Z', 'e': f'{today + dt.timedelta(days=1)}T00:00:00Z',
                                                 'sd': str(start)}}).encode()
    req = urllib.request.Request('https://api.cloudflare.com/client/v4/graphql', data=body,
                                 headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=60))


alerts, md = [], []
try:
    r = ask() if tok else {'errors': [{'message': 'no token'}]}
except Exception as e:   # network trouble: say so, but don't raise an alarm about spending
    r = {'errors': [{'message': f'request failed: {e}'}]}
errs = r.get('errors') or []
acc = (((r.get('data') or {}).get('viewer') or {}).get('accounts') or [None])[0]
if acc is None:
    msg = '; '.join(e.get('message', '') for e in errs)[:300]
    if not tok or 'auth' in msg.lower() or 'permission' in msg.lower() or 'not authorized' in msg.lower():
        alerts.append('SETUP: the storage cost check can\'t read Cloudflare analytics yet. In Cloudflare: My Profile > API Tokens > '
                      'Create Token > "Read analytics and logs" template (or a custom token with Account > Account Analytics > Read), '
                      'then add it in GitHub: this repo > Settings > Secrets and variables > Actions > New secret named '
                      f'CF_ANALYTICS_TOKEN. (Cloudflare said: {msg})')
    else:
        print('analytics not read this time:', msg)
else:
    days = {}
    for g in acc.get('ops') or []:
        d, act, n = g['dimensions']['date'], g['dimensions']['actionType'], g['sum']['requests']
        a, b = days.setdefault(d, [0, 0])
        if act in FREE: continue
        if act in CLASS_A: days[d][0] += n
        else: days[d][1] += n
    stored = {}
    for g in acc.get('st') or []:
        d = g['dimensions']['date']
        stored[d] = stored.get(d, 0) + (g['max']['payloadSize'] or 0)
    gb = stored[max(stored)] / 1e9 if stored else None
    md.append('| Day (UTC) | Writes/lists | Reads | Request cost |')
    md.append('|---|---:|---:|---:|')
    for d in sorted(days):
        a, b = days[d]
        md.append(f'| {d} | {a:,} | {b:,} | ${a * A_PRICE + b * B_PRICE:,.2f} |')
    if gb is not None:
        md.append(f'\nStored: {gb:,.0f} GB, about ${gb * GB_MONTH:,.0f} a month at today\'s size (keeps growing: nothing is deleted).')
    # judge the last full day, so a half-finished day never looks cheap or alarming
    y = str(today - dt.timedelta(days=1))
    if y in days:
        a, b = days[y]
        usd = a * A_PRICE + b * B_PRICE
        if usd > LIMIT_DAY_USD:
            alerts.append(f'OVER: storage requests cost ${usd:,.2f} on {y} (limit ${LIMIT_DAY_USD:,.0f}/day): {a:,} writes/lists '
                          f'(${a * A_PRICE:,.2f}) and {b:,} reads (${b * B_PRICE:,.2f}). A build is probably re-reading or '
                          're-listing storage more than it needs to.')

open('alert.txt', 'w').write('\n\n'.join(alerts))
open('r2_cost.md', 'w').write('\n'.join(md) + '\n')
print('\n'.join(md)); print('\n'.join(alerts) or 'no alerts')
