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


NET_PARTS = {'net_overlap': 30, 'net_proc': 30}   # Oct 31, 2026: same counts as dashboard/build_network.py PART_FILES


def net_joins(s):
    """The Network access tab joins its split files in dash.calc('net_overlap_all' / 'net_proc_all'); make each list every
    part build_network.py writes (missing parts would load as errors, so the list must match the bot's count)."""
    import re
    for name, n in NET_PARTS.items():
        m = re.search(r"(dash\.calc\('%s_all', \{.*?inputs: \[)(.*?)(\],)" % name, s, re.S)
        if not m:
            print('control center layout changed; the', name, 'join was not updated'); continue
        want = ', '.join(f"'{name}'" if i == 0 else f"'{name}_{i + 1}'" for i in range(n))
        if m.group(2).replace('\n', ' ').split() != want.split():
            s = s[:m.start(2)] + want + s[m.end(2):]
    return s


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
    s = net_joins(s)
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
