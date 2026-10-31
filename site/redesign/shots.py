"""Checks and screenshots of the V2 preview build (Oct 31, 2026). Serves the built folder on this machine (the deployed
preview is password-protected), with the DFW per-code data read the way the site's functions read it, then walks both
journeys in Chromium and records what it saw. Output: OUT/shots/*.png and OUT/checks.json."""
import http.server
import json
import os
import re
import socketserver
import threading

CODES_OK = re.compile(r'^/price-finder/pf/(t|h)/([0-9A-Z]{1,5})\.txt$')


def run(w, out, local_pf=None):
    site = os.path.join(w, 'site')
    shots = os.path.join(out, 'shots'); os.makedirs(shots, exist_ok=True)
    getter = None
    if not local_pf:
        from site_files import s3, B
        cur = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
        def getter(kind, name):
            try:
                return s3.get_object(Bucket=B, Key=f'site/every/{cur}/{kind}/{name}' if kind in 't h' else f'site/every/{cur}/{name}')['Body'].read()
            except Exception as ex:
                print('shots: R2 read failed', kind, name, repr(ex)[:160], flush=True)
                return None
    else:
        def getter(kind, name):
            p = os.path.join(local_pf, (f'{kind}_{name}' if kind in 't h' else name))
            return open(p, 'rb').read() if os.path.exists(p) else None

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=site, **k)
        def log_message(self, *a): pass
        def do_GET(self):
            p = self.path.split('?')[0]
            m = CODES_OK.match(p)
            if m or p == '/price-finder/pf/g/geo.json':
                b = getter(m.group(1), m.group(2) + '.txt') if m else getter('g', 'geo.json')
                if b is None:
                    self.send_error(404); return
                self.send_response(200); self.send_header('Content-Type', 'text/plain' if m else 'application/json'); self.end_headers(); self.wfile.write(b); return
            return super().do_GET()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(('127.0.0.1', 8822), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    B = 'http://127.0.0.1:8822'
    from playwright.sync_api import sync_playwright
    C = {}
    def rec(k, v): C[k] = v; print('CHECK', k, '=', json.dumps(v)[:300], flush=True)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        def pg(width=1280, height=900, scale=1):
            ctx = br.new_context(viewport={'width': width, 'height': height}, device_scale_factor=scale)
            p = ctx.new_page(); errs = []
            p.on('pageerror', lambda e: errs.append(str(e)[:200]))
            p.errs = errs
            return p
        def shot(p, name, full=True):
            p.screenshot(path=os.path.join(shots, name + '.png'), full_page=full)

        try:
            # ---------- V2 journey, desktop ----------
            p = pg()
            p.goto(B + '/v2/'); p.wait_for_timeout(1200); shot(p, 'v2-01-home-1280')
            p.fill('#hProc', 'knee mri'); p.wait_for_timeout(300)
            p.keyboard.press('ArrowDown'); p.keyboard.press('Enter'); p.wait_for_timeout(200)
            rec('v2_home_combobox_picked', p.eval_on_selector('#hProc', 'e => [e.value, e.dataset.code]'))
            p.click('#hForm button[type=submit]'); p.wait_for_url('**/v2/price-finder/**'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000)
            rec('v2_results_url', p.url.replace(B, ''))
            p.select_option('#net', index=1); p.wait_for_timeout(500)
            rec('v2_results_count_net', p.inner_text('#rCount'))
            shot(p, 'v2-02-results-network-1280')
            boxes = p.query_selector_all('#rList input[type=checkbox]')
            rec('v2_card_count_shown', len(boxes))
            if len(boxes) >= 2:
                boxes[0].check(); rec('v2_compare_after_1', [p.inner_text('#cmpN'), p.eval_on_selector('#cmpGo', 'b => b.disabled')])
                boxes[1].check(); rec('v2_compare_after_2', [p.inner_text('#cmpN'), p.eval_on_selector('#cmpGo', 'b => b.disabled')])
                p.click('#cmpGo'); p.wait_for_timeout(300); shot(p, 'v2-03-compare-dialog-1280', full=False)
                p.keyboard.press('Escape'); p.wait_for_timeout(200)
                rec('v2_compare_escape_focus', p.evaluate('document.activeElement && document.activeElement.id'))
            # cash: the same surfaces follow the payment choice (F02 counterpart in V2)
            p.click('#paySeg button[data-pay=cash]'); p.wait_for_timeout(400)
            rec('v2_cash_count', p.inner_text('#rCount')); rec('v2_cash_first_card_what', p.eval_on_selector_all('#rList .what', 'e => e.slice(0,2).map(x => x.textContent)'))
            rec('v2_cash_selection_cleared_for_missing', p.inner_text('#cmpN') if p.is_visible('#cmpN') else 'bar hidden')
            p.fill('#fZip', '75201'); p.click('#fZipGo'); p.wait_for_timeout(400)
            rec('v2_cash_zip_75201', p.inner_text('#rCount'))
            names = p.eval_on_selector_all('#rList h3', 'e => e.map(x => x.textContent)')
            rec('v2_cash_zip_names_has_dallas_county_hospital', any('Dallas County Hospital' == n for n in names))
            shot(p, 'v2-04-results-cash-zip-1280')
            p.goto(B + '/v2/price-finder/?area=dfw&code=45378&pay=cash'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000); p.wait_for_timeout(300)
            rec('v2_45378_cash_names', p.eval_on_selector_all('#rList h3', 'e => e.slice(0,8).map(x => x.textContent)'))
            rec('v2_45378_excluded_note', p.inner_text('.excl summary') if p.query_selector('.excl summary') else None)
            # receipt
            p.goto(B + '/v2/price-finder/?area=dfw&code=73721'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000)
            p.select_option('#net', index=1); p.wait_for_timeout(400)
            href = p.get_attribute('#rList h3 a', 'href')
            p.goto(B + href); p.wait_for_selector('.receipt', timeout=60000); p.wait_for_timeout(500)
            rec('v2_receipt_url', href); shot(p, 'v2-05-receipt-1280')
            rec('v2_receipt_has_source', bool(p.query_selector('details[open] .kv a[target=_blank]')))
            # calculator handoff
            c = p.get_attribute('a.btn.y[href*="plan-calculator"]', 'href')
            rec('v2_receipt_to_calc', c)
            p.goto(B + c); p.wait_for_selector('#mBody:not([hidden])', timeout=60000); p.wait_for_timeout(400)
            rec('v2_calc_proc', p.eval_on_selector('#mProc', 'e => e.value'))
            rec('v2_calc_tabs_vs_count', [p.inner_text('#mkFac'), p.inner_text('#mkPro'), p.inner_text('#mN')])
            p.click('#mkPro'); p.wait_for_timeout(200); rec('v2_calc_pro_tab_vs_count', [p.inner_text('#mkPro'), p.inner_text('#mN')])
            shot(p, 'v2-06-calculator-1280')
            p.click('#tMine'); p.wait_for_timeout(300); p.fill('#oDed', '500'); p.fill('#oCo', '20'); p.wait_for_timeout(200)
            rec('v2_calc_enter_my_plan', p.inner_text('#oEst')); shot(p, 'v2-07-calculator-my-plan-1280', full=False)
            rec('v2_page_errors', p.errs)

        except Exception as ex:
            rec('v2_journey_error', repr(ex)[:300])
        try:
            # ---------- the switch: V2 -> Original keeps context ----------
            p = pg()
            p.goto(B + '/v2/price-finder/?area=dfw&code=45378&pay=cash'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000)
            boxes = p.query_selector_all('#rList input[type=checkbox]')
            for b in boxes[:2]: b.check()
            p.hover('.hcf-vs a[data-v=orig]')
            rec('switch_v2_to_orig_href', p.get_attribute('.hcf-vs a[data-v=orig]', 'href'))
            p.click('.hcf-vs a[data-v=orig]'); p.wait_for_load_state('load'); p.wait_for_timeout(4000)
            rec('switch_orig_after', p.evaluate('({url: location.pathname + location.search, pay: document.getElementById("pay") && document.getElementById("pay").value, code: typeof S!=="undefined" && S.code})'))
            shot(p, 'orig-01-price-finder-from-v2-1280', full=False)
            p.hover('.hcf-vs a[data-v=v2]')
            rec('switch_orig_to_v2_href', p.get_attribute('.hcf-vs a[data-v=v2]', 'href'))
            # Original Compare view, cash: F02 slips
            try:
                p.goto(B + '/price-finder/?code=45378'); p.wait_for_timeout(5000)
                p.select_option('#pay', 'cash'); p.wait_for_timeout(1500)
                rec('orig_F02_slips_cash', p.eval_on_selector_all('.ux-bills .ux-slip', 'e => e.map(x => x.innerText.replace(/\\s+/g," "))'))
                shot(p, 'orig-02-compare-cash-slips-1280')
                rec('orig_cash_has_dallas_county_hospital', 'Dallas County Hospital' in p.inner_text('#patient') if p.query_selector('#patient') else None)
            except Exception as ex:
                rec('orig_F02_error', repr(ex)[:200])
            # Original calculator counts (F03)
            try:
                p.goto(B + '/plan-calculator/'); p.wait_for_timeout(2500)
                rec('orig_F03_counts', [p.inner_text('#kfac'), p.inner_text('#kpro'), p.inner_text('#count')])
                p.click('#kpro'); p.wait_for_timeout(300); rec('orig_F03_counts_pro', [p.inner_text('#kpro'), p.inner_text('#count')])
            except Exception as ex:
                rec('orig_F03_error', repr(ex)[:200])
            # Parkland profile (F01b)
            try:
                pk = [d for d in os.listdir(os.path.join(site, 'hospitals')) if d.startswith('parkland')]
                if pk:
                    p.goto(B + f'/hospitals/{pk[0]}/'); p.wait_for_timeout(500)
                    t = p.inner_text('body')
                    rec('orig_parkland_has_788', '$788.00' in t)
            except Exception as ex:
                rec('orig_parkland_error', repr(ex)[:200])
            # not ready
            p.goto(B + '/hospitals/'); p.wait_for_timeout(800)
            rec('switch_hospitals_to_v2_href', p.get_attribute('.hcf-vs a[data-v=v2]', 'href'))
            p.click('.hcf-vs a[data-v=v2]'); p.wait_for_load_state('load'); p.wait_for_timeout(300)
            rec('not_ready_page', [p.url.replace(B, ''), p.inner_text('h1'), p.get_attribute('#nrOrig', 'href')])
            shot(p, 'v2-08-not-ready-1280', full=False)
            p.goto(B + '/'); p.wait_for_timeout(800); shot(p, 'orig-03-home-with-switch-1280', full=False)
            rec('orig_page_errors', p.errs)

        except Exception as ex:
            rec('switch_error', repr(ex)[:300])
        try:
            # ---------- mobile, small and zoomed ----------
            for wd, name in ((390, 'v2-home-390'), (320, 'v2-home-320')):
                p = pg(wd, 844, 2)
                p.goto(B + '/v2/'); p.wait_for_timeout(800); shot(p, name)
                rec('overflow_' + name, p.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth'))
            p = pg(390, 844, 2)
            p.goto(B + '/v2/price-finder/?area=dfw&code=73721&pay=cash'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000); p.wait_for_timeout(400)
            shot(p, 'v2-results-cash-390'); rec('overflow_results_390', p.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth'))
            p.goto(B + '/price-finder/?code=73721'); p.wait_for_timeout(4000); shot(p, 'orig-price-finder-390', full=False)
            p = pg(640, 900, 2)   # 1280 px window at 200% zoom
            p.goto(B + '/v2/price-finder/?area=dfw&code=45378&pay=cash'); p.wait_for_selector('#rBody:not([hidden])', timeout=60000); p.wait_for_timeout(400)
            shot(p, 'v2-results-zoom200', full=False); rec('overflow_zoom200', p.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth'))
        except Exception as ex:
            rec('mobile_error', repr(ex)[:300])
        br.close()
    json.dump(C, open(os.path.join(out, 'checks.json'), 'w'), indent=1)
    srv.shutdown()
    return C
