"""Slim every Price Finder page already live, in one deploy (Nov 10, 2026; Betsy OK'd after the Kansas test).

site/page_slim.py on each live area page (DFW and every page in site/cities.json) and on the saved build copies
(site/deploy/price-finder.html, the template every city page is built from, and site/deploy/cities/<slug>/price-finder.html,
used by map-only refreshes). Each page is checked with page_slim.same() (same data, same "network not read for this code"
message for every code on the page); a page that fails the check, or whose code has changed, stays as it is and is
listed. Only the pages change: no new prices, so no audit-gate run is needed (the gate reads both forms).

Holds the site deploy lock from download to save; keeps a backup site/deploy/backups/current-before-slim.tgz.
  python site/slim_live.py [--no-deploy]
"""
import argparse, json, os, subprocess, sys, tarfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_lock, page_slim, pages_spill, procedure_pages as pp   # noqa: E402


def slim_file(text):
    new = page_slim.slim(text)
    page_slim.same(text, new)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-deploy', action='store_true')
    a = ap.parse_args()
    store = pp.Store('/tmp/slim')
    s3, B = store.s3, store.B
    out = Path('/tmp/slim'); out.mkdir(parents=True, exist_ok=True)
    d = out / 'deploy'
    if not a.no_deploy:
        deploy_lock.acquire(s3, B, 'slim every Price Finder page')
    s3.download_file(B, 'site/deploy/current.tgz', str(out / 'site.tgz'))
    with tarfile.open(out / 'site.tgz') as t:
        t.extractall(d, filter='data')
    cities = json.load(open(d / 'site' / 'cities.json', encoding='utf-8'))
    pages = [('dfw', d / 'site' / 'price-finder' / 'index.html')] + \
            [(c['slug'], d / 'site' / c['path'].strip('/') / 'index.html') for c in cities if c['slug'] != 'dfw']
    before = after = 0
    kept = []
    for slug, f in pages:
        if not f.is_file():
            continue
        s = f.read_text(encoding='utf-8')
        try:
            n = slim_file(s)
        except (Exception, SystemExit) as e:
            kept.append(f'{slug}: {e}'); continue
        before += len(s.encode()); after += len(n.encode())
        f.write_text(n, encoding='utf-8')
        print(f'{slug:<36} {len(s.encode()) / 2**20:6.2f} -> {len(n.encode()) / 2**20:6.2f} MiB', flush=True)
    print(f'\nall pages: {before / 2**20:,.0f} -> {after / 2**20:,.0f} MiB; kept as they were: {len(kept)}')
    for k in kept:
        print('  KEPT', k)
    tmpl = []   # saved build copies
    keys = ['site/deploy/price-finder.html'] + [o['Key'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix='site/deploy/cities/')
                                                for o in pg.get('Contents', []) if o['Key'].endswith('/price-finder.html')]
    for i, key in enumerate(keys):
        try:
            s = s3.get_object(Bucket=B, Key=key)['Body'].read().decode('utf-8')
            n = slim_file(s)
        except (Exception, SystemExit) as e:
            print('  saved copy kept as it was:', key, e); continue
        if n != s:
            (out / f'tmpl_{i}.html').write_text(n, encoding='utf-8'); tmpl.append((key, out / f'tmpl_{i}.html'))
    print(f'saved build copies slimmed: {len(tmpl)} of {len(keys)}')
    if a.no_deploy:
        print('not deployed'); return
    E = dict(os.environ)
    for k in ('R2_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN'):
        E[k] = ''.join(E.get(k, '').split())
    if not E.get('CLOUDFLARE_API_TOKEN'):
        sys.exit('CLOUDFLARE_API_TOKEN is not set; nothing deployed')
    with pages_spill.offload(str(d)):
        r = subprocess.run(['npx', '--yes', 'wrangler@3.114.0', 'pages', 'deploy', 'site', '--project-name', 'upfront-dfw-preview',
                            '--branch', 'main', '--commit-dirty=true'], cwd=d, env=dict(E, CLOUDFLARE_ACCOUNT_ID=E['R2_ACCOUNT_ID']),
                           capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit('deploy failed; the site is unchanged')
    s3.copy_object(Bucket=B, Key='site/deploy/backups/current-before-slim.tgz', CopySource={'Bucket': B, 'Key': 'site/deploy/current.tgz'})
    with tarfile.open(out / 'site_new.tgz', 'w:gz') as t:
        t.add(d, arcname='.')
    s3.upload_file(str(out / 'site_new.tgz'), B, 'site/deploy/current.tgz')
    deploy_lock.release()
    for key, f in tmpl:
        s3.upload_file(str(f), B, key)
    print('live: every Price Finder page slimmed')


if __name__ == '__main__':
    main()
