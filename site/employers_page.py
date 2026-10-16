"""The Employer Plans page (/employer-plans/): which Texas employers' health plans appear in the big insurers' price
file indexes, which networks they use, and what the employer's own Form 5500 filing says about the plan.

  python site/employers_page.py SITE_EMPLOYERS_JSON OUT_DIR
writes OUT_DIR/index.html and OUT_DIR/employers.json (the search list). Input: insurers/employers.py join output
(R2 bot/employers/<date>/site_employers.json). Every figure is a count or a value as filed; nothing is estimated.
"""
import html
import json
import sys
from datetime import date
from pathlib import Path

E = html.escape
FUND = {"self-funded": "Self-funded", "insured": "Insured", "mixed": "Insured and self-paid parts",
        "not stated": "Funding not stated"}
DOL = "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"
EFAST = "https://www.efast.dol.gov/5500Search/"


def n(x):
    return "—" if x is None else f"{int(x):,}"


def long_date(d):
    y, m, dd = (int(p) for p in str(d)[:10].split("-"))
    return date(y, m, dd).strftime("%B %-d, %Y")


def fund(e):
    f = FUND.get(e["funding"] or "", "No Form 5500 found")
    return f + (", stop-loss on file" if e.get("stop_loss") else "")


def main(src, out):
    D = json.load(open(src)); M = D["meta"]; emp = D["employers"]
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    c = M["counts"]
    dfw = [e for e in emp if e["dfw"]]
    top = [e for e in dfw if e.get("active")][:25]
    rows = "".join(
        f"<tr><td><b>{E(e['name'] or '')}</b><div class=\"meta\">{E((e['city'] or '').title())}</div></td>"
        f"<td>{E(', '.join(e['ins']))}</td><td>{E(fund(e))}</td><td>{n(e['active'])}</td><td>{E(str(e['year'] or ''))}</td></tr>"
        for e in top)
    ins_line = " · ".join(f"{E(k)} {n(v)}" for k, v in sorted(M["by_insurer"].items(), key=lambda kv: -kv[1]))
    cats = ", ".join(f"{E(k)} ({E(v)})" for k, v in M["catalogs"].items())
    years = " and ".join(str(y) for y in M.get("f5500") or []) or "latest"
    self_dfw = sum(1 for e in dfw if e["funding"] == "self-funded")
    # search list: [name, city, dfw, insurers {name: [networks]}, funding text, active, year, plan, ack, carriers, stop-loss carriers, ein]
    json.dump([[e["name"], (e["city"] or "").title(), 1 if e["dfw"] else 0, e["ins"], fund(e), e["active"], e["year"],
                e["plan"], e["ack"], e["carriers"], e["sl_carriers"], e["ein"]] for e in emp],
              open(out / "employers.json", "w"), separators=(",", ":"))
    page = TEMPLATE
    for k, v in dict(BUILT=long_date(M["built"]), N_ALL=n(c["employers"]), N_5500=n(c["with_5500"]), N_TX=n(len(emp)),
                     N_DFW=n(len(dfw)), N_DFW_SELF=n(self_dfw), ROWS=rows, INS_LINE=ins_line, CATALOGS=cats, YEARS=E(years),
                     DOL=DOL, EFAST=EFAST).items():
        page = page.replace("{{" + k + "}}", v)
    if "{{" in page:
        raise SystemExit("STOP: unfilled placeholder " + page[page.index("{{"):page.index("{{") + 40])
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out}/index.html ({len(page) / 1e3:.0f} KB), employers.json ({len(emp):,} Texas employers, {len(dfw):,} DFW)")


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#f6f1e7"><link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/manifest.webmanifest"><meta property="og:site_name" content="What It Costs"><meta property="og:type" content="website"><meta property="og:url" content="https://upfront-dfw-preview.pages.dev/employer-plans/"><meta name="twitter:card" content="summary"><meta property="og:title" content="Employer Plans · What It Costs"><meta name="description" content="Look up a Texas employer's health plan: which insurers list it in their federally required price files, which networks it uses, and what its Form 5500 filing says."><meta property="og:description" content="Look up a Texas employer's health plan: which insurers list it in their federally required price files, which networks it uses, and what its Form 5500 filing says."><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;box-sizing:border-box}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#faf9f5;color:#141413}[hidden]{display:none!important}</style></head><body>
<title>Employer Plans · What It Costs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Courier+Prime:wght@400;700&family=Public+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --paper:#f6f1e7; --paper-2:#efe7d8; --ink:#231f1a; --ink-2:#5c5448; --rule:#d6cbb8;
  --brick:#9b3a2a; --brick-soft:#f1dcd4;
  --display:"Newsreader",Georgia,serif; --type:"Courier Prime",ui-monospace,monospace; --body:"Public Sans",system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#1c1916; --paper-2:#26221d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d; --brick:#e0806c; --brick-soft:#3a231d; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#1c1916; --paper-2:#26221d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d; --brick:#e0806c; --brick-soft:#3a231d; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:16px/1.6 var(--body);padding-inline:16px;padding-block:0 56px}
