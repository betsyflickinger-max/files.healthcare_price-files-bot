"""Practice view for the Price Finder page (Oct 18, 2026, Betsy OK'd the practice view; tested on Mississippi).
Adds, to a page whose build has practices (every_code.py PRACTICE=1: per-code files carry 'p', embed.json carries 'prac'):
- a "Doctors and clinicians, by practice" list: one line per practice with its price (or the real lowest-highest range when
  its clinicians have different rates; never an average), the number of clinicians, and a fold-out listing every clinician
  with their own rate;
- a name box over that list that finds a doctor or a practice (a doctor is shown inside each practice they bill under);
- a note saying where each practice's name comes from (IRS records, two sources agreeing, or Medicare's directory). A group
  with no public name is listed by its clinicians: "A, B and C", or "A, B and 4 other clinicians";
- practices on the "every rate" board.
Pages without practice data behave exactly as before (every addition checks for D.prac / C.p).
  patch(html) -> html   (idempotent: marked /*prac*/)"""
import sys

MARK = '/*prac*/'
HELPERS = r"""
/*prac*/
const PRAC = D.prac || null;
const PRAC_HOW = {i: 'name: IRS records', b: 'name: insurer file + Medicare directory', m: 'name: Medicare directory', n: 'no public practice name'};
const facName = i => D.fac[i] ? D.fac[i][0] : 'NPI ' + i;
function pracName(pid) {
  const p = PRAC && PRAC[pid]; if (!p) return 'Practice';
  if (p[0]) return p[0];
  const ds = p[3], n = ds.length;
  if (n === 1) return facName(ds[0]);
  if (n === 2) return facName(ds[0]) + ' and ' + facName(ds[1]);
  if (n === 3) return facName(ds[0]) + ', ' + facName(ds[1]) + ' and ' + facName(ds[2]);
  return `${facName(ds[0])}, ${facName(ds[1])} and ${(n - 2).toLocaleString()} other clinicians`;
}
const qWords = () => (S.docQ || '').toLowerCase().trim();
const hit = (txt, q) => q && txt.toLowerCase().includes(q);
const markQ = (txt, q) => { const t = esc(txt); if (!q) return t; const i = txt.toLowerCase().indexOf(q); return i < 0 ? t : esc(txt.slice(0, i)) + '<mark>' + esc(txt.slice(i, i + q.length)) + '</mark>' + esc(txt.slice(i + q.length)); };
// one entry per practice for network `net`: rates sorted low to high, each with its clinicians
function pracEntries(C, net) {
  const out = []; let zero = 0;
  Object.entries(C.p || {}).forEach(([pid, ents]) => {
    const e = ents.filter(([r]) => r[0] === net); if (!e.length) return;
    const pos = e.filter(([r]) => !isZero(r) && r[2] === 0);
    if (!pos.length) { if (!e.some(([r]) => r[2] === 1)) zero++; return; }
    const doc = pos.filter(([r]) => r[1] === 1), use = (doc.length ? doc : pos).sort((a, b) => a[0][3] - b[0][3]);
    const P = (PRAC && PRAC[pid]) || ['', '', 'n', []];
    out.push({fi: -1, pid, name: pracName(pid), city: P[1], kind: 'R', how: P[2], facD: [], facP: [], docD: use.map(x => x[0]), ents: use,
              nDocs: new Set(use.flatMap(x => x[1])).size});
  });
  // a doctor who bills under more than one practice shows in each; say so, or two identical one-doctor lines look like a mistake
  const seen = {}; out.forEach(f => new Set(f.ents.flatMap(x => x[1])).forEach(i => { seen[i] = (seen[i] || 0) + 1; }));
  out.forEach(f => { f.multi = f.nDocs === 1 && seen[f.ents[0][1][0]] > 1; });
  return {list: out, zero};
}
function pracMatch(f, q) { return !q || hit(f.name, q) || f.ents.some(([, ds]) => ds.some(i => hit(facName(i), q))); }
function pracLine(f) {
  const q = qWords(), r = f.ents[0][0], hi = f.ents[f.ents.length - 1][0][3];
  const price = hi !== r[3] ? `<span class="price">${money(r[3])}–${money(hi)}</span>` : val(r);
  // while searching for a doctor, the fold-out shows only the rates that doctor has (the price range above stays the practice's)
  const ents = q && !hit(f.name, q) ? f.ents.filter(([, ds]) => ds.some(i => hit(facName(i), q))) : f.ents;
  const docs = ents.map(([x, ds]) => {
    const names = ds.map(facName), shown = q ? names.filter(n => hit(n, q)).concat(names.filter(n => !hit(n, q))) : names;
    const lim = q ? Math.max(6, names.filter(n => hit(n, q)).length) : 6;
    return `<li><span>${shown.slice(0, lim).map(n => markQ(n, q)).join('; ')}${shown.length > lim ? ` and ${(shown.length - lim).toLocaleString()} more` : ''}</span><span class="lead"></span>${money(x[3])}</li>`;
  }).join('');
  const sum = `${f.nDocs.toLocaleString()} clinician${f.nDocs > 1 ? 's' : ''} with this rate${f.ents.length > 1 ? ' · ' + f.ents.length + ' different rates' : ''}`;
  const solo = f.nDocs === 1 && facName(f.ents[0][1][0]) === f.name;   // a one-doctor line needs no fold-out
  const how = PRAC_HOW[f.how] ? `<div class="doc">${PRAC_HOW[f.how]}</div>` : '';
  return `<div class="pline"><div class="who"><b>${markQ(f.name, q)}</b>${f.city ? ' · ' + esc(f.city) : ''} ${flags(r)}${solo ? '' : `<details class="oth"${q ? ' open' : ''}><summary>${sum}</summary><ul>${docs}</ul></details>`}${how}${f.multi ? '<div class="doc">also bills under another practice</div>' : ''}${lab(r[10]) ? `<div class="doc">${esc(lab(r[10]))}</div>` : ''}</div><span class="lead"></span>
    <div class="right">${price}<div class="doc">clinician fee</div><div>${src(r)}</div></div></div>`;
}
function pracBoard(C) {
  const out = [];
  Object.entries(C.p || {}).forEach(([pid, ents]) => {
    const rs = ents.filter(([r]) => S.boardIns === 'All' || NET[r[0]].i === S.boardIns).map(([r, ds]) => { const x = r.slice(); x.nd = ds.length; return x; });
    if (!rs.length) return;
    const P = (PRAC && PRAC[pid]) || ['', '', 'n', []];
    out.push({fi: -1, name: pracName(pid), city: P[1], kind: 'R', nDocs: P[3].length, rs});
  });
  return out;
}
/*/prac*/
"""


