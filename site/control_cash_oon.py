"""Control center: the "Cash prices" and "Out of network" tabs (Oct 30, 2026, Betsy).

patch(d)   adds both tabs to <d>/site/control/index.html (after "Where the money goes", before "Project plan").
           Each step is skipped once done; a missing anchor (the page was rebuilt differently) is reported, never fatal.
Data: dashboard/build_cash_oon.py, built daily by .github/workflows/dashboard.yml (cash_oon job) and copied to R2
control/data/, where the control center's /control/api/data/<name> reads it. Links: files.healthcare/control#cash and
#out-of-network. Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy re-applies it.
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_cash_oon')
PLAN_BTN = '<button type="button" role="tab" data-tab="plan" aria-selected="false">Project plan</button>'
BTNS = ('<button type="button" role="tab" data-tab="cash" aria-selected="false">Cash prices</button>'
        '<button type="button" role="tab" data-tab="oon" aria-selected="false">Out of network</button>')
MONEY_SHOW = "if (which === 'money' && window.MONEY) window.MONEY.show();"

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('data-tab="cash"', PLAN_BTN, BTNS + PLAN_BTN),
    ('id="pg-cash"', '<div class="page" id="pg-plan" hidden></div>',
     '<div class="page" id="pg-cash" hidden></div>\n  <div class="page" id="pg-oon" hidden></div>\n  <div class="page" id="pg-plan" hidden></div>'),
    ("window.CASHTAB.show()", MONEY_SHOW,
     MONEY_SHOW + "\n"
     "    const pcash = document.getElementById('pg-cash'); if (pcash) pcash.hidden = which !== 'cash';\n"
     "    if (which === 'cash' && window.CASHTAB) window.CASHTAB.show();\n"
     "    const poon = document.getElementById('pg-oon'); if (poon) poon.hidden = which !== 'oon';\n"
     "    if (which === 'oon' && window.OONTAB) window.OONTAB.show();"),
    ("which === 'cash' ? 'cash'", "which === 'money' ? 'money' : 'top'",
     "which === 'money' ? 'money' : which === 'cash' ? 'cash' : which === 'oon' ? 'out-of-network' : 'top'"),
]


NET_HELPER = """  // Oct 31, 2026 (site/control_cash_oon.py): pairs and procedure rows load one area at a time; net_parts lists each
  // area's files (all areas in one join had passed 300 MB). Pair files are packed arrays: [header, [level, a, b, ...keys]].
  const NETCACHE = {};
  function NETIDS(kind, m) {
    const parts = rowsOf('net_parts'), ix = parts && parts.find((r) => r.market === m);
    if (!ix) return parts ? [] : null;
    const base = (kind === 'ov' ? 'net_ov_' : 'net_pr_') + String(m).toLowerCase().replace(/-/g, '_');
    return Array.from({length: kind === 'ov' ? ix.pair_files : ix.proc_files}, (_, i) => (i ? base + '_' + (i + 1) : base));
  }
  function NETAREA(kind, m) {
    const ids = NETIDS(kind, m); if (!ids) return null; if (!ids.length) return [];
    const ds = ids.map((id) => dash.data(id)); if (!ds.every((d) => d.status === 'ok')) return null;
    const key = kind + '|' + m, c = NETCACHE[key]; if (c && c.src === ds[0].data) return c.rows;
    let rows = [];
    if (kind === 'pr') ds.forEach((d) => { rows = rows.concat(d.data); });
    else ds.forEach((d) => { const h = d.data[0], K = h.keys; d.data.slice(1).forEach((x) => {
      const r = {market: h.market, level: x[0] ? 'insurer' : 'network', a: h.labels[x[1]], b: h.labels[x[2]]};
      for (let i = 3; i < K.length; i++) r[K[i]] = x[i];
      r.id = r.level + '|' + r.a + '>' + r.b; rows.push(r); }); });
    NETCACHE[key] = {src: ds[0].data, rows}; return rows;
  }
  NETAREA.err = (kind, m) => dash.data('net_parts').status === 'error' || (NETIDS(kind, m) || []).some((id) => dash.data(id).status === 'error');
