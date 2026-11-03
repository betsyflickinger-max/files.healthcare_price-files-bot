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
CSS = ('<style>/* Nov 3: overlap grid menus */ #n-heat-card .nh-ctl{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}'
       ' #n-heat-card .nh-ctl select{max-width:16em}</style>')


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