def _sub(s, old, new, label):
    if old not in s: raise SystemExit(f'practice_view: page code changed, cannot find: {label}')
    return s.replace(old, new, 1)


def patch(s):
    if MARK in s: return s
    s = _sub(s, "D.codes[code].f = JSON.parse(text).f;",
             "{ const J_ = JSON.parse(text); D.codes[code].f = J_.f; D.codes[code].p = J_.p || null; }", 'loadCode')
    s = _sub(s, "P: 'Individual doctors and clinicians'};", "P: 'Individual doctors and clinicians', R: 'Doctors and clinicians, by practice'};", 'KIND')
    s = _sub(s, "const isZero = r => r[4] & 4;", "const isZero = r => r[4] & 4;" + HELPERS, 'helpers')
    # patient view
    s = _sub(s, "  const zeroOnly = byFac.filter(f => f.zero).length;",
             "  let zeroOnly = byFac.filter(f => f.zero).length;", 'zeroOnly')
    s = _sub(s, "  const useFac = byFac.some(f => f.facD.length);",
             "  if (C.p) { const pe = pracEntries(C, net); byFac.push(...pe.list); zeroOnly += pe.zero; }   " + MARK + "\n  const useFac = byFac.some(f => f.facD.length);", 'practices in patient view')
    s = _sub(s, "  const line = f => {\n    const rs = primary(f), r = rs[0];",
             "  const line = f => {\n    if (f.kind === 'R') return pracLine(f);\n    const rs = primary(f), r = rs[0];", 'line')
    s = _sub(s, "    const list = byFac.filter(f => (drg && kind === 'H' ? (f.kind === 'H' || f.kind === 'A') : f.kind === kind) && primary(f).length).sort((a, b) => primary(a)[0][3] - primary(b)[0][3]);\n    if (!list.length) return '';",
             "    const all_ = byFac.filter(f => (drg && kind === 'H' ? (f.kind === 'H' || f.kind === 'A') : f.kind === kind) && primary(f).length).sort((a, b) => primary(a)[0][3] - primary(b)[0][3]);\n"
             "    if (!all_.length) return '';\n"
             "    const list = kind === 'R' ? all_.filter(f => pracMatch(f, qWords())) : all_;\n"
             "    const box = kind === 'R' ? `<label class=\"docq\">Find a doctor or practice <input id=\"docQ\" type=\"search\" autocomplete=\"off\" placeholder=\"last name or practice\" value=\"${esc(S.docQ || '')}\"></label>${qWords() && !list.length ? '<p class=\"empty\">No doctor or practice by that name has a rate in this network.</p>' : ''}` : '';", 'group filter')
    s = _sub(s, "    return `<div><h4>${label} · ${list.length.toLocaleString()}</h4>${list.slice(0, lim).map(line).join('')}",
             "    return `<div><h4>${label} · ${all_.length.toLocaleString()}</h4>${box}${list.slice(0, lim).map(line).join('')}", 'group head')
    s = _sub(s, "    <div class=\"cols\">${group('G', KIND.G)}${group('P', KIND.P)}</div>",
             "    <div class=\"cols\">${group('G', KIND.G)}${group('R', KIND.R)}${group('P', KIND.P)}</div>", 'cols')
    s = _sub(s, "  bindMore(renderPatient);\n}\n\n// ---------- full board ----------",
             "  bindMore(renderPatient);\n  const dq = $('#docQ'); if (dq) dq.addEventListener('input', () => { S.docQ = dq.value; S.showAll = {}; const p = dq.selectionStart; renderPatient(); const n = $('#docQ'); if (n) { n.focus(); n.setSelectionRange(p, p); } });   " + MARK + "\n}\n\n// ---------- full board ----------", 'search box')
    # board
    s = _sub(s, "  const rows = Object.entries(C.f).map(([fi, rs]) => ({...fac(+fi), fi: +fi, rs: rs.filter(r => S.boardIns === 'All' || NET[r[0]].i === S.boardIns)}))",
             "  const rows = [...Object.entries(C.f).map(([fi, rs]) => ({...fac(+fi), fi: +fi, rs: rs.filter(r => S.boardIns === 'All' || NET[r[0]].i === S.boardIns)})), ...pracBoard(C)]", 'board rows')
    s = _sub(s, "${f.kind === 'A' ? 'Surgery center' : 'Hospital or other facility'}",
             "${f.kind === 'R' ? `Practice · ${f.nDocs.toLocaleString()} clinician${f.nDocs > 1 ? 's' : ''}` : f.kind === 'A' ? 'Surgery center' : 'Hospital or other facility'}", 'board place')
    s = _sub(s, "${r[7] ? ` · +${r[7]} other` : ''}",
             "${r[7] ? ` · +${r[7]} other` : ''}${r.nd ? ` · ${r.nd.toLocaleString()} clinician${r.nd > 1 ? 's' : ''}` : ''}", 'board rate')
    s = _sub(s, ".cols>div{min-width:0}",
             ".cols>div{min-width:0}\n.docq{display:block;font-size:13px;color:var(--ink-2);margin:2px 0 8px}.docq input{display:block;width:100%;margin-top:4px;font:14px var(--body);padding:7px 10px;border:1px solid var(--rule);background:var(--paper-2);color:var(--ink);border-radius:2px}\n.pline mark{background:var(--warn-soft);color:inherit;padding:0 1px}", 'css')
    return s


if __name__ == '__main__':
    p = sys.argv[1]; s = open(p).read(); open(p, 'w').write(patch(s)); print('practice view added to', p)
