"""Control center: the "Changes" tab (Nov 2, 2026, Betsy).

patch(d)   adds the tab to <d>/site/control/index.html, after "Out of network" and before "Project plan". Each step is
           skipped once done; a missing anchor (the page was rebuilt differently) is reported, never fatal.
Data: insurers/change_ledger.py (every 6 hours) writes R2 control/data/changes.json and changes_gone.json, which the
control center reads at /control/api/data/<name>. Link: files.healthcare/control#changes. Called by site/home_v2.py
right after control_cash_oon.patch (its .co styles and the Out of network hooks this anchors on come from there).
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_changes')
PLAN_BTN = '<button type="button" role="tab" data-tab="plan" aria-selected="false">Project plan</button>'
BTN = '<button type="button" role="tab" data-tab="changes" aria-selected="false">Changes</button>'
OON_SHOW = "if (which === 'oon' && window.OONTAB) window.OONTAB.show();"
OON_HASH = "which === 'oon' ? 'out-of-network' : 'top'"

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('data-tab="changes"', PLAN_BTN, BTN + PLAN_BTN),
    ('id="pg-changes"', '<div class="page" id="pg-plan" hidden></div>',
     '<div class="page" id="pg-changes" hidden></div>\n  <div class="page" id="pg-plan" hidden></div>'),
    ("window.CHGTAB.show()", OON_SHOW,
     OON_SHOW + "\n"
     "    const pchg = document.getElementById('pg-changes'); if (pchg) pchg.hidden = which !== 'changes';\n"
     "    if (which === 'changes' && window.CHGTAB) window.CHGTAB.show();"),
    ("which === 'changes' ? 'changes'", OON_HASH, "which === 'oon' ? 'out-of-network' : which === 'changes' ? 'changes' : 'top'"),
]
START, END = '<!-- Control center: "Changes" tab', '<!-- /changes tab -->'


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a Changes tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    block = open(os.path.join(HERE, 'tab.html'), encoding='utf-8').read().rstrip() + '\n' + END
    if START in s and END in s:   # replace the old copy so edits to tab.html go out with the next deploy
        a = s.index(START); b = s.index(END) + len(END)
        s = s[:a] + block + s[b:]
    elif 'data-tab="changes"' in s:
        s = s.replace('</body>', block + '\n</body>', 1)
    changed = s != s0
    if changed:
        open(p, 'w', encoding='utf-8').write(s)
    return changed
