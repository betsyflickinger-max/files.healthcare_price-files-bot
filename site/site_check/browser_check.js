// Robot tester, part 2 (Nov 7, 2026): on each Price Finder page, open a sample of procedures the way a visitor would and
// check that prices actually load and read correctly. Run by site/site_check/run_browser.py against serve.py.
// For each code: the heading names the code; the rates load ("Could not load these rates" is a failure); no code text
// (NaN, undefined, null, [object Object]) shows; $0.00 shown as a price is flagged; and how many prices show.
const {chromium} = require('playwright');
const fs = require('fs');
const BASE = process.env.BASE || 'http://localhost:8765', PAGE = process.env.PAGE_PATH, OUT = process.env.OUT_FILE;
const WANT = JSON.parse(process.env.CODES || '[]'), EXTRA = +(process.env.RANDOM_CODES || 5);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({viewport: {width: 1300, height: 1000}});
  const errs = [], bad = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  p.on('response', r => { if (r.status() >= 400 && !/favicon|hcf-t\.js|__ev/.test(r.url())) bad.push(r.status() + ' ' + r.url().replace(BASE, '').slice(0, 120)); });
  await p.goto(BASE + PAGE, {waitUntil: 'domcontentloaded', timeout: 90000});
  await p.waitForFunction(() => typeof D !== 'undefined' && typeof S !== 'undefined' && typeof render === 'function', null, {timeout: 90000});
  const codes = await p.evaluate(([want, extra]) => {
    const all = Object.keys(D.codes), have = want.filter(c => D.codes[c]);
    for (let i = 0, seed = all.length; i < extra && all.length; i++) { seed = (seed * 9301 + 49297) % 233280; have.push(all[seed % all.length]); }
    return [...new Set(have)];
  }, [WANT, EXTRA]);
  // which care items (the common procedures) have no code at all on this page
  const CARE = JSON.parse(process.env.CARE || '[]');
  const missing = await p.evaluate(care => care.filter(([n, cs]) => !cs.some(c => D.codes[c])).map(([n]) => n), CARE);
  const rows = [];
  for (const c of codes) {
    errs.length = 0; bad.length = 0;
    await p.evaluate(c => { S.code = c; S.showAll = {}; render(); }, c);
    // wait until the price list settles (not loading, and the same text twice in a row)
    let last = '', same = 0;
    for (let i = 0; i < 40 && same < 2; i++) {
      await p.waitForTimeout(400);
      const t = await p.evaluate(() => (document.getElementById('board') || {}).innerText || '');
      if (t && !/loading/i.test(t) && t === last) same++; else same = 0;
      last = t;
    }
    const r = await p.evaluate(c => {
      const title = (document.getElementById('title') || {}).textContent || '', name = (D.codes[c] || {}).name || '';
      const main = ['board', 'patient', 'mapv'].map(id => (document.getElementById(id) || {}).innerText || '').join('\n');
      const leak = (main.match(/(?<![\w-])(NaN|undefined|\[object Object\]|null)(?![\w-])/g) || []);
      return {code: c, name, titleOk: !!name && title.trim().toLowerCase() === name.trim().toLowerCase(), title: title.slice(0, 90),
        loadFailed: /could not load/i.test(main), stillLoading: /loading/i.test((document.getElementById('board') || {}).innerText || ''),
        leaks: [...new Set(leak)], zero: (main.match(/\$0\.00(?!\d)/g) || []).length, prices: (main.match(/\$[\d,]+\.\d\d/g) || []).length,
        empty: /no (insurer|negotiated|published)? ?(rates|prices)|nothing (to show|listed)/i.test(main) };
    }, c);
    r.errors = [...errs]; r.httpErrors = [...new Set(bad)].slice(0, 4);
    rows.push(r);
  }
  fs.writeFileSync(OUT, JSON.stringify({page: PAGE, nCodes: await p.evaluate(() => Object.keys(D.codes).length), missing, rows}));
  await b.close();
})().catch(e => { fs.writeFileSync(OUT, JSON.stringify({page: PAGE, crash: String(e).slice(0, 300), rows: []})); });
