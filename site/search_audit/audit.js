// Search audit (Nov 7, 2026): on one Price Finder page, can each care item be found by the names people type, does
// typing each of its codes open that code, and does a search keep prices hidden until a code is picked?
// Run by site/search_audit/run_all.py (which serves the site and lists the pages); writes <AUDIT_DIR>/result-<n>.json.
// Background: the search before Nov 7 missed the right code for 63 of 111 care items (24 on their own plain name).
const {chromium} = require('playwright');
const fs = require('fs');
const DIR = process.env.AUDIT_DIR || '.', PAGE = process.env.PAGE_PATH || '/price-finder/', N = process.env.PAGE_N || '0';
const BASE = process.env.BASE || 'http://localhost:8765';
const tests = JSON.parse(fs.readFileSync(DIR + '/tests.json'));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  // 1) a word search shows a list and no prices; the address keeps ?q= only
  await p.goto(BASE + PAGE + '?q=' + encodeURIComponent('knee replacement'), {waitUntil: 'domcontentloaded'});
  await p.waitForFunction(() => typeof D !== 'undefined' && typeof S !== 'undefined' && document.getElementById('title'), null, {timeout: 60000});
  await p.waitForTimeout(1500);
  const searchView = await p.evaluate(() => ({
    list: !!document.querySelector('.ux-hits button[data-c]'),
    pricesHidden: document.body.classList.contains('pf-searching') && !(document.getElementById('board') || {}).offsetHeight,
    noCodeInUrl: !new URLSearchParams(location.search).get('code')}));
  // 2) each care item by its names; 3) each of its codes typed whole opens that code
  const res = await p.evaluate(tests => {
    const pr = document.getElementById('proc');
    const run = q => { pr.value = q; pr.dispatchEvent(new Event('change', {bubbles: true}));
      const bx = document.querySelector('.ux-hits'); return bx ? [...bx.querySelectorAll('button[data-c]')].map(x => x.dataset.c) : ['OPENED:' + S.code]; };
    const out = {names: [], codes: []}, seen = {};
    tests.forEach(([iid, name, q, exp]) => {
      const inData = exp.filter(c => D.codes[c]); if (!inData.length) return;
      const l = run(q), r = l.findIndex(c => inData.includes(c));
      out.names.push({item: name, q, rank: r < 0 ? null : r + 1});
      inData.forEach(c => { if (seen[c]) return; seen[c] = 1;   // hospital-stay codes typed the way people write them: "DRG 23", "743"
        const typed = /DRG/.test(D.codes[c].type || '') && c.length < 3 ? 'DRG ' + c : c, o = run(typed);
        out.codes.push({item: name, code: typed, ok: o[0] === 'OPENED:' + c, got: o[0] || 'a list with no codes'}); });
    });
    // a lone "5" must not open a code
    const five = run('5'); out.five = five[0] && five[0].indexOf('OPENED:') === 0 ? five[0] : 'ok';
    return out;
  }, tests);
  fs.writeFileSync(DIR + '/result-' + N + '.json', JSON.stringify({page: PAGE, searchView, ...res, errors: errs.slice(0, 5)}));
  await b.close();
})().catch(e => { fs.writeFileSync(DIR + '/result-' + N + '.json', JSON.stringify({page: PAGE, crash: String(e).slice(0, 300)})); process.exit(0); });
