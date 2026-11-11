"""Hospital rows v2 (docs/hospital-rows-v2.md): site/hosp_every.py keeps the 2026 allowed-amount fields at the end of each row,
leaves them blank for older files, and writes the live site's (v1) rows exactly as before. Small made-up hospital files in
the CMS layouts (CSV tall, CSV wide, JSON; template v2 without the fields and v3 with them). No storage, no keys.
The "old reader" is tests/fixtures/site_reader_nov11.py, a frozen copy of site/reader.py as the live site used it on
Nov 11, 2026 (before this change). Run: python -m pytest tests/test_hosp_rows_v2.py"""
import csv
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "site"), str(ROOT / "bot")]
import hosp_every as H  # noqa: E402
import hosp_rebuild as R  # noqa: E402
import hosp_rows  # noqa: E402

NEW = ["p10_amount", "p90_amount", "allowed_count", "file_version"]


def meta(version):
    return ("hospital_name,last_updated_on,version,location_name,hospital_address,license_number|TX,type_2_npi\n"
            f"Test Hospital,2026-01-15,{version},Test Hospital,1 Main St Dallas TX,12345,1234567890\n")


TALL_HEAD = ("description,code|1,code|1|type,code|2,code|2|type,modifiers,setting,billing_class,standard_charge|gross,"
             "standard_charge|discounted_cash,standard_charge|min,standard_charge|max,payer_name,plan_name,"
             "standard_charge|negotiated_dollar,standard_charge|negotiated_percentage,standard_charge|negotiated_algorithm,"
             "standard_charge|methodology")


def tall_v2(p):
    p.write_text(meta("2.0.0") + TALL_HEAD + ",estimated_amount,additional_generic_notes\n"
                 "Colonoscopy,45378,CPT,0750,RC,,outpatient,facility,3000,1500,900,4000,Aetna,PPO,1400,,,fee schedule,1450,\n"
                 'Colonoscopy,45378,CPT,0750,RC,,outpatient,facility,3000,1500,900,4000,Cigna,OAP,,55,,percent of total billed charges,,"note on\ntwo lines"\n'
                 "Knee replacement,470,MS-DRG,,,,inpatient,facility,90000,,,,UHC,Choice,32000,,,case rate,,\n"
                 "Room charge,0110,RC,,,,inpatient,facility,2000,,,,UHC,Choice,1800,,,per diem,,\n")
    return p


def tall_v3(p):
    p.write_text(meta("3.0.0") + TALL_HEAD + ",median_amount,10th_percentile,90th_percentile,count,additional_generic_notes\n"
                 "Colonoscopy,45378,CPT,0750,RC,,outpatient,facility,3000,1500,900,4000,Aetna,PPO,,55,,percent of total billed charges,1650.25,1200,2100.5,42,\n"
                 "Colonoscopy,45378,CPT,0750,RC,,outpatient,facility,3000,1500,900,4000,Cigna,OAP,,60,,percent of total billed charges,1700,1300,2000,1 through 10,\n"
                 "Colonoscopy,45378,CPT,0750,RC,,outpatient,facility,3000,1500,900,4000,UHC,Choice,1400,,,fee schedule,,,,0,\n"
                 "Knee replacement,470,MS-DRG,,,,inpatient,facility,90000,,,,Aetna,PPO,32000,,,case rate,,,,,\n")
    return p


def wide_v2(p):
    p.write_text(meta("2.0.0") + "description,code|1,code|1|type,setting,standard_charge|gross,"
                 "standard_charge|Aetna|PPO|negotiated_dollar,standard_charge|Aetna|PPO|methodology,estimated_amount|Aetna|PPO,"
                 "standard_charge|Cigna|OAP|negotiated_percentage,standard_charge|Cigna|OAP|methodology,estimated_amount|Cigna|OAP\n"
                 "Major joint replacement,470,MS-DRG,inpatient,90000,32000,case rate,31000,45,percent of total billed charges,\n"
                 "Colonoscopy,45378,CPT,outpatient,3000,1400,fee schedule,,,,\n")
    return p


