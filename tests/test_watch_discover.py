"""Hospital list -> File Watch entity records (Story 1.2): every row of the I/O matrix, offline."""
import csv
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
from discover import index_domain  # noqa: E402
from watch import ledger  # noqa: E402
from watch.pipeline import discover_hospitals as dh  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "watch_hospitals.csv")
REAL = os.path.join(os.path.dirname(__file__), "..", "data", "hospitals.csv")


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "hospitals.csv"
    shutil.copy(FIXTURE, p)
    return p


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(dh, "source_commit", lambda path: "abc123")


def run(csv_path, tmp_path, capsys, *extra):
    code = dh.main(["--csv", str(csv_path), "--sink", f"local:{tmp_path / 'ledger'}", *extra])
    out = capsys.readouterr()
    return code, out.out, out.err


def files(tmp_path):
    return sorted((tmp_path / "ledger").rglob("*.jsonl"))


def records(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def edit(csv_path, ccn, **changes):
    rows = list(csv.DictReader(open(csv_path, newline="")))
    fields = list(rows[0])
    for r in rows:
        if r["ccn"] == ccn:
            r.update(changes)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def test_first_run_writes_one_entity_per_hospital(csv_path, tmp_path, capsys):
    code, out, err = run(csv_path, tmp_path, capsys)
    assert code == 0
    [f] = files(tmp_path)
    rs = records(f)
    assert [r["entity_id"] for r in rs] == ["h:020001", "h:450002", "h:450003", "h:450004"]
    assert all(r["type"] == "entity" and r["source_commit"] == "abc123" for r in rs)
    assert all(r["at"].endswith("Z") for r in rs)
    assert rs[0]["source"].startswith("CMS Provider Data Catalog via ")
    assert {k: rs[0][k] for k in dh.COMPARED} == {
        "ccn": "020001", "name": "PROVIDENCE ALASKA MEDICAL CENTER", "city": "ANCHORAGE", "state": "AK",
        "hospital_type": "Acute Care Hospitals", "expected_index_url": "https://providence.org/cms-hpt.txt",
        "location_status": "expected"}
    assert rs[0]["run_id"] == f.stem
    assert "4 new, 0 changed" in out


def test_own_site_file_link_gives_expected_location(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    r = ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")["h:450002"]
    assert r["expected_index_url"] == "https://ownsite-hospital.org/cms-hpt.txt"
    assert r["location_status"] == "expected"


@pytest.mark.parametrize("ccn", ["450003", "450004"])  # file only on a shared host; nothing known at all
def test_no_known_site_is_location_unknown_not_a_failure(csv_path, tmp_path, capsys, ccn):
    code, out, _ = run(csv_path, tmp_path, capsys)
    r = ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")[f"h:{ccn}"]
    assert code == 0
    assert r["location_status"] == "unknown" and r["expected_index_url"] is None
    assert "2 with location unknown" in out


def test_rerun_with_nothing_changed_writes_nothing(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    code, out, _ = run(csv_path, tmp_path, capsys)
    assert code == 0
    assert out.startswith("0 new, 0 changed")
    assert len(files(tmp_path)) == 1


def test_bookkeeping_columns_changing_is_not_a_change(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    edit(csv_path, "020001", last_sha256="zzz", last_bytes="99", last_archived_run="2026-11-05/nat")
    _, out, _ = run(csv_path, tmp_path, capsys)
    assert out.startswith("0 new, 0 changed")


def test_renamed_hospital_gets_one_new_record_and_the_old_stays(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    edit(csv_path, "020001", name="PROVIDENCE ALASKA MEDICAL CENTER (RENAMED)")
    code, out, _ = run(csv_path, tmp_path, capsys)
    assert code == 0 and out.startswith("0 new, 1 changed")
    first, second = files(tmp_path)  # run ids are ULIDs, so file names sort by time
    [new] = records(second)
    assert new["entity_id"] == "h:020001" and new["name"].endswith("(RENAMED)")
    old = [r for r in records(first) if r["entity_id"] == "h:020001"][0]
    assert old["name"] == "PROVIDENCE ALASKA MEDICAL CENTER"
    assert new["record_id"] > old["record_id"]
    assert ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")["h:020001"] == new


def test_file_link_added_moves_hospital_out_of_unknown(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    edit(csv_path, "450004", mrf_url="https://www.nosite-hospital.org/751234569_standardcharges.json")
    _, out, _ = run(csv_path, tmp_path, capsys)
    assert out.startswith("0 new, 1 changed")
    [new] = records(files(tmp_path)[1])
    assert new["entity_id"] == "h:450004" and new["location_status"] == "expected"
    assert new["expected_index_url"] == "https://nosite-hospital.org/cms-hpt.txt"


def test_bad_ccns_are_skipped_counted_and_warned(csv_path, tmp_path, capsys):
    code, out, err = run(csv_path, tmp_path, capsys)
    assert code == 0
    assert "2 skipped for a bad CCN" in out
    assert "'4500'" in err and "'4500055'" in err and err.count("warning") == 2
    ids = {r["entity_id"] for r in records(files(tmp_path)[0])}
    assert not any(i in ids for i in ("h:4500", "h:4500055"))


@pytest.mark.parametrize("bad", ["45000a", "45000", "45000５"])  # lowercase, 5 digits, non-ASCII digit
def test_ccn_must_be_six_digits_or_capital_letters(csv_path, tmp_path, capsys, bad):
    with open(csv_path, "a", encoding="utf-8") as f:
        f.write(f"{bad},ODD CCN HOSPITAL,DENTON,TX,Acute Care Hospitals,odd.org,,,,,,\n")
    _, out, err = run(csv_path, tmp_path, capsys)
    assert "3 skipped for a bad CCN" in out and repr(bad) in err
    assert len(records(files(tmp_path)[0])) == 4


def test_letters_in_a_ccn_are_allowed_when_capital(csv_path, tmp_path, capsys):
    with open(csv_path, "a") as f:
        f.write("45T001,LETTER CCN HOSPITAL,DENTON,TX,Acute Care Hospitals,letter.org,,,,,,\n")
    run(csv_path, tmp_path, capsys)
    assert "h:45T001" in ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")


def test_hospital_dropped_from_list_is_reported_not_written(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    lines = open(csv_path).read().splitlines(keepends=True)
    open(csv_path, "w").write("".join(l for l in lines if not l.startswith("450004,")))
    code, out, _ = run(csv_path, tmp_path, capsys)
    assert code == 0 and out.startswith("0 new, 0 changed")
    assert "1 in the ledger but no longer on the list" in out
    assert len(files(tmp_path)) == 1


def test_other_entity_kinds_are_not_counted_as_missing_hospitals(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys)
    ledger.write([ledger.new_record("entity", "i:12345", "test")], "insurer-run", f"local:{tmp_path / 'ledger'}")
    _, out, _ = run(csv_path, tmp_path, capsys)
    assert "no longer on the list" not in out


def test_csv_saved_with_a_bom_still_reads(csv_path, tmp_path, capsys):
    csv_path.write_bytes(b"\xef\xbb\xbf" + csv_path.read_bytes())
    code, out, _ = run(csv_path, tmp_path, capsys)
    assert code == 0 and out.startswith("4 new")


def test_csv_without_a_ccn_column_fails(tmp_path, capsys):
    p = tmp_path / "h.csv"
    p.write_text("id,name\n450001,A\n")
    code, _, err = run(p, tmp_path, capsys)
    assert code == 1 and "no 'ccn' column" in err and not files(tmp_path)


def test_every_row_skipped_fails(tmp_path, capsys):
    p = tmp_path / "h.csv"
    p.write_text("ccn,name\n4500,A\nabc,B\n")
    code, _, err = run(p, tmp_path, capsys)
    assert code == 1 and "all 2 rows were skipped" in err and not files(tmp_path)


def test_short_row_is_read_as_blanks(tmp_path, capsys):
    p = tmp_path / "h.csv"
    p.write_text(open(FIXTURE).readline() + "450009,SHORT ROW HOSPITAL,WACO\n")
    code, _, _ = run(p, tmp_path, capsys)
    r = ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")["h:450009"]
    assert code == 0 and r["location_status"] == "unknown" and r["state"] == ""


def test_bad_sink_is_an_error_line_not_a_traceback(csv_path, capsys):
    code = dh.main(["--csv", str(csv_path), "--sink", "s3://bucket"])
    assert code == 2 and "error: sink must be" in capsys.readouterr().err


def test_missing_storage_credentials_is_an_error_line(csv_path, capsys, monkeypatch):
    def no_keys():
        raise ValueError("Invalid endpoint: ")
    monkeypatch.setattr(ledger, "StorageSink", no_keys)
    code = dh.main(["--csv", str(csv_path), "--sink", "storage"])
    assert code == 2 and "error: Invalid endpoint" in capsys.readouterr().err


def test_default_sink_is_the_repo_out_folder_wherever_it_is_run(csv_path, tmp_path, capsys, monkeypatch):
    asked, real = [], ledger.open_sink
    monkeypatch.setattr(ledger, "open_sink", lambda spec: asked.append(spec) or real(f"local:{tmp_path / 'l'}"))
    monkeypatch.chdir(tmp_path)
    assert dh.main(["--csv", str(csv_path)]) == 0
    assert asked[0] == f"local:{dh.ROOT / 'out'}"


def test_storage_sink_first_run_then_rerun_writes_nothing(csv_path, capsys, monkeypatch):
    pytest.importorskip("boto3")
    from test_watch_ledger import FakeS3
    s3, real = FakeS3(), ledger.StorageSink
    monkeypatch.setattr(ledger, "StorageSink", lambda: real(s3, "bucket"))
    code = dh.main(["--csv", str(csv_path), "--sink", "storage"])
    out = capsys.readouterr().out
    assert code == 0 and out.startswith("4 new, 0 changed") and len(s3.objects) == 1
    code = dh.main(["--csv", str(csv_path), "--sink", "storage"])
    out = capsys.readouterr().out
    assert code == 0 and out.startswith("0 new, 0 changed") and len(s3.objects) == 1


def test_repeated_ccn_is_skipped(csv_path, tmp_path, capsys):
    with open(csv_path, "a") as f:
        f.write("020001,DUPLICATE,ANCHORAGE,AK,Acute Care Hospitals,dup.org,,,,,,\n")
    _, out, err = run(csv_path, tmp_path, capsys)
    assert "1 skipped as repeats" in out and "already listed" in err
    assert ledger.read_latest("entity", f"local:{tmp_path / 'ledger'}")["h:020001"]["name"] != "DUPLICATE"


def test_existing_run_file_is_never_overwritten(csv_path, tmp_path, capsys):
    run(csv_path, tmp_path, capsys, "--run-id", "run-1")
    [f] = files(tmp_path)
    before = f.read_text()
    edit(csv_path, "020001", name="CHANGED")  # something to write, so write() itself is tested too
    code, out, err = run(csv_path, tmp_path, capsys, "--run-id", "run-1")
    assert code != 0 and "never replaced" in err
    assert f.read_text() == before and len(files(tmp_path)) == 1


def test_write_refuses_even_if_the_up_front_check_is_missed(csv_path, tmp_path, capsys, monkeypatch):
    run(csv_path, tmp_path, capsys, "--run-id", "run-1")
    monkeypatch.setattr(ledger, "run_exists", lambda run_id, sink: False)
    edit(csv_path, "020001", name="CHANGED")
    code, _, err = run(csv_path, tmp_path, capsys, "--run-id", "run-1")
    assert code != 0 and "already exists" in err


def test_real_list_unknown_count_matches_index_domain(tmp_path, capsys):
    """The real data/hospitals.csv: one record per hospital, and 'unknown' exactly where index_domain() is blank
    (6,011 and 784 on Nov 15, 2026; the list changes as CMS updates it). A rerun writes nothing."""
    if not os.path.exists(REAL):
        pytest.skip("data/hospitals.csv is not here")
    rows = list(csv.DictReader(open(REAL, newline="", encoding="utf-8")))
    code, out, _ = run(REAL, tmp_path, capsys)
    assert code == 0
    [f] = files(tmp_path)
    rs = records(f)
    assert len(rs) == len({r["ccn"] for r in rows}) == len(rows)
    blank = sum(1 for r in rows if not index_domain(r))
    assert sum(r["location_status"] == "unknown" for r in rs) == blank
    assert rs[0]["source"] == "CMS Provider Data Catalog via data/hospitals.csv"
    ids = [r["record_id"] for r in rs]
    assert ids == sorted(ids)
    code, out, _ = run(REAL, tmp_path, capsys)
    assert code == 0 and out.startswith("0 new, 0 changed") and len(files(tmp_path)) == 1


def test_source_commit_falls_back_outside_git(tmp_path, monkeypatch):
    monkeypatch.undo()  # use the real source_commit
    p = tmp_path / "h.csv"
    p.write_text("ccn\n")
    monkeypatch.setenv("GITHUB_SHA", "deadbeef")
    from watch.pipeline import discover_hospitals as real
    assert real.source_commit(p) == "deadbeef"
