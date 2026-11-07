"""Nov 7, 2026 (Betsy OK'd, $25 cap): rebuild every published page's hospital-file prices with the Nov 4 rules.

Why: the data accuracy audit (reports/audit/) found hospital-file "prices" that are DRG weights ($0.01, $2.95), hospice day
rates and percent-of-charges estimates ($0.33 for a brain MRI) on the pages. h2_build.py has left those out since Nov 4
(dff8b35), but every area's hospital files were built before that. The parsed rows are cached (data/hosp_every/rows/), so
only the h2 step runs again: minutes per area on a rented machine.

What it does: for each hospital build that has published pages, `hosp_area.py redo <its published areas>` (clears their h2
and publish marks and sets the build back to 'h2'). The hourly state-pages.yml (pages_loop.py) then rebuilds and
republishes the state pages; the Texas metros (hosp-tx-2026-10) are moved along by this job's own loop. Dallas-Fort Worth is
built by the monthly refresh (orchestrate.py) and is not touched here.
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import orchestrate as O   # storage client (same keys as every build)

SCOPES = ['s7', 'nc', 'ct'] + [k for k in json.load(open(f'{HERE}/state_scopes.json')) if not k.startswith('_')]


def stb(scope): return 'st' if scope == 's7' else 'st' + scope


def redo(build, scope):
    st = O.getj(f'site/builds/{build}/state.json', {})
    areas = sorted(a for a, v in (st.get('published') or {}).items() if str(v).startswith('live'))
    if not areas:
        print(build, ': nothing published, left alone', flush=True); return []
    env = {**os.environ, 'BUILD': build, 'HOSP_SCOPE': scope}
    r = subprocess.run([sys.executable, f'{HERE}/hosp_area.py', 'redo', *areas], env=env, capture_output=True, text=True)
    print(build, '->', ', '.join(areas), '\n', r.stdout[-1500:], r.stderr[-800:], flush=True)
    # regional pages (California, New York, Florida, Illinois, Pennsylvania regions) aren't in areas.json, so redo skips them:
    # clear their marks the way split_flow does when a state is split again
    plan = O.getj(f'site/builds/{build}/areas.json', {})
    st = O.getj(f'site/builds/{build}/state.json', {})
    for a in areas:
        if a in plan:
            continue
        try: O.s3.delete_object(Bucket=O.B, Key=f'site/builds/{build}/h2/{a}.done')
        except Exception: pass
        st.get('published', {}).pop(a, None); st.get('launches', {}).pop(f'h2-{a}', None)
        print('  region', a, 'cleared for rebuild', flush=True)
    st['stage'] = 'h2'
    O.putj(f'site/builds/{build}/state.json', st)
    return areas


def main():
    done = {}
    for scope in SCOPES:
        b = f'hosp-{stb(scope)}-2026-11'
        if O.getj(f'site/builds/{b}/state.json', None) is not None:
            done[b] = redo(b, scope)
    done['hosp-tx-2026-10'] = redo('hosp-tx-2026-10', '')
    O.putj('site/builds/hosp-redo-2026-11-07.json', {'at': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), 'builds': done})
    print('areas set to rebuild:', sum(len(v) for v in done.values()))


if __name__ == '__main__':
    main()
