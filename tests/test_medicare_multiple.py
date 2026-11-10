"""Private price as a multiple of Medicare (analysis/medicare_multiple/): made-up rows only, no storage, no downloads.
Run: python -m pytest tests/test_medicare_multiple.py"""
import csv
import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis" / "medicare_multiple"), str(ROOT / "insurers" / "pipeline")]
import cms  # noqa: E402
import rates  # noqa: E402
import summarize as summ  # noqa: E402

LOC = "04412-11"   # Dallas


def _csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_bench(d):
    d.mkdir(parents=True, exist_ok=True)
    _csv(d / "rbcs.csv", ["code", "rbcs_id", "cat", "cat_desc", "subcat", "subcat_desc", "family"],
         [["99213", "EO", "E", "Evaluation and Management", "EO", "Office", "Office visit"],
          ["70551", "IM", "I", "Imaging", "IM", "MRI", "MRI brain"], ["00790", "AN", "A", "Anesthesia", "AN", "Anesthesia", "Upper abdomen"]])
    _csv(d / "pfs.csv", ["code", "mod", "locality", "nonfacility", "facility", "status"],
         [["99213", "", LOC, 100.0, 60.0, "A"], ["70551", "", LOC, 200.0, "", "A"], ["70551", "26", LOC, 70.0, 70.0, "A"]])
    _csv(d / "zip.csv", ["zip5", "state", "locality", "rural"], [["75201", "TX", LOC, ""], ["79901", "TX", "04412-99", "R"]])
    _csv(d / "anes.csv", ["locality", "cf"], [[LOC, 20.44]])
    _csv(d / "opps.csv", ["code", "si", "apc", "rate", "wage_adj"], [["70551", "Q3", "5523", 250.0, "True"], ["36415", "N", "", 5.0, "False"]])
    _csv(d / "asc.csv", ["code", "pi", "rate", "wage_adj"], [["45378", "A2", 500.0, "True"]])
    _csv(d / "clfs.csv", ["code", "rate"], [["80053", 10.0]])
    _csv(d / "asp.csv", ["code", "rate", "unit"], [["J1100", 0.5, "1 MG"]])
    _csv(d / "dme.csv", ["code", "mod", "state", "nonrural", "rural"], [["E0601", "RR", "TX", 50.0, 90.0]])
    _csv(d / "amb.csv", ["code", "locality", "urban", "rural", "super_rural"], [["A0427", LOC, 700.0, 710.0, 800.0]])
    _csv(d / "drg.csv", ["drg", "weight", "title"], [["470", 2.0, "Hip or knee"]])
    _csv(d / "ipps.csv", ["ccn", "name", "wage_index", "op_per_weight", "cap_per_weight", "ucp_per_claim", "provider_type"],
         [["450021", "Hospital A", 1.0, 7000.0, 500.0, 1000.0, "0"]])
    _csv(d / "wi2026.csv", ["ccn", "wage_index"], [["450021", 1.0]])
    _csv(d / "hosp_zip.csv", ["ccn", "zip5", "state"], [["450021", "75201", "TX"]])
    _csv(d / "volumes.csv", ["state", "kind", "code", "place", "volume", "source"],
         [["TX", "professional", "99213", "O", 1000, "x"], ["TX", "outpatient", "70551", "", 100, "x"], ["TX", "inpatient", "470", "", 10, "x"]])
    # evidence of use: providers 1-4 and 7 billed Medicare for 99213; hospital 450021 billed some other DRG (not 470)
    _csv(d / "ev_prof.csv", ["npi", "code"], [[n, "99213"] for n in ("1", "2", "3", "4", "7")])
    _csv(d / "ev_out.csv", ["ccn", "apc"], [["450099", "5523"]])
    _csv(d / "ev_inp.csv", ["ccn", "drg"], [["450021", "999"]])
    (d / "sources.json").write_text(json.dumps({"pfs": {"what": "x", "year": "2026", "url": "u"}}))
    return d


def make_insurer(path, rows):
    cols = ["reporting_entity_name", "file_label", "billing_code_type", "billing_code", "npi", "tin", "negotiated_type",
            "negotiated_rate", "billing_class", "setting", "billing_code_modifier", "service_code", "negotiation_arrangement",
            "additional_information"]
    con = duckdb.connect()
    con.execute("create table t (" + ", ".join(f"{c} varchar" for c in cols) + ")")
    con.executemany(f"insert into t values ({', '.join('?' * len(cols))})", [[str(r.get(c, "")) for c in cols] for r in rows])
    con.execute(f"copy t to '{path}' (format parquet)")


def row(**k):
    base = dict(reporting_entity_name="Acme Health", file_label="Acme PPO", billing_code_type="CPT", billing_code="99213",
                npi="1", tin=None, negotiated_type="negotiated", negotiated_rate="100", billing_class="professional",
                setting="outpatient", billing_code_modifier="", service_code="11", negotiation_arrangement="ffs",
                additional_information="")
    base.update(k)
    if base["tin"] is None:
        base["tin"] = "T" + base["npi"]      # each provider its own practice unless the test says otherwise
    return base


