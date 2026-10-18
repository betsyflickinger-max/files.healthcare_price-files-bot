"""The Insurers page (/insurers/): how employers, insurers, parent companies, networks and providers connect, and every
U.S. health insurance parent company with the state-licensed companies it owns, sized by insured members (CMS MLR 2024).

  python site/insurers_page.py insurers/mlr/site_insurers.json OUT_DIR    -> OUT_DIR/index.html
Data: insurers/mlr/ (built Oct 16, 2026 from the CMS Medical Loss Ratio public use file, reporting year 2024).
"""
import json
import sys
from pathlib import Path


def main(src, out):
    data = json.load(open(src))
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    page = TEMPLATE.replace("{{DATA}}", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out}/index.html ({len(page) / 1e3:.0f} KB): {len(data)} parents, {sum(len(p['c']) for p in data)} companies")


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#f6f1e7"><link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta property="og:site_name" content="What It Costs"><meta property="og:type" content="website"><meta property="og:url" content="https://files.healthcare/insurers/"><meta property="og:title" content="Who Owns Your Health Plan · What It Costs"><meta name="description" content="Every U.S. health insurance parent company and the state-licensed companies it owns, sized by insured members, and how employers, insurers, networks and providers connect."><title>Who Owns Your Health Plan · What It Costs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Courier+Prime:wght@400;700&family=Public+Sans:wght@400;500;600;700&display=swap">
<style>
/* Layout: one reading column; a numbered flow map, then a size map of parent companies, then the full family list. */
:root{
  --paper:#f6f1e7; --paper-2:#ece3d2; --ink:#231f1a; --ink-2:#5c5448; --rule:#d6cbb8;
  --brick:#9b3a2a; --brick-soft:#f1dcd4;
  --nat:#9b3a2a; --multi:#2f5d73; --single:#7a6a3a;
  --nat-soft:#f1dcd4; --multi-soft:#d9e6ec; --single-soft:#ece4cc;
  --display:"Newsreader",Georgia,serif; --type:"Courier Prime",ui-monospace,monospace; --body:"Public Sans",system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#1c1916; --paper-2:#28231d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d; --brick:#e0806c; --brick-soft:#3a231d;
  --nat:#e0806c; --multi:#7fb3cc; --single:#cdb878; --nat-soft:#3a231d; --multi-soft:#1d2d35; --single-soft:#302a18; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#1c1916; --paper-2:#28231d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d; --brick:#e0806c; --brick-soft:#3a231d;
  --nat:#e0806c; --multi:#7fb3cc; --single:#cdb878; --nat-soft:#3a231d; --multi-soft:#1d2d35; --single-soft:#302a18; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:16px/1.6 var(--body);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 64px}
.wrap{max-width:1080px;margin:0 auto}
a{color:var(--brick)}
:focus-visible{outline:2px solid var(--brick);outline-offset:2px}
header{padding-block:40px 24px;border-bottom:2px solid var(--ink);display:grid;gap:14px}
.eyebrow{font:700 12px/1 var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--brick)}
h1{font:600 clamp(36px,7vw,60px)/1.02 var(--display);margin:0;text-wrap:balance}
.lede{margin:0;max-width:60ch;color:var(--ink-2);font-size:17px}
.chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{display:flex;align-items:baseline;gap:8px;padding:10px 14px;border:1.5px solid var(--ink);border-radius:2px}
.chip b{font:700 26px var(--type);font-variant-numeric:tabular-nums}
.chip span{font-size:14px;color:var(--ink-2)}
h2{font:600 30px/1.15 var(--display);margin:56px 0 6px;text-wrap:balance}
.sub{margin:0 0 16px;color:var(--ink-2);max-width:64ch;font-size:15px}
.flow{overflow-x:auto;-webkit-overflow-scrolling:touch;margin-top:8px}
.flow svg{display:block;min-width:900px;width:100%;height:auto}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:16px}
.step{padding:12px 14px;background:var(--paper-2);border-radius:2px;min-width:0}
.step b{display:block;font:700 13px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--brick);margin-bottom:2px}
.step p{margin:0;font-size:14.5px}
.key{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;margin:10px 0}
.key button{font:600 14px var(--body);display:flex;align-items:center;gap:8px;background:transparent;border:1.5px solid var(--rule);border-radius:999px;padding:5px 12px;color:var(--ink);cursor:pointer}
.key button[aria-pressed=false]{opacity:.45}
.key i{width:12px;height:12px;border-radius:2px;display:inline-block}
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:8px 0}
.tools input{font:16px var(--body);padding:9px 12px;border:1.5px solid var(--ink);border-radius:2px;background:transparent;color:var(--ink);width:100%;max-width:360px}
.tools select{font:15px var(--body);padding:8px;border:1.5px solid var(--rule);border-radius:2px;background:var(--paper);color:var(--ink)}
#tm{position:relative;width:100%;height:520px;margin-top:10px}
.tile{position:absolute;border:1px solid var(--paper);padding:6px 8px;overflow:hidden;cursor:pointer;color:var(--ink);text-align:left;font:inherit;border-radius:0}
.tile.sm{padding:0}
.tile .tn{font:600 14px/1.15 var(--body);display:block}
.tile .tl{font:12px var(--type);color:var(--ink-2)}
.tile.national{background:var(--nat-soft);box-shadow:inset 4px 0 0 var(--nat)}
.tile.multi_state{background:var(--multi-soft);box-shadow:inset 4px 0 0 var(--multi)}
.tile.single_state{background:var(--single-soft);box-shadow:inset 4px 0 0 var(--single)}
.tile:hover,.tile.on{outline:2px solid var(--ink);outline-offset:-2px;z-index:2}
.tile.dim{opacity:.18}
.panel{margin-top:14px;padding:18px;border:2px solid var(--ink);border-radius:2px;display:grid;gap:10px}
.panel h3{font:600 26px/1.1 var(--display);margin:0}
.pill{display:inline-block;font:700 11px var(--body);letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;color:var(--paper)}
.pill.national{background:var(--nat)}.pill.multi_state{background:var(--multi)}.pill.single_state{background:var(--single)}
.mk{display:flex;height:14px;border-radius:2px;overflow:hidden;background:var(--paper-2);max-width:520px}
.mk i{display:block;height:100%}
.mklab{display:flex;flex-wrap:wrap;gap:4px 16px;font:13px var(--type);color:var(--ink-2)}
.cos{display:grid;gap:6px;margin:0;padding:0;list-style:none}
.cos li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:8px 0;border-top:1px solid var(--rule)}
.cos .cn{font-weight:600;min-width:0}
.cos .cl{font:14px var(--type);font-variant-numeric:tabular-nums;text-align:right}
.sts{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px}
.sts span{font:12px var(--type);padding:1px 6px;border:1px solid var(--rule);border-radius:2px}
.list{margin-top:10px;border-top:2px solid var(--ink)}
details{border-bottom:1px solid var(--rule)}
summary{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:10px 0;cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary .dot{width:12px;height:12px;border-radius:2px;align-self:center}
summary .nm{font-weight:600;min-width:0}
summary .nm small{font-weight:400;color:var(--ink-2);margin-left:6px}
summary .lv{font:14px var(--type);font-variant-numeric:tabular-nums;white-space:nowrap}
details[open] summary .nm{color:var(--brick)}
details .body{padding:0 0 12px 32px}
.count{font:13px var(--type);color:var(--ink-2)}
.notes{margin-top:56px;padding-top:16px;border-top:2px solid var(--ink);display:grid;gap:10px;font-size:14px;color:var(--ink-2);max-width:72ch}
.notes b{color:var(--ink)}
.vt{display:inline-flex;border:1.5px solid var(--ink);border-radius:2px;overflow:hidden;justify-self:start}
.vt button{font:700 14px var(--body);padding:6px 16px;border:0;background:transparent;color:var(--ink);cursor:pointer}
.vt button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.cnote{margin:0;font-size:14px;color:var(--ink-2);max-width:70ch}
.ab{margin:0;font-size:15px;max-width:70ch}
.tag{display:inline-block;font:700 11px var(--body);letter-spacing:.08em;text-transform:uppercase;padding:2px 8px;border:1.5px solid var(--ink);border-radius:999px;margin-right:6px;vertical-align:1px}
.tag.blue{border-color:var(--multi);color:var(--multi)}
.callout{margin:12px 0 4px;padding:14px 16px;border:2px solid var(--ink);border-left-width:8px;max-width:76ch;font-size:15.5px}
.callout p{margin:0}.callout p+p{margin-top:8px}
.tree{display:grid;gap:0;margin-top:4px}
.nd{border:2px solid var(--ink);border-radius:2px;padding:10px 12px;background:var(--paper);font-weight:700;display:grid;gap:4px;min-width:0}
.nd small{font:400 13px/1.4 var(--body);color:var(--ink-2)}
.nd.par{background:var(--ink);color:var(--paper);font:600 20px/1.15 var(--display);max-width:560px}
.nd.par small{color:var(--paper);opacity:.85}
.nd.lic{border-style:dashed;border-color:var(--multi);max-width:560px}
.nd.ghost{border-style:dashed;border-color:var(--ink-2);font-weight:600;color:var(--ink-2)}
.ar{font:12px/1 var(--type);color:var(--ink-2);margin-left:22px;padding:8px 0 8px 14px;border-left:2px solid var(--ink);position:relative}
.ar::after{content:"";position:absolute;left:-7px;bottom:-2px;border:6px solid transparent;border-top:7px solid var(--ink);border-bottom:0}
.ar.out{border-left-style:dashed;border-left-color:var(--ink-2)}
.split{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:0 18px}
.br{display:grid;align-content:start;gap:0}
.br .nd+.nd{margin-top:8px}
.cos2{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.nd.co{font-size:15px;line-height:1.25}
.nd .bar{display:block;height:6px;background:var(--multi);border-radius:1px;font-style:normal}
.more{margin:8px 0 0;font-size:14px;color:var(--ink-2)}
@media (max-width:700px){.split{grid-template-columns:1fr}}
svg text{font-family:var(--body)}
@media (prefers-reduced-motion:no-preference){.tile{transition:opacity .2s}}
@media (max-width:620px){#tm{height:420px}.tile .tl{display:none}}
</style>
</head><body>
<div class="wrap">
<style>.sn{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px 16px;padding:14px 0;border-bottom:1px solid var(--rule)}.sn-brand{font:600 20px var(--display);color:var(--ink)!important;text-decoration:none}.sn-links{display:flex;flex-wrap:wrap;gap:4px 16px;font:14px var(--body)}.sn-links a{color:var(--brick);text-decoration:none}.sn-links a:hover{text-decoration:underline}.sn-links a[aria-current]{color:var(--ink);font-weight:600}</style><nav class="sn" aria-label="Site"><a class="sn-brand" href="/">What It Costs</a><span class="sn-links"><a href="/start-here/">Start here</a><a href="/price-finder/">Price Finder</a><a href="/plan-calculator/">Plan Calculator</a><a href="/price-file-watch/">Price File Watch</a><a href="/surprise-bills/">Surprise Bills</a><a href="/employer-plans/">Employer Plans</a><a href="/insurers/" aria-current="page">Insurers</a></span></nav>
<header>
  <div class="eyebrow">Health insurers in the U.S. · 2024 filings</div>
  <h1>Who owns your health plan</h1>
  <p class="lede">Most health insurance brands are owned by a handful of parent companies. Each parent owns separate insurance companies licensed state by state. Here is how the pieces connect, and every parent with the companies it owns.</p>
  <div class="chips">
    <div class="chip"><b id="n-par">200</b><span>parent companies</span></div>
    <div class="chip"><b id="n-co">484</b><span>insurance companies</span></div>
    <div class="chip"><b id="n-nat">7</b><span>sell in 20+ states</span></div>
    <div class="chip"><b id="n-top">6</b><span>parents cover half of insured members</span></div>
  </div>
</header>

<h2>How the money and the files flow</h2>
<p class="sub">Follow the numbers. Solid arrows are money or contracts. Dashed arrows are the public filings each one has to make, which is where this site's data comes from.</p>
<div class="flow" role="img" aria-label="Diagram: employers and people pay insurance companies or administrators; insurance companies are owned by parent companies; plans use networks that contract with providers; each party files public data.">
<svg viewBox="0 0 1000 620" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--ink-2)"/></marker>
    <marker id="ab" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--brick)"/></marker>
  </defs>
  <g style="font-size:11px;font-weight:700;letter-spacing:.08em;fill:var(--ink-2)">
    <text x="20" y="22">1 · WHO PAYS</text><text x="232" y="22">2 · WHO RUNS THE PLAN</text><text x="450" y="22">3 · WHO OWNS IT</text><text x="656" y="22">4 · THE NETWORK</text><text x="852" y="22">5 · WHO GETS PAID</text>
  </g>
  <g style="stroke:var(--ink);stroke-width:1.5">
    <rect x="20" y="40" width="180" height="70" rx="2" style="fill:var(--multi-soft)"/>
    <rect x="20" y="150" width="180" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="20" y="260" width="180" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="232" y="40" width="186" height="70" rx="2" style="fill:var(--multi-soft)"/>
    <rect x="232" y="150" width="186" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="232" y="260" width="186" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="450" y="120" width="180" height="130" rx="2" style="fill:var(--nat-soft);stroke:var(--brick);stroke-width:2"/>
    <rect x="656" y="60" width="170" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="656" y="170" width="170" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="656" y="280" width="170" height="70" rx="2" style="fill:var(--paper-2)"/>
    <rect x="852" y="120" width="130" height="130" rx="2" style="fill:var(--single-soft)"/>
  </g>
  <g style="fill:var(--ink);font-size:13.5px;font-weight:600">
    <text x="32" y="64">Employer that pays</text><text x="32" y="82">its own claims</text>
    <text x="32" y="174">Employer that buys</text><text x="32" y="192">insurance</text>
    <text x="32" y="284">A person on their</text><text x="32" y="302">own plan</text>
    <text x="244" y="64">Administrator (TPA)</text>
    <text x="244" y="174">Insurance company,</text><text x="244" y="192">licensed in one state</text>
    <text x="244" y="284">Stop-loss insurer</text>
    <text x="462" y="146">Parent company</text>
    <text x="668" y="84">The plan's network</text>
    <text x="668" y="194">BlueCard</text>
    <text x="668" y="304">Rental network</text>
    <text x="864" y="146">Hospitals,</text><text x="864" y="164">doctors, surgery</text><text x="864" y="182">centers, labs</text>
  </g>
  <g style="fill:var(--ink-2);font-size:12px">
    <text x="32" y="100">"self-funded"</text>
    <text x="32" y="210">"fully insured"</text>
    <text x="32" y="320">individual market</text>
    <text x="244" y="84">often an insurer's arm;</text><text x="244" y="100">pays claims from the employer</text>
    <text x="244" y="210">carries the risk</text>
    <text x="244" y="302">bought by self-funded</text><text x="244" y="318">employers for huge claims</text>
    <text x="462" y="168">owns many of the state</text><text x="462" y="184">companies in column 2</text>
    <text x="462" y="210">Example: UnitedHealth</text><text x="462" y="226">Group, 54 companies</text>
    <text x="668" y="102">contracts with negotiated</text><text x="668" y="118">prices</text>
    <text x="668" y="212">Blue plans lend each other</text><text x="668" y="228">their networks out of state</text>
    <text x="668" y="322">a network small plans and</text><text x="668" y="338">administrators lease</text>
    <text x="864" y="204">paid the negotiated</text><text x="864" y="220">rate, not the list</text><text x="864" y="236">price</text>
  </g>
  <g style="stroke:var(--ink-2);stroke-width:1.6;fill:none" marker-end="url(#ar)">
    <path d="M200 75 H228"/><path d="M200 185 H228"/><path d="M200 295 Q215 260 228 210"/>
    <path d="M200 102 C218 104 216 286 228 292"/>
    <path d="M418 75 Q440 80 447 140"/><path d="M418 185 H447"/><path d="M418 295 Q440 290 447 235"/>
    <path d="M630 160 Q645 110 653 100"/><path d="M630 200 H653"/><path d="M630 230 Q645 290 653 310"/>
    <path d="M826 95 Q840 110 849 150"/><path d="M826 205 H849"/><path d="M826 315 Q840 290 849 230"/>
  </g>
  <g style="fill:var(--ink-2);font-size:11px;font-style:italic">
    
  </g>
  <line x1="20" y1="392" x2="982" y2="392" style="stroke:var(--rule);stroke-width:1"/>
  <text x="20" y="420" style="font-size:11px;font-weight:700;letter-spacing:.08em;fill:var(--brick)">6 · WHAT EACH ONE HAS TO MAKE PUBLIC</text>
  <g style="stroke:var(--brick);stroke-width:1.5;fill:var(--paper)">
    <rect x="20" y="440" width="180" height="96" rx="2"/>
    <rect x="232" y="440" width="186" height="96" rx="2"/>
    <rect x="450" y="440" width="376" height="96" rx="2"/>
    <rect x="852" y="440" width="130" height="96" rx="2"/>
  </g>
  <g style="fill:var(--ink);font-size:13.5px;font-weight:600">
    <text x="32" y="464">Form 5500</text><text x="244" y="464">Loss-ratio report</text><text x="462" y="464">Insurer price files</text><text x="864" y="464">Hospital price</text><text x="864" y="482">files</text>
  </g>
  <g style="fill:var(--ink-2);font-size:12px">
    <text x="32" y="484">plan size, funding,</text><text x="32" y="500">insurers used</text><text x="32" y="522" style="fill:var(--brick)">→ Employer Plans page</text>
    <text x="244" y="484">members and premium,</text><text x="244" y="500">by state</text><text x="244" y="522" style="fill:var(--brick)">→ this page</text>
    <text x="462" y="484">every network's negotiated rates, plus an index of every</text><text x="462" y="500">employer plan and which files it uses</text><text x="462" y="522" style="fill:var(--brick)">→ Price Finder and Employer Plans</text>
    <text x="864" y="502">cash and</text><text x="864" y="518">negotiated prices</text>
  </g>
  <g style="stroke:var(--brick);stroke-width:1.4;fill:none;stroke-dasharray:5 4" marker-end="url(#ab)">
    <path d="M110 330 V436"/><path d="M325 330 V436"/><path d="M741 350 V436"/><path d="M917 250 V436"/>
  </g>
</svg>
</div>
<div class="steps">
  <div class="step"><b>1 · Who pays</b><p>Most people with job-based coverage are in plans where the employer pays the claims itself and only hires an insurer to run it.</p></div>
  <div class="step"><b>2 · Who runs it</b><p>The same brand can be the insurer (insured plans) or just the administrator (self-funded plans). Members usually can't tell which.</p></div>
  <div class="step"><b>3 · Who owns it</b><p>Each state license is a separate company. The family tree below groups them under the parent that owns them.</p></div>
  <div class="step"><b>4–5 · Network and providers</b><p>The network sets the price a hospital or doctor gets. That negotiated rate is what the price files reveal.</p></div>
</div>

<h2>The family tree, sized by members</h2>
<p class="sub">Each block is a parent company. Bigger block, more people in its insured plans in 2024. Click a block to see the companies it owns and where they sell.</p>
<div class="callout" id="counted">
  <p><b>Read this first: these numbers count only part of each company.</b> They count people in <b>fully insured</b> plans, where the insurance company pays the claims and carries the risk. Most people with job-based coverage are in <b>self-funded</b> plans instead: the employer pays the claims and the insurance company only runs the plan. Those people aren't in these filings, and neither are Medicare Advantage or Medicaid.</p>
  <p>So the same company can look much smaller here than it really is. HCSC (Blue Cross and Blue Shield of Texas) shows 6.3 million people here but <a href="https://www.beckerspayer.com/financial/health-care-service-corp-posts-1-9b-loss-in-2025/" target="_blank" rel="noopener">reported 27.3 million members</a> across all its business in 2025.</p>
</div>
<div class="key" id="key">
  <button type="button" data-s="national" aria-pressed="true"><i style="background:var(--nat)"></i>20+ states</button>
  <button type="button" data-s="multi_state" aria-pressed="true"><i style="background:var(--multi)"></i>2–19 states</button>
  <button type="button" data-s="single_state" aria-pressed="true"><i style="background:var(--single)"></i>One state</button>
</div>
<div class="tools">
  <input type="search" id="q" placeholder="Find a company, e.g. Ambetter, Oxford, Blue Cross" aria-label="Find a company">
  <select id="stf" aria-label="State"><option value="">Every state</option></select>
  <span class="count" id="cnt"></span>
</div>
<div id="tm" aria-label="Parent companies sized by insured members"></div>
<div class="panel" id="panel"></div>

<h2>Every parent and its companies</h2>
<p class="sub">The same 200 parents as a list, largest first. Open one to see each company it owns, its members, and the states it files in.</p>
<div class="list" id="list"></div>

<section class="notes">
  <p><b>Where this comes from.</b> CMS Medical Loss Ratio public use file, reporting year 2024 (the newest posted as of October 16, 2026): every insurance company's filing by state, with its holding company. "Members" means people in comprehensive medical plans (individual, small group and large group) on December 31, 2024. Parent companies follow each filing's NAIC group code; about 70 filings without one were matched by brand name.</p>
  <p><b>What it leaves out.</b> Self-funded employer plans (insurers only administer those, so their members aren't counted here), Medicare Advantage, Medicaid and short-term plans. That is why UnitedHealth, Aetna, Cigna and the Blue plans look smaller here than their real reach, and why Humana, which left the employer market, barely shows. Blue Cross Blue Shield plans are separate companies that share a brand and the BlueCard network, so each appears as its own parent.</p>
  <p><b>Price files.</b> Where a parent's public price-file page was found, its panel links to it. </p>
  <p>See which employers use each insurer on <a href="/employer-plans/">Employer Plans</a>, the rates their networks pay in the <a href="/price-finder/">Price Finder</a>, and who isn't publishing usable files in the <a href="/price-file-watch/">Price File Watch</a>.</p>
</section>
</div>
<script id="data" type="application/json">{{DATA}}</script>
<script>
(function(){
  var D=JSON.parse(document.getElementById('data').textContent);
  var SC={national:'20+ states',multi_state:'2–19 states',single_state:'One state'};
  var on={national:true,multi_state:true,single_state:true};
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
  var num=function(x){return Number(x||0).toLocaleString('en-US');};
  var short=function(x){return x>=1e6?(x/1e6).toFixed(1).replace(/\.0$/,'')+'M':x>=1e3?Math.round(x/1e3)+'K':String(x);};
  var q=document.getElementById('q'),stf=document.getElementById('stf'),tm=document.getElementById('tm'),panel=document.getElementById('panel'),cnt=document.getElementById('cnt'),list=document.getElementById('list');
  var states={};D.forEach(function(p){p.c.forEach(function(c){c[2].forEach(function(s){states[s]=1;});});});
  Object.keys(states).sort().forEach(function(s){var o=document.createElement('option');o.value=s;o.textContent=s;stf.appendChild(o);});
  var slug=function(n){return String(n).toLowerCase().replace(/&/g,' and ').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');};
  var sel=D[0].n;
  function fromHash(){var h=decodeURIComponent((location.hash||'').slice(1));var p=h&&D.find(function(x){return slug(x.n)===h;});return p?p.n:null;}

  function match(p){
    if(!on[p.s]) return false;
    var st=stf.value; if(st&&!p.c.some(function(c){return c[2].indexOf(st)>=0;})) return false;
    var t=q.value.trim().toLowerCase(); if(!t) return true;
    return p.n.toLowerCase().indexOf(t)>=0||p.c.some(function(c){return c[0].toLowerCase().indexOf(t)>=0;});
  }
  // squarified treemap (Bruls et al.): values scaled to areas, rows laid along the shorter side
  function squarify(items,x,y,w,h,out){
    var total=items.reduce(function(a,b){return a+b.v;},0); if(!total) return;
    var sc=w*h/total, rest=items.map(function(it){return {it:it,a:it.v*sc};});
    function worst(row,side){var s=0,mx=0,mn=Infinity;row.forEach(function(r){s+=r.a;mx=Math.max(mx,r.a);mn=Math.min(mn,r.a);});
      return Math.max(side*side*mx/(s*s),(s*s)/(side*side*mn));}
    while(rest.length){
      var side=Math.min(w,h),row=[rest[0]],i=1;
      while(i<rest.length&&worst(row.concat([rest[i]]),side)<=worst(row,side)){row.push(rest[i]);i++;}
      rest=rest.slice(row.length);
      var s=row.reduce(function(a,r){return a+r.a;},0);
      if(w>=h){var rw=s/h,yy=y;row.forEach(function(r){var hh=r.a/rw;out.push({d:r.it,x:x,y:yy,w:rw,h:hh});yy+=hh;});x+=rw;w-=rw;}
      else{var rh=s/w,xx=x;row.forEach(function(r){var ww=r.a/rh;out.push({d:r.it,x:xx,y:y,w:ww,h:rh});xx+=ww;});y+=rh;h-=rh;}
    }
  }
  function drawMap(vis){
    var W=tm.clientWidth,H=tm.clientHeight,items=D.filter(function(p){return p.l>0;}).map(function(p){return {v:p.l,p:p};}),out=[];
    squarify(items,0,0,W,H,out);
    tm.innerHTML=out.map(function(r){var p=r.d.p,big=r.w>70&&r.h>34;
      return '<button type="button" class="tile '+p.s+(big?'':' sm')+(vis[p.n]?'':' dim')+(p.n===sel?' on':'')+'" data-n="'+esc(p.n)+'" style="left:'+r.x.toFixed(1)+'px;top:'+r.y.toFixed(1)+'px;width:'+r.w.toFixed(1)+'px;height:'+r.h.toFixed(1)+'px" title="'+esc(p.n)+': '+num(p.l)+' members, '+p.c.length+' companies">'+(big?'<span class="tn">'+esc(p.n)+'</span><span class="tl">'+short(p.l)+' · '+p.c.length+' co.</span>':'')+'</button>';}).join('');
  }
  function companies(p){
    var st=stf.value,t=q.value.trim().toLowerCase();
    return '<ul class="cos">'+p.c.map(function(c){var hit=(t&&c[0].toLowerCase().indexOf(t)>=0)||(st&&c[2].indexOf(st)>=0);
      return '<li><span class="cn"'+(hit?' style="color:var(--brick)"':'')+'>'+esc(c[0])+'</span><span class="cl">'+(c[1]?num(c[1]):'no members')+'</span><span class="sts">'+c[2].map(function(s){return '<span'+(s===st?' style="border-color:var(--brick);color:var(--brick)"':'')+'>'+esc(s)+'</span>';}).join('')+'</span></li>';}).join('')+'</ul>';
  }
  function mix(p){var t=p.i+p.sg+p.lg||1;
    return '<div class="mk" aria-hidden="true"><i style="width:'+(100*p.i/t)+'%;background:var(--brick)"></i><i style="width:'+(100*p.sg/t)+'%;background:var(--multi)"></i><i style="width:'+(100*p.lg/t)+'%;background:var(--single)"></i></div>'+
      '<div class="mklab"><span>Individual '+num(p.i)+'</span><span>Small employer '+num(p.sg)+'</span><span>Large employer '+num(p.lg)+'</span></div>';}
var BLUE={'Health Care Service Corp (HCSC)':'Blue Cross and Blue Shield of Texas, Illinois, Oklahoma, New Mexico and Montana',
  'Elevance Health (Anthem)':'Anthem Blue Cross (California) and Anthem Blue Cross and Blue Shield in 13 more states, including New York, Ohio, Georgia, Indiana and Virginia',
  'Highmark Health':'Highmark Blue Cross Blue Shield (Pennsylvania, Delaware, West Virginia, Western New York) and Highmark Blue Shield',
  'Regence (Cambia)':'Regence BlueCross BlueShield (Oregon, Utah) and Regence BlueShield (Washington, Idaho)',
  'Wellmark BCBS':'Wellmark Blue Cross and Blue Shield (Iowa, South Dakota)',
  'Premera Blue Cross':'Premera Blue Cross (Washington) and Premera Blue Cross and Blue Shield of Alaska',
  'CareFirst BlueCross BlueShield':'CareFirst BlueCrossBlueShield (Maryland, Washington DC, Northern Virginia)',
  'Florida Blue (GuideWell)':'Florida Blue','HMSA (Hawaii Medical Service Association)':'Blue Cross and Blue Shield of Hawaii',
  'Lifetime Healthcare (Excellus)':'Excellus BlueCross BlueShield (New York)','Independence Blue Cross':'Independence Blue Cross (Pennsylvania)',
  'Horizon BCBS of New Jersey':'Horizon Blue Cross and Blue Shield of New Jersey','Capital Blue Cross':'Capital Blue Cross (Pennsylvania)',
  'Arkansas BCBS':'Arkansas Blue Cross and Blue Shield','BCBS of Louisiana':'Blue Cross and Blue Shield of Louisiana',
  'Blue Shield of California':1,'Blue Cross Blue Shield of Michigan':1,'Blue Cross and Blue Shield of North Carolina':1,'BCBS of Alabama':1,
  'BCBS of Massachusetts':1,'BCBS of South Carolina':1,'BCBS of Tennessee':1,'Blue Cross and Blue Shield of Arizona, Inc.':1,'BCBS of Minnesota':1,
  'BCBS of Kansas City':1,'BCBS of Mississippi (Mississippi Ins Grp)':1,'BCBS of Kansas':1,'Blue Cross and Blue Shield of Nebraska':1,
  'Blue Cross Blue Shield of North Dakota':1,'Blue Cross & Blue Shield of Rhode Island':1,'Blue Cross of Idaho Health Service, Inc.':1,'Blue Cross Blue Shield of Wyoming':1};
  var BCBS='https://www.bcbs.com/bcbs-companies-and-licensees';
  var mutual=function(p){return p.c.some(function(c){return /mutual/i.test(c[0]);});};
  var VIEW='list'; try{VIEW=localStorage.getItem('ins-view')==='map'?'map':'list';}catch(_){}
  var byName=function(n){return D.find(function(x){return x.n===n;});};
  function about(p){var h='',b=BLUE[p.n];
    if(b) h+='<p class="ab"><span class="tag blue">Blue Cross Blue Shield</span>'+(b===1?'One':'Sells as <b>'+esc(b)+'</b>. It is one')+' of the separate local companies the <a href="'+BCBS+'" target="_blank" rel="noopener">Blue Cross Blue Shield Association</a> licenses to use the Blue name. Each Blue company is run separately; they share the name and let members use each other’s networks (BlueCard).</p>';
    if(mutual(p)) h+='<p class="ab"><span class="tag">Member-owned</span>Its filing names it a mutual company: owned by its policyholders, with no stockholders.</p>';
    return h;}
  var CNOTE='<p class="cnote">Counts people in fully insured plans only. <a href="#counted">Not counted</a>: self-funded employer plans it runs, Medicare Advantage and Medicaid.</p>';
  function toggle(){return '<div class="vt" role="group" aria-label="Show companies as"><button type="button" data-v="list" aria-pressed="'+(VIEW==='list')+'">List</button><button type="button" data-v="map" aria-pressed="'+(VIEW==='map')+'">Map</button></div>';}
  function tree(p){
    var cs=p.c.slice().sort(function(a,b){return b[1]-a[1];}),max=(cs[0]&&cs[0][1])||1,show=cs.slice(0,12),more=cs.length-show.length;
    var h='<div class="tree">';
    if(BLUE[p.n]) h+='<div class="nd lic">Blue Cross Blue Shield Association<small>owns the Blue name and licenses it, one area at a time</small></div><div class="ar">licenses the Blue name to</div>';
    h+='<div class="nd par">'+esc(p.n)+'<small>'+num(p.l)+' people in fully insured plans'+(mutual(p)?' · owned by its members':'')+'</small></div>';
    h+='<div class="split"><div class="br"><div class="ar">owns these insurance companies, each licensed by a state</div><div class="cos2">'+show.map(function(c){
      return '<div class="nd co"><span>'+esc(c[0])+'</span><i class="bar" style="width:'+Math.max(2,100*c[1]/max).toFixed(1)+'%" aria-hidden="true"></i><small>'+(c[1]?num(c[1])+' people':'no members reported')+'</small><span class="sts">'+c[2].map(function(st){return '<span>'+esc(st)+'</span>';}).join('')+'</span></div>';}).join('')+'</div>'+
      (more>0?'<p class="more">+ '+more+' more companies in the List view</p>':'')+'</div>';
    h+='<div class="br"><div class="ar out">may also run (not counted here)</div><div class="nd ghost">Self-funded employer plans<small>The employer pays the claims; the insurer runs the plan for a fee. See <a href="/employer-plans/">Employer Plans</a>.</small></div><div class="nd ghost">Medicare Advantage and Medicaid plans<small>Reported in other filings.</small></div></div></div></div>';
    return h;}
  function body(p){return VIEW==='map'?tree(p):companies(p);}
  function drawPanel(){
    var p=byName(sel)||D[0];
    panel.innerHTML='<div><span class="pill '+p.s+'">'+SC[p.s]+'</span></div><h3>'+esc(p.n)+'</h3>'+
      '<div class="mklab" style="font-size:14px"><span><b style="color:var(--ink)">'+num(p.l)+'</b> members</span><span><b style="color:var(--ink)">'+p.c.length+'</b> compan'+(p.c.length===1?'y':'ies')+'</span><span><b style="color:var(--ink)">'+p.st+'</b> state'+(p.st===1?'':'s')+' with members</span></div>'+CNOTE+about(p)+mix(p)+
      (p.u?'<div><a href="'+esc(p.u)+'" target="_blank" rel="noopener">Its price-file page</a></div>':'<div class="mklab">No price-file page found for this parent yet.</div>')+toggle()+'<div class="vw" data-n="'+esc(p.n)+'">'+body(p)+'</div>';
  }
  function drawList(vis){
    list.innerHTML=D.filter(function(p){return vis[p.n];}).map(function(p){
      return '<details data-n="'+esc(p.n)+'"><summary><i class="dot" style="background:var(--'+(p.s==='national'?'nat':p.s==='multi_state'?'multi':'single')+')"></i><span class="nm">'+esc(p.n)+'<small>'+p.c.length+' compan'+(p.c.length===1?'y':'ies')+' · '+SC[p.s]+(BLUE[p.n]?' · Blue Cross Blue Shield':'')+'</small></span><span class="lv">'+num(p.l)+'</span></summary><div class="body" style="display:grid;gap:10px">'+about(p)+mix(p)+(p.u?'<p style="margin:0"><a href="'+esc(p.u)+'" target="_blank" rel="noopener">Price-file page</a></p>':'')+toggle()+'<div class="vw" data-n="'+esc(p.n)+'">'+body(p)+'</div></div></details>';}).join('');
  }
  document.addEventListener('click',function(e){var b=e.target.closest('.vt button');if(!b) return;VIEW=b.getAttribute('data-v');
    try{localStorage.setItem('ins-view',VIEW);}catch(_){}
    document.querySelectorAll('.vt button').forEach(function(x){x.setAttribute('aria-pressed',x.getAttribute('data-v')===VIEW);});
    document.querySelectorAll('.vw').forEach(function(el){var p=byName(el.getAttribute('data-n'));if(p) el.innerHTML=body(p);});});
  function render(){
    var vis={},n=0,co=0;D.forEach(function(p){if(match(p)){vis[p.n]=1;n++;co+=p.c.length;}});
    if(!vis[sel]){var f=D.find(function(p){return vis[p.n];});if(f) sel=f.n;}
    cnt.textContent=n+' of '+D.length+' parents · '+num(co)+' companies';
    drawMap(vis);drawPanel();drawList(vis);
  }
  tm.addEventListener('click',function(e){var b=e.target.closest('.tile');if(!b) return;sel=b.getAttribute('data-n');
    tm.querySelectorAll('.tile.on').forEach(function(x){x.classList.remove('on');});b.classList.add('on');drawPanel();
    try{history.replaceState(null,'','#'+slug(sel));}catch(_){}});
  document.getElementById('key').addEventListener('click',function(e){var b=e.target.closest('button');if(!b) return;var s=b.getAttribute('data-s');on[s]=!on[s];b.setAttribute('aria-pressed',on[s]);render();});
  var t;q.addEventListener('input',function(){clearTimeout(t);t=setTimeout(render,150);});stf.addEventListener('change',render);
  var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(render,150);});
  var h0=fromHash(); if(h0) sel=h0;
  render();
  if(h0) panel.scrollIntoView();
  window.addEventListener('hashchange',function(){var h=fromHash();if(h){sel=h;render();panel.scrollIntoView({behavior:'smooth'});}});
})();
</script>
</body></html>
"""

if __name__ == "__main__":
    main(*sys.argv[1:3])
