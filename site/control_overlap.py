"""Control center, Network access tab: insurer and network filters on "How much networks overlap" (Nov 3, 2026, Betsy).

The grid used to follow only the Networks/Insurers switch and Insurer menu at the top of the tab, so from the grid it
looked stuck on "All <insurer> networks". The grid's own header now has:
  - Insurers combined / Each network   (the same switch as the top of the tab; both stay in step)
  - Rows: All insurers or one insurer  (the same as the tab's Insurer menu)
  - Columns: All insurers or one insurer (grid only; e.g. BCBSTX's networks against Aetna's)
In "Each network", thin lines split the grid between insurers. No data changes.

patch(d) edits <d>/site/control/index.html. Each step is skipped once done; a missing anchor (the page was rebuilt
differently) is reported, never fatal. Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy
re-applies it.
"""
import os

KIND_SEG = ('<div class="seg" role="group" aria-label="Providers counted"><button type="button" data-nkind="all">All providers</button>'
            '<button type="button" data-nkind="hosp">Hospitals only</button></div>')
INS_WIRE = ("    $('#ninsurer').addEventListener('change', (e) => dash.setParams({ninsurer: e.target.value || null, nnet: null, nb: null}));")
INS_FILL = ("    if (accAll) { const s = $('#ninsurer'); s.replaceChildren(new Option('All insurers', ''), ...insList.map((i) => new Option(i, i))); s.value = ins || ''; }")
HEAT_END = ".text((d) => Math.round(100 * d.r[f]));"

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('id="nh-ins"', KIND_SEG,
     '<div class="controls nh-ctl">'
     '<div class="seg" role="group" aria-label="Grid shows"><button type="button" data-nlevel="insurer">Insurers combined</button>'
     '<button type="button" data-nlevel="network">Each network</button></div>'
     '<label class="muted" for="nh-ins">Rows</label><select id="nh-ins" aria-label="Insurer in the rows"></select>'
     '<label class="muted" for="nh-vs">Columns</label><select id="nh-vs" aria-label="Insurer in the columns"></select>'
     + KIND_SEG + '</div>'),
    ("$('#nh-vs')", INS_WIRE,
     INS_WIRE + "\n"
     "    // Nov 3 (site/control_overlap.py): the overlap grid's own menus. Rows = the tab's insurer; Columns = grid only.\n"
     "    if ($('#nh-ins')) $('#nh-ins').addEventListener('change', (e) => dash.setParams({ninsurer: e.target.value || null, nnet: null, nb: null}));\n"
     "    if ($('#nh-vs')) $('#nh-vs').addEventListener('change', (e) => dash.setParams({nvs: e.target.value || null}));"),
    ("const vs = insList.includes(p.nvs)", INS_FILL,
     INS_FILL + "\n"
     "    const vs = insList.includes(p.nvs) ? p.nvs : null;   // Nov 3: the overlap grid's Columns menu\n"
     "    if (accAll) [['#nh-ins', ins], ['#nh-vs', vs]].forEach(([id, v]) => { const s = $(id); if (!s) return;\n"
     "      s.replaceChildren(new Option('All insurers', ''), ...insList.map((i) => new Option(i, i))); s.value = v || ''; });"),
    ("drawHeat(acc, vs ?", "drawHeat(acc, accAll, ov, pick);",
     "drawHeat(acc, vs ? accAll.filter((r) => r.insurer === vs) : accAll, ov, pick);"),
    ("lines between insurers", HEAT_END,
     HEAT_END + "\n"
     "    if (LEVEL() === 'network') {   // Nov 3 (site/control_overlap.py): lines between insurers\n"
     "      const ri = rowsAcc.slice().sort(order).map((r) => r.insurer), ci = colsAcc.slice().sort(order).map((r) => r.insurer);\n"
     "      const sep = svg.append('g').style('pointer-events', 'none').style('stroke', 'var(--color-fg-muted)').style('stroke-width', 1.25);\n"
     "      ri.forEach((v, i) => { if (i && v !== ri[i - 1]) sep.append('line').attr('x1', lab - 4).attr('x2', lab + cell * cn.length).attr('y1', top + i * cell - 0.5).attr('y2', top + i * cell - 0.5); });\n"
     "      ci.forEach((v, j) => { if (j && v !== ci[j - 1]) sep.append('line').attr('x1', lab + j * cell - 0.5).attr('x2', lab + j * cell - 0.5).attr('y1', top - 4).attr('y2', top + cell * rn.length); });\n"
     "    }"),
]
# Nov 3 (later): "Download crosswalk (CSV)": every network-to-network pair in the picked area (or insurer-to-insurer in
# Insurers combined), as listed in the grid, ignoring the Rows/Columns menus so the file is the whole crosswalk.
COLS_SEL = '<label class="muted" for="nh-vs">Columns</label><select id="nh-vs" aria-label="Insurer in the columns"></select>'
HEAT_CALL = "drawHeat(acc, vs ? accAll.filter((r) => r.insurer === vs) : accAll, ov, pick);"
STEPS += [
    ('id="nh-csv"', COLS_SEL, COLS_SEL + '<button type="button" id="nh-csv" title="Every pair in this area, one row each">Download crosswalk (CSV)</button>'),
    ("window.NH_CSV = ", HEAT_CALL, HEAT_CALL + "\n      window.NH_CSV = {ov, accAll, market: p.market, level: LEVEL()};"),
    ("$('#nh-csv').addEventListener", "    if ($('#nh-vs')) $('#nh-vs').addEventListener",
     "    if ($('#nh-csv')) $('#nh-csv').addEventListener('click', () => {   // Nov 3: the whole crosswalk for the picked area\n"
     "      const X = window.NH_CSV; if (!X || !X.ov || !X.ov.length) return;\n"
     "      const ins = new Map((X.accAll || []).map((r) => [r.label, r.insurer])), q = (v) => v == null ? '' : /[\",\\n]/.test(String(v)) ? '\"' + String(v).replace(/\"/g, '\"\"') + '\"' : String(v);\n"
     "      const F = ['shared', 'a_providers', 'share_of_a_in_b', 'jaccard', 'shared_hospitals', 'a_hospitals', 'hospital_share_of_a_in_b', 'matched_prices', 'a_lower_share', 'same_share', 'a_vs_b_middle'];\n"
     "      const head = ['area', 'level', 'row_insurer', 'row_' + X.level, 'column_insurer', 'column_' + X.level, ...F];\n"
     "      const rows = X.ov.slice().sort((a, b) => (ins.get(a.a) || '').localeCompare(ins.get(b.a) || '') || a.a.localeCompare(b.a) || (ins.get(a.b) || '').localeCompare(ins.get(b.b) || '') || a.b.localeCompare(b.b))\n"
     "        .map((r) => [X.market, r.level, ins.get(r.a), r.a, ins.get(r.b), r.b, ...F.map((f) => r[f])].map(q).join(','));\n"
     "      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([[head.join(','), ...rows].join('\\n') + '\\n'], {type: 'text/csv'}));\n"
     "      a.download = `network-crosswalk_${String(X.market).toLowerCase()}_${X.level}s_${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(a); a.click(); a.remove();\n"
     "    });\n"
     "    if ($('#nh-vs')) $('#nh-vs').addEventListener"),
]
# Nov 3 (later, Betsy): the Market menu goes from the whole country down to one area. dashboard/build_network.py adds
# roll-ups ("US" = United States, insurers combined; "TX" = Texas whole state, insurers and networks), lists each area's
# parent in net_parts, and writes net_access in parts (net_access.json, _2 ... _6). The tab keeps its own area (nmk) so
# picking National here does not change the Prices tab. Prices stay inside one area; roll-ups show counts only.
ACC_JOIN = ("  const rowsOf = (id) => { const d = dash.data(id); return d.status === 'ok' ? d.data : null; };\n"
            "  const P = () => dash.params();\n")
