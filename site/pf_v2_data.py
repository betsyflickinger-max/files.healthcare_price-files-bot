"""Data for the Price Finder v2 mock-up (Oct 19, 2026): one procedure in one area as a places x insurers table.

Rows: hospitals and surgery centers with a published facility fee for the code (same filters as the price pages:
kind of place, name test, no percent-of-charges, no "unusually low"/"unusually high", no $0, full service only).
Columns: Medicare for that place (after CMS's local wage adjustment where we matched the place to its Medicare record,
national otherwise), Medicare Advantage (the lowest Medicare Advantage line in the hospital's own price file), and one
column per insurer network. Doctor's fee per network: the lowest, middle and highest published professional fee
across DFW doctors and groups (each a real listed price; the middle is the middle listed price, never an average).

  python site/pf_v2_data.py CODE D.json t.json h.json npis.json med_local.json packages.parquet OUT.json
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from procedure_pages import FERTILITY, NOT_HERE, PARPLAN, SPECIALTY, kind_of, looks_placeholder, nice  # noqa: E402


def build(code, D, t, h, npis, ml, pkg_does):
    C = D['codes'][code]
    cat = C.get('cat', '')
    f = t['f']
    nets = [n.split('|', 1) for n in D['nets']]
    med = D['med']['codes'][code]

    def fits(fi):
        x = D['fac'][int(fi)]
        nm, kd = x[0].lower(), kind_of(x)
        ok = kd in {'H', 'A'} and not NOT_HERE.search(nm) and not FERTILITY.search(nm)
        for rx, cats in SPECIALTY:
            if ok and rx.search(nm) and cat not in cats:
                ok = False
        return ok

    def median(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if len(xs) >= 5 else None

    dollar = lambda r: not r[2] and not r[4] & 6 and r[3] > 0   # r[3] is already the full-service (no modifier) headline
    m_fac = median([r[3] for fi, rs in f.items() if fits(fi) for r in rs if not r[1] and dollar(r)])
    m_doc = median([r[3] for rs in f.values() for r in rs if r[1] and dollar(r)])

    def keep(r, m):
        return dollar(r) and not (m and r[3] < 0.2 * m) and not r[4] & 8 and not (m and looks_placeholder(r[3], m))

    places, docs = {}, {}
    for fi, rs in f.items():
        for r in rs:
            if r[1]:
                if keep(r, m_doc):
                    k = (fi, r[0])
                    docs[k] = min(docs.get(k, 1e12), r[3])
                continue
            if not fits(fi) or not keep(r, m_fac):
                continue
            p = places.setdefault(fi, {})
            if r[0] not in p or r[3] < p[r[0]][0]:
                p[r[0]] = [round(r[3], 2), r[5], r[6]]

    # doctor's fee per network: lowest / middle / highest listed price across doctors and groups
    by_net = {}
    for (fi, n), v in docs.items():
        by_net.setdefault(n, []).append(v)
    doc = {}
    for n, vs in by_net.items():
        vs.sort()
        doc[n] = {'lo': vs[0], 'mid': vs[len(vs) // 2], 'hi': vs[-1], 'n': len(vs)}

    # Medicare Advantage from hospitals' own files (product type 2), matched to places by name
    H = D['hosp']
    norm = lambda s: re.sub(r'\b(llc|lp|inc|the|of|at|subsidiary|company|corporation|hospital|medical|center|health)\b|[^a-z0-9 ]', ' ',
                            (s or '').lower()).split()
    ma_by_src = {}
    plans = h.get('p') or []
    for r in h.get('r', []):
        if r[2] != 2 or r[4] or r[5] or r[6] <= 0 or r[0] >= len(H['src']):
            continue
        if r[0] not in ma_by_src or r[6] < ma_by_src[r[0]]['v']:
            x = H['src'][r[0]]
            ma_by_src[r[0]] = {'v': round(r[6], 2), 'ins': H['ins'][r[1]], 'plan': plans[r[3]] if r[3] < len(plans) else '',
                               'date': x[3], 'url': x[4], 'row': r[7], 'name': x[0], 'city': x[1]}

    cash_by_src = {}
    for r in h.get('c', []):
        if r[5] != 0 or r[2] <= 0 or r[0] >= len(H['src']):
            continue
        if r[0] not in cash_by_src or r[2] < cash_by_src[r[0]]['v']:
            x = H['src'][r[0]]
            cash_by_src[r[0]] = {'v': round(r[2], 2), 'date': x[3], 'url': x[4], 'row': r[4], 'name': x[0], 'city': x[1],
                                 'what': "hospital's price file, hospital fee only"}
    posted = [{'v': c['v'], 'date': c.get('chk', ''), 'url': c.get('src', ''), 'name': c['name'], 'city': c.get('city', ''),
               'what': 'posted cash price' + (f" ({c['label']})" if c.get('label') else '')} for c in D.get('cash', []) if c.get('code') == code]

    def ma_for(name, city, pool=None):
        a = set(norm(name))
        best, score = None, 0
        for m in (ma_by_src.values() if pool is None else pool):
            b = set(norm(m['name']))
            if not a or not b:
                continue
            j = len(a & b) / len(a | b)
            if m['city'] and city and m['city'].lower() != city.lower():
                j -= 0.3
            if j > score:
                best, score = m, j
        return best if score >= 0.6 else None

    out_places = []
    for fi, p in places.items():
        x = D['fac'][int(fi)]
        kd = kind_of(x)
        npi = npis[int(fi)]
        m = ml.get(npi)
        if kd == 'H':
            nat, share = med['opps'][0], 0.60
        else:
            nat, share = med['asc'][0], 0.50
        local = round(nat * (share * m[1] + 1 - share), 2) if m and m[0] == kd else None
        name, city = nice(x[0]), nice(x[1])
        out_places.append({'i': int(fi), 'name': name, 'city': city, 'kind': kd, 'npi': npi,
                           'does': npi in pkg_does, 'med': local or nat, 'med_local': bool(local),
                           'ma': ma_for(name, city) if kd == 'H' else None,
                           'cash': min([c for c in (ma_for(name, city, cash_by_src.values()) if kd == 'H' else None,
                                                    ma_for(name, city, posted)) if c], key=lambda c: c['v'], default=None),
                           'fees': {str(n): v for n, v in p.items()}})
    # one row per place: a place listed under two NPIs (same name and city) keeps its lowest fee in each network
    merged = {}
    for o in out_places:
        k = (o['name'].lower(), o['city'].lower(), o['kind'])
        if k not in merged:
            merged[k] = o
            continue
        m = merged[k]
        for n, v in o['fees'].items():
            if n not in m['fees'] or v[0] < m['fees'][n][0]:
                m['fees'][n] = v
        m['does'] = m['does'] or o['does']
        for f in ('ma', 'cash'):
            if o[f] and (not m[f] or o[f]['v'] < m[f]['v']):
                m[f] = o[f]
        if o['med_local'] and not m['med_local']:
            m['med'], m['med_local'] = o['med'], True
    out_places = list(merged.values())
    out_places.sort(key=lambda o: (not o['does'], min(v[0] for v in o['fees'].values())))
    pfs = med['pfs']['dal']
    return {'code': code, 'name': C['name'], 'nets': D['nets'], 'dates': D['dates'], 'urls': D['urls'],
            'parplan': [i for i, n in enumerate(nets) if PARPLAN.search(n[1])],
            'doc': {str(k): v for k, v in doc.items()},
            'medicare': {'opps': med['opps'][0], 'asc': med['asc'][0], 'doc_fac': pfs[1], 'doc_office': pfs[0],
                         'src': D['med']['src']},
            'ma_hospitals': len(ma_by_src), 'places': out_places}


if __name__ == '__main__':
    import duckdb
    code, Dp, tp, hp, np_, mlp, pq, outp = sys.argv[1:9]
    D = json.load(open(Dp))
    does = {r[0] for r in duckdb.sql(f"select distinct facility_npi from '{pq}' where does_procedure").fetchall()}
    o = build(code, D, json.load(open(tp)), json.load(open(hp)), json.load(open(np_)), json.load(open(mlp))['npi'], does)
    json.dump(o, open(outp, 'w'), separators=(',', ':'))
    print(len(o['places']), 'places;', sum(1 for p in o['places'] if p['ma']), 'with Medicare Advantage;',
          sum(1 for p in o['places'] if p['does']), 'with evidence;', len(o['doc']), 'networks with doctor fees')
