"""Cost-report labor share from a tiny made-up HCRIS zip. Run: python -m pytest tests/"""
import os
import sys
import zipfile

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "costreports"))
import labor_share as LS  # noqa: E402


def test_read_year(tmp_path):
    z = tmp_path / "HOSP10FY2024.ZIP"
    rpt = "1,2,450021,,1,07/01/2024,06/30/2025,12/05/2025,N,N,V,04011,4,,F,,,\n2,2,450999,,1,01/01/2024,12/31/2024,06/01/2025,N,N,V,04011,4,,F,,,\n3,2,453302,,1,01/01/2024,12/31/2024,06/01/2025,N,N,V,04011,4,,F,,,\n"
    alpha = ("1,S200001,00200,00100,DALLAS\n1,S200001,00200,00200,TX\n1,S200001,00200,00300,75246-\n1,S200001,00200,00400,DALLAS\n1,S200001,00300,00100,BIG HOSPITAL\n"
             "2,S200001,00200,00100,AUSTIN\n2,S200001,00200,00200,TX\n2,S200001,00200,00300,78701\n2,S200001,00200,00400,TRAVIS\n2,S200001,00300,00100,NOT DFW\n"
             "3,S200001,00200,00100,DALLAS\n3,S200001,00200,00200,TX\n3,S200001,00200,00300,75235\n3,S200001,00200,00400,DALLAS\n3,S200001,00300,00100,NO PART V\n")
    nmrc = ("1,A000000,20000,00100,400\n1,S300005,00100,00200,100\n1,G300000,00400,00100,1000\n"
            "2,A000000,20000,00100,50\n2,G300000,00400,00100,100\n"
            "3,A000000,20000,00100,300\n3,G300000,00400,00100,1200\n")
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("HOSP10_2024_rpt.csv", rpt); f.writestr("HOSP10_2024_alpha.csv", alpha); f.writestr("HOSP10_2024_nmrc.csv", nmrc)
    rows = LS.read_year(duckdb.connect(), "2024", z, tmp_path, LS.dfw_counties(), LS.zip_county())
    by = {r["ccn"]: r for r in rows}
    assert set(by) == {"450021", "453302"}                       # Travis County left out
    big = by["450021"]
    assert big["contract_labor"] == 0 and big["contract_labor_note"]  # Part V filed, no contract labor entered
    assert big["labor_share"] == "50.0%"                          # (400 + 100 + 0) / 1000
    nov = by["453302"]
    assert nov["labor_share"] == "" and nov["salaries_share"] == "25.0%" and nov["hospital_type"] == "children's"


def test_kind():
    assert LS.kind("450021") == "short-term acute" and LS.kind("451300") == "critical access" and LS.kind("454119") == "psychiatric"
