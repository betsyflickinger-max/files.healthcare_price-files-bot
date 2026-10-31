"""Area dropdowns: states first, each state's places beside it (Oct 31, 2026, Betsy).

Every area dropdown on the price site and the control center lists only states. A state with more than one place (Texas
metros, California's regions) opens its places beside it on hover, or on click or tap; a state with one place picks it.

  python site/area_menu.py DIR     (DIR holds site/, like every deploy step)

apply(d):
  1. writes <d>/site/area-menu.js from site/assets/area-menu.js, with the place -> state list (AREA_MAP) filled in from
     site/cities.json and procedure_pages.area_state (the same rule the price pages and the homepage map use);
  2. links it from every page that has a dropdown (any .html with "<select", which includes the Price Finder, whose area
     picker is made after cities.json loads, and the control center).
Which dropdowns it changes is in the script (SEL): the homepage/story "Where" (#natArea), sign-up "Where" (name=area), the
Price Finder "Area" (#area), and the control center's Market and Area pickers (#market, #nmarket, #c-mkt, #o-mkt, #o-parea).
The page's own <select> stays (hidden) and keeps the value, so no page code changes. Idempotent; called by sitewide.py
(every deploy path) and by home_v2.py deploy (so a homepage-only deploy sees the change).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TAG = '<script src="/area-menu.js" defer></script>'
NAMES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut',
         'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
         'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
         'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
         'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
         'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
         'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
         'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
         'PR': 'Puerto Rico'}
OLDKEY = {'austin': 'AUS', 'san-antonio': 'SAT', 'houston': 'HOU', 'el-paso': 'ELP', 'dfw': 'DFW'}   # control-center market keys (dashboard/build_*.py)
MAP_RX = re.compile(r'/\*AREA_MAP\*/.*?/\*AREA_MAP_END\*/', re.S)


def state_map(site):
    """{'names': {place name: state name}, 'keys': {slug / url slug / path / market key: state name}} from cities.json."""
    try:
        from procedure_pages import area_state, area_url_slug
    except Exception:
        def area_state(a): return 'TX'
        def area_url_slug(s): return s
    names, keys = {}, {}
    try:
        L = json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8'))
    except Exception:
        L = []
    for c in L:
        slug = c.get('slug') or ''
        st = NAMES.get(area_state({'slug': slug}), 'Texas')
        if c.get('name'):
            names[c['name']] = st
        for k in (slug, area_url_slug(slug), c.get('path'), OLDKEY.get(slug), slug.upper()):
            if k:
                keys[k] = st
    return {'names': names, 'keys': keys, 'fallback': 'Texas'}


def apply(d):
    site = os.path.join(d, 'site')
    if not os.path.isdir(site):
        return 0
    js = open(os.path.join(HERE, 'assets', 'area-menu.js'), encoding='utf-8').read()
    js = MAP_RX.sub(lambda m: '/*AREA_MAP*/' + json.dumps(state_map(site), sort_keys=True) + '/*AREA_MAP_END*/', js, 1)
    changed = 0
    p = os.path.join(site, 'area-menu.js')
    if not os.path.isfile(p) or open(p, encoding='utf-8').read() != js:
        open(p, 'w', encoding='utf-8').write(js); changed += 1
    for dp, _, fn in os.walk(site):
        if os.path.join('site', 'looks') in dp:
            continue
        for f in fn:
            if not f.endswith(('.html', '.htm')):
                continue
            q = os.path.join(dp, f)
            try:
                s = open(q, encoding='utf-8').read()
            except UnicodeDecodeError:
                continue
            if '<select' not in s or TAG in s:
                continue
            i = s.lower().find('</head>')
            if i < 0:
                continue
            open(q, 'w', encoding='utf-8').write(s[:i] + TAG + s[i:]); changed += 1
    return changed


if __name__ == '__main__':
    print('area menus:', apply(sys.argv[1]), 'files updated')