def wide_v3(p):
    cols = []
    for pay in ("Aetna|PPO", "Cigna|OAP"):
        cols += [f"standard_charge|{pay}|negotiated_dollar", f"standard_charge|{pay}|negotiated_percentage",
                 f"standard_charge|{pay}|methodology", f"median_amount|{pay}", f"10th_percentile|{pay}",
                 f"90th_percentile|{pay}", f"count|{pay}"]
    p.write_text(meta("3.0.0") + "description,code|1,code|1|type,setting,standard_charge|gross," + ",".join(cols) + "\n"
                 "Major joint replacement,470,MS-DRG,inpatient,90000,,45,percent of total billed charges,38000,31000,52000,25,"
                 "33000,,case rate,,,,0\n"
                 "Colonoscopy,45378,CPT,outpatient,3000,1400,,fee schedule,1450,1200,1700,1 through 10,,,,,,,\n")
    return p


def json_file(p, v3):
    payers = [{"payer_name": "Aetna", "plan_name": "PPO", "standard_charge_percentage": 55, "methodology": "percent of total billed charges"},
              {"payer_name": "UHC", "plan_name": "Choice", "standard_charge_dollar": 1400, "methodology": "fee schedule"}]
    if v3:
        payers[0].update({"median_amount": 1650.25, "10th_percentile": 1200, "90th_percentile": 2100.5, "count": "42"})
        payers[1].update({"median_amount": 1400, "10th_percentile": 1400.0, "90th_percentile": 1400, "count": 12.0})
    else:
        payers[0]["estimated_amount"] = 1600
    doc = {"hospital_name": "Test Hospital", "last_updated_on": "2026-01-15", "version": "3.0.0" if v3 else "2.0.0",
           "location_name": ["Test Hospital"], "hospital_address": ["1 Main St"], "type_2_npi": ["1234567890"],
           "standard_charge_information": [
               {"description": "Colonoscopy", "code_information": [{"code": "45378", "type": "CPT"}],
                "standard_charges": [{"setting": "outpatient", "gross_charge": 3000, "discounted_cash": 1500,
                                      "payers_information": payers}]},
               {"description": "Knee", "code_information": [{"code": "470", "type": "MS-DRG"}],
                "standard_charges": [{"setting": "inpatient", "gross_charge": 90000}]}]}
    p.write_text(json.dumps(doc))   # (hosp_every.py strips a byte-order mark before it parses)
    return p


def codecols(p):
    p.write_text("description,CPT,HCPCS,MS-DRG,payer_name,plan_name,standard_charge,standard_charge_percent,methodology,"
                 "50th_percentile,10th_percentile,90th_percentile,count\n"
                 "Colonoscopy,45378,,,Aetna,PPO,1400,,fee schedule,1450,1200,1700,15\n"
                 "Knee,,,470,UHC,Choice,32000,,case rate,,,,\n")
    return p


MAKERS = {"tall_v2.csv": tall_v2, "tall_v3.csv": tall_v3, "wide_v2.csv": wide_v2, "wide_v3.csv": wide_v3,
          "v2.json": lambda p: json_file(p, False), "v3.json": lambda p: json_file(p, True)}
JOB = dict(key="raw/hospitals/2026-11/TX/abc_test.csv.zst", url="https://example.org/test.csv", name="Test Hospital")
SHA = "ab" * 32


def rows(path, tmp_path, fields, name="rows.csv"):
    out = tmp_path / name
    n = H.parse_to_csv(str(path), JOB, SHA, str(out), fields)
    with open(out, newline="") as f:
        got = list(csv.DictReader(f))
    assert len(got) == n
    return out, got


@pytest.fixture(scope="module")
def old_reader(tmp_path_factory):
    """The Nov 11 site/reader.py run the way hosp_every.py runs it: every line passes, hosp_every's code matcher."""
    src = (ROOT / "tests" / "fixtures" / "site_reader_nov11.py").read_text().split("def main():")[0]
    ns, argv = {"__name__": "old_reader"}, sys.argv
    sys.argv = ["x", str(ROOT / "site" / "codes89.csv"), "x", str(tmp_path_factory.mktemp("old_out"))]
    try:
        exec(src, ns)
    finally:
        sys.argv = argv
    ns["LINE_RE"], ns["match"] = re.compile(r""), H.match
    return ns


def old_rows(ns, path, tmp_path):
    parser = ns["parse_json"] if ns["is_json"](str(path)) else ns["parse_csv"]
    out = tmp_path / "old.csv"
    with open(out, "w", newline="") as fo:
        w = csv.DictWriter(fo, ns["FIELDS"], extrasaction="ignore")
        w.writeheader()
        for row in parser(str(path)):
            w.writerow(dict(row, raw_key=JOB["key"], source_url=JOB["url"], sha256=SHA, hospital_name=row.get("hospital_name") or JOB["name"]))
    return out


