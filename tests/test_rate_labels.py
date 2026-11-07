"""Labels for insurer rates that may never be used: labels only, every row kept. Made-up rows, no storage needed.
Run: python -m pytest tests/"""
import os
import sys

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "insurers", "pipeline"))
import rate_labels as RL  # noqa: E402


def table(con, rows):
    con.execute("""create or replace table r (npi varchar, tin varchar, billing_code varchar, billing_code_modifier varchar,
                   billing_class varchar, setting varchar, negotiated_type varchar, negotiated_rate double, service_code varchar)""")
    con.executemany("insert into r values (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return "r"


def test_labels():
    con = duckdb.connect()
    rows = [
        # 20 unrelated codes, one amount, one provider: label c (the Aetna $3,682.00 pattern)
        *[("111", "T1", c, "", "institutional", "outpatient", "negotiated", 3682.0, "22")
          for c in ["29881", "29882", "45378", "45380", "47562", "49505", "66984", "70551", "73721", "74177",
                    "27447", "27130", "43239", "64483", "19120", "52000", "58558", "63030", "36415", "93000"]],
        # same service listed twice at the same provider (two place-of-service lists): label b on both copies
        ("222", "T2", "45378", "", "institutional", "outpatient", "negotiated", 1500.0, "22"),
        ("222", "T2", "45378", "", "institutional", "outpatient", "negotiated", 1500.0, "24"),
        # far from Medicare: 30x and 0.2x the made-up Medicare figure of 1,000
        ("333", "T3", "70551", "", "institutional", "outpatient", "negotiated", 30000.0, "22"),
        ("333", "T3", "73721", "", "institutional", "outpatient", "negotiated", 200.0, "22"),
        # ordinary rate, percentage rate, $0 rate: no label
        ("444", "T4", "70551", "", "institutional", "outpatient", "negotiated", 1800.0, "22"),
        ("444", "T4", "73721", "", "institutional", "outpatient", "percentage", 55.0, "22"),
        ("444", "T4", "74177", "", "institutional", "outpatient", "negotiated", 0.0, "22"),
    ]
    t = table(con, rows)
    con.execute("create table b as select * from (values ('70551', 'facility', 1000.0, 'test'), ('73721', 'facility', 1000.0, 'test')) v(billing_code, fee, medicare_amount, medicare_basis)")
    out = con.execute(f"select npi, billing_code, negotiated_rate, far_from_medicare, repeated_amount, repeat_count, one_amount_many_codes "
                      f"from ({RL.labeled_sql(t, 'b', RL._columns(con, t))})").fetchall()
    assert len(out) == len(rows)                         # nothing dropped
    by = {}
    for npi, code, v, a, b, n, c in out:
        by.setdefault((npi, code, v), []).append((a, b, n, c))
    assert all(x == (False, False, 1, True) for k, xs in by.items() if k[0] == "111" for x in xs if k[1] not in ("70551", "73721")), by
    assert by[("111", "70551", 3682.0)] == [(False, False, 1, True)]   # 3.7x Medicare: inside 50%-800%
    assert by[("222", "45378", 1500.0)] == [(False, True, 2, False)] * 2
    assert by[("333", "70551", 30000.0)] == [(True, False, 1, False)]
    assert by[("333", "73721", 200.0)] == [(True, False, 1, False)]
    assert by[("444", "70551", 1800.0)] == [(False, False, 1, False)]
    assert by[("444", "73721", 55.0)] == [(False, False, 1, False)]
    assert by[("444", "74177", 0.0)] == [(False, False, 1, False)]

    c = RL.counts(con, t, "b")
    assert c["rows"] == len(rows) and c["one_amount_many_codes"] == 20
    assert c["repeated_amount_rows"] == 2 and c["repeated_amount_extra_copies"] == 1
    assert c["far_from_medicare"] == 2 and c["below_half_medicare"] == 1 and c["above_8x_medicare"] == 1
    assert c["any_label"] == 24


def test_few_codes_not_labeled():
    """A real flat fee for a few related codes (or 10 codes in one family) is not label c."""
    con = duckdb.connect()
    rows = [("555", "T5", c, "", "professional", "", "negotiated", 120.0, "11") for c in ["99212", "99213", "99214"]]
    rows += [("666", "T6", f"993{i:02d}", "", "professional", "", "negotiated", 80.0, "11") for i in range(12)]
    t = table(con, rows)
    assert RL.counts(con, t)["one_amount_many_codes"] == 0


def test_no_medicare_figure_means_no_label():
    con = duckdb.connect()
    t = table(con, [("777", "T7", "470", "", "institutional", "inpatient", "negotiated", 999999.0, "21")])
    c = RL.counts(con, t, None)
    assert c["far_from_medicare"] == 0 and c["with_medicare_figure"] == 0 and c["medicare_figures_used"] is False


def test_bench_rows():
    med = {"med": {"70551": {"opps": [450.0, "S", "5523"], "pfs": {"dal": [300.0, 95.5]}},
                   "80053": {"lab": 10.56}}}
    rows = set(RL.bench_rows(med))
    assert ("70551", "facility", 450.0, "Medicare hospital outpatient rate (national), CY2026") in rows
    assert ("70551", "professional", 95.5, "Medicare doctor fee, Dallas, 2026") in rows
    assert ("80053", "facility", 10.56, "Medicare lab fee schedule, 2026") in rows
