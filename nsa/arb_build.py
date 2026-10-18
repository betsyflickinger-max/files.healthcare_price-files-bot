"""Site data from the No Surprises Act arbitration tables (nsa/idr_files.py output).

Uses the latest four quarters CMS has published. Every figure is a count, or an actual value from CMS's rows
taken at a rank (the "middle" is the value at the middle position when sorted; for an even count, the lower of the
two middle values). Nothing is averaged or estimated.

Writes to R2 data/idr/site/ (or ./local/ with --local):
  arb_tx.json    Price Finder data, for every Texas metro area in CMS's "Geographical Region" (MSA):
                 per service code: lines, lines with dollar amounts, middle QPA / plan offer / provider offer / award,
                 lines where the provider's offer was chosen; plus Texas providers by NPI (lines, disputes, won).
  texas.json     the Surprise Bills page: Texas vs national by quarter, who files, which insurers and plans,
                 most disputed services, the Dallas-Fort Worth price board (with published in-network doctor's fees
                 and Medicare for the same codes)
  plans.json     every Texas health plan / issuer name in the period, for the employer search

Run: python nsa/arb_build.py [--local] [--work DIR]
"""
import argparse
import base64
import collections
import gzip
import io
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))
DFW = "Dallas-Fort Worth-Arlington, TX"
PAGE = "https://www.cms.gov/nosurprises/policies-and-resources/Reports"
STANDARD = {"derived", "billed under another tax ID", "outpatient", "inpatient", "fee schedule"}  # rate labels that aren't a partial service


def mid(vals):
    v = sorted(x for x in vals if x is not None)
    return v[(len(v) - 1) // 2] if v else None


class Store:
    def __init__(self, local, work, dry=False):
        self.local, self.work, self.dry = local, Path(work), dry
        if not local:
            import store
            self.s3, self.bucket = store.r2()

    def get(self, key):
        if self.local:
            p = ROOT / "local" / key
            return p.read_bytes() if p.exists() else None
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            return None

    def fetch(self, key):
        p = self.work / key
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            b = self.get(key)
            if b is None:
                return None
            p.write_bytes(b)
        return p

    def put(self, key, data):
        if self.local or self.dry:
            p = ROOT / "local" / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        else:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="application/json")
        print(f"  wrote {key} ({len(data) / 1e3:,.0f} KB)")

    def list(self, prefix):
        if self.local:
            return sorted(str(p.relative_to(ROOT / "local")) for p in (ROOT / "local" / prefix).glob("*.parquet"))
        out = []
        for pg in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            out += [o["Key"] for o in pg.get("Contents", [])]
        return sorted(out)


NPI_KEY = "data/scope/tx_npis_all.parquet"   # Texas rows of the CMS NPPES file (see its .source.txt)
KINDS = [("261QE0002X", "fser", "emergency care centers (freestanding ERs)"), ("282", "hosp", "hospitals"), ("283", "hosp", "hospitals"),
         ("284", "hosp", "hospitals"), ("273", "hosp", "hospitals"), ("286", "hosp", "hospitals"), ("207P", "erdoc", "emergency medicine groups"),
         ("2085", "rad", "radiology groups"), ("207U", "rad", "radiology groups"), ("261QR02", "rad", "radiology groups"), ("207L", "anes", "anesthesia groups"),
         ("3675", "anes", "anesthesia groups"), ("261QU0200X", "uc", "urgent care centers")]


def kind_sql():
    w = " ".join(f"when taxonomy_1 like '{pre}%' then '{k}'" for pre, k, _ in KINDS)
    return f"case when taxonomy_1 is null then 'unk' {w} else 'other' end"