# ------------------------------------------------------------------ the live site's rows don't change

def test_fields_v2_appends_only():
    assert H.FIELDS_V2[:len(H.FIELDS)] == H.FIELDS
    assert H.FIELDS_V2[len(H.FIELDS):] == NEW


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_v1_rows_byte_identical_to_old_reader(name, tmp_path, old_reader):
    f = MAKERS[name](tmp_path / name)
    assert old_reader["FIELDS"] == H.FIELDS
    new, _ = rows(f, tmp_path, H.FIELDS)
    assert new.read_bytes() == old_rows(old_reader, f, tmp_path).read_bytes()


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_v2_old_columns_unchanged(name, tmp_path, old_reader):
    f = MAKERS[name](tmp_path / name)
    _, v2 = rows(f, tmp_path, H.FIELDS_V2)
    with open(old_rows(old_reader, f, tmp_path), newline="") as fo:
        old = list(csv.DictReader(fo))
    assert len(v2) == len(old) > 0
    assert [{k: r[k] for k in H.FIELDS} for r in v2] == old


# ------------------------------------------------------------------ the new columns

def test_tall_v3(tmp_path):
    _, r = rows(tall_v3(tmp_path / "t.csv"), tmp_path, H.FIELDS_V2)
    got = [(x["payer_name"], x["median_amount"], x["p10_amount"], x["p90_amount"], x["allowed_count"], x["file_version"]) for x in r]
    assert got == [("Aetna", "1650.25", "1200", "2100.5", "42", "3.0.0"), ("Cigna", "1700", "1300", "2000", "1 through 10", "3.0.0"),
                   ("UHC", "", "", "", "0", "3.0.0"), ("Aetna", "", "", "", "", "3.0.0")]


def test_wide_v3(tmp_path):
    _, r = rows(wide_v3(tmp_path / "w.csv"), tmp_path, H.FIELDS_V2)
    got = [(x["code"], x["payer_name"], x["median_amount"], x["p10_amount"], x["p90_amount"], x["allowed_count"]) for x in r]
    assert got == [("470", "Aetna", "38000", "31000", "52000", "25"), ("470", "Cigna", "", "", "", "0"),
                   ("45378", "Aetna", "1450", "1200", "1700", "1 through 10")]


def test_json_v3(tmp_path):
    _, r = rows(json_file(tmp_path / "h.json", True), tmp_path, H.FIELDS_V2)
    got = [(x["code"], x["payer_name"], x["p10_amount"], x["p90_amount"], x["allowed_count"], x["file_version"]) for x in r]
    assert got == [("45378", "Aetna", "1200", "2100.5", "42", "3.0.0"), ("45378", "UHC", "1400.0", "1400", "12", "3.0.0"),
                   ("470", "", "", "", "", "3.0.0")]


@pytest.mark.parametrize("name", ["tall_v2.csv", "wide_v2.csv", "v2.json"])
def test_old_files_blank_never_zero(name, tmp_path):
    _, r = rows(MAKERS[name](tmp_path / name), tmp_path, H.FIELDS_V2)
    assert r and all(x["p10_amount"] == x["p90_amount"] == x["allowed_count"] == "" for x in r)
    assert {x["file_version"] for x in r} == {"2.0.0"}