@pytest.fixture()
def run(tmp_path):
    bench = make_bench(tmp_path / "bench")
    npis = [str(i) for i in range(1, 9)]
    _csv(tmp_path / "prov.csv", ["npi", "zip5", "kind", "wage_index", "ccn"],
         [[n, "75201", "", "", ""] for n in npis] + [["900", "75201", "H", 1.1, "450021"]])
    tables = tmp_path / "rates"
    tables.mkdir()
    R = []
    # 99213 office visit: providers 1-6 at 1.1x .. 1.6x of $100, provider 7 at 10x (far from Medicare), provider 8 twice
    for i, v in enumerate([110, 120, 130, 140, 150, 160], 1):
        R.append(row(npi=str(i), negotiated_rate=str(v)))
    R.append(row(npi="7", negotiated_rate="1000"))
    R += [row(npi="8", tin="T1", negotiated_rate="125"), row(npi="8", tin="T1", negotiated_rate="125")]   # a repeated copy: one unit;
    # provider 8 never billed Medicare for 99213 but works in provider 1's practice (same TIN), which did
    R.append(row(npi="1", negotiated_rate="50", negotiated_type="percentage"))                 # percent of charges
    R.append(row(npi="2", negotiated_rate="0"))                                                # $0
    R.append(row(npi="3", billing_code_type="CDT", billing_code="D0120", negotiated_rate="45"))  # dental: no benchmark
    # hospital 900: outpatient MRI facility fee and a hip replacement stay, and a per-day rate
    R.append(row(npi="900", billing_class="institutional", billing_code="70551", negotiated_rate="660"))
    R.append(row(npi="900", billing_class="institutional", billing_code_type="MS-DRG", billing_code="470", negotiated_rate="32000"))
    R.append(row(npi="900", billing_class="institutional", billing_code_type="MS-DRG", billing_code="470", negotiated_rate="4000",
                 negotiated_type="per diem"))
    make_insurer(tables / "acme.parquet", R)
    # a "Traditional" plan: must be its own figure ("unclear")
    make_insurer(tables / "trad.parquet", [row(file_label="BCBS Traditional", npi=str(i), negotiated_rate=str(200 + i)) for i in range(1, 7)])
    # hospital file rows: commercial and Medicare Advantage plans
    hosp = tmp_path / "hosp.csv"
    _csv(hosp, ["code", "code_type", "setting", "billing_class", "payer_name", "plan_name", "negotiated_dollar",
                "negotiated_percentage", "negotiated_algorithm", "methodology", "modifiers", "hospital_name", "allowed_count"],
         [["470", "MS-DRG", "inpatient", "facility", "Acme", "PPO", "40000", "", "", "case rate", "", "Hospital A", "1 through 10"],
          ["470", "MS-DRG", "inpatient", "facility", "Acme", "Medicare Advantage HMO", "17000", "", "", "case rate", "", "Hospital A", "0"],
          ["470", "MS-DRG", "inpatient", "facility", "Acme", "PPO", "", "45", "", "percent of total billed charges", "", "Hospital A", ""],
          ["70551", "CPT", "outpatient", "facility", "Acme", "PPO", "900", "", "", "fee schedule", "", "Hospital A", "0"]])
    allowed = tmp_path / "allowed.csv"
    _csv(allowed, ["insurer", "plan", "code_type", "code", "tin", "npi", "billing_class", "modifier", "service_code", "allowed_amount"],
         [["Acme", "Acme PPO", "CPT", "99213", "T1", str(i), "professional", "", "11", 300 + i] for i in range(1, 7)])
    out = tmp_path / "out"
    work = tmp_path / "work"
    sys.argv = ["run.py", "local", "--state", "TX", "--bench", str(bench), "--prov", str(tmp_path / "prov.csv"),
                "--insurer", str(tables / "*.parquet"), "--hospital", f"{hosp}:450021:TX", "--allowed", str(allowed),
                "--work", str(work), "--out", str(out)]
    import run as runmod
    runmod.main()
    rd = lambda n: list(csv.DictReader(open(out / "tx" / n)))
    return dict(codes=rd("codes.csv"), buckets=rd("buckets.csv"), totals=rd("totals.csv"), coverage=rd("coverage.csv"),
                nobench=rd("no_benchmark_codes.csv"), tails=rd("tails.csv"), providers=rd("providers.csv"),
                methods=rd("methods.csv"), md=(out / "tx" / "summary.md").read_text())


def pick(rows, **k):
    return [r for r in rows if all(r.get(a) == b for a, b in k.items())]


def test_pfs_formula_and_locality_key():
    rvu = "\n".join(["HCPCS,MOD,DESCRIPTION,CODE,PAYMENT,RVU,PE RVU,INDICATOR,PE RVU,INDICATOR,RVU" + ",x" * 15,
                     "99213,,Office,A,,1.30,1.20,,0.50,,0.10" + ",0" * 14 + ",33.4009"])
    gp = {"04412-11": (1.009, 0.996, 0.858, "DALLAS", "TX")}
    out = cms.pfs_rows(rvu, gp)
    nf = round((1.30 * 1.009 + 1.20 * 0.996 + 0.10 * 0.858) * 33.4009, 2)
    fa = round((1.30 * 1.009 + 0.50 * 0.996 + 0.10 * 0.858) * 33.4009, 2)
    assert out == [("99213", "", "04412-11", nf, fa, "A")]