def filer_kinds(con, npi_file, domains):
    """For each provider email domain: share of its Texas lines by the provider type the NPI registry lists (primary taxonomy).
    Also the freestanding ERs (registry type 'Clinic/Center, Emergency Care') with the most Texas lines."""
    con.execute(f"create or replace view nk as select npi, name, city, {kind_sql()} kind from read_parquet('{npi_file}')")
    out = {}
    for d in domains:
        rows = con.execute("""select coalesce(nk.kind,'unk'), count(*) from tx left join nk on nk.npi = tx.provider_facility_npi_number
                              where provider_email_domain = ? group by 1 order by 2 desc""", [d]).fetchall()
        out[d] = rows
    fser = con.execute("""select nk.name, nk.city, count(*), count(distinct dispute_number), mode(provider_email_domain)
                          from tx join nk on nk.npi = tx.provider_facility_npi_number where nk.kind = 'fser'
                          group by 1, 2 order by 3 desc limit 15""").fetchall()
    tot = con.execute("""select count(*), count(distinct nk.npi) from tx join nk on nk.npi = tx.provider_facility_npi_number
                         where nk.kind = 'fser'""").fetchone()
    return out, fser, list(tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read and write ./local/")
    ap.add_argument("--dry", action="store_true", help="read R2, write ./local/ (testing)")
    ap.add_argument("--work", default=os.environ.get("RUNNER_TEMP", "/tmp") + "/arb")
    a = ap.parse_args()
    st = Store(a.local, a.work, a.dry)
    keys = {t: st.list(f"data/idr/{t}/") for t in ("disputes", "qpa_offers")}
    periods = sorted({k.rsplit("/", 1)[-1][:-8] for k in keys["disputes"]})
    latest = periods[-4:]
    print("quarters:", ", ".join(periods), "| using", latest[0], "to", latest[-1])
    for t, ks in keys.items():
        for k in ks:
            st.fetch(k)
    W = st.work
    con = duckdb.connect()
    q = lambda s: con.execute(s).fetchall()
    files = lambda t, ps: "[" + ",".join(f"'{W}/data/idr/{t}/{p}.parquet'" for p in ps) + "]"
    con.execute(f"create view dl as select * from read_parquet({files('disputes', latest)}, union_by_name=true)")
    con.execute(f"create view ql as select * from read_parquet({files('qpa_offers', latest)}, union_by_name=true)")
    con.execute("create view tx as select * from dl where location_of_service = 'TX'")
    won = "offer_selected_from_provider_or_issuer like 'In Favor of Provider%'"
    src = dict(page=PAGE, quarters=latest, checked=date.today().isoformat(),
               files=[f"federal-idr-puf-{p}" for p in latest], tables="R2 data/idr/<table>/<quarter>.parquet")

    # ---------------------------------------------------------------- 1. Price Finder: per metro, per code
    qcols = {r[0] for r in q("describe ql")}
    nomod = "coalesce(service_code_modifier_s, 'N/R') in ('N/R', '', 'N/A')" if "service_code_modifier_s" in qcols else "true"
    rows = q(f"""select geographical_region, service_code, count(*) n, count(qpa_num) d,
                        list(qpa_num) filter (where qpa_num is not null), list(prevailing_offer_num) filter (where qpa_num is not null),
                        list(provider_facility_offer_num) filter (where qpa_num is not null), list(health_plan_issuer_offer_num) filter (where qpa_num is not null),
                        count(*) filter (where {won}), mode(place_of_service_code)
                 from ql where geographical_region like '%, TX' or geographical_region like '%, TX-%'
                 group by all""")
    regions = collections.defaultdict(dict)
    for reg, code, n, d, qs, aw, po, io_, w, pos in rows:
        # [lines, lines with $, middle QPA, middle award, middle provider offer, middle plan offer, provider's offer chosen, usual place of service]
        regions[reg][code] = [n, d, mid(qs or []), mid(aw or []), mid(po or []), mid(io_ or []), w, pos]
    prov = {}
    for npi, name, grp, spec, n, disp, w, codes in q(f"""
            select provider_facility_npi_number, mode(provider_facility_name), mode(provider_facility_group_name),
                   mode(practice_facility_specialty_or_type), count(*), count(distinct dispute_number), count(*) filter (where {won}),
                   list(service_code)
            from tx where regexp_full_match(provider_facility_npi_number, '[0-9]{{10}}') group by 1"""):
        top = [c for c, _ in collections.Counter(codes).most_common(3)]
        prov[npi] = [n, disp, w, name, grp if grp not in ("N/R", "NR", "") else "", spec, top]
    arb = dict(src=src, regions=regions, providers=prov)
    st.put("data/idr/site/arb_tx.json", json.dumps(arb, separators=(",", ":")).encode())
    print(f"  {len(regions)} Texas metro areas, {sum(len(v) for v in regions.values()):,} code rows, {len(prov):,} Texas providers")

    # ---------------------------------------------------------------- 2. Texas page
    T = dict(src=src)
    counts = {}
    for p in periods:
        f = f"'{W}/data/idr/disputes/{p}.parquet'"
        counts[p] = q(f"select count(*), count(*) filter (where location_of_service='TX') from read_parquet({f})")[0]
    T["trend"] = [[p, us, txn] for p, (us, txn) in counts.items()]
    us_n, tx_n = q("select count(*) from dl")[0][0], q("select count(*) from tx")[0][0]
    T["totals"] = dict(us_lines=us_n, tx_lines=tx_n, tx_disputes=q("select count(distinct dispute_number) from tx")[0][0],
                       tx_won=q(f"select count(*) from tx where {won}")[0][0],
                       tx_plan_won=q("select count(*) from tx where offer_selected_from_provider_or_issuer like 'In Favor of Plan%'")[0][0],
                       us_won=q(f"select count(*) from dl where {won}")[0][0],
                       states=q("select location_of_service, count(*) from dl group by 1 order by 2 desc limit 6"))
    T["plan_types"] = q(f"select health_plan_type, count(*), count(*) filter (where {won}) from tx group by 1 order by 2 desc")
    T["insurers"] = q(f"""select health_plan_issuer_email_domain, count(*), count(distinct dispute_number), count(*) filter (where {won}),
                                count(*) filter (where health_plan_type like 'Either partially or fully self-insured%'), mode(health_plan_issuer_name)
                         from tx group by 1 order by 2 desc limit 15""")
    T["filers"] = q(f"""select provider_email_domain, count(*), count(distinct dispute_number), count(*) filter (where {won}),
                              count(distinct provider_facility_npi_number), mode(practice_facility_specialty_or_type)
                       from tx group by 1 order by 2 desc limit 15""")
    npi_file = W / NPI_KEY
    if not npi_file.exists():
        npi_file.parent.mkdir(parents=True, exist_ok=True)
        b = st.get(NPI_KEY)
        if b: npi_file.write_bytes(b)
    if npi_file.exists():
        T["filer_kinds"], T["fser_top"], T["fser_total"] = filer_kinds(con, npi_file, [r[0] for r in T["filers"]])
        T["kind_labels"] = {k: lab for _, k, lab in KINDS}
        T["npi_src"] = (st.get(NPI_KEY + ".source.txt") or b"").decode().strip()
    T["groups"] = q(f"""select case when provider_facility_group_name in ('N/R','NR','') then provider_facility_name else provider_facility_group_name end g,
                              count(*), count(distinct dispute_number), count(*) filter (where {won}), mode(provider_email_domain), mode(practice_facility_specialty_or_type)
                       from tx group by 1 order by 2 desc limit 15""")
    T["services"] = q(f"""select service_code, mode(item_or_service_description), count(*), count(*) filter (where {won})
                         from tx group by 1 order by 3 desc limit 15""")
    T["specialties"] = q(f"select practice_facility_specialty_or_type, count(*) from tx group by 1 order by 2 desc limit 10")
    T["tx_regions"] = sorted(([r, sum(v[0] for v in c.values())] for r, c in regions.items()), key=lambda x: -x[1])[:12]

    # DFW board: most disputed codes in the DFW metro, with published in-network doctor's fees and Medicare (#1, #5)
    dfw = regions.get(DFW, {})
    top = sorted(((c, v) for c, v in dfw.items() if v[1] >= 50), key=lambda x: -x[1][1])[:20]
    cur = (st.get("site/every/CURRENT") or b"").decode().strip()
    page = st.fetch("site/deploy/price-finder.html")
    Dp = None
    if page:
        s = page.read_text(encoding="utf-8"); tag = '<script type="application/json" id="data">'
        i = s.index(tag) + len(tag); Dp = json.loads(s[i:s.index("</script>", i)])
    npis = json.loads(st.get(f"site/every/{cur}/npis.json") or b"[]") if cur else []
    arb_fi = {str(i) for i, n in enumerate(npis) if n in prov}   # Price Finder providers that went to arbitration in Texas
    T["arb_on_page"] = [len(arb_fi), sum(prov[npis[int(i)]][0] for i in arb_fi)]
    board = []
    for code, v in top:
        nm = (Dp or {}).get("codes", {}).get(code, {}).get("name") if Dp else None
        desc = q(f"select mode(item_or_service_description) from tx where service_code='{code}'")[0][0]
        doc = doc_arb = None
        if cur and Dp and code in Dp["codes"]:
            t = st.get(f"site/every/{cur}/t/{code}.txt")
            if t:
                f = json.loads(gzip.decompress(base64.b64decode(t.strip())))["f"]
                L = Dp["labs"]
                ok = lambda r: r[1] == 1 and r[2] == 0 and not (r[4] & 4) and r[3] > 0 and (r[10] < 0 or set(x.strip() for x in L[r[10]].split(",")) <= STANDARD)
                vals = [r[3] for rs in f.values() for r in rs if ok(r)]
                if vals:
                    doc = [mid(vals), len(vals), len({fi for fi, rs in f.items() if any(ok(r) for r in rs)})]
                av = [r[3] for fi, rs in f.items() if fi in arb_fi for r in rs if ok(r)]
                doc_arb = [mid(av), len(av), len({fi for fi, rs in f.items() if fi in arb_fi and any(ok(r) for r in rs)})] if av else None
        med = None
        m = (Dp or {}).get("med", {}).get("codes", {}).get(code, {}) if Dp else {}
        if m.get("lab") and not m.get("pfs"):
            med = m["lab"]
        if m.get("pfs"):
            med = m["pfs"]["dal"][1] if str(v[7]) in ("19", "21", "22", "23", "24") else m["pfs"]["dal"][0]
            if med is None:
                med = m["pfs"]["dal"][0] or m["pfs"]["dal"][1]
        board.append(dict(code=code, name=nm or desc, desc=desc, n=v[0], d=v[1], qpa=v[2], award=v[3], prov=v[4], plan=v[5],
                          won=v[6], pos=v[7], doc=doc, doc_arb=doc_arb, med=med))
    T["dfw_board"] = board
    T["dfw_lines"] = sum(v[0] for v in dfw.values())
    T["dfw_dollar_lines"] = sum(v[1] for v in dfw.values())
    T["price_finder_build"] = cur
    T["medicare_src"] = (Dp or {}).get("med", {}).get("src", {}).get("pfs") if Dp else None
    st.put("data/idr/site/texas.json", json.dumps(T, separators=(",", ":"), default=str).encode())

    # ---------------------------------------------------------------- 3. employer / plan search (Texas)
    plans = q(f"""select trim(health_plan_issuer_name) nm, mode(health_plan_issuer_email_domain), mode(health_plan_type), count(*),
                         count(distinct dispute_number), count(*) filter (where {won}), list(distinct location_of_service)
                  from tx where trim(health_plan_issuer_name) not in ('', 'N/R', 'NR', 'Unknown', 'N/A') group by 1 order by 4 desc""")
    st.put("data/idr/site/plans.json", json.dumps(dict(src=src, plans=[p[:6] for p in plans]), separators=(",", ":")).encode())
    print(f"  {len(plans):,} Texas plan / issuer names")


if __name__ == "__main__":
    main()
