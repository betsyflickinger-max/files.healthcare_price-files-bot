"""The hospital file reader keeps the 2026 (CMS v3.0) allowed-amount fields: median, 10th and 90th percentile, and the
count of allowed amounts. Small made-up files in all three CMS layouts (CSV tall, CSV wide, JSON). No storage needed.
Run: python -m pytest tests/"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot"))
import reader  # noqa: E402

META = ("hospital_name,last_updated_on,version,location_name,hospital_address,license_number|TX,type_2_npi\n"
        "Test Hospital,2026-01-15,3.0.0,Test Hospital,1 Main St Dallas TX,12345,1234567890\n")


def codes(tmp_path):
    p = tmp_path / "codes.csv"
    p.write_text("code\n45378\n470\n")
    reader.load_codes(str(p))


def test_csv_tall(tmp_path):
    codes(tmp_path)
    f = tmp_path / "tall.csv"
    f.write_text(META + "description,code|1,code|1|type,setting,standard_charge|gross,payer_name,plan_name,"
                 "standard_charge|negotiated_dollar,standard_charge|negotiated_percentage,standard_charge|methodology,"
                 "median_amount,10th_percentile,90th_percentile,count,additional_generic_notes\n"
                 "Colonoscopy,45378,CPT,outpatient,3000,Aetna,PPO,,55,percent of total billed charges,1650.25,1200,2100.5,42,\n"
                 "Colonoscopy,45378,CPT,outpatient,3000,Cigna,OAP,,60,percent of total billed charges,1700,1300,2000,1 through 10,\n"
                 "Colonoscopy,45378,CPT,outpatient,3000,UHC,Choice,1400,,fee schedule,,,,,\n")
    rows = list(reader.parse_csv(str(f)))
    assert len(rows) == 3
    a, c, u = rows
    assert (a["median_amount"], a["p10_amount"], a["p90_amount"], a["allowed_count"]) == ("1650.25", "1200", "2100.5", "42")
    assert c["allowed_count"] == "1 through 10"
    assert u["allowed_count"] == "" and u["negotiated_dollar"] == "1400"


def test_csv_wide(tmp_path):
    codes(tmp_path)
    f = tmp_path / "wide.csv"
    f.write_text(META + "description,code|1,code|1|type,setting,standard_charge|gross,"
                 "standard_charge|Aetna|PPO|negotiated_percentage,standard_charge|Aetna|PPO|methodology,"
                 "median_amount|Aetna|PPO,10th_percentile|Aetna|PPO,90th_percentile|Aetna|PPO,count|Aetna|PPO\n"
                 "Major joint replacement,470,MS-DRG,inpatient,90000,45,percent of total billed charges,38000,31000,52000,0\n")
    rows = list(reader.parse_csv(str(f)))
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "470" and r["payer_name"] == "Aetna"
    assert (r["median_amount"], r["p10_amount"], r["p90_amount"], r["allowed_count"]) == ("38000", "31000", "52000", "0")


def test_json(tmp_path):
    codes(tmp_path)
    f = tmp_path / "h.json"
    f.write_text(json.dumps({
        "hospital_name": "Test Hospital", "last_updated_on": "2026-01-15", "version": "3.0.0",
        "location_name": ["Test Hospital"], "hospital_address": ["1 Main St"], "type_2_npi": ["1234567890"],
        "standard_charge_information": [{
            "description": "Colonoscopy", "code_information": [{"code": "45378", "type": "CPT"}],
            "standard_charges": [{"setting": "outpatient", "gross_charge": 3000, "payers_information": [
                {"payer_name": "Aetna", "plan_name": "PPO", "standard_charge_percentage": 55, "methodology": "percent of total billed charges",
                 "median_amount": 1650.25, "10th_percentile": 1200, "90th_percentile": 2100.5, "count": "42"},
                {"payer_name": "Cigna", "plan_name": "OAP", "standard_charge_algorithm": "see contract", "methodology": "other",
                 "median_amount": 1700, "10th_percentile": 1300, "90th_percentile": 2000, "count": "1 through 10"},
                {"payer_name": "UHC", "plan_name": "Choice", "standard_charge_dollar": 1400, "methodology": "fee schedule"}]}]}]}))
    rows = list(reader.parse_json(str(f)))
    assert len(rows) == 3
    a, c, u = rows
    assert (a["p10_amount"], a["p90_amount"], a["allowed_count"]) == (1200, 2100.5, "42")
    assert c["allowed_count"] == "1 through 10"
    assert u["allowed_count"] == "" and u["p10_amount"] == ""


def test_fields_written(tmp_path):
    """The bot writes rows with reader.FIELDS; the new columns are at the end so older column positions don't move."""
    assert reader.FIELDS[-3:] == ["p10_amount", "p90_amount", "allowed_count"]
    assert reader.FIELDS.index("median_amount") == 26


def test_count_number():
    assert reader.allowed_count_number("1 through 10") == (1, False)
    assert reader.allowed_count_number("25") == (25, True)
    assert reader.allowed_count_number("0") == (0, True)
    assert reader.allowed_count_number("") == (None, False)
    assert reader.allowed_count_number("2,025") == (None, False)   # CMS: a thousands separator is not allowed
