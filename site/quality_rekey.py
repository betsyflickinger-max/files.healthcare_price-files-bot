"""DFW Price Finder quality ratings, keyed by NPI so a new build can never show a rating on the wrong provider.

Why: pf/q/quality.txt matches ratings to providers by their POSITION in the page's provider list (D.fac). The monthly
refresh rebuilds D.fac (new providers, new order) but kept the old quality.txt, so from the Oct 12 build every hospital,
surgery-center and clinician rating pointed at a different provider (found Oct 18, 2026; ratings hidden the same day).

Fix: the ratings are stored once by NPI / CCN in R2 reference/site/quality_dfw_by_npi.json, and quality.txt is rendered for
the page's current provider order (site/every/<build>/npis.json, same order as D.fac) every time the page is published.

  python site/quality_rekey.py source SITE_DIR      build the NPI-keyed source from SITE_DIR's quality.txt + public matches, save to R2
  python site/quality_rekey.py render NPIS_JSON PAGE_HTML OUT_TXT   write quality.txt for that page (orchestrate.py publish)

How providers are matched to Medicare facilities (CCN), public records only:
  hospitals, long-term care and rehab hospitals: hospital_profiles.build() - NPPES organization NPIs at the facility's CMS
    address (same ZIP and street number, hospital taxonomy) plus the NPIs the hospital's own price file lists (type_2_npi)
  surgery centers: site/med_local.py (R2 site/med_local/2026.json) - NPPES practice address = CMS Provider of Services address
  clinicians: the CMS Doctors and Clinicians record already carries its NPI
An NPI that matches more than one facility gets no rating.
"""
import base64
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(ROOT / "site"))
KEY = "reference/site/quality_dfw_by_npi.json"
BY_POS = ("h", "pm", "a", "d")


def dec(b):
    return json.loads(gzip.decompress(base64.b64decode(b.strip())))


def enc(Q):
    return base64.b64encode(gzip.compress(json.dumps(Q, separators=(",", ":")).encode(), 6)).decode()


def source(site_dir):
    import store
    import hospital_profiles as hp
    s3, B = store.r2()
    site = Path(site_dir) / "site"
    Q = dec((site / "price-finder/pf/q/quality.txt").read_text())
    # ratings themselves (self-describing, no positions): surgery centers by CCN, clinicians by NPI
    try:
        old = json.loads(s3.get_object(Bucket=B, Key=KEY)["Body"].read())
    except Exception:
        old = {}
    asc = dict(old.get("asc", {}))
    for r in Q.get("a", {}).values():
        asc.setdefault(r["ccn"], r)
    docs = dict(old.get("docs", {}))
    for r in Q.get("d", {}).values():
        docs.setdefault(r["n"], r)
    if not asc or not docs:
        sys.exit("STOP: no surgery-center or clinician ratings to keep (quality.txt already emptied and no saved source)")
    # NPI -> CCN matches
    cand = defaultdict(set)
    L = hp.load(site, Path(site_dir) / ".hosp_cache")
    for h in hp.build(L).values():
        for n in h["npi_all"]:
            cand[n].add(h["ccn"])
    M = json.loads(s3.get_object(Bucket=B, Key="site/med_local/2026.json")["Body"].read())
    for n, (kind, _wi, ccn, _cbsa) in M["npi"].items():
        if kind == "A":
            cand[n].add(ccn)
    npi_ccn = {n: next(iter(c)) for n, c in cand.items() if len(c) == 1}
    base = {k: v for k, v in Q.items() if k not in BY_POS}
    S = dict(base=base, asc=asc, docs=docs, npi_ccn=npi_ccn,
             note="Ratings by CCN/NPI; quality_rekey.py render places them for a page's provider order.")
    s3.put_object(Bucket=B, Key=KEY, Body=json.dumps(S, separators=(",", ":")).encode(), ContentType="application/json")
    print(f"saved {KEY}: {len(npi_ccn)} NPI->CCN matches ({sum(len(c) > 1 for c in cand.values())} ambiguous dropped), "
          f"{len(asc)} surgery centers, {len(docs)} clinicians")
    return S


def render(S, npis, fac):
    """quality dict for a page whose providers are fac (D.fac) with NPIs npis (same order)."""
    assert len(npis) == len(fac), "npis.json is not aligned with the page's provider list"
    Q = dict(S["base"])
    H, PR = Q.get("H", {}), Q.get("PR", {})
    h, pm, a, d = {}, {}, {}, {}
    for i, n in enumerate(npis):
        kind = fac[i][2]
        ccn = S["npi_ccn"].get(str(n))
        if kind == "H" and ccn:
            if ccn in H:
                h[str(i)] = ccn
            elif ccn in PR:
                pm[str(i)] = ccn
        elif kind in ("A", "G") and ccn and ccn in S["asc"]:
            a[str(i)] = S["asc"][ccn]
        elif kind == "P" and str(n) in S["docs"]:
            d[str(i)] = S["docs"][str(n)]
    Q.update(h=h, pm=pm, a=a, d=d)
    return Q


def page_fac(page_html):
    s = Path(page_html).read_text(encoding="utf-8")
    i = s.index('id="data"')
    return json.loads(s[s.index(">", i) + 1:s.index("</script>", i)])["fac"]


def render_files(npis_json, page_html, out_txt):
    """Never leaves positional ratings from another build: without the source or NPIs, provider ratings are left empty."""
    import store
    s3, B = store.r2()
    fac = page_fac(page_html)
    try:
        S = json.loads(s3.get_object(Bucket=B, Key=KEY)["Body"].read())
        npis = json.load(open(npis_json))
        Q = render(S, npis, fac)
    except Exception as e:
        print("quality ratings left empty for this build:", e)
        Q = dec(Path(out_txt).read_text()) if Path(out_txt).exists() else {}
        Q.update({k: {} for k in BY_POS})
    Path(out_txt).write_text(enc(Q))
    print(f"quality.txt: {len(Q['h'])} hospitals, {len(Q['pm'])} rehab/long-term care, {len(Q['a'])} surgery centers, {len(Q['d'])} clinicians")


if __name__ == "__main__":
    if sys.argv[1] == "source":
        source(sys.argv[2])
    elif sys.argv[1] == "render":
        render_files(*sys.argv[2:5])