def test_nearest_rank_uses_listed_values():
    assert summ.nearest_rank([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert summ.nearest_rank([1.0, 2.0, 3.0, 4.0, 5.0], 90) == 5.0
    assert summ.nearest_rank([3.0, 1.0, 2.0], 10) == 1.0


def test_office_visit_percentiles_and_labels(run):
    a = pick(run["codes"], rates="all rates", source="insurer", status="in-network", code="99213")[0]
    # units: 1.1 1.2 1.3 1.4 1.5 1.6 1.25 10.0 -> sorted 1.1 1.2 1.25 1.3 1.4 1.5 1.6 10.0 ; middle = 4th of 8
    assert a["figure"] == "yes"
    assert float(a["middle"]) == 1.3 and float(a["p10"]) == 1.1 and float(a["p90"]) == 10.0
    assert a["units"] == "8"                       # the repeated copy at provider 8 counts once; $0 and percent are out
    k = pick(run["codes"], rates=summ.RANGE, source="insurer", status="in-network", code="99213")[0]
    assert float(k["p90"]) == 1.6 and k["units"] == "7"   # the 10x rate is labeled "far from Medicare", left out here only


def test_traditional_plan_is_unclear_never_in_network(run):
    u = pick(run["codes"], rates="all rates", source="insurer", status="unclear", code="99213")
    assert u and u[0]["figure"] == "yes" and float(u[0]["middle"]) == 2.03
    assert all("Traditional" not in r["bucket"] for r in run["codes"])
    inn = pick(run["codes"], rates="all rates", source="insurer", status="in-network", code="99213")[0]
    assert inn["units"] == "8"


def test_out_of_network_kept_separate(run):
    o = pick(run["codes"], rates="all rates", source="allowed", status="out-of-network", code="99213")[0]
    assert float(o["middle"]) == 3.03 and o["units"] == "6"


def test_kept_out_and_counted(run):
    what = {(c["source"], c["status"], c["what"]) for c in run["coverage"]}
    assert ("insurer", "in-network", "kept out of the ratio: percent of charges") in what
    assert ("insurer", "in-network", "kept out of the ratio: zero") in what
    assert ("insurer", "in-network", "kept out of the ratio: per day") in what
    assert ("hospital", "in-network", "kept out of the ratio: percent of charges") in what
    nb = pick(run["nobench"], code="D0120")
    assert nb and nb[0]["units"] == "1"


def test_too_few_providers_gets_no_figure(run):
    mri = pick(run["codes"], rates="all rates", source="insurer", view="outpatient_hospital", code="70551")[0]
    assert mri["figure"].startswith("no: fewer than 5") and mri["middle"] == ""
    # 660 / (250 x (0.6 x 1.1 + 0.4)) = 660 / 265 = 2.49, kept in the data even without a figure
    assert mri["units"] == "1"


def test_hospital_stay_uses_hospitals_own_rate_and_programs_apart(run):
    drg = pick(run["codes"], rates="all rates", source="insurer", view="inpatient", code="470")
    assert drg and drg[0]["units"] == "1"   # 32000 / (2 x 7500 + 1000) = 2.0; one hospital -> no figure
    h = pick(run["codes"], rates="all rates", source="hospital", code="470")
    progs = {r["program"] for r in h}
    assert progs == {"commercial", "Medicare Advantage"}


def test_weighted_total_is_ratio_of_sums(run):
    t = pick(run["totals"], figure="Insurer files, in-network", rates="all rates", subtotal="")[0]
    # only 99213 has a figure (8 providers): weighted = 1000 x 130 / (1000 x 100) = 1.3; equal weight = 1.3
    assert float(t["medicare_use_weighted"]) == 1.3 and float(t["equal_weight"]) == 1.3
    assert "weighted by Medicare's mix of care, which skews older" in run["md"].lower() or "skews older" in run["md"]


def test_status_and_program_rules():
    con = duckdb.connect()
    s = lambda x: con.execute(f"select {rates.STATUS_SQL.format(x=repr(x))}").fetchone()[0]
    p = lambda x: con.execute(f"select {rates.PROGRAM_SQL.format(x=repr(x))}").fetchone()[0]
    assert s("BCBS Traditional") == "unclear"
    assert s("Aetna Out of Network") == "out-of-network"
    assert s("Aetna Open Access Managed Choice") == "in-network"
    assert p("Humana Medicare Advantage PPO") == "Medicare Advantage"
    assert p("Superior STAR Medicaid") == "Medicaid / dual"
    assert p("BCBS Blue Choice PPO") == "commercial"


def test_split_by_provider_gives_identical_counts(tmp_path):
    """A big table is read in passes split by provider; every label looks at one provider, so the counts must match."""
    bench = make_bench(tmp_path / "bench")
    _csv(tmp_path / "prov.csv", ["npi", "zip5", "kind", "wage_index", "ccn"], [[str(i), "75201", "", "", ""] for i in range(1, 30)])
    codes = [f"{f}{n:02d}" for f in ("993", "450", "702") for n in range(10, 14)]           # 12 codes in 3 families
    R = [row(npi=str(i), billing_code="99213", negotiated_rate=str(90 + i)) for i in range(1, 30)]
    R += [row(npi="5", billing_code=c, negotiated_rate="3682") for c in codes]              # one amount, many codes
    R += [row(npi="6", negotiated_rate="555"), row(npi="6", negotiated_rate="555")]         # a repeated copy
    make_insurer(tmp_path / "t.parquet", R)
    totals = []
    for k in (1, 3):
        con = duckdb.connect()
        rates.register_bench(con, str(bench), f"read_csv('{tmp_path / 'prov.csv'}', all_varchar=true)", ["TX"])
        t = f"read_parquet('{tmp_path / 't.parquet'}')"
        have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
        got = []
        for j in range(k):
            out = tmp_path / f"o{k}_{j}"
            rates.reduce_table(con, rates.insurer_units(t, have, None, None, j, k), dict(source="insurer", scope="x", table_name="t"), str(out))
            got += con.execute(f"select code, rate, units, units_keep, units_many from '{out}.part.parquet'").fetchall()
        agg = {}
        for code, rate, u, uk, um in got:
            a = agg.setdefault((code, rate), [0, 0, 0])
            a[0] += u
            a[1] += uk
            a[2] += um
        totals.append(agg)
    assert totals[0] == totals[1]
    assert sum(v[2] for v in totals[0].values()) == 12          # the 12 one-amount rates are labeled in both
    assert totals[0][("99213", 96.0)][0] == 1 and totals[0][("99213", 555.0)][0] == 1


# ---------------------------------------------------------------- fix 1: evidence that the provider does the service

def test_evidence_view_keeps_high_prices_and_uses_practice(run):
    e = pick(run["codes"], rates=summ.EVIDENCE, source="insurer", status="in-network", code="99213")[0]
    # evidence: providers 1-4 and 7 billed Medicare; 8 through its practice (same TIN as provider 1); 5 and 6 have none
    # units 1.1 1.2 1.3 1.4 10.0 1.25 -> sorted 1.1 1.2 1.25 1.3 1.4 10.0: middle = 3rd of 6, 90th = the 10x rate (kept)
    assert e["units"] == "6" and e["providers_at_least"] == "6" and e["figure"] == "yes"
    assert float(e["middle"]) == 1.25 and float(e["p90"]) == 10.0


def test_hospital_file_listing_is_evidence_for_insurer_rates(run):
    # hospital 450021 never billed Medicare for DRG 470 or APC 5523, but its own file lists 470 and 70551 -> evidence (b)
    for code in ("470", "70551"):
        e = pick(run["codes"], rates=summ.EVIDENCE, source="insurer", code=code)
        assert e and e[0]["units"] == "1", code


def test_hospital_count_of_allowed_amounts_is_evidence_for_its_own_rates(run):
    # (c) is per code: the file counts "1 through 10" paid claims for DRG 470 (PPO row), so every 470 rate in the file has
    # evidence, the Medicare Advantage row too. For 70551 the only count is "0": listed, but no evidence for its own rate.
    for prog in ("commercial", "Medicare Advantage"):
        assert pick(run["codes"], rates=summ.EVIDENCE, source="hospital", code="470", program=prog)[0]["units"] == "1"
    assert pick(run["codes"], rates=summ.ALL, source="hospital", code="70551")[0]["units"] == "1"
    assert not pick(run["codes"], rates=summ.EVIDENCE, source="hospital", code="70551")


def test_tails_table_lists_far_rates_with_evidence(run):
    t = pick(run["tails"], source="insurer", status="in-network", code="99213")
    assert len(t) == 1 and t[0]["side"] == "over 8×" and t[0]["units"] == "1" and t[0]["units_with_evidence"] == "1"
    assert float(t[0]["highest_listed_amount"]) == 1000.0
    assert "Rates under 0.5× or over 8× Medicare" in run["md"]


def test_three_views_in_totals_and_coverage(run):
    views = {r["rates"] for r in pick(run["totals"], figure="Insurer files, in-network", subtotal="")}
    assert views == {summ.ALL, summ.EVIDENCE, summ.RANGE}
    c = pick(run["coverage"], source="insurer", status="in-network", what="in the ratio")[0]
    # 99213: 8 units, 6 with evidence (5 billed Medicare + 1 by practice); DRG 470 and MRI at the hospital: (b) evidence
    assert c["units"] == "10" and c["units_with_evidence"] == "8" and c["evidence_medicare_billing"] == "6"
    p = pick(run["providers"], source="insurer", status="in-network", bucket="(all buckets in the totals)")[0]
    assert p["providers"] == "9" and p["providers_evidence"] == "7"


def test_evidence_builders(tmp_path):
    _csv(tmp_path / "phy.csv", ["Rndrng_NPI", "Rndrng_Prvdr_State_Abrvtn", "HCPCS_Cd", "Place_Of_Srvc", "Tot_Srvcs"],
         [["111", "TX", "99213", "O", "20"], ["111", "TX", "99213", "F", "12"], ["222", "OK", "99213", "O", "15"]])
    assert cms.ev_prof_rows(tmp_path / "phy.csv", {"TX"}) == [("111", "99213")]
    _csv(tmp_path / "out.csv", ["Rndrng_Prvdr_CCN", "Rndrng_Prvdr_State_Abrvtn", "APC_Cd"], [["450021", "TX", "5523"], ["010001", "AL", "5072"]])
    assert cms.ev_out_rows(tmp_path / "out.csv", {"TX"}) == [("450021", "5523")]
    _csv(tmp_path / "inp.csv", ["Rndrng_Prvdr_CCN", "Rndrng_Prvdr_State_Abrvtn", "DRG_Cd"], [["450021", "TX", "003"], ["450021", "TX", "470"]])
    assert cms.ev_inp_rows(tmp_path / "inp.csv", {"TX"}) == [("450021", "3"), ("450021", "470")]


def test_fetch_api_pages_by_state(tmp_path, monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        off = int(url.split("offset=")[1].split("&")[0])
        rows = [{"Rndrng_NPI": str(i), "HCPCS_Cd": "99213"} for i in range(off, min(off + 2, 5))]
        return json.dumps(rows).encode()
    monkeypatch.setattr(cms, "_get", fake_get)
    n = cms.fetch_api("https://x/data", tmp_path / "o.csv", ["TX"], "Rndrng_Prvdr_State_Abrvtn", "Rndrng_NPI,HCPCS_Cd", page=2)
    assert n == 5 and len(list(csv.DictReader(open(tmp_path / "o.csv")))) == 5
    assert all("filter%5BRndrng_Prvdr_State_Abrvtn%5D=TX" in u for u in seen)


# ---------------------------------------------------------------- fix 2: place of service for doctor fees

def _reduce_one(tmp_path, R, name="t", prov_rows=None, extra=None):
    """Reduce one made-up insurer table with the test benchmark; returns the part rows as dicts."""
    bench = make_bench(tmp_path / "bench")
    if extra:
        extra(bench)
    _csv(tmp_path / "prov.csv", ["npi", "zip5", "kind", "wage_index", "ccn"], prov_rows or [[str(i), "75201", "", "", ""] for i in range(1, 30)])
    make_insurer(tmp_path / f"{name}.parquet", R)
    con = duckdb.connect()
    rates.register_bench(con, str(bench), f"read_csv('{tmp_path / 'prov.csv'}', all_varchar=true)", ["TX"])
    t = f"read_parquet('{tmp_path / name}.parquet')"
    have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
    rates.reduce_table(con, rates.insurer_units(t, have), dict(source="insurer", scope="x", table_name=name), str(tmp_path / f"o_{name}"))
    c = con.execute(f"select * from '{tmp_path / f'o_{name}'}.part.parquet' order by rate")
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def test_place_of_service_methods_and_blend(tmp_path):
    def mix(b):   # Medicare sees 99213 25% at facilities in Texas; 70551 only nationally (60%)
        _csv(b / "posmix.csv", ["state", "code", "facility_services", "office_services", "share_facility"],
             [["TX", "99213", 25, 75, 0.25], ["US", "70551", 60, 40, 0.6]])
    R = [row(npi="1", service_code="22", negotiated_rate="101"),            # facility place -> facility rate 60
         row(npi="2", service_code="11", negotiated_rate="102"),            # office -> office rate 100
         row(npi="3", service_code="11,22", negotiated_rate="103"),         # both kinds -> blend 0.25 x 60 + 0.75 x 100 = 90
         row(npi="4", service_code="", negotiated_rate="104"),              # not stated -> blend 90
         row(npi="5", service_code='["02"]', negotiated_rate="105"),        # telehealth POS 02 -> facility rate
         row(npi="6", service_code="", billing_code="45378", negotiated_rate="106")]   # no fee-schedule row -> no benchmark
    P = {r["rate"]: r for r in _reduce_one(tmp_path, R, extra=mix)}
    assert P[101.0]["medicare_amount"] == 60.0 and P[101.0]["pos"] == "service code: facility"
    assert P[102.0]["medicare_amount"] == 100.0 and P[102.0]["pos"] == "service code: office"
    assert P[103.0]["medicare_amount"] == 90.0 and P[103.0]["pos"] == "both kinds of place: blended by Medicare's state site mix"
    assert P[104.0]["medicare_amount"] == 90.0 and P[104.0]["pos"] == "not stated: blended by Medicare's state site mix"
    assert P[105.0]["medicare_amount"] == 60.0
    assert (P[104.0]["medicare_facility"], P[104.0]["medicare_office"]) == (60.0, 100.0)


def test_place_of_service_fallbacks(tmp_path):
    # 70551: no Texas mix -> national; only an office (non-facility) rate exists for the global code -> that one
    def mix(b):
        _csv(b / "posmix.csv", ["state", "code", "facility_services", "office_services", "share_facility"], [["US", "99213", 60, 40, 0.6]])
    R = [row(npi="1", service_code="", negotiated_rate="111"), row(npi="2", service_code="", billing_code="70551", negotiated_rate="300")]
    P = {r["code"]: r for r in _reduce_one(tmp_path, R, extra=mix)}
    assert P["99213"]["medicare_amount"] == 76.0 and P["99213"]["pos"] == "not stated: blended by Medicare's national site mix"
    assert P["70551"]["medicare_amount"] == 200.0 and P["70551"]["pos"] == "not stated: the only Medicare rate for this code"


def test_place_of_service_counts_and_low_high_range(run):
    office = pick(run["methods"], question="place of service (doctor fees)", source="insurer", status="in-network", method="service code: office")
    assert office and office[0]["units"] == "8"
    a = pick(run["codes"], rates=summ.ALL, source="insurer", status="in-network", code="99213")[0]
    # every rate here is an office rate (100); against the facility rate (60) the same middle would be 130 / 60
    assert float(a["middle_vs_office_rate"]) == 1.3 and float(a["middle_vs_facility_rate"]) == round(130 / 60, 3)
    assert "How each rate was handled" in run["md"]


def test_posmix_and_allowed_dollars_from_geography_file():
    hdr = "Rndrng_Prvdr_Geo_Lvl,Rndrng_Prvdr_Geo_Desc,HCPCS_Cd,Place_Of_Srvc,Tot_Srvcs,Avg_Mdcr_Alowd_Amt\n"
    phy = hdr + "\n".join(["National,National,99213,F,600,50", "National,National,99213,O,400,80",
                           "State,Texas,99213,F,30,50", "State,Texas,99213,O,90,80", "State,Oklahoma,99213,O,5,70"])
    mix = cms.posmix_rows(phy, {"TX"})
    assert ("TX", "99213", 30.0, 90.0, 0.25) in mix and ("US", "99213", 600.0, 400.0, 0.6) in mix and len(mix) == 2
    empty = "Rndrng_Prvdr_Geo_Lvl,Rndrng_Prvdr_Geo_Desc,HCPCS_Cd,CAPC_Srvcs\n"
    vol = cms.volume_rows(phy, empty, "Rndrng_Prvdr_Geo_Lvl,Rndrng_Prvdr_Geo_Desc,DRG_Cd,Tot_Dschrgs\n",
                          "Rfrg_Prvdr_Geo_Lvl,Rfrg_Prvdr_Geo_Desc,HCPCS_Cd,Tot_Suplr_Srvcs\n", {"TX"})
    assert ("TX", "professional", "99213", "F", 30.0, "vol_physician", 1500.0) in vol


# ---------------------------------------------------------------- fix 3: anesthesia per unit vs per case

def test_anesthesia_sorted_per_unit_or_per_case(tmp_path):
    R = [row(npi="1", billing_code="00790", negotiated_rate="61.32"),                                   # per unit: 3x CF 20.44
         row(npi="2", billing_code="00790", negotiated_rate="1500"),                                    # per case (size)
         row(npi="3", billing_code="00790", negotiated_rate="300"),                                     # unclear
         row(npi="4", billing_code="00790", negotiated_rate="450", additional_information="Per unit"),  # the rate says per unit
         row(npi="5", billing_code="00790", negotiated_rate="120", additional_information="Flat rate per case")]
    P = {r["rate"]: r for r in _reduce_one(tmp_path, R)}
    assert P[61.32]["rate_kind"] == "dollar" and P[61.32]["medicare_amount"] == 20.44 and P[61.32]["view"] == "anesthesia"
    assert P[450.0]["rate_kind"] == "dollar" and P[450.0]["units_far"] == 1     # 22x: kept, labeled far, goes to the tails table
    assert P[1500.0]["rate_kind"] == P[120.0]["rate_kind"] == rates.ANES_CASE
    assert P[300.0]["rate_kind"] == rates.ANES_UNCLEAR
    assert P[1500.0]["medicare_amount"] is None                                 # no ratio for a whole case


def test_anesthesia_weighted_by_medicare_dollars():
    office = dict(medicare_volume_2024=1000, middle_private_amount=130.0, middle_medicare_amount=100.0)
    anes = dict(medicare_volume_2024=None, medicare_dollars_2024=50000.0, middle_private_amount=61.32, middle_medicare_amount=20.44)
    # (1000 x 130 + 50000 x 3.0) / (1000 x 100 + 50000) = 280000 / 150000
    assert summ._weighted([office, anes]) == round(280000 / 150000, 3)
    assert summ.dollars_for({("$professional", "00790"): 50000.0}, "anesthesia", "00790") == 50000.0
    assert summ.volume_for({("professional", "00790"): 900}, "anesthesia", "00790") is None


# ---------------------------------------------------------------- fix 4: market segment from the tables of contents
import segments  # noqa: E402


def test_network_segments_from_toc_hios_and_form_5500(tmp_path):
    con = duckdb.connect()
    con.execute("""create table xw as select * from (values
        ('pl-2ua-hr23', '111111111', 'ein', 'group'), ('pl-2ua-hr23', '222222222', 'ein', 'group'),
        ('ambx', '12345TX0010001', 'hios', ''), ('ambx', '67890TX0020002', '', ''),
        ('mixed', '333333333', 'ein', 'group'), ('mixed', '12345TX0010003', 'hios', 'individual'),
        ('selffunded', '044444444', 'ein', ''), ('nothing', 'x1', 'other', '')) t(network_key, plan_id, plan_id_type, plan_market_type)""")
    con.execute("create table f5 as select '44444444' ein")          # the bot's Form 5500 table, EIN without its leading zero
    S = segments.network_segments(con, "xw", "f5")
    assert S["pl-2ua-hr23"]["segment"] == segments.GROUP and S["pl-2ua-hr23"]["method"] == segments.TOC
    assert S["ambx"]["segment"] == segments.INDIVIDUAL and S["ambx"]["method"] == segments.HIOS
    assert S["mixed"]["segment"] == segments.BOTH and S["mixed"]["method"] == segments.TOC
    assert S["selffunded"]["segment"] == segments.GROUP and S["selffunded"]["method"] == segments.F5500
    assert S["nothing"]["segment"] == segments.UNKNOWN and S["nothing"]["method"] == segments.NONE
    # a rate table is matched to the network whose key is in its file name (longest key wins)
    assert segments.table_segment("2026-09-05_pl-2ua-hr23_Aetna-Life-Insurance-Company", S)["segment"] == segments.GROUP
    assert segments.table_segment("some_other_file", S) is None


def test_segment_on_rates_with_fallback_and_method(tmp_path):
    P = _reduce_one(tmp_path, [row(npi="1", file_label="Ambetter Marketplace")], name="a")
    assert P[0]["segment"] == "individual (marketplace)" and P[0]["segment_method"] == segments.NAME
    P = _reduce_one(tmp_path, [row(npi="1", file_label="Ambetter Marketplace")], name="b")
    con = duckdb.connect()
    rates.register_bench(con, str(tmp_path / "bench"), f"read_csv('{tmp_path / 'prov.csv'}', all_varchar=true)", ["TX"])
    t = f"read_parquet('{tmp_path / 'b.parquet'}')"
    have = {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}
    rates.reduce_table(con, rates.insurer_units(t, have, seg=(segments.GROUP, segments.TOC)), dict(source="insurer", scope="x", table_name="b"),
                       str(tmp_path / "o_c"))
    r = con.execute(f"select segment, segment_method from '{tmp_path / 'o_c'}.part.parquet'").fetchone()
    assert r == (segments.GROUP, segments.TOC)       # the table of contents wins over the network's name


def test_allowed_amount_file_names_its_market():
    doc = {"plan_name": "Acme PPO", "plan_market_type": "individual", "plan_id_type": "hios", "plan_id": "12345TX0010001",
           "out_of_network": [{"billing_code_type": "CPT", "billing_code": "99213", "allowed_amounts": [
               {"tin": {"value": "T1"}, "billing_class": "professional", "service_code": ["11"],
                "payments": [{"allowed_amount": 300, "providers": [{"npi": [1]}]}]}]}]}
    r = list(rates.allowed_rows(doc, "Acme"))
    assert r[0]["plan_market_type"] == "individual" and r[0]["plan_id"] == "12345TX0010001"
    con = duckdb.connect()
    con.execute("create table prov as select '1' npi, 'H' kind, 1.0 wage_index, null ccn, '04412-11' locality, '' rural, 'TX' state")
    con.execute("create table allowed as select * from (values ('Acme', 'Acme PPO', 'CPT', '99213', 'T1', '1', 'professional', '', '11', 300.0, 'individual', 'hios', 'X')) "
                "t(insurer, plan, code_type, code, tin, npi, billing_class, modifier, service_code, allowed_amount, plan_market_type, plan_id_type, plan_id)")
    seg, how = con.execute(f"select segment, segment_method from ({rates.allowed_units('allowed')})").fetchone()
    assert seg == segments.INDIVIDUAL and how.startswith("allowed-amount file")


def test_segment_methods_counted(run):
    seg = [m for m in run["methods"] if m["question"].startswith("market segment")]
    assert any(m["method"] == "not stated in file: not stated anywhere" for m in seg)


# ---------------------------------------------------------------- fix 5: hospital files matched by their own identifiers
import hospital_match as hm  # noqa: E402


def test_hospital_files_matched_by_their_own_identifiers():
    known = {"450021": "TX", "450022": "TX", "450023": "TX", "370001": "OK"}
    npi_ccn = {"1234567890": {"450021"}, "2222222222": {"450022", "450023"}, "3333333333": {"370001"}}
    U = "https://h.example/"
    files = [
        dict(key="A", state="TX", type_2_npi="1234567890", license_number="H-12345", license_state="TX", url=U + "a.json"),
        dict(key="B", state="TX", location_name="Hospital B, CMS certification 450022", url=U + "751234567_hospital-b_standardcharges.json"),
        dict(key="C", state="TX", license_number="h 12345", license_state="TX"),           # same license as A
        dict(key="D", state="TX", url=U + "75-1234567_hospital-b-west_standardcharges.csv"),  # same EIN as B
        dict(key="E", state="TX", type_2_npi="2222222222|9999999999"),                     # a system file: two hospitals
        dict(key="F", state="TX"),                                                         # says nothing: the bot's list
        dict(key="G", state="TX"),                                                         # says nothing, not on the list
        dict(key="H", state="TX", type_2_npi="3333333333"),                                # its NPI is an Oklahoma hospital
    ]
    fb = {"A": "450021", "B": "450099", "E": "450023", "F": "450022", "H": "450021"}
    M = hm.match_files(files, npi_ccn, known, fb)
    assert (M["A"]["ccn"], M["A"]["method"], M["A"]["agrees_with_list"]) == ("450021", hm.M_NPI, "yes")
    assert (M["B"]["ccn"], M["B"]["method"], M["B"]["agrees_with_list"]) == ("450022", hm.M_CCN, "no")
    assert (M["C"]["ccn"], M["C"]["method"]) == ("450021", hm.M_LIC)
    assert (M["D"]["ccn"], M["D"]["method"]) == ("450022", hm.M_EIN)
    assert (M["E"]["ccn"], M["E"]["method"]) == ("450023", hm.M_NPI_LIST)
    assert (M["F"]["ccn"], M["F"]["method"]) == ("450022", hm.M_LIST)
    assert (M["G"]["ccn"], M["G"]["method"]) == (None, hm.M_NONE)
    assert (M["H"]["ccn"], M["H"]["method"]) == ("450021", hm.M_LIST)
    c = hm.counts(M)
    assert c[hm.M_NPI] == 1 and c[hm.M_LIST] == 2 and sum(c.values()) == 8


def test_hospital_match_rows_and_unmatched_files_stay_listed():
    import run as runmod
    doc = {"items": [dict(source="hospital", key="k1", name="A", state="TX", ccn="450021", match_method=hm.M_NPI, fallback_ccn="450021",
                          agrees_with_list="yes", file_npis=["1234567890"], lane="gh", rows=0, bytes=5),
                     dict(source="hospital-unmatched", key="k2", name="G", state="TX", ccn="", match_method=hm.M_NONE, lane="none", rows=0, bytes=0)]}
    rows = runmod.hospital_match_rows(doc, "TX")
    assert [r["method"] for r in rows] == [hm.M_NPI, hm.M_NONE] and rows[0]["npis_in_file"] == "1234567890"
    est = runmod.estimate(dict(items=doc["items"] + [dict(source="insurer", lane="gh", rows=10, bytes=1)]))
    assert est["tables"] == 2 and est["hospital_files_not_matched"] == 1


# ---------------------------------------------------------------- fix 6: third total weighted by MEPS (under 65, private)
import meps  # noqa: E402


def test_meps_shares_from_public_use_file_columns():
    pd = pytest.importorskip("pandas")
    cols = {f"{stem}24": [10.0, 30.0, 999.0, 50.0] for stem, _, _ in meps.EVENTS}
    d = pd.DataFrame(dict(AGELAST=[30, 40, 70, 50], INSCOV24=[1, 1, 1, 2], PERWT24F=[1.0, 2.0, 5.0, 9.0], **cols))
    d["TOTEXP24"] = sum(d[f"{stem}24"] for stem, _, _ in meps.EVENTS)
    rows, people = meps.shares_from_frame(d)
    assert people == 2                      # the 70-year-old and the publicly insured person are out
    ob = next(r for r in rows if r["variable"] == "OBVEXP24")
    assert ob["dollars"] == 70 and ob["share"] == round(1 / len(meps.EVENTS), 5)


def test_meps_total_weights_groups_by_spending(tmp_path):
    f = tmp_path / "m.csv"
    _csv(f, ["year", "variable", "event_type", "group", "dollars", "share"],
         [[2024, "OBVEXP24", "Office", "Doctor and clinician fees", 30, 0.3], [2024, "IPFEXP24", "Inpatient", "Hospital stays", 15, 0.15],
          [2024, "RXEXP24", "Rx", "", 25, 0.25], [2024, "TOTEXP24", "All", "(total)", 100, 1.0]])
    rows = [dict(view="professional", medicare_volume_2024=100, middle_private_amount=150.0, middle_medicare_amount=100.0),
            dict(view="inpatient", medicare_volume_2024=1, middle_private_amount=30000.0, middle_medicare_amount=10000.0)]
    t, parts = meps.meps_total(rows, summ._weighted, f)
    # (0.30 x 1.5 + 0.15 x 3.0) / 0.45 = 2.0; prescriptions have no kind of care here and are left out
    assert t == 2.0
    assert {p["group"]: p["multiple"] for p in parts}["Hospital stays"] == 3.0


def test_meps_committed_shares_and_total_in_report(run):
    g, rows = meps.load_shares()
    assert abs(sum(float(r["share"]) for r in rows if r["group"] != "(total)") - 1.0) < 0.001
    assert set(g) == set(meps.GROUP_VIEWS)
    t = pick(run["totals"], figure="Insurer files, in-network", rates=summ.ALL, subtotal="")[0]
    assert float(t["meps_weighted"]) == 1.3          # only doctor fees have a figure in the made-up data
    assert "under 65" in run["md"] and "HC-256" in run["md"]
