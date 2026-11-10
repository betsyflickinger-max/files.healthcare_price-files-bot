"""Page slimming (site/page_slim.py): same message for every code and network, in Python and in the browser's own code.
Run: python -m pytest tests/"""
import json, os, subprocess, sys, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site"))
import page_slim as PS  # noqa: E402

JS = """<script>
const D = JSON.parse(document.getElementById('data').textContent);
const S = {code: null};
function scopeMsg(N) {
  const sc = D.scope[`${N.i}|${N.n}`];
  return sc && !sc.includes(S.code) ? `We have read this network's file for ${sc.length} procedures so far, and this is not one of them yet.` : 'This network has no published rate for this code in Kansas.';
}
</script>"""


def page():
    codes = {c: {"name": c} for c in ["00100", "27447", "45378", "64415", "99213", "G0121", "J1885", "70551", "0055T"]}
    D = {"codes": codes, "nets": ["Aetna|Open Access", "Cigna|LocalPlus", "UHC|Choice Plus"],
         "scope": {"Aetna|Open Access": ["00100", "27447", "99999", "G0121"],          # 99999: read, but not on the page
                   "Cigna|LocalPlus": ["45378"]},
         "coming": {"3049F": {"name": "x"}}}
    return '<html><body>' + PS.TAG + json.dumps(D) + '</script>' + JS + '</body></html>'


def test_same_in_python():
    old = page()
    new = PS.slim(old)
    assert PS.same(old, new)
    _, D, _ = PS.split(new)
    assert "coming" not in D and D["scope"]["Aetna|Open Access"][0] == 4 and "scHas" in new


def test_same_in_browser():
    """Runs both pages' own scopeMsg for every code and network in headless Chromium (skipped if Playwright is missing)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        import pytest; pytest.skip("playwright not installed")
    old, new = page(), PS.slim(page())
    probe = """() => { const out = []; for (const c of Object.keys(D.codes)) { S.code = c;
                for (const n of D.nets) { const [i, p] = n.split('|'); out.push(c + ' ' + n + ' ' + scopeMsg({i, n: p})); } }
                return out; }"""
    with sync_playwright() as p:
        b = p.chromium.launch()
        res = []
        for h in (old, new):
            pg = b.new_page(); pg.set_content(h); res.append(pg.evaluate(probe))
        b.close()
    assert res[0] == res[1] and len(res[0]) == 27
    assert any("for 4 procedures" in x for x in res[1]) and any("no published rate" in x for x in res[1])
