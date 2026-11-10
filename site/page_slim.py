"""Price Finder page slimming, step 1 (Nov 9, 2026, Betsy OK'd: one state first). Same page, same behavior, fewer bytes.

What a page's data block carried that it didn't need (measured with site/page_sizes.py, Nov 9):
  - "coming": names of codes not built yet (Kansas 1.4 MB). The page code never reads it; embed.json in storage keeps it
    for the builds (every_code.py, merge_build.py), so it is simply left off the page.
  - "scope": for each network, every code its file was read for, as a list of code strings (DFW 4.7 MB, Kansas 1.9 MB).
    The page uses it only to say "We have read this network's file for N procedures so far, and this is not one of them
    yet." So each network becomes [N, bits]: N = the list's full length (same number as before), bits = base64 of one bit
    per code on the page, in sorted code order (bit set = the network's file covers that code). A code that isn't on the
    page can't be picked, so the message is the same for every code a visitor can choose.

slim(html) returns the slimmed page; the page code gets two small helpers (scHas, scLen) that read both the old list
form and the new [N, bits] form. scope_sets(D) / scope_len(v) let Python readers (audit_rules.py, insurer_profiles.py)
read either form. Used by city_page.py for areas listed in SLIM_PAGES (comma-separated, or "all").

  python site/page_slim.py old.html new.html     # slim one saved page and check it says the same thing for every code
"""
import base64, json, os, sys

TAG = '<script type="application/json" id="data">'
OLD_JS = ("  const sc = D.scope[`${N.i}|${N.n}`];\n"
          "  return sc && !sc.includes(S.code) ? `We have read this network's file for ${sc.length} procedures so far")
NEW_JS = ("  const sc = D.scope[`${N.i}|${N.n}`];\n"
          "  return sc && !scHas(sc, S.code) ? `We have read this network's file for ${scLen(sc)} procedures so far")
HELPERS = """// Nov 9, 2026 (site/page_slim.py): a network's scope is a list of codes, or [count, base64 bits over the page's sorted codes]
let SC_I = null; const SC_B = {};
function scLen(sc) { return typeof sc[0] === 'number' ? sc[0] : sc.length; }
function scHas(sc, code) {
  if (typeof sc[0] !== 'number') return sc.includes(code);
  if (!SC_I) { SC_I = {}; Object.keys(D.codes).sort().forEach((c, i) => { SC_I[c] = i; }); }
  const i = SC_I[code]; if (i == null) return false;
  const b = SC_B[sc[1]] || (SC_B[sc[1]] = atob(sc[1]));
  return ((b.charCodeAt(i >> 3) || 0) >> (i & 7) & 1) === 1;
}
function scopeMsg(N) {"""


def split(s):
    a = s.index(TAG) + len(TAG); b = s.index('</script>', a)
    return s[:a], json.loads(s[a:b]), s[b:]


def join(pre, D, post):
    return pre + json.dumps(D, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/') + post


def bits(codes, have):
    b = bytearray((len(codes) + 7) // 8)
    for i, c in enumerate(codes):
        if c in have: b[i >> 3] |= 1 << (i & 7)
    return base64.b64encode(bytes(b)).decode()


def is_slim(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) and isinstance(v[1], str)


def scope_len(v):
    return v[0] if is_slim(v) else len(v or [])


def scope_sets(D):
    """{network: set of codes} for either form (slim form: only the page's own codes, which is all a reader can ask about)."""
    order = sorted(D.get('codes') or {})
    out = {}
    for k, v in (D.get('scope') or {}).items():
        if is_slim(v):
            b = base64.b64decode(v[1])
            out[k] = {c for i, c in enumerate(order) if i >> 3 < len(b) and b[i >> 3] >> (i & 7) & 1}
        else:
            out[k] = set(v)
    return out


def slim(html):
    pre, D, post = split(html)
    if pre.count(OLD_JS) + post.count(OLD_JS) != 1 or (pre + post).count('function scopeMsg(N) {') != 1:
        raise SystemExit('STOP: page slimming: the page code around scopeMsg changed; not slimmed (update site/page_slim.py)')
    pre, post = [x.replace(OLD_JS, NEW_JS).replace('function scopeMsg(N) {', HELPERS) for x in (pre, post)]
    D.pop('coming', None)
    order = sorted(D['codes'])
    D['scope'] = {k: (v if is_slim(v) else [len(v), bits(order, set(v))]) for k, v in (D.get('scope') or {}).items()}
    return join(pre, D, post)


def same(old, new):
    """Checks the slimmed page says the same thing as the old one: every code on it, every network."""
    _, A, _ = split(old)
    _, B, _ = split(new)
    assert set(A) - {'coming'} == set(B), 'data block keys differ'
    for k in A:
        if k not in ('coming', 'scope'):
            assert A[k] == B[k], f'{k} changed'
    sa, sb = scope_sets(A), scope_sets(B)
    for net, v in (A.get('scope') or {}).items():
        assert scope_len(v) == scope_len(B['scope'][net]), f'{net}: count changed'
        assert sa[net] & set(A['codes']) == sb[net], f'{net}: codes on the page differ'
    return True


def wanted(slug):
    v = os.environ.get('SLIM_PAGES', '').strip()
    return v == 'all' or slug in {x.strip() for x in v.split(',') if x.strip()}


if __name__ == '__main__':
    old = open(sys.argv[1], encoding='utf-8').read()
    new = slim(old)
    same(old, new)
    open(sys.argv[2], 'w', encoding='utf-8').write(new)
    print(f'{sys.argv[1]}: {len(old.encode()) / 2**20:.2f} MiB -> {len(new.encode()) / 2**20:.2f} MiB; same message for every code and network')
