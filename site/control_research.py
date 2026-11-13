"""Control center: the "Research" tab (Nov 13, 2026; Research Desk v1, story 1.1).

patch(d)   adds the tab to <d>/site/control/index.html, after "GitHub" and before "Project plan", plus
           control_research/block.html (styles + script) before </body>. Each step is skipped once done; a missing anchor
           (the page was rebuilt differently) is reported, never fatal. Called by site/home_v2.py after control_github.patch,
           whose GitHub tab lines it anchors on.
Data: /control/api/data/research_index (storage control/data/research_index.json), written by the research build.
Private like the rest of the control center. Link: files.healthcare/control#research.
Plan: healthcare-files-plan research-desk/prd-research-desk-v1.md and epics-research-desk-v1.md (card DX-10).
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_research')
PLAN_BTN = '<button type="button" role="tab" data-tab="plan" aria-selected="false">Project plan</button>'
GH_BTN = '<button type="button" role="tab" data-tab="github" aria-selected="false">GitHub</button>'
BTN = '<button type="button" role="tab" data-tab="research" aria-selected="false">Research</button>'
GH_PAGE = '<div class="page" id="pg-github" hidden></div>'
GH_SHOW = "if (which === 'github' && window.GHTAB) window.GHTAB.show();"
GH_HASH = "which === 'github' ? 'github' : 'top'"

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('data-tab="research"', GH_BTN + PLAN_BTN, GH_BTN + BTN + PLAN_BTN),
    ('id="pg-research"', GH_PAGE, GH_PAGE + '\n  <div class="page" id="pg-research" hidden></div>'),
    ("window.RDTAB.show()", GH_SHOW,
     GH_SHOW + "\n"
     "    const prd = document.getElementById('pg-research'); if (prd) prd.hidden = which !== 'research';\n"
     "    if (which === 'research' && window.RDTAB) window.RDTAB.show();"),
    ("which === 'research' ? 'research'", GH_HASH, "which === 'github' ? 'github' : which === 'research' ? 'research' : 'top'"),
]
START, END = '<!-- Control center: "Research" tab', '<!-- /research tab -->'


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a Research tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    block = open(os.path.join(HERE, 'block.html'), encoding='utf-8').read().rstrip()
    if START in s and END in s:   # replace the old copy so edits to block.html go out with the next deploy
        a = s.index(START); b = s.index(END) + len(END)
        s = s[:a] + block + s[b:]
    elif 'data-tab="research"' in s:
        s = s.replace('</body>', block + '\n</body>', 1)
    changed = s != s0
    if changed:
        open(p, 'w', encoding='utf-8').write(s)
    return changed