.wrap{max-width:1040px;margin:0 auto}
a{color:var(--brick)}
a:focus-visible,input:focus-visible,label:focus-within{outline:2px solid var(--brick);outline-offset:2px}
.asof{font:13px var(--type);color:var(--ink-2)}
header{padding-block:36px 24px;border-bottom:2px solid var(--ink);display:grid;gap:12px}
.eyebrow{font:600 12px/1 var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--brick)}
h1{font:600 clamp(34px,6.5vw,56px)/1.04 var(--display);margin:0;text-wrap:balance}
.lede{margin:0;max-width:62ch;color:var(--ink-2);font-size:17px}
.tally{display:flex;flex-wrap:wrap;gap:8px 28px;font:14px var(--type);color:var(--ink-2);padding-top:6px}
.tally b{font:700 22px var(--type);color:var(--ink);margin-right:6px;font-variant-numeric:tabular-nums}
h2{font:600 28px/1.15 var(--display);margin:48px 0 6px;text-wrap:balance}
.sub{margin:0 0 16px;color:var(--ink-2);max-width:66ch;font-size:15px}
.meta{font-size:12.5px;color:var(--ink-2);font-weight:400}
.tw{overflow-x:auto;margin-top:6px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font:600 11.5px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);text-align:right;padding:8px 0 6px 12px;border-bottom:1px solid var(--ink);vertical-align:bottom}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{padding:9px 0 9px 12px;border-bottom:1px solid var(--rule);text-align:right;font:14px var(--type);font-variant-numeric:tabular-nums;vertical-align:top}
td:first-child{font:15px/1.35 var(--body);min-width:200px}
td:first-child b{font-weight:600}
td:nth-child(2),td:nth-child(3){font-family:var(--body);text-align:left}
th:nth-child(2),th:nth-child(3){text-align:left}
.search{margin-top:14px;display:grid;gap:10px}
.search input[type=search]{font:16px var(--body);padding:10px 12px;border:1.5px solid var(--ink);border-radius:2px;background:transparent;color:var(--ink);width:100%;max-width:520px}
.opt{font-size:14px;color:var(--ink-2);display:flex;gap:8px;align-items:center}
.card{border-top:1px solid var(--rule);padding:16px 0}
.card h3{font:600 20px/1.2 var(--display);margin:0}
.facts{display:flex;flex-wrap:wrap;gap:4px 22px;font:13.5px var(--type);color:var(--ink-2);margin-top:6px}
.facts b{color:var(--ink);font-weight:700}
.ins{margin-top:10px;display:grid;gap:8px}
.ins div{font-size:14px}
.ins b{font-weight:600}
.nets{color:var(--ink-2)}
.empty{color:var(--ink-2);font-size:14px}
.notes{margin-top:48px;padding-top:16px;border-top:2px solid var(--ink);display:grid;gap:12px;font-size:14px;color:var(--ink-2);max-width:70ch}
.notes b{color:var(--ink)}
</style>

<div class="wrap">
<style>.sn{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px 16px;padding:14px 0;border-bottom:1px solid var(--rule)}.sn-brand{font:600 20px var(--display);color:var(--ink)!important;text-decoration:none}.sn-links{display:flex;flex-wrap:wrap;gap:4px 16px;font:14px var(--body)}.sn-links a{color:var(--brick);text-decoration:none}.sn-links a:hover{text-decoration:underline}.sn-links a[aria-current]{color:var(--ink);font-weight:600}</style><nav class="sn" aria-label="Site"><a class="sn-brand" href="/">What It Costs</a><span class="sn-links"><a href="/start-here/">Start here</a><a href="/price-finder/">Price Finder</a><a href="/plan-calculator/">Plan Calculator</a><a href="/price-file-watch/">Price File Watch</a><a href="/surprise-bills/">Surprise Bills</a><a href="/employer-plans/" aria-current="page">Employer Plans</a></span></nav>
<div class="asof" style="padding-top:8px">Insurer indexes and Form 5500 data read {{BUILT}}</div>

<header>
  <div class="eyebrow">For HR teams and employers · Texas</div>
  <h1>Look up an employer's health plan</h1>
  <p class="lede">Insurers and plan administrators must publish an index of every employer plan they run and the price files each plan uses. Employers that sponsor larger plans file a Form 5500 with the U.S. Department of Labor. We read both and matched them by the employer's tax ID. Search a Texas employer to see which insurer lists its plan, which networks the plan uses, and how the employer says the plan is funded.</p>
  <div class="tally"><span><b>{{N_TX}}</b>Texas employers</span><span><b>{{N_DFW}}</b>in Dallas–Fort Worth</span><span><b>{{N_DFW_SELF}}</b>DFW employers that file as self-funded</span></div>
</header>

<h2 id="search">Search</h2>
<div class="search">
  <label for="q" class="sub" style="margin:0">Employer name, city or 9-digit tax ID (EIN). Texas employers listed in the price file indexes of UnitedHealthcare, Anthem, Cigna, Aetna and Blue Cross and Blue Shield of Texas.</label>
  <input id="q" type="search" placeholder="e.g. Texas Instruments, Irving, 750289970" autocomplete="off">
  <label class="opt"><input type="checkbox" id="dfwonly" checked> Dallas–Fort Worth only</label>
  <div id="res" aria-live="polite"></div>