MK_FILL = ("      const names = new Map((markets || []).map((m) => [m.market, m.name]));\n"
           "      const keys = [...new Set(access.map((r) => r.market))].sort((x, y) => (x === 'DFW' ? -1 : y === 'DFW' ? 1 : (names.get(x) || x).localeCompare(names.get(y) || y)));\n"
           "      const s = $('#nmarket'); s.replaceChildren(...keys.map((k) => new Option(names.get(k) || k, k))); s.value = p.market;\n")
MK_WIRE = "    $('#nmarket').addEventListener('change', (e) => dash.setParams({market: e.target.value, nnet: null}));"
SEGS = "seg('data-nlevel', LEVEL()); seg('data-nkind', KINDP()); seg('data-nfee', FEE());"
HEAT0 = "const el = $('#n-heat'); el.classList.remove('dash-skeleton'); el.replaceChildren();"
ROLL_MSG = "'Prices are compared inside one area. Pick an area under this one in the Market menu to see them.'"
STEPS += [
    ("NETACC_IDS", ACC_JOIN,
     "  // Nov 3 (site/control_overlap.py): net_access arrives in parts; the tab's own area is the nmk setting (falls back to market)\n"
     "  const NETACC_IDS = ['net_access', 'net_access_2', 'net_access_3', 'net_access_4', 'net_access_5', 'net_access_6']; let NETACC_C = null;\n"
     "  const rowsOf = (id) => {\n"
     "    if (id === 'net_access') { const ds = NETACC_IDS.map((x) => dash.data(x));\n"
     "      if (ds[0].status !== 'ok' || ds.some((d) => d.status === 'loading')) return null;   // a part not there yet (404) counts as empty\n"
     "      if (NETACC_C && NETACC_C.src.every((x, i) => x === ds[i].data)) return NETACC_C.rows;\n"
     "      NETACC_C = {src: ds.map((d) => d.data), rows: [].concat(...ds.map((d) => d.status === 'ok' && Array.isArray(d.data) ? d.data : []))}; return NETACC_C.rows; }\n"
     "    const d = dash.data(id); return d.status === 'ok' ? d.data : null; };\n"
     "  const P = () => { const p = dash.params(); return p.nmk ? Object.assign({}, p, {market: p.nmk}) : p; };\n"),
    ("data-all", MK_FILL,
     "      const names = new Map((markets || []).map((m) => [m.market, m.name]));   // Nov 3: National, then each state with 'All of <state>' first\n"
     "      const meta = new Map((rowsOf('net_parts') || []).map((r) => [r.market, r])); meta.forEach((r, k) => { if (r.name && !names.has(k)) names.set(k, r.name); });\n"
     "      const parents = new Set([...meta.values()].map((r) => r.parent).filter(Boolean));\n"
     "      const keys = [...new Set(access.map((r) => r.market))].sort((x, y) => (x === 'US' ? -1 : y === 'US' ? 1 : x === 'DFW' ? -1 : y === 'DFW' ? 1 : (names.get(x) || x).localeCompare(names.get(y) || y)));\n"
     "      const opt = (k) => { const o = new Option(names.get(k) || k, k), r = meta.get(k) || {};\n"
     "        if (k === 'US') o.textContent = 'All of the United States';\n"
     "        else if (r.rollup || parents.has(k)) { const st = r.state || names.get(k) || k; o.textContent = 'All of ' + st; o.setAttribute('data-st', st); o.setAttribute('data-all', '1'); }\n"
     "        return o; };\n"
     "      const s = $('#nmarket'); s.replaceChildren(...keys.map(opt)); s.value = p.market;\n"),
    ("|| ((rowsOf('net_parts') || []).find((r) => r.market === p.market) || {}).name",
     "const mkName = markets ? (markets.find((m) => m.market === p.market) || {}).name : '';",
     "const mkName = (markets ? (markets.find((m) => m.market === p.market) || {}).name : '') || ((rowsOf('net_parts') || []).find((r) => r.market === p.market) || {}).name;"),
    ("nmk: e.target.value", MK_WIRE,
     "    $('#nmarket').addEventListener('change', (e) => dash.setParams(Object.assign({nmk: e.target.value, nnet: null, nb: null}, e.target.value === 'US' ? {nlevel: 'insurer'} : {})));"),
    ("window.NET_ROLLUP = ", SEGS,
     SEGS + " window.NET_ROLLUP = !!((rowsOf('net_parts') || []).find((r) => r.market === p.market) || {}).rollup;"),
    ("const hmsg = ", HEAT0,
     HEAT0 + "\n"
     "    const hmsg = (t) => { const q = document.createElement('p'); q.className = 'muted'; q.textContent = t; el.appendChild(q); const k0 = $('#n-heat-key'); if (k0) k0.innerHTML = ''; };   // Nov 3\n"
     "    if (LEVEL() === 'network' && (!overlap.length || !rowsAcc.length)) return hmsg(P().market === 'US' ? 'Nationally the grid is by insurer: pick Insurers combined, or pick a state or area in the Market menu to see each network.'\n"
     "      : rowsAcc.length ? `${rowsAcc.length} networks here are too many for a network-by-network grid. Pick Insurers combined, or an area under this one.` : 'No networks to compare here.');\n"
     "    if (rowsAcc.length * colsAcc.length > 250000) return hmsg('Too many networks for one grid here. Pick one insurer in Rows or Columns, or Insurers combined.');"),
    ("NET_ROLLUP ? 'Prices are compared inside one area. Pick an area under this one in the Market menu to see them.' : 'No network has enough priced procedures",
     "'No network has enough priced procedures here yet.'", "(window.NET_ROLLUP ? " + ROLL_MSG + " : 'No network has enough priced procedures here yet.')"),
    ("NET_ROLLUP ? 'Prices are compared inside one area. Pick an area under this one in the Market menu to see them.' : 'No network has enough priced rates",
     "'No network has enough priced rates here yet.'", "(window.NET_ROLLUP ? " + ROLL_MSG + " : 'No network has enough priced rates here yet.')"),
    ("NET_ROLLUP ? 'Prices are compared inside one area. Pick an area under this one in the Market menu to see them.' : 'No network has 5 or more",
     "'No network has 5 or more priced providers for this procedure and fee type.'", "(window.NET_ROLLUP ? " + ROLL_MSG + " : 'No network has 5 or more priced providers for this procedure and fee type.')"),
    ("NET_ROLLUP ? 'Prices are compared inside one area. Pick an area under this one in the Market menu to see them.' : 'Not enough shared",
     "'Not enough shared priced providers to compare.'", "(window.NET_ROLLUP ? " + ROLL_MSG + " : 'Not enough shared priced providers to compare.')"),
]
CSS = ('<style>/* Nov 3: overlap grid menus */ #n-heat-card .nh-ctl{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}'
       ' #n-heat-card .nh-ctl select{max-width:16em}</style>')


