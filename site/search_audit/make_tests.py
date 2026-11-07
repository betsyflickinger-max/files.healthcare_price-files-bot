"""Write tests.json for site/search_audit/audit.js: every care item's plain name, its name without the parenthesis, the
word in the parenthesis, and its everyday words (site/search_aliases.py WORDS), each paired with the item's codes."""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
import search_aliases as sa  # noqa: E402

ids = {}
for r in csv.DictReader(open(os.path.join(ROOT, 'reference', 'care_items', 'crosswalk_codes.csv'), encoding='utf-8')):
    ids.setdefault(r['plain_name'], r['item_id'])
tests = []
for name, _, codes in sa.build():
    iid = ids.get(name, '')
    qs = {name, re.sub(r'\s*\(.*?\)', '', name).strip()}
    m = re.search(r'\((.*?)\)', name)
    if m:
        qs.add(m.group(1))
    qs |= {w for w in sa.WORDS.get(iid, '').split() if len(w) >= 5}
    tests += [[iid, name, q, codes] for q in sorted(qs)]
json.dump(tests, open(os.path.join(os.environ.get('AUDIT_DIR', '.'), 'tests.json'), 'w'))
print(len(tests), 'queries')
