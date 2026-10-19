"""Dollar math for "percent of billed charges" contracts (Oct 18, 2026, Betsy asked for it).
An insurer or hospital file can say a contract pays a percentage of what the hospital bills, with no dollar figure. Hospitals
post their list price ("gross charge") for each code in their own price files, so where we have that, the page shows the
worked example:  85% of billed charges x the hospital's posted list price $1,200 = $1,020 for this line.
Both numbers are real and linked; the result is labeled as a calculation for that one line (a bill can include other
charges, and the percentage applies to those too). No list price, no match: the page shows the percentage alone, as before.
- Hospital-file percentages: the list price comes from the same file, same code, same setting (inpatient/outpatient) when
  the file says, same fee type (facility/professional).
- Insurer-file percentages: the provider (NPI) is matched to its hospital's own price file through the hospital's CMS number
  (CMS Hospital Enrollments lists each hospital's NPIs; the hospital step records each file's CMS number). D.hlink =
  {provider index: [hospital file index, ...]}, built by hlink_for().
  patch(html) -> html (idempotent, marked /*lpm*/)"""
import collections, csv, json

MARK = '/*lpm*/'
HELPERS = r"""
/*lpm*/
const HLINK = D.hlink || {};
// list prices a hospital file posts for this code: same file, same fee type, same setting when both sides say one.
// Highest first: the main service is usually the biggest charge; smaller lines under the same code (add-ons, supplies) follow.
function listPrices(code, s, doc, set) {
  const hc = H.codes[code]; if (!hc) return [];
  const rs = hc.c.filter(c => c[0] === s && c[3] > 0 && !!c[5] === !!doc);
  const same = set ? rs.filter(c => c[1] === set) : rs, use = same.length ? same : rs, seen = new Set();
  return use.slice().sort((a, b) => b[3] - a[3]).filter(c => !seen.has(c[3]) && seen.add(c[3])).map(c => ({v: c[3], row: c[4], d: (hc.d || [])[c[6]] || ''}));
}
function lpmLine(pct, s, lps, who) {
  if (!lps.length) return '';
  const x = hsrc(s), one = lp => `${pct}% × ${money(lp.v)} = <b>${money(Math.round(pct * lp.v) / 100)}</b>`;
  const desc = lp => lp.d ? ` <span class="lpmd">(“${esc(lp.d)}”)</span>` : '';
  const main = lps[0], rest = lps.slice(1);
  return `<div class="doc lpm">${one(main)} for this line, using ${esc(who || x.name)}'s posted list price${desc(main)} ${hlink(s, main.row)}</div>` +
    (rest.length ? `<details class="oth lpm"><summary>${rest.length} other line${rest.length > 1 ? 's' : ''} this hospital bills under this code</summary><ul>${rest.slice(0, 8).map(lp =>
      `<li><span>${one(lp)}${desc(lp)} ${hlink(s, lp.row)}</span></li>`).join('')}${rest.length > 8 ? `<li class="doc">and ${rest.length - 8} more</li>` : ''}</ul></details>` : '');
}
// a hospital-file percentage, priced with the same file's list price
const lpmH = r => r[5] ? lpmLine(r[6], r[0], listPrices(S.code, r[0], r[4], r[8]), '') : '';
// an insurer-file percentage for provider fi, priced with its own hospital file's list price
function lpmIns(fi, r) {
  const ss = HLINK[fi] || []; let out = '';
  ss.forEach(s => { out += lpmLine(r[3], s, listPrices(S.code, s, r[1] === 1, 0), ''); });
  return out;
}
/*/lpm*/
"""
NOTE = ("<p class=\"sub\">Where the hospital posts a list price for this code in its own price file, we show the math for that one line: "
        "the percentage times its list price. A real bill can include other charges (supplies, drugs, other services), and the "
        "percentage applies to those too.</p>")


def _sub(s, old, new, label):
    if old not in s: raise SystemExit(f'list_price_math: page code changed, cannot find: {label}')
    return s.replace(old, new, 1)


def patch(s):
    if MARK in s: return s
    s = _sub(s, "const hval = r => r[5] ? `<span class=\"pct\">${r[6]}% of billed charges</span>` : `<span class=\"price\">${money(r[6])}</span>`;",
             "const hval = r => r[5] ? `<span class=\"pct\">${r[6]}% of billed charges</span>${lpmH(r)}` : `<span class=\"price\">${money(r[6])}</span>`;" + HELPERS, 'hval')
    s = _sub(s, "No dollar figure in the file. The amount depends on the facility's list price, so ask the facility for it.</p>` +\n      pct.map(f => `<div class=\"pline\"><div class=\"who\"><b>${esc(f.name)}</b> · ${esc(f.city)}</div><span class=\"lead\"></span><div class=\"right\">${val(f.facP[0])}<div>${src(f.facP[0])}</div></div></div>`).join('')",
             "No dollar figure in the insurer's file. The amount depends on the facility's list price.</p>" + NOTE + "` +\n      pct.map(f => `<div class=\"pline\"><div class=\"who\"><b>${esc(f.name)}</b> · ${esc(f.city)}${lpmIns(f.fi, f.facP[0])}</div><span class=\"lead\"></span><div class=\"right\">${val(f.facP[0])}<div>${src(f.facP[0])}</div></div></div>`).join('')",
             'insurer percent rows')
    s = _sub(s, ".cols>div{min-width:0}", ".cols>div{min-width:0}\n.lpm b{font-family:var(--mono,inherit)}.lpmd{color:var(--ink-2)}", 'css')
    return s


def hlink_for(src, areas, enroll_csv, npis, file_npis=None):
    """src: the page's D.hosp.src; areas: the hospital step's areas.json; enroll_csv: CMS Hospital Enrollments file;
    npis: the build's npis.json; file_npis: R2 reference/geo/names.json ({'file:<id>': [address, NPIs]}: the NPIs each
    hospital lists in its own price file, required by CMS; catches NPIs a hospital bills insurers under but never enrolled
    with Medicare). Returns {provider index: [hospital file index]}."""
    import re
    jobs = {j['id']: j['ccn'] for a in areas.values() for j in a['jobs']}
    en = collections.defaultdict(set)
    for r in csv.DictReader(open(enroll_csv, encoding='latin-1')): en[r['CCN']].add(r['NPI'])
    pos = {n: i for i, n in enumerate(npis)}
    out = collections.defaultdict(list)
    for si, x in enumerate(src):
        mine = set(en.get(jobs.get(x[5]), ()))
        own = (file_npis or {}).get('file:' + x[5])
        if own: mine |= set(re.findall(r'\b\d{10}\b', str(own[1] if len(own) > 1 else '')))
        for n in mine:
            if n in pos and si not in out[str(pos[n])]: out[str(pos[n])].append(si)
    return dict(out)
