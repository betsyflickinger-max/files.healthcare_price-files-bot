"""Robot tester, part 1 (Nov 7, 2026): read every page of the pulled site and list what's broken or unfinished.

Usage: python site/site_check/static_check.py w/site      -> out/board/site_check_static.json (+ run summary)
Checks every HTML page for: internal links to pages that don't exist, placeholder or draft text, text that leaked
from code (undefined, NaN, null, None, {{ }}), and pages with no title or no main heading. Pages that the
password-protected control center owns (/control/) are skipped.
"""
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

site = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'w/site')
SKIP = ('control/', 'api/')
LEAK = re.compile(r'(?<![\w-])(undefined|NaN|\$NaN|\[object Object\]|None(?= ?[<\n])|null(?= ?[<\n]))(?![\w-])')
DRAFT = re.compile(r'Pending legal review|placeholder text|Lorem ipsum|\bTODO\b|\bTBD\b|\bFIXME\b|\[(?:insert|name|date|link|TK)[^\]]{0,40}\]|\{\{[^}]{0,40}\}\}', re.I)
HREF = re.compile(r'''href=["'](/[^"'#?]*)''')


def text_of(h):
    h = re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>', ' ', h)   # page text only, not code
    return html.unescape(re.sub(r'<[^>]+>', ' ', h))


def exists(path):
    p = os.path.join(site, path.lstrip('/'))
    return os.path.isfile(p) or os.path.isfile(os.path.join(p, 'index.html')) or os.path.isfile(p + '.html') or os.path.isfile(p + '/index.html')


problems = defaultdict(list)          # kind -> [(page, detail)]
pages = 0
link_ok = {}
for root, _, fs in os.walk(site):
    rel = os.path.relpath(root, site).replace(os.sep, '/')
    if rel.startswith(SKIP):
        continue
    for f in fs:
        if not f.endswith('.html'):
            continue
        pages += 1
        page = '/' + (rel + '/' if rel != '.' else '') + ('' if f == 'index.html' else f)
        h = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
        t = text_of(h)
        for m in set(LEAK.findall(t)):
            i = t.find(m); problems['code text showing on the page'].append((page, f'“{m}” in “…{" ".join(t[max(0, i - 60):i + 40].split())}…”'))
        for m in set(DRAFT.findall(t)):
            i = t.find(m); problems['draft or placeholder text'].append((page, f'“{" ".join(t[max(0, i - 50):i + 60].split())}”'))
        if not re.search(r'<title>\s*[^<\s]', h):
            problems['no page title'].append((page, ''))
        if not re.search(r'<h1\b', h, re.I):
            problems['no main heading (h1)'].append((page, ''))
        for href in set(HREF.findall(h)):
            if href.startswith(('/cdn-cgi/', '/api/', '/__', '/control')) or re.search(r'\.(js|css|json|png|svg|ico|csv|pdf|xml|txt|webmanifest|woff2?)$', href):
                continue
            if href not in link_ok:
                link_ok[href] = exists(href)
            if not link_ok[href]:
                problems['link to a page that does not exist'].append((page, href))

rows = []
for kind, xs in problems.items():
    by_detail = Counter(d for _, d in xs)
    for d, n in by_detail.most_common():
        ex = [p for p, d2 in xs if d2 == d][:3]
        rows.append({'id': f'{kind}|{d}', 'problem': kind, 'detail': d, 'pages': n, 'examples': ' '.join(ex)})
rows.sort(key=lambda r: (-r['pages'], r['problem']))
os.makedirs('out/board', exist_ok=True)
json.dump(rows, open('out/board/site_check_static.json', 'w'), separators=(',', ':'))
print(f'static check: {pages} pages, {sum(len(v) for v in problems.values())} problems in {len(rows)} groups')
for k, v in sorted(problems.items(), key=lambda kv: -len(kv[1])):
    print(f'  {len(v):6}  {k}')
summ = os.environ.get('GITHUB_STEP_SUMMARY')
if summ:
    with open(summ, 'a') as f:
        f.write(f'## Robot tester: every page ({pages} pages)\n\n| Problem | Detail | Pages | Examples |\n|---|---|---|---|\n')
        for r in rows[:80]:
            f.write(f"| {r['problem']} | {r['detail'][:120].replace('|', '/')} | {r['pages']} | {r['examples'][:160]} |\n")
