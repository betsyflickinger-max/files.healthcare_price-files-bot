"""Put No Surprises Act arbitration figures into a Price Finder page (DFW, Texas cities) and the site nav.

  page_arb(arb_all, slug, npis, codes)  -> the page's D.arb, or None when the page's area isn't a Texas metro
  patch_page(html, arb)                 -> html with the arbitration code and data (idempotent; arb None removes the data)
  remap(D, npis)                        -> after a monthly rebuild changes the provider list, re-key D.arb.p by position
  add_nav(html)                         -> adds "Surprise Bills" to the site nav (idempotent)

D.arb = {name, region, q: [first, last quarter], src, c: {code: [lines, lines with $, QPA, award, provider offer,
plan offer, provider's offer chosen, place of service]}, p: {provider position: [lines, disputes, chosen]},
np: {npi: [...]}}. The page code never names a city (city_page.py stops on DFW wording outside the data);
the area name comes from the data.
"""
import json
import re

REGION = {  # page slug -> CMS "Geographical Region" (the metro area the plan reported)
    "dfw": "Dallas-Fort Worth-Arlington, TX", "houston": "Houston-The Woodlands-Sugar Land, TX",
    "austin": "Austin-Round Rock-Georgetown, TX", "san-antonio": "San Antonio-New Braunfels, TX", "el-paso": "El Paso, TX",
    "mcallen": "McAllen-Edinburg-Mission, TX", "killeen-temple": "Killeen-Temple, TX",
    "brownsville-harlingen": "Brownsville-Harlingen, TX", "corpus-christi": "Corpus Christi, TX",
    "beaumont-port-arthur": "Beaumont-Port Arthur, TX", "lubbock": "Lubbock, TX", "waco": "Waco, TX", "longview": "Longview, TX",
    "college-station-bryan": "College Station-Bryan, TX", "amarillo": "Amarillo, TX", "tyler": "Tyler, TX",
    "abilene": "Abilene, TX", "midland": "Midland, TX", "odessa": "Odessa, TX", "wichita-falls": "Wichita Falls, TX",
    "texarkana": "Texarkana, TX-AR", "san-angelo": "San Angelo, TX", "victoria": "Victoria, TX"}
CMS = "https://www.cms.gov/nosurprises/policies-and-resources/Reports"
TAG = '<script type="application/json" id="data">'

JS = r"""/*arb*/
const ARB = D.arb || null;
const qtr = q => String(q).replace(/^(\d{4})-q(\d)$/, 'Q$2 $1');
const arbPer = () => `${qtr(ARB.q[0])} to ${qtr(ARB.q[1])}`;
function arbBlock(code) {
  const a = ARB && ARB.c && ARB.c[code]; if (!a) return '';
  const [n, d, qpa, award, prov, plan, won] = a;
  const head = '<h4>When a surprise bill for this goes to federal arbitration</h4>';
  const sub = `<p class="sub">Out-of-network bills for this code in the ${esc(ARB.name)} area that went to federal arbitration under the No Surprises Act, decided ${arbPer()}: ${n.toLocaleString()} disputed line${n > 1 ? 's' : ''}. The arbitrator picks the plan's offer or the provider's; it picked the provider's on ${won.toLocaleString()}. Not a price you pay: for emergency care and surprise bills, the law limits your share to your in-network cost-sharing. <a href="/surprise-bills/">How arbitration works</a></p>`;
  if (!d || qpa == null) return head + sub + '<p class="sub">CMS withholds the dollar amounts when a code has fewer than 10 disputed lines in an area.</p>';
  const lk = `<a class="src" href="${esc(ARB.src)}" target="_blank" rel="noopener" title="CMS Federal IDR public use files">CMS ↗</a>`;
  const L = [["Plan's offer", 'what the plan offered to pay', plan],
             ['Qualifying payment amount (QPA)', "the plan's median in-network rate (2019 rates plus inflation), as the plan reported it", qpa],
             ["Provider's offer", 'what the provider asked for', prov],
             ["Arbitrator's award", 'the offer the arbitrator picked', award]];
  return head + sub + L.filter(x => x[2] != null).map(([t, m, v]) => `<div class="pline"><div class="who"><b>${t}</b><div class="meta">${m} · middle of ${d.toLocaleString()} lines with dollar amounts</div></div><span class="lead"></span><div class="right"><span class="price">${money(v)}</span><div>${lk}</div></div></div>`).join('');
}
function arbProv(fi) {
  const p = ARB && ARB.p && ARB.p[fi]; if (!p) return '';
  const [lines, disp, won] = p;
  return `<div class="doc">Federal surprise-bill arbitration in Texas, ${arbPer()}: ${disp.toLocaleString()} dispute${disp > 1 ? 's' : ''} (${lines.toLocaleString()} line${lines > 1 ? 's' : ''}); the arbitrator picked this provider's offer on ${won.toLocaleString()}. <a href="/surprise-bills/#providers">About this</a></div>`;
}
/*/arb*/
"""

