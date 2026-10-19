"""Price Finder v2 mock-up page (Oct 19, 2026, Betsy's notes): one procedure as a places x insurers table.

  python site/pf_v2_mock.py DATA.json OUT/index.html

What it tries (for Betsy to react to before any of it goes on the 32 Price Finders):
  - one table: each hospital/surgery center is a row; columns are Medicare for that place, Medicare Advantage (from the
    hospital's own file), cash price, and one column per insurer (each with its own network picker). The top row is the
    doctor's (professional) fee in each network, since doctors bill separately and don't belong to one place.
  - pick one network ("Paying with") and the table turns into facility fee + doctor's fee = both bills, against Medicare.
  - tick places and press Compare to see them side by side.
  - every cell is tinted by how many times Medicare it is (the four stripe colors), and every price links to its file.
  - Medicare appears once (its own column); the separate benchmark block is gone.
  - "Expect more than one bill" stays, with what changes the bill for this procedure.
Data: site/pf_v2_data.py. Nothing is estimated or averaged; the doctor's "typical" fee is the middle listed price.
"""
import html
import json
import sys

DATA, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(DATA))

PAGE = r'''<!doctype html>
<html lang="en" data-look="units" data-theme="light">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>What a colonoscopy costs in Dallas–Fort Worth · Price Finder (test) · The Healthcare Files</title>
<link rel="icon" href="/favicon-32.png" sizes="32x32">
<link rel="stylesheet" href="/units.css">
<style>
:root{--blue:#2E5BE6;--blue-d:#1F45C4;--blue-l:#3D69EC;--blue-soft:#DCE5FC;--yel:#F7C925;--org:#F08A24;--grn:#3DB86B;--red:#E6402E;
  --ground:#F4F1EA;--paper:#fff;--ink:#151515;--muted:#4A4A4A;--rule:#151515;--hair:#d9d3c5;
  --mono:"Look DM Mono",ui-monospace,monospace;--sans:"Look Hanken",system-ui,sans-serif;
  --t1:#E3F4E9;--t2:#FDF3CF;--t3:#FCE3CC;--t4:#FADAD5;--money:#1F45C4}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--ground);color:var(--ink);font:16px/1.5 var(--sans);border-top:10px solid;border-image:linear-gradient(90deg,var(--blue) 0 20%,var(--yel) 20% 40%,var(--org) 40% 60%,var(--grn) 60% 80%,var(--red) 80%) 1}
a{color:var(--blue-d)}
.w{max-width:1180px;margin:0 auto;padding:0 16px}
.test{background:#E6402E;color:#fff;font:600 13px/1.3 var(--mono);text-align:center;padding:6px 16px}
/* masthead */
.mast{background:var(--blue);color:#fff}
.bar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-block:18px 14px;flex-wrap:wrap}
.nav{display:flex;gap:4px 18px;flex-wrap:wrap;font:500 14px var(--sans)}
.nav a{color:#fff;text-decoration:none}.nav a[aria-current]{text-decoration:underline;text-underline-offset:4px;text-decoration-color:var(--yel);text-decoration-thickness:2px}
.nav .start{background:var(--yel);color:var(--ink);padding:4px 10px;font-weight:700}
.hero{padding:28px 0 30px;background:repeating-linear-gradient(var(--blue) 0 26px,var(--blue-l) 26px 28px)}
.kick{font:500 13px/1.2 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--yel);margin:0 0 10px}
h1{font:800 clamp(34px,6vw,64px)/.98 var(--sans);text-transform:uppercase;letter-spacing:-.01em;margin:0 0 12px;max-width:16ch}
h1 em{font-style:normal;color:var(--yel)}
.code{font:400 14px var(--mono);color:#DCE5FC;margin:0 0 18px}
.pick{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:end}
.pick label{display:grid;gap:4px;font:500 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:#DCE5FC}
.pick select{font:600 16px var(--sans);padding:9px 34px 9px 10px;border:0;border-radius:0;background:#fff;color:var(--ink);min-width:min(320px,100%);max-width:100%}
.big3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:22px}
.tile{background:#fff;color:var(--ink);border-top:6px solid var(--ink);padding:12px 14px}
.tile p{margin:0}.tile .l{font:500 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.tile .v{font:600 30px/1.15 var(--mono);color:var(--money);margin:4px 0}
.tile .s{font-size:13.5px;color:var(--muted)}
/* sections */
main{padding:8px 0 64px}
section{padding:34px 0 10px;border-bottom:2px solid var(--rule)}
section:last-child{border-bottom:0}
.sk{font:500 13px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--blue);margin:0 0 6px}
h2{font:800 clamp(26px,4vw,42px)/1.02 var(--sans);text-transform:uppercase;margin:0 0 10px}
.lede{max-width:70ch;color:var(--muted);margin:0 0 16px}
/* toolbar + legend */
.tools{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:4px 0 12px}
.tools input[type=search]{font:500 15px var(--sans);padding:8px 10px;border:2px solid var(--ink);background:#fff;min-width:220px;max-width:100%}
.seg{display:inline-flex;border:2px solid var(--ink)}
.seg button{font:600 14px var(--sans);background:#fff;border:0;padding:7px 12px;cursor:pointer;color:var(--ink)}
.seg button+button{border-left:2px solid var(--ink)}
.seg button[aria-pressed=true]{background:var(--ink);color:#fff}
.chk{font-size:14px;display:flex;gap:6px;align-items:center}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13.5px;color:var(--muted);margin:0 0 10px}
.legend .sw{display:inline-block;width:16px;height:16px;vertical-align:-3px;margin-right:5px;border:1px solid rgba(0,0,0,.15)}
/* the table */
.tw{overflow-x:auto;border:2px solid var(--ink);background:#fff;-webkit-overflow-scrolling:touch}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--hair);text-align:right;white-space:nowrap;vertical-align:top}
thead th{position:sticky;top:0;background:#fff;z-index:2;border-bottom:2px solid var(--ink);font:600 13px var(--sans);text-align:right;vertical-align:bottom}
thead th .ins{display:block;font-weight:800;font-size:14px}
thead th select{font:500 12px var(--sans);max-width:150px;margin-top:4px;border:1px solid var(--hair);background:#fff;padding:2px}
th.pl,td.pl{position:sticky;left:0;background:#fff;text-align:left;white-space:normal;min-width:220px;max-width:280px;z-index:1;border-right:2px solid var(--ink)}
thead th.pl{z-index:3}
td.pl b{font-weight:700}td.pl .m{display:block;font-size:12.5px;color:var(--muted)}
td.pl label{display:flex;gap:8px;align-items:flex-start;cursor:pointer}
td.pl input{margin-top:4px}
.kind{font:500 10px var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:0 4px;border:1px solid currentColor;color:var(--muted);margin-left:2px;white-space:nowrap}
.v{font:600 15px var(--mono);color:var(--money);font-variant-numeric:tabular-nums;text-decoration:none;display:inline-block}
a.v:hover{text-decoration:underline}
.x{display:block;font:500 11px var(--mono);color:var(--muted)}
.flat{background:var(--yel);color:var(--ink);padding:0 4px;margin-top:4px;display:inline-block}
.none{color:#9a9488;font:400 14px var(--mono)}
td.b1{background:var(--t1)}td.b2{background:var(--t2)}td.b3{background:var(--t3)}td.b4{background:var(--t4)}
td.med{background:#F7F5EF}td.med .v{color:var(--ink)}
tr.docrow td{background:var(--blue-soft);border-bottom:2px solid var(--ink);font-size:13px}
tr.docrow td.pl{background:var(--blue-soft)}
tr.docrow .v{font-size:14px}
tr.sel td{box-shadow:inset 0 2px 0 var(--yel),inset 0 -2px 0 var(--yel)}
.lowest{outline:2px solid var(--ink);outline-offset:-2px}
.more{margin:12px 0 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:14px;color:var(--muted)}
.btn{font:700 14px var(--sans);text-transform:uppercase;letter-spacing:.04em;background:var(--ink);color:#fff;border:0;padding:10px 16px;cursor:pointer}
.btn.y{background:var(--yel);color:var(--ink)}
/* one-network view: bar against Medicare */
.barcell{min-width:180px;text-align:left}
.track{position:relative;height:14px;background:#EEE9DD;margin-top:4px}
.fill{position:absolute;left:0;top:0;bottom:0;background:var(--blue)}
.mline{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
/* compare tray + dialog */
.tray{position:sticky;bottom:0;z-index:5;background:var(--ink);color:#fff;padding:10px 16px;display:none;align-items:center;gap:14px;justify-content:center;flex-wrap:wrap}
.tray.on{display:flex}
dialog{border:2px solid var(--ink);padding:0;max-width:min(1100px,96vw);width:100%;background:var(--ground)}
dialog::backdrop{background:rgba(21,21,21,.55)}
.dh{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--blue);color:#fff}
.dh h3{margin:0;font:800 20px var(--sans);text-transform:uppercase}
.dh button{background:#fff;border:0;font:700 14px var(--sans);padding:6px 12px;cursor:pointer}
.cmp{overflow-x:auto;padding:16px}
.cmp table{background:#fff;border:2px solid var(--ink)}
.cmp th{text-align:right;white-space:normal;min-width:150px}
.cmp th:first-child,.cmp td:first-child{text-align:left;position:static;min-width:200px;white-space:normal}
.win{background:var(--t1)}
/* bills */
.slips{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:8px 0 18px}
.slip{background:#fff;padding:14px 16px 16px;font:400 14px/1.45 var(--mono);box-shadow:0 1px 0 rgba(0,0,0,.08);border-bottom:3px solid var(--ink);position:relative}
.slip.maybe{background:transparent;border:2px dashed var(--ink)}
.slip .n{font-size:11.5px;letter-spacing:.12em;text-align:center;border-bottom:1px dashed var(--ink);padding-bottom:6px;margin:0 0 8px}
.slip .t{font-weight:600;font-size:16px;margin:0 0 2px}
.slip .d{font-size:12.5px;color:var(--muted);margin:0 0 10px}
.slip .amt{border-top:1px dashed var(--ink);padding-top:8px;display:flex;justify-content:space-between;gap:8px}
.slip .amt b{color:var(--money);font-weight:600}
.slip .src{font:400 12px var(--sans);color:var(--muted);margin:6px 0 0}
.when{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:0 0 22px}
.when div{background:#fff;border-left:6px solid var(--yel);padding:12px 14px}
.when h3{font:700 16px var(--sans);margin:0 0 4px}
.when p{margin:0;font-size:14.5px;color:var(--muted)}
.when .tag{font:500 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--ink);background:var(--yel);padding:1px 6px;display:inline-block;margin-bottom:6px}
.fine{font-size:13px;color:var(--muted);max-width:80ch}
@media (max-width:640px){
  .nav{font-size:13px;gap:4px 12px}
  th.pl,td.pl{min-width:160px;max-width:180px}
  .tools input[type=search]{min-width:0;width:100%}
}
</style>
</head>
<body>
<div class="test">TEST LAYOUT · Price Finder v2 mock-up for Betsy · real DFW data, not linked from the site</div>
<header class="mast">
 <div class="w bar">
  <a class="logo" href="/">The Healthcare <span>Files</span></a>
  <nav class="nav" aria-label="Site"><a class="start" href="/start-here/">Start here</a><a href="/price-finder/" aria-current="page">Price Finder</a><a href="/plan-calculator/">Plan Calculator</a><a href="/price-file-watch/">Price File Watch</a><a href="/surprise-bills/">Surprise Bills</a><a href="/insurers/">Insurers</a><a href="/hospitals/">Hospitals</a></nav>
 </div>
 <div class="hero"><div class="w">
  <p class="kick">What it costs · Dallas–Fort Worth</p>
  <h1>What a <em>colonoscopy</em> costs</h1>
  <p class="code">Colonoscopy (diagnostic) · CPT 45378 · one of CMS's 70 shoppable services</p>
  <div class="pick">
   <label>Paying with<select id="pay"></select></label>
  </div>
  <div class="big3" id="big3"></div>
 </div></div>
</header>
<main class="w">
 <section id="table">
  <p class="sk">What it costs at each place</p>
  <h2 id="th2">Every place, every insurer</h2>
  <p class="lede" id="tlede"></p>
  <div class="tools">
   <input type="search" id="q" placeholder="Find a hospital, surgery center or city" aria-label="Find a place">
   <div class="seg" role="group" aria-label="Kind of place"><button data-k="" aria-pressed="true">All</button><button data-k="A" aria-pressed="false">Surgery centers</button><button data-k="H" aria-pressed="false">Hospitals</button></div>
   <label class="chk"><input type="checkbox" id="ev" checked> Only places with evidence they do colonoscopies</label>
  </div>
  <p class="legend" id="legend"></p>
  <div class="tw"><table id="t"></table></div>
  <div class="more"><button class="btn" id="moreb" type="button">Show more</button><span id="count"></span></div>
  <p class="fine" id="tfine"></p>
 </section>
 <section id="bills">
  <p class="sk">What it costs, all in</p>
  <h2>Expect more than one bill</h2>
  <p class="lede">The table above is one bill: the place's. A colonoscopy usually brings three or four, often from different companies. <span id="billnet"></span></p>
  <div class="slips" id="slips"></div>
  <p class="sk" style="margin-top:8px">When this colonoscopy costs more</p>
  <div class="when">
   <div><span class="tag">It started as a screening</span><h3>Screening or diagnostic changes who pays</h3><p>Most plans cover a routine screening colonoscopy at no cost to you under the Affordable Care Act. If it's done to check symptoms, or as a follow-up, it's billed as diagnostic (this code), and you pay toward your deductible. Ask how it will be billed before you schedule.</p></div>
   <div><span class="tag">They find a polyp</span><h3>A different code, plus a lab bill</h3><p>Removing a polyp is billed under a different code (<a href="/price-finder/?code=45385">45385</a> by snare, <a href="/price-finder/?code=45380">45380</a> by biopsy), and the tissue goes to a lab: bill 4 arrives. On a screening, federal rules say removing a polyp shouldn't add cost-sharing on most private plans (<a href="https://www.dol.gov/sites/dolgov/files/EBSA/about-ebsa/our-activities/resource-center/faqs/aca-part-xii.pdf">ACA FAQs Part XII</a>).</p></div>
   <div><span class="tag">You're sedated</span><h3>Anesthesia is its own company</h3><p>Sedation is usually billed by a separate anesthesia group, by the minute. At an in-network hospital or surgery center, the No Surprises Act stops an out-of-network anesthesiologist from billing you more than your in-network share.</p></div>
  </div>
 </section>
</main>
<div class="tray" id="tray"><span id="trayn"></span><button class="btn y" id="cmpb" type="button">Compare side by side</button><button class="btn" id="clr" type="button" style="background:transparent;border:1px solid #fff">Clear</button></div>
<dialog id="dlg" aria-labelledby="dlgh"><div class="dh"><h3 id="dlgh">Side by side</h3><button type="button" id="dlgx">Close</button></div><div class="cmp" id="cmp"></div></dialog>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
const D=JSON.parse(document.getElementById('data').textContent);
const NETS=D.nets.map(s=>s.split('|')), PAR=new Set(D.parplan);
const $=s=>document.querySelector(s), esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>'$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const times=x=>(x<10?x.toFixed(1):Math.round(x))+'×';
const band=x=>x<=1.5?1:x<=3?2:x<=5?3:4;
const BANDS=[['t1','up to 1.5× Medicare'],['t2','1.5–3×'],['t3','3–5×'],['t4','over 5×']];
// insurers and their networks (default: the network listing the most places; ParPlan never the default)
const cnt={};D.places.forEach(p=>Object.keys(p.fees).forEach(n=>cnt[n]=(cnt[n]||0)+1));
const INS={};NETS.forEach(([ins,plan],i)=>{if(cnt[i])(INS[ins]=INS[ins]||[]).push(i)});
const ORDER=Object.keys(INS).sort((a,b)=>Math.max(...INS[b].map(i=>cnt[i]))-Math.max(...INS[a].map(i=>cnt[i])));
const colNet={};ORDER.forEach(ins=>{colNet[ins]=INS[ins].filter(i=>!PAR.has(i)).sort((a,b)=>cnt[b]-cnt[a])[0]??INS[ins][0]});
const FLAT={};Object.keys(cnt).forEach(n=>{const m={};let top=0;D.places.forEach(p=>{const f=p.fees[n];if(f){m[f[0]]=(m[f[0]]||0)+1;top=Math.max(top,m[f[0]])}});if(cnt[n]>=5&&top>=cnt[n]/2)FLAT[n]=[+Object.keys(m).find(k=>m[k]===top),top]});
const netLab=n=>{const [a,b]=NETS[n];return b.toLowerCase().startsWith(a.toLowerCase())?b:a+' '+b};
const S={pay:'all',q:'',k:'',ev:true,n:25,sel:new Set()};
// paying-with picker
const pay=$('#pay');
pay.innerHTML='<option value="all">All insurers (compare them)</option>'+ORDER.map(ins=>'<optgroup label="'+esc(ins)+'">'+INS[ins].map(i=>'<option value="'+i+'">'+esc(ins+' · '+NETS[i][1])+(PAR.has(i)?' (not a network you pick)':'')+'</option>').join('')+'</optgroup>').join('')+'<option value="cash">Paying cash (no insurance)</option>';
pay.onchange=()=>{S.pay=pay.value;S.n=25;draw()};
$('#q').oninput=e=>{S.q=e.target.value.toLowerCase();S.n=25;draw()};
document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.seg button').forEach(x=>x.setAttribute('aria-pressed',x===b));S.k=b.dataset.k;S.n=25;draw()});
$('#ev').onchange=e=>{S.ev=e.target.checked;S.n=25;draw()};
$('#moreb').onclick=()=>{S.n+=50;draw()};
const link=(f,txt,x)=>'<a class="v" href="'+esc(D.urls[f[2]])+'" title="'+esc((x?times(x)+' Medicare · ':'')+'file dated '+D.dates[f[1]]+' · opens the source file')+'" target="_blank" rel="noopener">'+txt+'</a>';
const medOf=p=>p.med;
function rows(){
  return D.places.filter(p=>(!S.ev||p.does)&&(!S.k||p.kind===S.k)&&(!S.q||(p.name+' '+p.city).toLowerCase().includes(S.q)));
}
function cellFee(p,n){
  const f=p.fees[n]; if(!f) return '<td><span class="none" title="No published rate in this network">—</span></td>';
  const x=f[0]/medOf(p); return '<td class="b'+band(x)+'">'+link(f,money(f[0]),x)+'<span class="x">'+times(x)+' Medicare</span></td>';
}
function placeCell(p){
  const on=S.sel.has(p.i);
  return '<td class="pl"><label><input type="checkbox" data-i="'+p.i+'"'+(on?' checked':'')+' aria-label="Compare '+esc(p.name)+'"><span><b>'+esc(p.name)+'</b><span class="m">'+esc(p.city)+' <span class="kind">'+(p.kind==='H'?'hospital':'surgery center')+'</span>'+(p.does?'':' · listed, may not offer this')+'</span></span></label></td>';
}
function medCell(p){return '<td class="med"><span class="v">'+money(p.med)+'</span><span class="x">'+(p.med_local?'this place':'national rate')+'</span></td>'}
function maCell(p){
  if(!p.ma) return '<td class="med"><span class="none" title="'+(p.kind==='H'?'Not in this hospital\'s price file':'Surgery centers don\'t have to post Medicare Advantage rates')+'">—</span></td>';
  return '<td class="med"><a class="v" style="color:var(--ink)" href="'+esc(p.ma.url)+'" target="_blank" rel="noopener" title="'+esc(p.ma.ins+' · '+p.ma.plan+' · file dated '+p.ma.date+', row '+p.ma.row)+'">'+money(p.ma.v)+'</a><span class="x">'+esc(p.ma.ins)+'</span></td>';
}
function cashCell(p){
  if(!p.cash) return '<td><span class="none">—</span></td>';
  const x=p.cash.v/p.med;return '<td class="b'+band(x)+'"><a class="v" href="'+esc(p.cash.url)+'" target="_blank" rel="noopener" title="'+esc(p.cash.what+(p.cash.date?' · '+p.cash.date:''))+'">'+money(p.cash.v)+'</a><span class="x">'+times(x)+' Medicare</span></td>';
}
function big3(list){
  const all=[];list.forEach(p=>{if(S.pay==='all')Object.entries(p.fees).forEach(([n,f])=>{if(!PAR.has(+n)&&!FLAT[n])all.push([f[0],p,+n])});else if(S.pay==='cash'){if(p.cash)all.push([p.cash.v,p,null])}else if(p.fees[S.pay])all.push([p.fees[S.pay][0],p,+S.pay])});
  if(!all.length){$('#big3').innerHTML='';return}
  all.sort((a,b)=>a[0]-b[0]);const lo=all[0],hi=all[all.length-1];
  const lab=e=>esc(e[1].name)+(e[2]!=null?' · '+esc(netLab(e[2])):'');
  $('#big3').innerHTML='<div class="tile"><p class="l">Lowest place fee'+(S.pay==='all'?', any network':'')+'</p><p class="v">'+money(lo[0])+'</p><p class="s">'+lab(lo)+'</p></div>'+
   '<div class="tile"><p class="l">Highest place fee</p><p class="v">'+money(hi[0])+'</p><p class="s">'+lab(hi)+' · '+times(hi[0]/lo[0])+' the lowest</p></div>'+
   '<div class="tile"><p class="l">Medicare, for comparison</p><p class="v" style="color:var(--ink)">'+money(D.medicare.asc)+' – '+money(D.medicare.opps)+'</p><p class="s">surgery center – hospital, national rate, 2026; doctor '+money(D.medicare.doc_fac)+' (Dallas)</p></div>';
}
function draw(){
  const list=rows();
  big3(list);
  $('#legend').innerHTML='<span>Each price is shaded by how many times Medicare\'s rate for that same place it is:</span>'+BANDS.map(b=>'<span><i class="sw" style="background:var(--'+b[0]+')"></i>'+b[1]+'</span>').join('');
  const t=$('#t');let h='';
  if(S.pay==='all'){const lo=p=>Math.min(...ORDER.map(ins=>p.fees[colNet[ins]]&&!FLAT[colNet[ins]]?p.fees[colNet[ins]][0]:1e12));list.sort((a,b)=>(!a.does-!b.does)||(lo(a)-lo(b)))}
  const shown=list.slice(0,S.n);
  if(S.pay==='all'){
    $('#th2').textContent='Every place, every insurer';
    $('#tlede').textContent='Each row is one place\'s own fee (the facility fee) in each insurer\'s network. The first row is the doctor\'s fee, which is a separate bill from whichever gastroenterologist does it. Pick a network at the top of a column, or choose your own under "Paying with" to see both bills together.';
    h='<thead><tr><th class="pl">Place<span class="x" style="font-weight:400">tick 2 or more to compare</span></th><th>Medicare<span class="x">traditional, 2026</span></th><th>Medicare Advantage<span class="x">hospital files</span></th><th>Cash<span class="x">no insurance</span></th>'+
      ORDER.map(ins=>'<th><span class="ins">'+esc(ins)+'</span>'+(INS[ins].length>1?'<select data-ins="'+esc(ins)+'" aria-label="'+esc(ins)+' network">'+INS[ins].map(i=>'<option value="'+i+'"'+(i===colNet[ins]?' selected':'')+'>'+esc(NETS[i][1])+'</option>').join('')+'</select>':'<span class="x">'+esc(NETS[INS[ins][0]][1])+'</span>')+(FLAT[colNet[ins]]?'<span class="x flat">same '+money(FLAT[colNet[ins]][0])+' at '+FLAT[colNet[ins]][1]+' of '+cnt[colNet[ins]]+' places</span>':'')+'</th>').join('')+'</tr></thead><tbody>';
    h+='<tr class="docrow"><td class="pl"><b>Doctor\'s fee</b><span class="m">separate bill · typical listed fee in DFW (range on hover)</span></td><td class="med"><span class="v" style="color:var(--ink)">'+money(D.medicare.doc_fac)+'</span><span class="x">Dallas</span></td><td class="med"><span class="none">—</span></td><td><span class="none">ask</span></td>'+
      ORDER.map(ins=>{const g=D.doc[colNet[ins]];return '<td>'+(g?'<span class="v" title="'+esc('Lowest '+money(g.lo)+' · middle '+money(g.mid)+' · highest '+money(g.hi)+' across '+g.n.toLocaleString()+' listed doctors and groups')+'">'+money(g.mid)+'</span><span class="x">'+money(g.lo)+'–'+money(g.hi)+'</span>':'<span class="none">—</span>')+'</td>'}).join('')+'</tr>';
    shown.forEach(p=>{h+='<tr'+(S.sel.has(p.i)?' class="sel"':'')+'>'+placeCell(p)+medCell(p)+maCell(p)+cashCell(p)+ORDER.map(ins=>cellFee(p,colNet[ins])).join('')+'</tr>'});
  } else if(S.pay==='cash'){
    $('#th2').textContent='Paying cash';
    $('#tlede').textContent='Cash prices a place posts on its website or lists in its hospital price file, next to Medicare\'s rate for the same place. Most surgery centers don\'t publish one: call and ask, and ask for a written Good Faith Estimate.';
    h='<thead><tr><th class="pl">Place</th><th>Cash price</th><th>Medicare</th><th class="barcell">Against Medicare</th></tr></thead><tbody>';
    shown.filter(p=>p.cash).sort((a,b)=>a.cash.v-b.cash.v).forEach(p=>{const x=p.cash.v/p.med;h+='<tr>'+placeCell(p)+cashCell(p)+medCell(p)+barCell(p.cash.v,p.med)+'</tr>'});
  } else {
    const n=+S.pay,g=D.doc[n];
    $('#th2').textContent=netLab(n);
    $('#tlede').textContent='Both bills in your network: the place\'s fee plus the doctor\'s. The doctor\'s figure is the middle fee this network lists across DFW gastroenterologists and groups (each one a real listed price); yours depends on who does it. Lowest total first.';
    h='<thead><tr><th class="pl">Place</th><th>Place\'s fee</th><th>+ Doctor\'s fee<span class="x">typical</span></th><th>= Both bills</th><th>Medicare, both<span class="x">this place + doctor</span></th><th class="barcell">Against Medicare</th></tr></thead><tbody>';
    shown.filter(p=>p.fees[n]).sort((a,b)=>a.fees[n][0]-b.fees[n][0]).forEach(p=>{const f=p.fees[n],tot=f[0]+(g?g.mid:0),mt=p.med+D.medicare.doc_fac,x=f[0]/p.med;
      h+='<tr>'+placeCell(p)+'<td class="b'+band(x)+'">'+link(f,money(f[0]),x)+'<span class="x">'+times(x)+' Medicare</span></td><td>'+(g?'<span class="v" title="'+esc('Lowest '+money(g.lo)+' · highest '+money(g.hi))+'">'+money(g.mid)+'</span><span class="x">'+money(g.lo)+'–'+money(g.hi)+'</span>':'<span class="none">—</span>')+'</td><td><span class="v" style="font-size:17px">'+money(tot)+'</span></td><td class="med"><span class="v">'+money(mt)+'</span></td>'+barCell(tot,mt)+'</tr>'});
  }
  t.innerHTML=h+'</tbody>';
  const total=S.pay==='all'?list.length:S.pay==='cash'?list.filter(p=>p.cash).length:list.filter(p=>p.fees[S.pay]).length;
  $('#count').textContent='Showing '+Math.min(S.n,total)+' of '+total+' places';
  $('#moreb').hidden=S.n>=total;
  $('#tfine').innerHTML='Medicare: CMS 2026 fee schedules (<a href="'+esc(D.medicare.src.opps[1])+'">hospital outpatient</a>, <a href="'+esc(D.medicare.src.asc[1])+'">surgery center</a>, <a href="'+esc(D.medicare.src.pfs[1])+'">doctors</a>), adjusted for each place\'s local wages where we matched it to its Medicare record. Medicare Advantage: the lowest Medicare Advantage line in the hospital\'s own price file; surgery centers don\'t have to post one. A yardstick, not a price you can get unless you\'re on Medicare. Percent-of-charges rates, rates flagged unusually low and filler-looking rates are left out, as on the price pages. Every price links to the file it came from.';
  t.querySelectorAll('select[data-ins]').forEach(s=>s.onchange=()=>{colNet[s.dataset.ins]=+s.value;draw()});
  t.querySelectorAll('input[data-i]').forEach(c=>c.onchange=()=>{const i=+c.dataset.i;c.checked?S.sel.add(i):S.sel.delete(i);c.closest('tr').classList.toggle('sel',c.checked);tray()});
  slips();
}
function barCell(v,m){const mx=Math.max(v,m)*1.05,w=v/mx*100,ml=m/mx*100;return '<td class="barcell"><span class="x">'+times(v/m)+' Medicare</span><div class="track" aria-hidden="true"><div class="fill" style="width:'+w+'%"></div><div class="mline" style="left:'+ml+'%" title="Medicare"></div></div></td>'}
function tray(){const n=S.sel.size;$('#tray').classList.toggle('on',n>0);$('#trayn').textContent=n+' place'+(n===1?'':'s')+' ticked'+(n<2?' · tick one more to compare':'');$('#cmpb').disabled=n<2}
$('#clr').onclick=()=>{S.sel.clear();tray();draw()};
$('#dlgx').onclick=()=>$('#dlg').close();
$('#cmpb').onclick=()=>{
  const ps=D.places.filter(p=>S.sel.has(p.i));
  const nets=[...new Set(ps.flatMap(p=>Object.keys(p.fees).map(Number)))].sort((a,b)=>NETS[a].join().localeCompare(NETS[b].join()));
  let h='<table><thead><tr><th>Network</th>'+ps.map(p=>'<th>'+esc(p.name)+'<span class="x">'+esc(p.city)+' · '+(p.kind==='H'?'hospital':'surgery center')+'</span></th>').join('')+'</tr></thead><tbody>';
  const row=(lab,vals,isMed)=>{const nums=vals.filter(v=>v!=null);const mn=Math.min(...nums);return '<tr><td>'+lab+'</td>'+vals.map(v=>'<td class="'+(v!=null&&v===mn&&nums.length>1&&!isMed?'win':'')+'">'+(v==null?'<span class="none">—</span>':'<span class="v"'+(isMed?' style="color:var(--ink)"':'')+'>'+money(v)+'</span>')+'</td>').join('')+'</tr>'};
  h+=row('<b>Medicare</b> (this place)',ps.map(p=>p.med),true)+row('<b>Medicare Advantage</b>',ps.map(p=>p.ma?p.ma.v:null),true)+row('<b>Cash</b>',ps.map(p=>p.cash?p.cash.v:null));
  nets.forEach(n=>{h+=row(esc(NETS[n].join(' · ')),ps.map(p=>p.fees[n]?p.fees[n][0]:null))});
  $('#cmp').innerHTML=h+'</tbody></table><p class="fine">The place\'s fee only. Green: the lowest of the places you picked, in that network. The doctor, anesthesia and any lab bill separately.</p>';
  $('#dlg').showModal();
};
function slips(){
  const n=S.pay!=='all'&&S.pay!=='cash'?+S.pay:null;
  const g=n!=null?D.doc[n]:null,b=n!=null?(D.bills[n]||{}):{};
  const fees=n!=null?D.places.filter(p=>p.does&&p.fees[n]).map(p=>p.fees[n][0]).sort((a,c)=>a-c):[];
  $('#billnet').textContent=n!=null?'Amounts below are '+NETS[n].join(' · ')+'\'s published lowest to highest in DFW.':'Pick your network under "Paying with" to see your network\'s amounts on each slip.';
  const rng=(a)=>a&&a[0]!=null?money(a[0])+'–'+money(a[1]):'ask';
  const sl=(i,t,dsc,amt,src,maybe)=>'<div class="slip'+(maybe?' maybe':'')+'"><p class="n">BILL '+i+' OF 4</p><p class="t">'+t+'</p><p class="d">'+dsc+'</p><p class="amt"><span>'+(n!=null?'RANGE':'PRICE')+'</span><b>'+amt+'</b></p><p class="src">'+src+'</p></div>';
  $('#slips').innerHTML=
    sl(1,'The place','facility fee: room, staff, equipment',fees.length?money(fees[0])+'–'+money(fees[fees.length-1]):'see table','The table above, per place.')+
    sl(2,'The doctor','the gastroenterologist who does it',g?money(g.lo)+'–'+money(g.hi):'by network','Typical (middle listed fee): '+(g?money(g.mid):'pick a network')+'. Medicare: '+money(D.medicare.doc_fac)+'.')+
    sl(3,'Anesthesia','often a separate company, billed by time',n!=null?rng(b.anes):'by network','<a href="/price-finder/?code=00811">Look up anesthesia prices →</a>')+
    sl(4,'Lab work, maybe','only if tissue goes to a pathologist',n!=null?rng(b.path):'by network','<a href="/price-finder/?code=88305">Look up pathology prices →</a>',true);
}
draw();
})();
</script>
</body>
</html>'''

page = PAGE.replace('__DATA__', json.dumps(d, separators=(',', ':')).replace('</', '<\\/'))
import os
os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
open(OUT, 'w', encoding='utf-8').write(page)
print('wrote', OUT, len(page))
