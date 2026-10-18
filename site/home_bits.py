# shared homepage-hero pieces (Oct 18): search box over the common procedures, quiet trust line
HOME_CSS2 = """.nat-q{position:relative;flex:1 1 320px;min-width:0}.nat-q input{width:100%;box-sizing:border-box;min-height:52px;border:0;padding:14px 12px;font-size:18px;background:var(--paper);color:var(--ink)}
.nat-q ul{position:absolute;left:0;right:0;top:100%;z-index:30;margin:2px 0 0;padding:0;list-style:none;background:var(--paper);color:var(--ink);border:2px solid var(--ink);box-shadow:0 10px 0 -2px rgba(0,0,0,.25)}
.nat-q li{padding:12px 14px;font-size:17px;cursor:pointer;border-top:1px solid rgba(0,0,0,.08)}.nat-q li:first-child{border-top:0}.nat-q li[aria-selected=true],.nat-q li:hover{background:var(--ground)}
.nat-q li.all{border-top:2px solid var(--ink);padding:0}.nat-q li.all a{display:block;padding:12px 14px;font-weight:700;color:var(--stamp);text-decoration:none}
.nat-foot{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px 24px;max-width:1040px;margin-top:8px;padding-top:16px;border-top:1px solid rgba(255,255,255,.25)}
.nat-foot .nat-trust{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0;font:500 15px/1.4 var(--body);color:var(--board-sub);letter-spacing:0}.nat-foot .nat-trust span::before{content:"\\2713";color:var(--hi);font-weight:800;margin-right:7px}
.nat-foot .nat-new{margin:0;font:700 16px var(--body);color:var(--board-ink);text-underline-offset:4px;white-space:nowrap}
"""
HOME_JS = """<script>(function(){var f=document.getElementById('natForm');if(!f)return;var q=document.getElementById('natQ'),L=document.getElementById('natList'),S=document.getElementById('natProc');
var O=[].map.call(S.options,function(o){return {v:o.value,t:o.textContent}}),items=[],act=-1;
function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function close(){L.hidden=true;q.setAttribute('aria-expanded','false');q.removeAttribute('aria-activedescendant')}
function show(){var raw=q.value.trim(),t=raw.toLowerCase();if(!t){close();return}
items=O.filter(function(o){return o.t.toLowerCase().indexOf(t)>=0}).slice(0,6);
L.innerHTML=items.map(function(o,i){var k=o.t.toLowerCase().indexOf(t);return '<li role="option" id="nq'+i+'" data-i="'+i+'" aria-selected="false">'+esc(o.t.slice(0,k))+'<b>'+esc(o.t.slice(k,k+t.length))+'</b>'+esc(o.t.slice(k+t.length))+'</li>'}).join('')
+'<li class="all"><a href="/price-finder/?q='+encodeURIComponent(raw)+'">Search all __EVERY__ billing codes for \\u201c'+esc(raw)+'\\u201d \\u2192</a></li>';
L.hidden=false;q.setAttribute('aria-expanded','true');act=-1}
function pick(i){var o=items[i];if(!o)return;S.value=o.v;q.value=o.t;close()}
q.addEventListener('input',show);q.addEventListener('focus',function(){q.select()});q.addEventListener('blur',function(){setTimeout(close,150)});
q.addEventListener('keydown',function(e){if(L.hidden)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();act=Math.max(0,Math.min(items.length-1,act+(e.key==='ArrowDown'?1:-1)));[].forEach.call(L.querySelectorAll('li[data-i]'),function(c,j){c.setAttribute('aria-selected',String(j===act))});q.setAttribute('aria-activedescendant','nq'+act)}else if(e.key==='Enter'&&act>=0){e.preventDefault();pick(act)}else if(e.key==='Escape'){close()}});
L.addEventListener('mousedown',function(e){var li=e.target.closest('li[data-i]');if(li){e.preventDefault();pick(+li.dataset.i)}});
f.addEventListener('submit',function(e){e.preventDefault();var raw=q.value.trim(),hit=O.filter(function(o){return o.t.toLowerCase()===raw.toLowerCase()})[0];
if(raw&&!hit){location.href='/price-finder/?q='+encodeURIComponent(raw);return}if(hit)S.value=hit.v;
location.href='/costs/'+document.getElementById('natArea').value+'/'+S.value+'/'})})();</script>"""
LEDE = '<p style="font-size:21px;color:var(--board-sub);max-width:44em">Hospitals and insurers have to publish their prices. They buried them in files too big to open. <b style="color:var(--board-ink)">We opened them.</b></p>'
def qbox(opts, every):
    return ('<div class="nat-q"><input id="natQ" type="search" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="natList" '
            f'placeholder="Search {every} procedures, tests and services" value="Colonoscopy (diagnostic)"><ul id="natList" role="listbox" aria-label="Matching procedures" hidden></ul>'
            f'<select id="natProc" aria-hidden="true" tabindex="-1" hidden>{opts}</select></div>')
def foot(every):
    return (f'<div class="nat-foot"><p class="nat-trust"><span>Free</span><span>No ads</span><span>{every} billing codes</span><span>Every price linked to its source</span></p>'
            '<a class="nat-new" href="/start-here/">New here? How it works <span aria-hidden="true">→</span></a></div>')
