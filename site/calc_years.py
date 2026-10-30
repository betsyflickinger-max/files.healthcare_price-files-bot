"""Plan Calculator: a 2027 / 2026 plan-year switch (Oct 30, 2026; Betsy: show 2027 first during open enrollment, and keep
2026 for people on a 2026 plan).

The page keeps its 2026 data block (id="data") and gets the 2027 block as id="data2027". A "Which plan year?" choice at
the top of the HealthCare.gov mode uses the page's own option buttons (.pick/.opt, like "Where does your plan come from?").
Choosing a year reloads the page with ?year=2026 or ?year=2027; with no ?year the newest year shows. Re-running replaces
the 2027 block with the newest data and changes nothing else.

  python site/calc_years.py DIR calculator/data/2027/calc_data_2027.json        # DIR from site_files.py pull
  python site/calc_years.py --page FILE calculator/data/2027/calc_data_2027.json  # patch one HTML file (local test)
"""
import json
import os
import re
import sys

MARK = "/*calcyears*/"
PICK = """<div class="pick" role="group" aria-labelledby="yearq" id="yearpick">
  <p class="pickq" id="yearq">Which plan year?</p>
  <div class="pickb">
    <button type="button" class="opt" id="y2027" aria-pressed="false" data-year="2027"><b>2027 plans</b><span>Open enrollment: plans that start January 1, 2027.</span></button>
    <button type="button" class="opt" id="y2026" aria-pressed="false" data-year="2026"><b>2026 plans</b><span>The plan you have now, through December 31, 2026.</span></button>
  </div>
</div>
"""
JS = MARK + """const YEARS={2027:'data2027',2026:'data'};
let YEAR=+new URLSearchParams(location.search).get('year');if(!YEARS[YEAR])YEAR=2027;
document.querySelectorAll('#yearpick .opt').forEach(b=>{b.setAttribute('aria-pressed',String(+b.dataset.year===YEAR));
  b.addEventListener('click',()=>{const u=new URL(location.href);u.searchParams.set('year',b.dataset.year);location.href=u.toString();});});
document.querySelector('header .eyebrow').textContent='The Healthcare Files · '+YEAR+' marketplace plans';
document.querySelectorAll('.calcyear').forEach(e=>e.textContent=YEAR);
const D=JSON.parse(document.getElementById(YEARS[YEAR]).textContent);"""
OLD_D = "const D=JSON.parse(document.getElementById('data').textContent);"


def patch(s, d2027):
    block = '<script type="application/json" id="data2027">' + json.dumps(d2027, separators=(",", ":")).replace("</", "<\\/") + "</script>"
    if MARK in s:   # already patched: refresh the 2027 data only
        return re.sub(r'<script type="application/json" id="data2027">.*?</script>', lambda m: block, s, count=1, flags=re.S)
    assert OLD_D in s, "the page's data line changed; check the page before patching"
    s = s.replace(OLD_D, JS, 1)
    s = s.replace('<script type="application/json" id="data">', block + '<script type="application/json" id="data">', 1)
    s = s.replace('<div id="mkt">\n', '<div id="mkt">\n' + PICK, 1)
    s = s.replace("public use files for 2026.", 'public use files for <span class="calcyear">2026</span>.', 1)
    s = s.replace('"Oscar Insurance Company":"Oscar"}', '"Oscar Insurance Company":"Oscar","WellPoint":"Wellpoint"}', 1)
    assert 'id="yearpick"' in s, "couldn't place the year choice"
    return s


def main():
    a = sys.argv[1:]
    page = a[1] if a[0] == "--page" else os.path.join(a[0], "site", "plan-calculator", "index.html")
    d2027 = json.load(open(a[-1]))
    s = open(page, encoding="utf-8").read()
    t = patch(s, d2027)
    open(page, "w", encoding="utf-8").write(t)
    print(f"{page}: {'patched' if t != s else 'unchanged'} ({len(d2027['plans'])} 2027 plans)")


if __name__ == "__main__":
    main()