</div>

<h2>Largest Dallas–Fort Worth employers we found</h2>
<p class="sub">By active participants on the employer's most recent health-plan Form 5500. "Listed by" is the insurer or administrator whose price file index names the employer's plan; an employer can use more than one.</p>
<div class="tw"><table>
<thead><tr><th>Employer</th><th>Listed by</th><th>Funding (Form 5500)</th><th>Active participants</th><th>Form 5500 year</th></tr></thead>
<tbody>{{ROWS}}</tbody></table></div>

<section class="notes">
  <p><b>Where this comes from.</b> Insurer price file indexes (federal Transparency in Coverage rule): {{CATALOGS}}. Employers per insurer, nationwide: {{INS_LINE}}. Form 5500 health-plan filings, data years {{YEARS}}, from the Department of Labor's <a href="{{DOL}}" target="_blank" rel="noopener">Form 5500 datasets</a>; look up any filing by employer name in <a href="{{EFAST}}" target="_blank" rel="noopener">EFAST2</a>. {{N_ALL}} employers appear in the indexes; {{N_5500}} of them have a health-plan Form 5500.</p>
  <p><b>What "funding" means here.</b> It is what the employer's filing says, not our judgment. <i>Insured</i>: a Schedule A shows health coverage bought from an insurer. <i>Self-funded</i>: no insured health coverage on file, and the plan pays benefits from the employer's assets or a trust. <i>Insured and self-paid parts</i>: the filing shows both, often an insured option next to self-paid benefits. <i>Stop-loss on file</i>: the plan bought stop-loss insurance, which self-funded plans use to cap large claims.</p>
  <p><b>What this leaves out.</b> Only plans that must file a Form 5500 (mostly 100 or more participants) show participants and funding. Location is the sponsor's mailing address on the filing; a Texas address doesn't mean every member lives in Texas. Insurers not listed above (for example, smaller administrators) aren't searched yet. Network names are the insurer's own file descriptions; to see the rates in a network, use the <a href="/price-finder/">Price Finder</a>.</p>
</section>
</div>
<script>
(function(){
  var P=null,q=document.getElementById('q'),res=document.getElementById('res'),only=document.getElementById('dfwonly');
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
  var num=function(x){return x==null?'—':Number(x).toLocaleString('en-US');};
  function load(){ if(P) return Promise.resolve(); return fetch('employers.json').then(function(r){return r.json();}).then(function(x){P=x;}); }
  function card(e){
    var ins=Object.keys(e[3]).map(function(k){var nets=e[3][k];return '<div><b>'+esc(k)+'</b>'+(nets.length?' <span class="nets">· '+nets.map(esc).join(' · ')+'</span>':'')+'</div>';}).join('');
    var f='<span>'+esc(e[4])+'</span>';
    if(e[5]!=null) f+='<span><b>'+num(e[5])+'</b> active participants</span>';
    if(e[6]) f+='<span>Form 5500 '+esc(e[6])+'</span>';
    if(e[9]) f+='<span>Insured by '+esc(e[9])+'</span>';
    if(e[10]) f+='<span>Stop-loss: '+esc(e[10])+'</span>';
    return '<div class="card"><h3>'+esc(e[0])+'</h3><div class="meta">'+esc(e[1])+(e[2]?' · Dallas–Fort Worth':'')+' · EIN '+esc(e[11])+(e[7]?' · '+esc(e[7]):'')+'</div><div class="facts">'+f+'</div><div class="ins">'+ins+'</div>'+(e[8]?'<div class="meta" style="margin-top:8px">Form 5500 filing ID '+esc(e[8])+'</div>':'')+'</div>';
  }
  function show(){ var t=q.value.trim().toLowerCase(); if(t.length<2){res.innerHTML='';return;}
    load().then(function(){
      var d=t.replace(/[^0-9]/g,'');
      var hits=P.filter(function(e){ if(only.checked&&!e[2]) return false;
        return String(e[0]).toLowerCase().indexOf(t)>=0||String(e[1]).toLowerCase().indexOf(t)>=0||(d.length>=6&&String(e[11]).indexOf(d)===0);});
      res.innerHTML=hits.length?hits.slice(0,20).map(card).join('')+(hits.length>20?'<p class="empty">'+num(hits.length)+' matches; showing the first 20 (largest first). Add a word to narrow it.</p>':''):'<p class="empty">No Texas employer by that name in these insurers\' indexes'+(only.checked?' in Dallas–Fort Worth. Uncheck "Dallas–Fort Worth only" to search all of Texas.':'.')+'</p>';
    }).catch(function(){res.innerHTML='<p class="empty">Could not load the employer list.</p>';});
  }
  var tm; q.addEventListener('input',function(){clearTimeout(tm);tm=setTimeout(show,180);}); only.addEventListener('change',show);
})();
</script>
</body></html>
"""

if __name__ == "__main__":
    main(*sys.argv[1:3])
