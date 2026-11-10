"""One-time move, Nov 10, 2026 (Betsy OK'd the two-page rebuild): providers at the 8 Bell/Coryell-area ZIP codes that are not
Census ZIP areas (e.g. 76508, Baylor Scott & White Medical Center - Temple) go from the Small towns page to Killeen-Temple for
November, without re-splitting every Texas table.

Why it is exact: tx_split.py copies ALL of a provider's rows into every metro its ZIPs map to. So a provider's rows in the
small-towns tables are all its rows, and moving them gives what a full re-split would give for these two metros. Only the
killeen-temple additions of tx_zip_metro_extra.py are used now; the other 113 newly placed ZIPs move at the December build
(their pages aren't rebuilt this month, so moving them now would drop them from the site for a month).

Steps (DRY=1 prints only):
  1. every small-towns rates/ and membership/ table: rows of the moved providers are added to the killeen-temple table of the same
     name (unless that provider is already there) and removed from small-towns unless the provider also has a small-towns ZIP;
     originals are copied first to history/tx-move-2026-11-10/
  2. data/tx/metro/{small-towns,killeen-temple}/npis.parquet rebuilt the same way
  3. both metros' November results (site/every-tx/<m>/2026-11/) are moved to history/, their work folders and stage-A caches cleared
  4. site/builds/tx-2026-11/state.json goes back to 'build' with these two pages unpublished: orchestrate_tx.py rebuilds just
     these two (the others keep their embed.json) and republishes just these two.
"""
import csv, io, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import boto3, duckdb

E = os.environ
DRY = bool(E.get('DRY'))
START = int(E.get('START') or 1)   # START=3 resumes after steps 1-2 finished (re-running them would overwrite the backups)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'bot'))
import store   # noqa: E402  (trims the secrets' stray whitespace, which a bare boto3 call chokes on)
s3, B = store.r2()
MONTH, FROM, TO = '2026-11', 'small-towns', 'killeen-temple'
HIST = 'history/tx-move-2026-11-10/'
W = E.get('WORK', '/tmp/txmove'); os.makedirs(W, exist_ok=True)
NEWSRC = 'GeoNames postal codes (county) + county page in this table; ZIP not a Census ZIP area'


def ls(p): return [o['Key'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix=p) for o in pg.get('Contents', [])]
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def put(local, key):
    if DRY: log('DRY upload', key); return
    s3.upload_file(local, B, key)
def copy(src, dst):
    if DRY: return
    s3.copy({'Bucket': B, 'Key': src}, B, dst)
def delete_all(keys):
    if DRY: log('DRY delete', len(keys), 'files'); return
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=B, Delete={'Objects': [{'Key': k} for k in keys[i:i + 1000]], 'Quiet': True})


# the November table as it was (Census rows) + only the killeen-temple additions
rows = list(csv.DictReader(open(f'{HERE}/../reference/geo/tx_zip_metro.csv', encoding='utf-8')))
old = {r['zip5']: r['slug'] for r in rows if r['source'] != NEWSRC}
new = dict(old); moved_zips = sorted(r['zip5'] for r in rows if r['source'] == NEWSRC and r['slug'] == TO)
new.update({z: TO for z in moved_zips})
log('moved ZIPs:', moved_zips)
BIG3 = [('770', '775'), ('780', '782'), ('786', '787'), ('798', '799'), ('750', '753'), ('760', '762')]
def metro(z5, table):
    if any(a <= z5[:3] <= b for a, b in BIG3): return 'big'
    return table.get(z5, 'small-towns')

s3.download_file(B, 'data/scope/tx_npis_all.parquet', f'{W}/npis.parquet')
c = duckdb.connect()
c.execute("set memory_limit='10GB'; set preserve_insertion_order=false")
zips = c.execute(f"select distinct npi, left(zip5, 5) from read_parquet('{W}/npis.parquet')").fetchall()
was, now = {}, {}
for npi, z in zips:
    was.setdefault(npi, set()).add(metro(z or '', old)); now.setdefault(npi, set()).add(metro(z or '', new))
move = sorted(n for n in now if TO in now[n] and TO not in was[n] and FROM in was[n])      # rows to add to killeen-temple
drop = sorted(n for n in move if FROM not in now[n])                                         # rows to take off small-towns
log(len(move), 'providers move to', TO, '(', len(drop), 'leave', FROM, ')')
if not move: sys.exit('nothing to move')
c.execute('create table mv(npi varchar)'); c.executemany('insert into mv values (?)', [(str(n),) for n in move])
c.execute('create table dr(npi varchar)'); c.executemany('insert into dr values (?)', [(str(n),) for n in drop])