CALLS = [  # (exact text in the page, replacement); each must match once or the patch stops
    ("const SHOP = new Set(D.shop || []);", None),   # anchor: JS goes right before it
    ("    ${medBlock(code)}\n    ${strip(pts)}", "    ${medBlock(code)}\n    ${arbBlock(code)}\n    ${strip(pts)}"),
    ("$('#board').innerHTML = medBlock(S.code) + cashBlock(S.code, '') +", "$('#board').innerHTML = medBlock(S.code) + arbBlock(S.code) + cashBlock(S.code, '') +"),
    ("${other}${qualFor(f.fi, f.kind)}</div>", "${other}${qualFor(f.fi, f.kind)}${arbProv(f.fi)}</div>"),
    ("({...fac(+fi), rs: rs.filter(", "({...fac(+fi), fi: +fi, rs: rs.filter("),
    ("<div class=\"place\">${esc(f.city)} · ${f.kind === 'A' ? 'Surgery center' : 'Hospital or other facility'}</div></div>",
     "<div class=\"place\">${esc(f.city)} · ${f.kind === 'A' ? 'Surgery center' : 'Hospital or other facility'}</div>${arbProv(f.fi)}</div>"),
]


def split(s):
    a = s.index(TAG) + len(TAG)
    b = s.index("</script>", a)
    return s[:a], json.loads(s[a:b]), s[b:]


def join(pre, D, post):
    return pre + json.dumps(D, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/") + post


def page_arb(arb_all, slug, npis, codes=None):
    reg = REGION.get(slug)
    if not reg or reg not in arb_all["regions"]:
        return None
    c = arb_all["regions"][reg]
    if codes is not None:
        c = {k: v for k, v in c.items() if k in codes}
    P = arb_all["providers"]
    np_ = {n: P[n][:3] for n in (npis or []) if n in P}
    q = arb_all["src"]["quarters"]
    return dict(name=re.sub(r", TX(-\w+)?$", "", reg), region=reg, q=[q[0], q[-1]], src=CMS, c=c,
                p={str(i): np_[n] for i, n in enumerate(npis or []) if n in np_}, np=np_)


def remap(D, npis):
    """After merge_page.py replaces the provider list: re-key provider figures by the new positions, or drop them."""
    a = D.get("arb")
    if not a:
        return
    if npis is None:
        a.pop("p", None)
        return
    a["p"] = {str(i): a["np"][n] for i, n in enumerate(npis) if n in a.get("np", {})}


def patch_page(html, arb):
    pre, D, post = split(html)
    if "/*arb*/" in post:
        post = re.sub(r"/\*arb\*/.*?/\*/arb\*/\n", lambda m: JS, post, flags=re.S)
    else:
        for old, new in CALLS:
            if post.count(old) != 1:
                raise SystemExit(f"STOP: Price Finder code changed; expected once: {old[:80]!r} (found {post.count(old)})")
            post = post.replace(old, JS + old) if new is None else post.replace(old, new)
    if arb:
        D["arb"] = arb
    else:
        D.pop("arb", None)
    return add_nav(join(pre, D, post))


NAV_OLD = '<a href="/price-file-watch/"'
NAV_ADD = '<a href="/surprise-bills/">Surprise Bills</a>'


def add_nav(html):
    """Adds the Surprise Bills link after Price File Watch in the site's nav bars (the three nav styles the site uses).
    Pages without one are left alone; running it twice changes nothing."""
    out, pos = [], 0
    for m in re.finditer(r'<(span|nav)[^>]*class="(sn-links|toplinks|nav)"[^>]*>', html):
        end = html.find("</" + m.group(1) + ">", m.end())
        block = html[m.end():end]
        if end < 0 or "/surprise-bills/" in block or NAV_OLD not in block:
            continue
        j = m.end() + block.index(NAV_OLD)
        k = html.index("</a>", j) + 4
        out.append(html[pos:k] + NAV_ADD); pos = k
    return "".join(out) + html[pos:]
