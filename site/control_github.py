"""Control center, "GitHub" card on the Visitors tab (Nov 3, 2026, Betsy).

patch(d)  adds control_github/block.html to <d>/site/control/index.html (before </body>). The block finds the Visitors
          tab by its tables (#v-events / #v-signups), adds one card under them, and loads its own data from
          /control/api/data/github_traffic (R2 control/data/github_traffic.json, written daily by
          board/github_traffic.py via .github/workflows/github-traffic.yml). GitHub never names viewers: the card shows
          counts, plus the people who starred, forked, watch or follow.
Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy re-applies it; editing block.html and
redeploying replaces the old copy.
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_github')
START, END = '<!-- Control center: "GitHub" card', '<!-- /github card -->'


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    block = open(os.path.join(HERE, 'block.html'), encoding='utf-8').read().rstrip()
    if not block.endswith(END):
        block += '\n' + END
    if START in s and END in s:   # replace the old copy so edits to block.html go out with the next deploy
        a = s.index(START); b = s.index(END) + len(END)
        s = s[:a] + block + s[b:]
    elif '</body>' in s:
        i = s.rindex('</body>')
        s = s[:i] + block + '\n' + s[i:]
    else:
        print('control center layout changed; the GitHub card was not added')
        return False
    if s != s0:
        open(p, 'w', encoding='utf-8').write(s)
    return s != s0
