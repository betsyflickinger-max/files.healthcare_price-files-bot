"""File Watch ledger: shared keys, time-sortable ids, one file per run, never overwritten (Story 1.2). Offline."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from watch import ledger  # noqa: E402


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock in milliseconds; also resets the same-millisecond counter."""
    t = [1_794_774_002_641]  # 2026-11-15T20:20:02.641Z
    monkeypatch.setattr(ledger, "_now_ms", lambda: t[0])
    monkeypatch.setattr(ledger, "_last", [0, 0])
    return t


def rec(eid="h:450001", **kw):
    return ledger.new_record("entity", eid, "test source", **kw)


def test_record_has_shared_keys_and_utc_time(clock):
    r = rec(name="A")
    assert list(r)[:5] == ["record_id", "type", "entity_id", "at", "source"]
    assert r["type"] == "entity" and r["entity_id"] == "h:450001" and r["source"] == "test source"
    assert r["at"] == "2026-11-15T20:20:02.641Z"
    assert len(r["record_id"]) == 26 and r["name"] == "A"


def test_record_ids_sort_by_time(clock):
    ids = []
    for step in (0, 0, 0, 5, 1000, 0, 60_000):  # several in the same millisecond, then later
        clock[0] += step
        ids.append(rec()["record_id"])
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_record_ids_still_sort_if_clock_steps_back(clock):
    a = rec()
    clock[0] -= 10_000
    b = rec()
    assert b["record_id"] > a["record_id"] and b["at"] >= a["at"]


def test_record_id_encodes_the_time(clock):
    r = rec()
    b32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    ms = 0
    for c in r["record_id"][:10]:
        ms = ms * 32 + b32.index(c)
    assert ms == clock[0]


@pytest.mark.parametrize("args,msg", [
    (("verdict", "h:450001", "s"), "unknown record type"),
    (("entity", "", "s"), "missing entity_id"),
    (("entity", "450001", "s"), "not '<kind>:<id>'"),
    (("entity", "h:450001", ""), "missing source"),
])
def test_bad_records_are_refused(clock, args, msg):
    with pytest.raises(ValueError, match=msg):
        ledger.new_record(*args)


