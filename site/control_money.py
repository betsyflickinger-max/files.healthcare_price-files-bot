"""Control center: the "Where the money goes" tab (Oct 25, 2026, Betsy).

patch(d)        adds the tab to <d>/site/control/index.html and copies money-bill.js next to it. Each step is skipped once
                done; a missing anchor (the page was rebuilt differently) is reported, never fatal.
upload(s3, B)   puts the tab's fixed yearly data (site/control_money/data/*.json) in R2 control/data/, where the
                control center's /control/api/data/<name> reads it. Only uploads files that changed.

Called by site/home_v2.py (deploy and build), so every Homepage-pages deploy re-applies it.
Data: CMS MLR public use file 2024 (premium dollar), Oct 2026 OPPS/ASC/PFS + FY2026 wage index (procedure dollar),
2026 PFS + 2024 Medicare utilization + 2023 hospital cost reports (malpractice). Notes: project docs
claude/dollar-breakdown-oct24.md and claude/malpractice-share-oct24.md. Refresh the JSON files by hand when CMS posts new years.
"""
import hashlib
import os
import shutil

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'control_money')
TAB_BTN = '<button type="button" role="tab" data-tab="money" aria-selected="false">Where the money goes</button>'

STEPS = [   # (marker that shows the step is done, anchor, replacement)
    ('data-tab="money"',
     '<button type="button" role="tab" data-tab="plan" aria-selected="false">Project plan</button>',
     TAB_BTN + '<button type="button" role="tab" data-tab="plan" aria-selected="false">Project plan</button>'),
    ('id="pg-money"',
     '<div class="page" id="pg-visitors" hidden></div>',
     '<div class="page" id="pg-visitors" hidden></div>\n  <div class="page" id="pg-money" hidden></div>'),
    ("which !== 'money'",
     "if (which === 'plan' && window.PLAN) window.PLAN.show();",
     "if (which === 'plan' && window.PLAN) window.PLAN.show();\n"
     "    const pm = document.getElementById('pg-money'); if (pm) pm.hidden = which !== 'money';\n"
     "    if (which === 'money' && window.MONEY) window.MONEY.show();"),
    ("which === 'money' ? 'money'",
     "which === 'plan' ? 'plan' : 'top'",
     "which === 'plan' ? 'plan' : which === 'money' ? 'money' : 'top'"),
]


def patch(d):
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in STEPS:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a money-tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    if 'id="tpl-money"' not in s and 'data-tab="money"' in s:
        s = s.replace('</body>', open(os.path.join(HERE, 'tab.html'), encoding='utf-8').read() + '\n</body>', 1)
    changed = s != s0
    if changed:
        open(p, 'w', encoding='utf-8').write(s)
    src, dst = os.path.join(HERE, 'money-bill.js'), os.path.join(d, 'site', 'control', 'money-bill.js')
    if not os.path.isfile(dst) or open(src, 'rb').read() != open(dst, 'rb').read():
        shutil.copyfile(src, dst)
        changed = True
    return changed


def upload(s3, bucket):
    folder = os.path.join(HERE, 'data')
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.json'):
            continue
        body = open(os.path.join(folder, name), 'rb').read()
        key = f'control/data/{name}'
        md5 = hashlib.md5(body).hexdigest()
        try:
            if s3.head_object(Bucket=bucket, Key=key)['ETag'].strip('"') == md5:
                continue
        except Exception:
            pass
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json')
        print('uploaded', key)
