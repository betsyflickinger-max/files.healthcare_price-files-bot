"""Audit gate: the data accuracy audit's rule checks (Layer 1) on a Price Finder page before it goes live (Nov 9, 2026, Betsy: "do all of it").

Spec: Healthcare folder DATA-ACCURACY-AUDIT.md, "Any Critical failure blocks publishing". Runs site/audit_rules.audit_area on the
new page and its per-code files (the build's own folders, not the live ones), for the 89 featured procedures:

  - Critical findings (wrong state, another insurer's file, bad NPI, stay weights shown as prices, missing source links):
    the page is held, the live page stays as it is, and the reason is printed with up to 5 examples per rule.
  - Major / Review findings never block; they are counted in the report.
  - F1-F3 (price moved 3x, an insurer's lines fell 25%, providers fell 10%) against this area's last snapshot: Review only.

Every check is saved to storage audit/gate/<date>/<area>.json. After the page goes live, save_snapshot() keeps what it shows
in history/published/<date>/<area>/{insurer,hospital}.parquet (kept permanently, for change over time).

Never fails open by accident: if the check itself breaks (a bug, storage down), the page is held and the error printed.
AUDIT_GATE=report lets a page through with its findings reported (for a deliberate override; say why in the commit).

Used by site/city_page.py (state, regional and Texas city pages) and site/orchestrate.py (DFW).
"""
import collections, datetime as dt, json, os, shutil, sys, tempfile, traceback
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TODAY = dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()


def check(page, slug, path, prefixes, s3=None, B=None):
    """page: the new Price Finder page (local file). prefixes: {'t': storage folder of its insurer files ending in t/,
    'h': its hospital files ending in h/ or None}. Returns (ok, message, snapshot folder or None)."""
    import audit_rules as ar
    work = tempfile.mkdtemp(prefix=f'gate-{slug}-')
    snap = os.path.join(work, 'snap')
    try:
        site = os.path.join(work, 'site')
        dst = os.path.join(site, 'site', path.strip('/'), 'index.html')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(page, dst)
        a = {'slug': slug, 'path': path}
        r = ar.audit_area((site, a, False, snap, None, {'t': prefixes.get('t'), 'h': prefixes.get('h')}))
        n = collections.Counter(r['n'])
        review = []
        if s3 is not None and os.path.isfile(os.path.join(snap, slug, 'insurer.parquet')):
            try:   # F1-F3 against this area's newest earlier snapshot (Review: reported, never blocks)
                keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix='history/published/')
                        for o in p.get('Contents', [])]
                days = sorted({k.split('/')[2] for k in keys if k.endswith(f'/{slug}/insurer.parquet') and k.split('/')[2] < TODAY})
                if days:
                    pdir = os.path.join(work, 'prev')
                    os.makedirs(os.path.join(pdir, slug), exist_ok=True)
                    s3.download_file(B, f'history/published/{days[-1]}/{slug}/insurer.parquet', os.path.join(pdir, slug, 'insurer.parquet'))
                    review, _ = ar.compare(pdir, snap, slug)
                    for x in review:
                        n[x['rule']] += 1
            except Exception as e:
                print('  audit gate: change-since-last-snapshot check skipped:', type(e).__name__, e, flush=True)
        crit = {k: v for k, v in n.items() if ar.LEVEL.get(k) == 'Critical' and v}
        other = {k: v for k, v in n.items() if ar.LEVEL.get(k) != 'Critical' and v}
        ex = [e for e in r['ex'] if e['rule'] in crit]
        shown = collections.Counter()
        lines = []
        for e in ex:
            shown[e['rule']] += 1
            if shown[e['rule']] <= 5:
                lines.append(f"    {e['rule']} {e.get('code', '')} {e.get('provider', '')} {e.get('insurer', '')} "
                             f"{e.get('value', '')} {e.get('detail', '')}".rstrip())
        checked = dict(r.get('checked') or {})
        msg = (f"audit gate {slug}: {sum(crit.values()):,} Critical finding(s)" + (f" {dict(crit)}" if crit else '') +
               f"; other: {dict(sorted(other.items()))}; checked {checked}")
        if lines:
            msg += '\n' + '\n'.join(lines)
        if s3 is not None:
            try:
                rep = {'area': slug, 'date': TODAY, 'critical': crit, 'other': other, 'checked': checked,
                       'examples': [e for e in r['ex']][:400] + review[:100], 'prefixes': prefixes}
                s3.put_object(Bucket=B, Key=f'audit/gate/{TODAY}/{slug}.json', Body=json.dumps(rep, default=str).encode(),
                              ContentType='application/json')
            except Exception as e:
                print('  audit gate: report not saved:', e, flush=True)
        ok = not crit
        if not ok and os.environ.get('AUDIT_GATE', '').lower() == 'report':
            msg += '\n  AUDIT_GATE=report: let through anyway'
            ok = True
        return ok, msg, (snap if os.path.isdir(os.path.join(snap, slug)) else None)
    except Exception:
        return False, f'audit gate {slug}: the check itself failed, so the page is held:\n' + traceback.format_exc()[-2500:], None


def save_snapshot(s3, B, slug, snap):
    """After the page is live: keep what it shows (history/published/<date>/<area>/). Never raises."""
    if not snap:
        return
    try:
        for fn in os.listdir(os.path.join(snap, slug)):
            s3.upload_file(os.path.join(snap, slug, fn), B, f'history/published/{TODAY}/{slug}/{fn}')
        print(f'  history snapshot saved: history/published/{TODAY}/{slug}/', flush=True)
    except Exception as e:
        print('  history snapshot not saved:', e, flush=True)
    finally:
        shutil.rmtree(os.path.dirname(snap), ignore_errors=True)


if __name__ == '__main__':
    # dry run on pages already live: python site/audit_gate.py dfw,st-louis-area   (reads the deployed site; changes nothing)
    import tarfile, procedure_pages as pp
    store = pp.Store('/tmp/gate-live')
    s3, B = store.s3, store.B
    os.makedirs('/tmp/gate-live', exist_ok=True)
    s3.download_file(B, 'site/deploy/current.tgz', '/tmp/gate-live.tgz')
    with tarfile.open('/tmp/gate-live.tgz') as t:
        t.extractall('/tmp/gate-live', filter='data')
    store.site_dir = '/tmp/gate-live'
    areas = {a['slug']: a for a in json.load(open('/tmp/gate-live/site/cities.json', encoding='utf-8'))}
    held = 0
    for slug in sys.argv[1].split(','):
        a = areas.get(slug)
        if not a:
            print('SKIP', slug, '(not in cities.json)'); continue
        page = os.path.join('/tmp/gate-live/site', a['path'].strip('/'), 'index.html')
        ok, msg, snap = check(page, slug, a['path'], {'t': store.prefix(a, 't'), 'h': store.prefix(a, 'h')})
        print(('PASS ' if ok else 'HOLD ') + msg, flush=True)
        held += not ok
    print(f'{held} of {len(sys.argv[1].split(","))} would be held')
