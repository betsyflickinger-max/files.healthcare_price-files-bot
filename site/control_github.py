"""Control center, "GitHub" tab (Nov 3, 2026, Betsy; a card on the Visitors tab earlier the same morning).

patch(d)  adds the tab to <d>/site/control/index.html, after "Changes" and before "Project plan", plus
          control_github/block.html (styles + script) before </body>. Each step is skipped once done; a missing anchor
          (the page was rebuilt differently) is reported, never fatal. Must run after control_changes.patch, whose
          Changes tab lines it anchors on.
Data: board/github_traffic.py (daily, .github/workflows/github-traffic.yml) writes R2 control/data/github_traffic.json,
which the tab loads from /control/api/data/github_traffic. GitHub never names viewers: the tab shows counts, plus the
people who starred, forked, watch or follow. Link: files.healthcare/control#github.
Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy re-applies it; editing block.html and
redeploying replaces the old copy.
"""
import os

from control_changes import BTN as CHG_BTN, PLAN_BTN

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_github')
BTN = '<button type="button" role="tab" data-tab="github" aria-selected="false">GitHub</button>'
CHG_SHOW = "if (which === 'changes' && window.CHGTAB) window.CHGTAB.show();"
CHG_HASH = "which === 'changes' ? 'changes' : 'top'"

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('data-tab="github"', CHG_BTN + PLAN_BTN, CHG_BTN + BTN + PLAN_BTN),
    ('id="pg-github"', '<div class="page" id="pg-changes" hidden></div>',
     '<div class="page" id="pg-changes" hidden></div>\n  <div class="page" id="pg-github" hidden></div>'),
    ("window.GHTAB.show()", CHG_SHOW,
     CHG_SHOW + "\n"
     "    const pgh = document.getElementById('pg-github'); if (pgh) pgh.hidden = which !== 'github';\n"
     "    if (which === 'github' && window.GHTAB) window.GHTAB.show();"),
    ("which === 'github' ? 'github'", CHG_HASH, "which === 'changes' ? 'changes' : which === 'github' ? 'github' : 'top'"),
]
START, END = '<!-- Control center: "GitHub"', '<!-- /github card -->'


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a GitHub tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    block = open(os.path.join(HERE, 'block.html'), encoding='utf-8').read().rstrip()
    if not block.endswith(END):
        block += '\n' + END
    if START in s and END in s:   # replace the old copy (including the Visitors-tab card) so edits go out with the next deploy
        a = s.index(START); b = s.index(END) + len(END)
        s = s[:a] + block + s[b:]
    elif '</body>' in s:
        i = s.rindex('</body>')
        s = s[:i] + block + '\n' + s[i:]
    if s != s0:
        open(p, 'w', encoding='utf-8').write(s)
    return s != s0