# 1. tables
tot = dict(added=0, removed=0, tables=0)
for sub in (('rates', 'membership') if START <= 1 else ()):
    for k in ls(f'data/tx/metro/{FROM}/{sub}/'):
        if not k.endswith('.parquet'): continue
        t = k.rsplit('/', 1)[1]
        s3.download_file(B, k, f'{W}/from.parquet')
        cast = "cast(npi as varchar)"
        n_mv = c.execute(f"select count(*) from read_parquet('{W}/from.parquet') where {cast} in (select npi from mv)").fetchone()[0]
        if not n_mv: os.remove(f'{W}/from.parquet'); continue
        tk = f'data/tx/metro/{TO}/{sub}/{t}'
        have_to = bool(ls(tk))
        if have_to: s3.download_file(B, tk, f'{W}/to.parquet')
        add = f"select * from read_parquet('{W}/from.parquet') where {cast} in (select npi from mv)"
        if have_to:
            c.execute(f"""copy (select * from read_parquet('{W}/to.parquet') union all by name
                               ({add} and {cast} not in (select distinct cast(npi as varchar) from read_parquet('{W}/to.parquet'))))
                          to '{W}/to_new.parquet' (format parquet, compression zstd)""")
        else:
            c.execute(f"copy ({add}) to '{W}/to_new.parquet' (format parquet, compression zstd)")
        c.execute(f"copy (select * from read_parquet('{W}/from.parquet') where {cast} not in (select npi from dr)) to '{W}/from_new.parquet' (format parquet, compression zstd)")
        a = c.execute(f"select count(*) from read_parquet('{W}/to_new.parquet')").fetchone()[0] - (c.execute(f"select count(*) from read_parquet('{W}/to.parquet')").fetchone()[0] if have_to else 0)
        r = c.execute(f"select count(*) from read_parquet('{W}/from.parquet')").fetchone()[0] - c.execute(f"select count(*) from read_parquet('{W}/from_new.parquet')").fetchone()[0]
        copy(k, HIST + k)
        if have_to: copy(tk, HIST + tk)
        put(f'{W}/to_new.parquet', tk); put(f'{W}/from_new.parquet', k)
        tot['added'] += a; tot['removed'] += r; tot['tables'] += 1
        log(sub, t, f'+{a} rows to {TO}, -{r} rows from {FROM}')
        for f in ('from', 'to', 'to_new', 'from_new'):
            if os.path.exists(f'{W}/{f}.parquet'): os.remove(f'{W}/{f}.parquet')
log('tables:', tot)

# 2. provider lists
for m in ((FROM, TO) if START <= 2 else ()):
    keep = sorted(n for n in now if m in now[n])
    c.execute('create or replace table kp(npi varchar)'); c.executemany('insert into kp values (?)', [(str(n),) for n in keep])
    c.execute(f"copy (select * from read_parquet('{W}/npis.parquet') where cast(npi as varchar) in (select npi from kp)) to '{W}/np_{m}.parquet' (format parquet, compression zstd)")
    k = f'data/tx/metro/{m}/npis.parquet'
    copy(k, HIST + k); put(f'{W}/np_{m}.parquet', k)
    log(m, 'providers:', c.execute(f"select count(distinct npi) from read_parquet('{W}/np_{m}.parquet')").fetchone()[0])

# 3. November results and work folders
for m in (FROM, TO):
    res = ls(f'site/every-tx/{m}/{MONTH}/')
    with ThreadPoolExecutor(64) as ex: list(ex.map(lambda k: copy(k, HIST + k), res))   # 64 at a time: one by one took hours
    delete_all(res)
    work = ls(f"work/every-tx/{m}/v{MONTH.replace('-', '')}/") + ls(f'work/every-tx/{m}/Acache/')
    delete_all(work)
    log(m, 'results moved to history:', len(res), '; work files cleared:', len(work))

# 4. state
sk = f'site/builds/tx-{MONTH}/state.json'
st = json.loads(s3.get_object(Bucket=B, Key=sk)['Body'].read())
copy(sk, HIST + sk)
st['stage'] = 'build'
for m in (FROM, TO): (st.get('cities') or {}).pop(m, None)
st.setdefault('log', []).append(time.strftime('%Y-%m-%d %H:%M') + f' tx_move.py: {len(move)} providers {FROM} -> {TO}; rebuilding these two pages')
if DRY: log('DRY state ->', st['stage'], 'cities left:', len(st.get('cities') or {}))
else: s3.put_object(Bucket=B, Key=sk, Body=json.dumps(st, indent=1).encode())
log('DONE')