def test_caller_cannot_set_ledger_keys(clock):
    with pytest.raises(ValueError, match="set by the ledger"):
        rec(at="2020-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="set by the ledger"):
        rec(record_id="X")


def test_result_records_need_the_ad3_result_keys(clock):
    with pytest.raises(ValueError, match="result record is missing"):
        ledger.new_record("result", "h:450001", "s", check_id="findable")
    r = ledger.new_record("result", "h:450001", "s", check_id="findable", rule_version_id="v1", run_id="r1",
                          state="passed", evidence_ids=[])
    assert r["state"] == "passed"


def test_all_ad3_types_and_entity_are_accepted(clock):
    for t in ("notice", "reply", "correction", "official_action", "rule_published", "submission", "entity"):
        assert ledger.new_record(t, "h:450001", "s")["type"] == t


def test_write_one_jsonl_file_per_run_under_the_utc_day(clock, tmp_path):
    rs = [rec("h:450001"), rec("h:450002")]
    where = ledger.write(rs, "run-1", f"local:{tmp_path}")
    path = tmp_path / "watch/ledger/2026/11/15/run-1.jsonl"
    assert where == str(path)
    lines = path.read_text().splitlines()
    assert [json.loads(x) for x in lines] == rs


def test_write_refuses_to_overwrite(clock, tmp_path):
    ledger.write([rec()], "run-1", f"local:{tmp_path}")
    path = tmp_path / "watch/ledger/2026/11/15/run-1.jsonl"
    before = path.read_text()
    with pytest.raises(FileExistsError):
        ledger.write([rec("h:999999")], "run-1", f"local:{tmp_path}")
    assert path.read_text() == before
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    assert ledger.run_exists("run-1", f"local:{tmp_path}") and not ledger.run_exists("run-2", f"local:{tmp_path}")


def test_write_nothing_writes_no_file(tmp_path):
    assert ledger.write([], "run-1", f"local:{tmp_path}") is None
    assert not (tmp_path / "watch").exists()


def test_run_id_is_checked_even_with_nothing_to_write(tmp_path):
    with pytest.raises(ValueError, match="run_id"):
        ledger.write([], "../x", f"local:{tmp_path}")


def test_successful_write_leaves_only_the_jsonl(clock, tmp_path):
    ledger.write([rec()], "run-1", f"local:{tmp_path}")
    day = tmp_path / "watch/ledger/2026/11/15"
    assert [p.name for p in day.iterdir()] == ["run-1.jsonl"]


def test_overwrite_refused_even_if_the_exists_check_is_fooled(clock, tmp_path, monkeypatch):
    ledger.write([rec()], "run-1", f"local:{tmp_path}")
    path = tmp_path / "watch/ledger/2026/11/15/run-1.jsonl"
    before = path.read_text()
    real = ledger.Path.exists
    monkeypatch.setattr(ledger.Path, "exists", lambda self, *a, **k: False if self == path else real(self, *a, **k))
    with pytest.raises(FileExistsError):
        ledger.write([rec("h:999999")], "run-1", f"local:{tmp_path}")
    monkeypatch.undo()
    assert path.read_text() == before
    assert [p.name for p in path.parent.iterdir()] == ["run-1.jsonl"]


@pytest.mark.parametrize("line,msg", [
    ("[1, 2]", "not a record"),
    ('"text"', "not a record"),
    ('{"record_id": "01M7GDVTYH6JVPV3SFYH82DPWJ", "type": "entity"}', "missing entity_id"),
    ('{"type": "entity", "entity_id": "h:450001"}', "missing record_id"),
])
def test_unreadable_ledger_lines_name_the_file_and_line(tmp_path, line, msg):
    day = tmp_path / "watch/ledger/2026/11/15"
    day.mkdir(parents=True)
    (day / "run-1.jsonl").write_text(line + "\n")
    with pytest.raises(ValueError, match=f"run-1.jsonl line 1: .*{msg}"):
        ledger.read_latest("entity", f"local:{tmp_path}")


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a b", None])
def test_bad_run_ids_are_refused(clock, tmp_path, bad):
    with pytest.raises(ValueError, match="run_id"):
        ledger.write([rec()], bad, f"local:{tmp_path}")


def test_read_latest_gives_newest_record_per_entity_of_that_type(clock, tmp_path):
    sink = f"local:{tmp_path}"
    old = rec("h:450001", name="Old name")
    other = rec("h:450002", name="Other")
    ledger.write([old, other], "run-1", sink)
    clock[0] += 86_400_000  # next day
    new = rec("h:450001", name="New name")
    note = ledger.new_record("notice", "h:450001", "s")
    ledger.write([new, note], "run-2", sink)
    latest = ledger.read_latest("entity", sink)
    assert latest == {"h:450001": new, "h:450002": other}
    assert list(ledger.read_all(sink, "entity")).count(old) == 1  # the old record stays
    assert ledger.read_latest("notice", sink) == {"h:450001": note}


def test_read_latest_on_empty_ledger(tmp_path):
    assert ledger.read_latest("entity", f"local:{tmp_path}") == {}


def test_bad_sink_is_refused():
    with pytest.raises(ValueError, match="sink"):
        ledger.open_sink("s3://bucket")


class FakeS3:
    def __init__(self):
        self.objects = {}

    head_error = None  # set to e.g. "403" to make every existence check fail

    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if self.head_error:
            raise ClientError({"Error": {"Code": self.head_error}}, "HeadObject")
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        import io
        return {"Body": io.BytesIO(self.objects[Key])}

    def get_paginator(self, name):
        objs = self.objects

        class P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in objs if k.startswith(Prefix)]}
        return P()


def test_storage_sink_uses_the_same_keys_and_refuses_to_overwrite(clock):
    pytest.importorskip("boto3")
    s3 = FakeS3()
    sink = ledger.StorageSink(s3, "bucket")
    r = rec()
    ledger.write([r], "run-1", sink)
    assert list(s3.objects) == ["watch/ledger/2026/11/15/run-1.jsonl"]
    assert ledger.read_latest("entity", sink) == {"h:450001": r}
    with pytest.raises(FileExistsError):
        ledger.write([rec("h:999999")], "run-1", sink)


@pytest.mark.parametrize("code", ["403", "SlowDown", "500"])
def test_storage_check_that_fails_never_lets_a_write_through(clock, code):
    pytest.importorskip("boto3")
    from botocore.exceptions import ClientError
    s3 = FakeS3()
    sink = ledger.StorageSink(s3, "bucket")
    ledger.write([rec()], "run-1", sink)
    before = dict(s3.objects)
    s3.head_error = code
    with pytest.raises(ClientError):
        ledger.write([rec("h:999999")], "run-1", sink)
    assert s3.objects == before
