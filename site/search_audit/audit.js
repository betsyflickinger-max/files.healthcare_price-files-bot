// Search audit (Nov 7, 2026): does the Price Finder search find each care item's codes by the names people type?
// Old search (before Nov 7) vs the live pf-table.js. Usage: pull the site (python site/site_files.py pull w), serve w/site on
// localhost:8765 (python -m http.server 8765), write tests.json with site/search_audit/make_tests.py, then node site/search_audit/audit.js.
// Nov 7 result: old search missed the right code for 63 of 111 care items (24 on their own plain name); new: 0 missed.
const {chromium}=require('playwright');const fs=require('fs');
const SP=process.env.AUDIT_DIR||'./';
const tests=JSON.parse(fs.readFileSync(SP+'tests.json'));
(async()=>{const b=await chromium.launch();const p=await b.newPage();
await p.goto('http://localhost:8765/price-finder/',{waitUntil:'domcontentloaded'});await p.waitForTimeout(2500);
const res=await p.evaluate((tests)=>{
 // OLD search, copied from the version live before Nov 7 (pf-table.js "search: any word order")
 var SYN={mri:'magnetic resonance',ct:'computed tomography',cat:'computed tomography','x-ray':'xray',xray:'x-ray',ultrasound:'sonogram',echo:'echocardiogram',egd:'upper endoscopy',mammogram:'mammography',mammo:'mammography','c-section':'cesarean',csection:'cesarean',physical:'preventive',checkup:'preventive',bloodwork:'blood',scope:'endoscopy',replacement:'arthroplasty',shot:'injection',stitches:'repair'};
 var toks=t=>String(t).toLowerCase().replace(/[^a-z0-9 -]+/g,' ').split(/ +/).filter(Boolean);
 var hasW=(n,w)=>{var w2=w.replace(/s$/,'');return n.indexOf(w)>=0||n.indexOf(w2)>=0||(SYN[w]&&n.indexOf(SYN[w])>=0)};
 var codes=Object.keys(D.codes);
 function oldSearch(qq){var tw=toks(qq);var exact=codes.filter(c=>c.toLowerCase()===qq.trim().toLowerCase());
  var all=codes.filter(c=>{var n=(D.codes[c].name||'').toLowerCase();return tw.length&&tw.every(w=>hasW(n,w))});
  var near=all.length?[]:codes.map(c=>{var n=(D.codes[c].name||'').toLowerCase();return [c,tw.filter(w=>w.length>2&&hasW(n,w)).length]}).filter(x=>x[1]).sort((a,b)=>b[1]-a[1]).map(x=>x[0]);
  return {list:exact.concat(all.filter(c=>exact.indexOf(c)<0),near).slice(0,60),exactMatch:all.length+exact.length>0}}
 function newSearch(q){var pr=document.getElementById('proc');pr.value=q;pr.dispatchEvent(new Event('change',{bubbles:true}));
  var bx=document.querySelector('.ux-hits');return bx?[...bx.querySelectorAll('button[data-c]')].map(x=>x.dataset.c):['OPENED:'+S.code]}
 return tests.map(([iid,name,q,exp])=>{const inData=exp.filter(c=>D.codes[c]);const o=oldSearch(q),n=newSearch(q);
  const rank=(l)=>{let r=l.findIndex(c=>inData.includes(c));return r<0?null:r+1};
  return {iid,name,q,inData:inData.length,oldRank:rank(o.list),oldExact:o.exactMatch,oldTop:o.list.slice(0,3).map(c=>D.codes[c].name),newRank:rank(n)}});
},tests);
fs.writeFileSync(SP+'audit.json',JSON.stringify(res));await b.close()})();