"""
NET_STEPS = [   # (marker, anchor, replacement) for the Network access tab
    ("NETAREA('ov'", "  dash.onData(() => {\n    if (!shown || !built) return;\n    const p = P(), markets = rowsOf('markets'), access = rowsOf('net_access'), overlap = rowsOf('net_overlap_all'), summary = rowsOf('net_summary'), proc = rowsOf('net_proc_all');",
     NET_HELPER + "  dash.onData(() => {\n    if (!shown || !built) return;\n    const p = P(), markets = rowsOf('markets'), access = rowsOf('net_access'), overlap = NETAREA('ov', p.market), summary = rowsOf('net_summary'), proc = NETAREA('pr', p.market);"),
    ("NETAREA.err('ov'", "} else if (dash.data('net_overlap_all').status === 'error') {", "} else if (NETAREA.err('ov', p.market)) {"),
    ("NETAREA.err('pr'", "} else if (dash.data('net_proc_all').status === 'error')", "} else if (NETAREA.err('pr', p.market))"),
    ("inputs: ['net_access', 'net_parts', 'markets']", "inputs: ['net_access', 'net_overlap_all', 'markets']", "inputs: ['net_access', 'net_parts', 'markets']"),
    ("const np = (net_overlap || []).find(",
     "const ov = net_overlap.filter((r) => r.market === m && r.level === 'network').map((r) => Number(r.share_of_a_in_b)).sort((a, b) => a - b);",
     "const np = (net_overlap || []).find((r) => r.market === m);   // net_parts: the middle overlap is worked out by the bot"),
    ("overlap_mid: np ? np.overlap_mid", "overlap_mid: ov.length ? ov[Math.floor((ov.length - 1) / 2)] : null", "overlap_mid: np ? np.overlap_mid : null"),
    # Oct 31 (later): the headline boxes read net_headline, worked out by the bot (board/net_headline.py); the in-page
    # net_summary calc is only a fallback (it left the boxes blank on the live page).
    ("rowsOf('net_headline')", "summary = rowsOf('net_summary')", "summary = rowsOf('net_headline') || rowsOf('net_summary')"),
]


def net_area(s):
    """The Network access tab: load pairs and procedure rows for the picked area only (dashboard/build_network.py
    write_areas), and stop the old all-areas joins (net_overlap_all / net_proc_all) from fetching 30+ files each."""
    import re
    for done, a, b in NET_STEPS:
        if done in s: continue
        if s.count(a) != 1: print('control center layout changed; a network-access step was skipped:', done); continue
        s = s.replace(a, b)
    for name in ('net_overlap', 'net_proc'):
        m = re.search(r"(dash\.calc\('%s_all', \{.*?inputs: \[)(.*?)(\],\s*fn: )(.*?)(,\n\}\);)" % name, s, re.S)
        if not m: print('control center layout changed; the', name, 'join was not replaced'); continue
        if m.group(2) != "'net_parts'":
            s = s[:m.start(2)] + "'net_parts'" + m.group(3) + "(p) => p || []" + s[m.end(4):]
    return re.sub(r"description: 'Joins the \d+ network-(pair|by-procedure) files[^']*'",
                  r"description: 'Since Oct 31, 2026 the network-\1 rows load one area at a time when the area is picked (net_parts lists the files).'", s)


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a cash/out-of-network tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    s = net_area(s)
    tab = open(os.path.join(HERE, 'tab.html'), encoding='utf-8').read()
    start, end = '<!-- Control center: "Cash prices" and "Out of network" tabs', '<!-- /cash-oon tabs -->'
    block = tab.rstrip() + '\n' + end
    if start in s and end in s:   # replace the old copy so edits to tab.html go out with the next deploy
        a = s.index(start); b = s.index(end) + len(end)
        s = s[:a] + block + s[b:]
    elif 'data-tab="cash"' in s:
        s = s.replace('</body>', block + '\n</body>', 1)
    changed = s != s0
    if changed:
        open(p, 'w', encoding='utf-8').write(s)
    return changed