# Nov 4, 2026 (Betsy lifted the freeze): at "All of the United States" the same button downloads the NATIONAL network-by-
# network crosswalk (dashboard/build_xwalk_us.py, daily dashboard run): every two networks that share a provider, counted
# once by NPI across areas, with both shares. The grid there stays by insurer; the file is read in parts from the control data.
XW_ANCHOR = "      const X = window.NH_CSV; if (!X || !X.ov || !X.ov.length) return;\n"
XW_JS = (
    "      const pm_ = dash.params(); if ((pm_.nmk || pm_.market) === 'US') return window.NAT_XWALK($('#nh-csv'));   // Nov 4: national file\n")
NAT_FN = (
    "    window.NAT_XWALK = async (btn) => {   // Nov 4 (site/control_overlap.py): national network crosswalk, read in parts\n"
    "      const get = (id) => fetch('/control/api/data/' + id, {credentials: 'same-origin', cache: 'no-store'}).then((r) => {\n"
    "        if (!r.ok) throw new Error(r.status === 404 ? 'The national crosswalk is not built yet. It comes with the next daily data run.' : 'Could not load ' + id + ' (' + r.status + ')');\n"
    "        return r.json(); });\n"
    "      const t0 = btn.textContent; btn.disabled = true; btn.textContent = 'Loading national file…';\n"
    "      try {\n"
    "        const h = await get('net_xwalk_us'), parts = [h];\n"
    "        for (let j = 2; j <= (h.parts || 1); j++) { btn.textContent = `Loading part ${j} of ${h.parts}…`; parts.push(await get('net_xwalk_us_' + j)); }\n"
    "        const N = h.networks, r4 = (x) => Math.round(x * 1e4) / 1e4, q = (v) => v == null ? '' : /[\",\\n]/.test(String(v)) ? '\"' + String(v).replace(/\"/g, '\"\"') + '\"' : String(v);\n"
    "        const out = [['area', 'row_insurer', 'row_network', 'column_insurer', 'column_network', 'shared', 'row_providers', 'column_providers',\n"
    "          'share_of_row_in_column', 'share_of_column_in_row', 'jaccard', 'shared_hospitals', 'row_hospitals', 'column_hospitals'].join(',')];\n"
    "        for (const p of parts) for (const [a, b, s, sh] of p.rows) { const A = N[a], Bn = N[b];\n"
    "          out.push(['United States', A[0], A[1], Bn[0], Bn[1], s, A[2], Bn[2], r4(s / Math.max(1, A[2])), r4(s / Math.max(1, Bn[2])),\n"
    "            r4(s / Math.max(1, A[2] + Bn[2] - s)), sh, A[3], Bn[3]].map(q).join(',')); }\n"
    "        const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([out.join('\\n') + '\\n'], {type: 'text/csv'}));\n"
    "        a.download = `network-crosswalk_us_networks${h.min_shared > 1 ? '_sharing-' + h.min_shared + '-plus' : ''}_${(h.made || '').slice(0, 10)}.csv`;\n"
    "        document.body.appendChild(a); a.click(); a.remove();\n"
    "        if (h.min_shared > 1) alert(`The national file lists network pairs that share at least ${h.min_shared} providers (all pairs would not fit).`);\n"
    "      } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = t0; }\n"
    "    };\n")
CSV_WIRE = "    if ($('#nh-csv')) $('#nh-csv').addEventListener('click', () => {"
STEPS += [
    ("window.NAT_XWALK = async", CSV_WIRE, NAT_FN + CSV_WIRE),
    ("return window.NAT_XWALK(", XW_ANCHOR, XW_ANCHOR.replace("      const X", XW_JS + "      const X")),
]


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; an overlap-grid step was skipped:', done)
            continue
        s = s.replace(a, b)
    if 'overlap grid menus' not in s and '</head>' in s:
        s = s.replace('</head>', CSS + '\n</head>', 1)
    if s != s0:
        open(p, 'w', encoding='utf-8').write(s)
        return True
    return False
