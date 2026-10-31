"""Control center, "Every state" table (Oct 31, 2026, Betsy).

patch(d)  adds control_state_lists/block.html to <d>/site/control/index.html (before </body>):
          - every count (Hospitals, Have file, Coverage, Failed, No file) lists the hospitals behind it: hover for the
            first 12 names, click for the full list (city, status, what the bot found, file date, file website);
          - the counts and coverage bar are colored by completion (green 90%+, yellow 75-89%, red under 75%), which also
            replaces the blue that sitewide.py's Oct 19 "prices in Units blue" rule (.n) was giving these cells.
Uses the page's own "hospitals" and "states" datasets (dashboard/build.py), so nothing new is built or stored.
Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy re-applies it; editing block.html and
redeploying replaces the old copy.
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_state_lists')
START, END = '<!-- Control center: "Every state" table', '<!-- /state-lists -->'


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    if 'id="states-table"' not in s:
        print('control center layout changed; the Every-state lists were not added')
        return False
    block = open(os.path.join(HERE, 'block.html'), encoding='utf-8').read().rstrip()
    if not block.endswith(END):
        block += '\n' + END
    if START in s and END in s:
        a = s.index(START); b = s.index(END) + len(END)
        s = s[:a] + block + s[b:]
    else:
        i = s.rindex('</body>')
        s = s[:i] + block + '\n' + s[i:]
    if s != s0:
        open(p, 'w', encoding='utf-8').write(s)
    return s != s0
