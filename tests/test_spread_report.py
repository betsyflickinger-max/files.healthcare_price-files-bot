"""Spread report on made-up monthly tables: stable pairs only, listed values only, with and without labeled rates.
Run: python -m pytest tests/"""
import os
import sys

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "insurers"))
import spread_report as SR  # noqa: E402


def write_month(tmp, month, rows):
    d = tmp / month
    d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("""create table t (npi varchar, tin varchar, billing_code varchar, billing_code_modifier varchar, billing_class varchar,
                   setting varchar, negotiated_type varchar, negotiated_rate double, reporting_entity_name varchar,
                   file_label varchar, last_updated_on varchar)""")
    con.executemany("insert into t values (?,?,?,?,?,?,?,?,?,?,?)",
                    [(n, "T", c, "", "institutional", "outpatient", "negotiated", v, "Aetna", "Aetna Open Access", month + "-01")
                     for n, c, v in rows])
    con.execute(f"copy t to '{d / 'aetna.parquet'}' (format parquet)")


def test_spread(tmp_path):
    steady = [(f"1{i:02d}", "70551", 1000.0 + 100 * i) for i in range(10)]          # 10 providers, every month
    for m, extra in (("2026-09", []), ("2026-10", [("999", "70551", 50000.0)]), ("2026-11", []), ("2026-12", [])):
        write_month(tmp_path, m, steady + extra)
    con = duckdb.connect()
    con.execute("create table b as select '70551' billing_code, 'facility' fee, 1000.0 medicare_amount, 'test' medicare_basis")
    SR.collect(con, SR.tables(["2026-09", "2026-10", "2026-11", "2026-12"], str(tmp_path)), ["70551"], "b", str(tmp_path))
    SR.stable_pairs(con)
    out = SR.stats(con)
    nov = [r for r in out if r["month"] == "2026-11" and r["rates"] == "all rates"][0]
    assert nov["n"] == 10                       # the one-month $50,000 pair is not a stable pair
    assert nov["p10"] == 1000.0 and nov["p90"] == 1800.0 and nov["p50"] == 1400.0   # listed values (nearest rank)
    assert nov["ratio_90_10"] == 1.8 and nov["iqr"] == 1700.0 - 1200.0
    assert nov["p50_x_medicare"] == 1.4
    dec = [r for r in out if r["month"] == "2026-12" and r["rates"] == "all rates"][0]
    assert "new Transparency in Coverage rule" in dec["series_break"] and not nov["series_break"]


def test_two_months_is_not_stable(tmp_path):
    write_month(tmp_path, "2026-10", [("1", "45378", 900.0)])
    write_month(tmp_path, "2026-11", [("1", "45378", 900.0)])
    con = duckdb.connect()
    SR.collect(con, SR.tables(["2026-10", "2026-11"], str(tmp_path)), ["45378"], None, str(tmp_path))
    SR.stable_pairs(con)
    assert SR.stats(con) == []


def test_helpers():
    assert SR.nearest_rank([1, 2, 3, 4], 50) == 2 and SR.nearest_rank([1, 2, 3, 4, 5], 50) == 3
    assert SR.nearest_rank([5], 90) == 5 and SR.nearest_rank([], 50) is None
    assert SR.weighted_middle([(100, 1), (200, 10), (300, 1)]) == 200
    assert SR.weighted_middle([(100, 5), (200, 0)]) == 100


def test_write(tmp_path):
    steady = [(f"1{i:02d}", "70551", 1000.0 + 100 * i) for i in range(10)]
    for m in ("2026-10", "2026-11", "2026-12"):
        write_month(tmp_path / "in", m, steady)
    con = duckdb.connect()
    SR.collect(con, SR.tables(["2026-10", "2026-11", "2026-12"], str(tmp_path / "in")), ["70551"], None, str(tmp_path))
    SR.stable_pairs(con)
    out = SR.stats(con)
    SR.OUT = tmp_path / "out"
    w = SR.people_weighted(out, {"Aetna": 100})
    last = SR.write(out, w, ["2026-10", "2026-11", "2026-12"], ["70551"])
    md = (tmp_path / "out" / f"{last}.md").read_text()
    assert "Series break" in md and "MRI brain" in md and "weighted by people covered" in md
    assert (tmp_path / "out" / "series.csv").read_text().count("\n") == 1 + len(out)