def test_codecols_layout(tmp_path):
    _, r = rows(codecols(tmp_path / "c.csv"), tmp_path, H.FIELDS_V2)
    assert [(x["code"], x["median_amount"], x["p10_amount"], x["p90_amount"], x["allowed_count"], x["file_version"]) for x in r] == \
        [("45378", "1450", "1200", "1700", "15", ""), ("470", "", "", "", "", "")]


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_same_fields_as_bot_reader(name, tmp_path):
    """The port matches bot/reader.py (PR #414) value for value on the 2026 fields."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bot_reader_414", ROOT / "bot" / "reader.py")
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    codes = tmp_path / "codes.csv"
    codes.write_text("code\n45378\n470\n")
    bot.load_codes(str(codes))
    f = MAKERS[name](tmp_path / name)
    theirs = list((bot.parse_json if bot.is_json(str(f)) else bot.parse_csv)(str(f)))
    _, ours = rows(f, tmp_path, H.FIELDS_V2)
    s = lambda v: "" if v in (None, "") else str(v)
    key = lambda x: (s(x.get("code")), s(x.get("payer_name")))
    assert sorted((key(x), s(x.get("median_amount")), s(x.get("p10_amount")), s(x.get("p90_amount")), s(x.get("allowed_count"))) for x in theirs) == \
        sorted((key(x), x["median_amount"], x["p10_amount"], x["p90_amount"], x["allowed_count"]) for x in ours)


def test_parquet_columns_and_blanks(tmp_path):
    import duckdb
    out, _ = rows(tall_v3(tmp_path / "t.csv"), tmp_path, H.FIELDS_V2)
    H.to_parquet(str(out), str(tmp_path / "v2.parquet"))
    out1, _ = rows(tall_v3(tmp_path / "t.csv"), tmp_path, H.FIELDS, "v1.csv")
    H.to_parquet(str(out1), str(tmp_path / "v1.parquet"))
    con = duckdb.connect()
    cols = lambda p: [x[0] for x in con.execute(f"describe select * from '{p}'").fetchall()]
    assert cols(tmp_path / "v1.parquet") == H.FIELDS
    assert cols(tmp_path / "v2.parquet") == H.FIELDS_V2
    # the evidence-of-use test analysis/medicare_multiple/rates.py runs: blank (NULL) counts are not "used"; "0" isn't either
    counted = con.execute(f"select coalesce(cast(allowed_count as varchar), '') not in ('', '0') from '{tmp_path / 'v2.parquet'}'").fetchall()
    assert [c[0] for c in counted] == [True, True, False, False]
    r = R.compare_files(str(tmp_path / "v1.parquet"), str(tmp_path / "v2.parquet"))
    assert r["old_columns_same"] is True and r["rows_with_count"] == 3 and r["file_version"] == "3.0.0"


def test_rows_version_from_setting(monkeypatch):
    monkeypatch.delenv("ROWS_VERSION", raising=False)
    assert H.is_v2("data/hosp_every/") is False
    assert H.is_v2(hosp_rows.V2) is True
    monkeypatch.setenv("ROWS_VERSION", "v2")
    assert H.is_v2("anything/") is True


# ------------------------------------------------------------------ the setting

def test_setting_defaults_to_old_rows():
    s = hosp_rows.setting()
    assert s["use"] == "v1" and s["v1"] == "data/hosp_every/"
    assert hosp_rows.write_prefix() == "data/hosp_every/"
    assert hosp_rows.read_prefixes() == ["data/hosp_every/"]
    assert re.fullmatch(r"data/\d{4}-\d{2}-\d{2}/hosp_every_v2/", s["v2"])


def test_setting_switch_and_fallback(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"use": "v2", "v1": "data/hosp_every", "v2": "data/x/hosp_every_v2"}))
    assert hosp_rows.read_prefixes(str(p)) == ["data/x/hosp_every_v2/", "data/hosp_every/"]
    assert hosp_rows.write_prefix(str(p)) == "data/x/hosp_every_v2/"
    listing = {"data/x/hosp_every_v2/rows/": [("data/x/hosp_every_v2/rows/aaaa.parquet", 5)],
               "data/hosp_every/rows/": [("data/hosp_every/rows/aaaa.parquet", 9), ("data/hosp_every/rows/bbbb.parquet", 7)]}
    got = hosp_rows.rows_keys(lambda pre: listing.get(pre, []), str(p))
    assert got == {"aaaa": ("data/x/hosp_every_v2/rows/aaaa.parquet", 5), "bbbb": ("data/hosp_every/rows/bbbb.parquet", 7)}
    p.write_text("{not json")
    assert hosp_rows.read_prefixes(str(p)) == ["data/hosp_every/"]
    p.write_text(json.dumps({"use": "v3"}))
    assert hosp_rows.use(str(p)) == "v1"


# ------------------------------------------------------------------ the rebuild workflow's checks

def test_pause_names_match_maintenance():
    text = (ROOT / "board" / "maintenance.py").read_text()
    assert f'TITLE = "{R.MAINT_TITLE}"' in text
    assert f'HOSPITAL_HOLD = "{R.HOSPITAL_HOLD}"' in text
    assert H.HOLD == R.HOSPITAL_HOLD


class _Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


def test_paused_issue():
    open_ = [{"number": 7, "title": "Something else"}, {"number": 493, "title": "Bot paused for maintenance: storage move"}]
    assert R.paused_issue("o/r", "t", get=lambda u, p: _Resp(200, open_)) == 493
    assert R.paused_issue("o/r", "t", get=lambda u, p: _Resp(200, open_[:1])) is None
    with pytest.raises(RuntimeError):
        R.paused_issue("o/r", "t", get=lambda u, p: _Resp(502, {}))
    with pytest.raises(RuntimeError):
        R.paused_issue("", "")


def test_jobs_for_scopes():
    listed = [dict(ccn="450021", name="BAYLOR DALLAS", state="TX", mrf_url="u1", last_key="raw/hospitals/x/a.json.zst",
                   last_sha256="a" * 64, last_bytes="2000000000"),
              dict(ccn="450068", name="MEMORIAL HERMANN", state="TX", mrf_url="u2", last_key="raw/hospitals/x/b.csv.zst",
                   last_sha256="b" * 64, last_bytes="1000000000"),
              dict(ccn="450069", name="SAME FILE AS ABOVE", state="TX", mrf_url="u2", last_key="raw/hospitals/x/b.csv.zst",
                   last_sha256="b" * 64, last_bytes="1000000000"),
              dict(ccn="010001", name="SOUTHEAST HEALTH", state="AL", mrf_url="u3", last_key="raw/hospitals/x/c.csv.zst",
                   last_sha256="c" * 64, last_bytes=""),
              dict(ccn="450070", name="NO FILE", state="TX", mrf_url="", last_key="", last_sha256="", last_bytes="")]
    z = R.zips()
    assert R.is_dfw(z["450021"]) and not R.is_dfw(z["450068"])
    tx = R.jobs_for("tx", listed=listed)
    assert [j["id"] for j in tx] == ["a" * 16, "b" * 16] and tx[0]["fmt"] == "json" and tx[1]["bytes"] == 1_000_000_000
    assert [j["id"] for j in R.jobs_for("dfw", listed=listed)] == ["a" * 16]
    assert [j["id"] for j in R.jobs_for("all", listed=listed)] == ["a" * 16, "b" * 16, "c" * 16]


def test_estimate():
    jobs = [dict(id="a", bytes=4_500_000_000, fmt="csv"), dict(id="b", bytes=3_000_000_000, fmt="json"), dict(id="c", bytes=0, fmt="csv")]
    e = R.estimate(jobs, machines=4, price=0.1, per_gb=0.01)
    assert e["files_to_parse"] == 3 and e["files_without_size"] == 1 and e["machines"] == 1
    secs = 1000 + 1000 + 3750e6 / 1e6 / 4.5 + 3 * R.FILE_OVERHEAD_S
    assert e["machine_hours"] == round(secs / 3600 + R.BOOT_H, 1)
    assert e["raw_gb"] == 11.2 and e["total_usd"] == round(e["machine_usd"] + e["storage_download_usd"], 2)
    assert R.estimate(jobs, done={"a", "b", "c"})["files_to_parse"] == 0


def test_free_machines_respects_shares_reserve_and_card():
    class D:
        def __init__(self, room, names): self._room, self._names = room, names
        def names(self): return self._names
        def limit(self): return 25
        def room(self): return self._room
    class S:
        def __init__(self, cap): self.cap, self.seen = cap, None
        def build_cap(self, bid, limit, reserve, names, s3, b, log=print):
            self.seen = (bid, limit, reserve); return self.cap
    me = R.bid("tx")
    s = S(6)
    assert R.free_machines(4, 336, None, None, "tx", D(room=10, names=[]), s) == 4
    assert s.seen == (me, 25, R.RESERVE_SLOTS) and me.endswith("a")         # counted as a rebuild (machine_shares)
    assert R.free_machines(4, 336, None, None, "tx", D(room=3, names=[]), S(6)) == 1      # 2 slots always left free
    assert R.free_machines(4, 336, None, None, "tx", D(room=0, names=[]), S(6)) == 0      # room() is 0 at the card cap
    assert R.free_machines(4, 336, None, None, "tx", D(room=10, names=[f"upfront-site-{me}-0"] * 5), S(6)) == 1   # cap counts its own
    assert R.free_machines(4, 15, None, None, "tx", D(room=10, names=[]), S(6)) == 2     # not more machines than files need


def test_start_needs_yes(monkeypatch):
    class A:
        confirm, scope = "no", "tx"
    with pytest.raises(SystemExit, match="confirm = yes"):
        R.cmd_start(A, None, None)


def test_workflow_is_manual_only():
    wf = (ROOT / ".github" / "workflows" / "hosp-rows-v2.yml").read_text()
    assert "workflow_dispatch" in wf and "schedule" not in wf and "cron" not in wf
    for word in ("estimate", "start", "status", "confirm", "dfw", "tx", "all"):
        assert word in wf
