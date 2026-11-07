"""DFW quality measures from tiny made-up CMS files: not rated always has a reason; fewer-measures flag; no ranking.
Run: python -m pytest tests/"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site"))
import care_quality_dfw as Q  # noqa: E402


def w(p, header, rows):
    with open(p, "w", newline="") as f:
        x = csv.writer(f); x.writerow(header); x.writerows(rows)
    return p


def test_measures(tmp_path):
    gh = ["Facility ID", "Facility Name", "City/Town", "State", "ZIP Code", "County/Parish", "Hospital overall rating", "Hospital overall rating footnote"]
    for g in Q.GROUPS:
        gh += [f"{g} Group Measure Count", f"Count of Facility {g} Measures", f"{g} Group Footnote"]
    full = ["450001", "BIG", "DALLAS", "TX", "75201", "DALLAS", "4", ""] + ["10", "9", ""] * 5
    thin = ["450002", "SMALL", "PLANO", "TX", "75024", "COLLIN", "Not Available", "16"] + ["10", "1", ""] * 5
    away = ["450003", "FAR", "AUSTIN", "TX", "78701", "TRAVIS", "3", ""] + ["10", "9", ""] * 5
    cat = {k: dict(title=k, page="https://example/" + k, modified="2026-07-22") for k in Q.DATASETS}
    P = dict(gen=w(tmp_path / "g.csv", gh, [full, thin, away]),
             hc=w(tmp_path / "h.csv", ["Facility ID", "HCAHPS Measure ID", "HCAHPS Answer Description", "Patient Survey Star Rating",
                                        "Patient Survey Star Rating Footnote", "HCAHPS Answer Percent", "HCAHPS Answer Percent Footnote",
                                        "Number of Completed Surveys", "Start Date", "End Date"],
                  [["450001", "H_RECMND_DY", "Definitely recommend", "Not Applicable", "", "70", "", "500", "10/01/2024", "09/30/2025"]]),
             hcn=w(tmp_path / "hn.csv", ["HCAHPS Measure ID", "HCAHPS Answer Percent", "Start Date", "End Date"], [["H_RECMND_DY", "69", "", ""]]))
    fn = {"16": "There are too few measures or measure groups reported to calculate a star rating or measure group score."}
    out = Q.hospitals(P, cat, fn, {"DALLAS", "COLLIN"}, "2026-11-07")
    star = {r["ccn"]: r for r in out if r["measure_id"] == "overall_star"}
    assert set(star) == {"450001", "450002"}
    assert star["450001"]["value"] == "4" and not star["450001"]["fewer_measures_reported"]
    assert star["450002"]["value"] == "" and star["450002"]["not_rated_reason"].startswith("not rated. CMS footnote 16: There are too few")
    assert star["450002"]["fewer_measures_reported"] == "yes"
    rec = [r for r in out if r["measure_id"] == "H_RECMND_DY"][0]
    assert rec["value"] == "70" and rec["national_value"] == "69%" and "10/01/2024" in rec["data_period"]
    assert all(r["value"] != "" or r["not_rated_reason"] for r in out)       # never blank without a reason
    assert not any("score" in k or "rank" in k for k in Q.FIELDS)            # no composite score or rank column
