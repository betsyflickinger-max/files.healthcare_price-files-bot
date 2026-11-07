"""People weights: labeled public counts only, never scaled or split. Made-up Form 5500 join; the real MLR file.
Run: python -m pytest tests/"""
import os
import sys

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "insurers"))
import people_weights as PW  # noqa: E402


def test_people_weights(tmp_path):
    p = tmp_path / "employers.parquet"
    con = duckdb.connect()
    con.execute(f"""copy (select * from (values
        ('1', 'TX', 'self-funded', 'hcsc', 500, null, '2024'),
        ('2', 'TX', 'self-funded', 'hcsc', null, 300, '2024'),
        ('3', 'TX', 'insured', 'hcsc', 900, null, '2024'),
        ('4', 'OK', 'self-funded', 'hcsc', 700, null, '2024'),
        ('5', 'TX', 'self-funded', 'aetna, uhc', 250, null, '2025'),
        ('6', 'TX', 'self-funded', 'uhc', null, null, '2024'))
      v(ein, state, funding, listed_by, active_participants, participants_boy, f5500_year)) to '{p}' (format parquet)""")
    f = PW.f5500_texas(str(p))
    assert f["hcsc"] == (2, 800, "2024")                 # insured and Oklahoma plans left out
    assert f["more than one"] == (1, 250, "2025")        # not split between Aetna and UHC
    assert "uhc" not in f                                 # no participant count: not counted, not guessed
    rows = {r["insurer"]: r for r in PW.build(f)}
    b = rows["BCBSTX"]
    assert b["insured_lives_total"] == 3507937 and b["self_funded_participants_5500"] == 800
    assert b["people_total_listed"] == 3507937 + 800
    assert rows["UnitedHealthcare"]["self_funded_participants_5500"] == 0
    assert rows["Wellpoint"]["insured_source"] == "not in the MLR file for Texas"
    assert rows["(listed by more than one insurer)"]["note"] == "not used as a weight"


def test_mlr_only():
    rows = {r["insurer"]: r for r in PW.build(None)}
    assert rows["Oscar"]["insured_lives_total"] == 141000 and "people_total_listed" not in rows["Oscar"]
