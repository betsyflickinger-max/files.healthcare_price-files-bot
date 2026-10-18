"""Checks for merge_build.py's merge rules (no R2 needed): python site/merge_build_test.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge_build as M

def row(net, v, fee=0, t=0, flags=0, d=0, u=0, lab=-1, others=()):
    return [net, fee, t, float(v), flags, d, u, len(others), [list(o) for o in others], 0, lab]

be = dict(nets=['Aetna|Open Access', 'Cigna|LocalPlus'], dates=['2026-10-01'], urls=['u-aetna', 'u-cigna'], labs=['inpatient'],
          fac=[['Hosp A', 'Atlanta', 'H'], ['Dr B', 'Atlanta', 'P']], codes={'1': {'n': 3}, '2': {'n': 1}},
          scope={'Cigna|LocalPlus': ['1']})
bn = ['111', '222']
# ADD: one new network (Anthem), and a refreshed Cigna (replaces the old one); one provider new to the state (333)
ae = dict(nets=['Cigna|LocalPlus', 'Anthem|Blue Open Access'], dates=['2026-10-15'], urls=['u-cigna-new', 'u-anthem'],
          labs=['inpatient', 'outpatient'], fac=[['Dr B', 'Atlanta', 'P'], ['Clinic C', 'Macon', 'G']],
          codes={'1': {'n': 2}, '3': {'n': 1, 'name': 'new code'}}, scope={})
an = ['222', '333']
P = M.plan(be, bn, ae, an)
assert P['nets'] == ['Aetna|Open Access', 'Cigna|LocalPlus', 'Anthem|Blue Open Access'], P['nets']
assert P['nmap'] == [1, 2] and P['replaced'] == [1]
assert P['dates'] == ['2026-10-01', '2026-10-15'] and P['dmap'] == [1]
assert P['urls'] == ['u-aetna', 'u-cigna', 'u-cigna-new', 'u-anthem'] and P['umap'] == [2, 3]
assert P['labs'] == ['inpatient', 'outpatient'] and P['lmap'] == [0, 1]
assert P['npis'] == ['111', '222', '333'] and P['pmap'] == [1, 2]
assert P['fac'][2] == ['Clinic C', 'Macon', 'G'] and len(P['fac']) == 3

# code 1: base has Aetna at both providers + old Cigna at Dr B; add has new Cigna at Dr B (pi 0 -> 1) and Anthem at Clinic C
bf = {'0': [row(0, 1000), row(1, 900, u=1)], '1': [row(0, 200, fee=1), row(1, 180, fee=1, u=1)]}
af = {'0': [row(0, 190, fee=1, u=0, lab=1, others=[(220, 0)])], '1': [row(1, 1500, u=1)]}
f, n, nets = M.merge_code(bf, af, P)
assert all(r[0] != 1 or r[6] == 2 for rows in f.values() for r in rows), 'old Cigna rows must be gone'
assert f['0'] == [row(0, 1000)], f['0']                       # Aetna untouched, old Cigna dropped
dr = f['1']; assert [r[0] for r in dr] == [0, 1], dr          # Dr B: Aetna + NEW Cigna (sorted by network)
assert dr[1][3] == 190 and dr[1][5] == 1 and dr[1][6] == 2 and dr[1][10] == 1 and dr[1][8] == [[220.0, 0]], dr[1]
assert f['2'][0][0] == 2 and f['2'][0][6] == 3, f['2']        # Anthem at the new provider (index 2)
assert n == 4 and nets == {0, 1, 2}, (n, nets)

# flags on added rows: median of 5+ headline rates; a rate under a fifth gets 2, a filler-looking one gets 8
bf = {str(i): [row(0, 1000 + i)] for i in range(5)}
af = {'0': [row(1, 100)], '1': [row(1, 59999.99, flags=0)]}
P2 = M.plan(dict(be, fac=be['fac'] * 3, codes={'9': {'n': 5}}), [str(i) for i in range(6)], ae, ['0', '1'])
f, n, _ = M.merge_code(bf, af, P2)
low = [r for r in f['0'] if r[3] == 100][0]; high = [r for r in f['1'] if r[3] == 59999.99][0]
assert low[4] & 2 and not low[4] & 8, low
assert high[4] & 8, high
assert all(r[4] == 0 for k in bf for r in f[k] if r[0] == 0), 'base rows keep their flags'
# with the BASE build's stored median, added rows are judged against it (here 10,000: 1,500 is under a fifth)
f, n, _ = M.merge_code(bf, {'0': [row(1, 1500)]}, P2, {'0': [10000.0, 40]})
assert [r for r in f['0'] if r[3] == 1500][0][4] & 2
# round trip of the file format
assert M.decode(M.encode(f)) == f
print('merge_build checks passed')
