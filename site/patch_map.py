"""Add the Map view to the Price Finder page (idempotent). Usage: python patch_map.py page.html
Adds: a "Map" button beside "For patients" / "Full price board", a <section id="mapv">, the map.js script tag,
setView/render hooks, and a notes paragraph. merge_page.py only replaces the data block, so this survives monthly refreshes."""
import sys
p = sys.argv[1]; h = open(p, encoding='utf-8').read()
if 'id="vMap"' in h:
    print('already patched'); sys.exit(0)
def sub(old, new):
    global h
    assert h.count(old) == 1, 'anchor not unique/found: ' + old[:80]
    h = h.replace(old, new)
sub('<button type="button" id="vBoard" aria-pressed="false">Full price board</button>',
    '<button type="button" id="vBoard" aria-pressed="false">Full price board</button>\n    <button type="button" id="vMap" aria-pressed="false">Map</button>')
sub('<section id="board" hidden></section>', '<section id="board" hidden></section>\n<section id="mapv" hidden></section>')
sub('<script type="application/json" id="data">', '<script src="/price-finder/map.js"></script>\n<script type="application/json" id="data">')
sub("""  $('#patient').hidden = v !== 'patient'; $('#board').hidden = v !== 'board'; $('#payWrap').hidden = v !== 'patient';""",
    """  $('#vMap').setAttribute('aria-pressed', v === 'map');
  $('#patient').hidden = v !== 'patient'; $('#board').hidden = v !== 'board'; $('#mapv').hidden = v !== 'map'; $('#payWrap').hidden = v === 'board';""")
sub("""$('#vBoard').addEventListener('click', () => setView('board'));""",
    """$('#vBoard').addEventListener('click', () => setView('board'));
$('#vMap').addEventListener('click', () => setView('map'));""")
sub("""    $('#patient').innerHTML = msg; $('#board').innerHTML = msg;""", """    $('#patient').innerHTML = msg; $('#board').innerHTML = msg; $('#mapv').innerHTML = msg;""")
sub("""  if (C.err) { $('#patient').innerHTML = $('#board').innerHTML = '<p class="empty">Could not load these rates. Refresh the page to try again.</p>'; return; }
  S.view === 'patient' ? renderPatient() : renderBoard();""",
    """  if (C.err) { $('#patient').innerHTML = $('#board').innerHTML = $('#mapv').innerHTML = '<p class="empty">Could not load these rates. Refresh the page to try again.</p>'; return; }
  S.view === 'patient' ? renderPatient() : S.view === 'map' && window.renderMap ? window.renderMap() : renderBoard();""")
sub("""  <p>Published prices are not quotes.""",
    """  <p><b>Map.</b> The map places each provider at the practice address it gives the federal NPI Registry, using the U.S. Census Bureau's geocoder, and each hospital price at the hospital named in its file. Places we couldn't place are still listed, marked "not on map". A ZIP code or location you enter is used only on the page to measure distance and is never saved or sent. <a href="/methodology/#map">How the map works</a>.</p>
  <p>Published prices are not quotes.""")
open(p, 'w', encoding='utf-8').write(h); print('patched', p)
