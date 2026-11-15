"""The File Watch ledger: every fact is one record in an append-only JSONL file (AD-1 to AD-3).

Records are never edited or deleted. A changed fact is a new record; the latest record per entity wins.
One run writes one file, watch/ledger/YYYY/MM/DD/<run_id>.jsonl, either on disk or in object storage
(bot/store.r2(), R2 or B2 via STORAGE_ENDPOINT). Writing never replaces an existing file.

Shared keys on every record: record_id (ULID: sorts by time), type, entity_id, at (UTC ISO-8601), source.
"""
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1] / "bot"
PREFIX = "watch/ledger/"
SHARED_KEYS = ("record_id", "type", "entity_id", "at", "source")
# AD-3 record types, plus "entity" (Story 1.2): a hospital's registration and attributes.
TYPES = ("result", "notice", "reply", "correction", "official_action", "rule_published", "submission", "entity")
# Extra keys AD-3 requires on check results.
TYPE_KEYS = {"result": ("check_id", "rule_version_id", "run_id", "state", "evidence_ids")}
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ENTITY_ID = re.compile(r"^[a-z]+:\S+$")
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32, as ULID uses


def _store():
    """bot/store.py, imported the way the bot's own scripts do (bot/ on the path; insurers/bot.py shadows 'bot')."""
    if str(BOT_DIR) not in sys.path:
        sys.path.insert(0, str(BOT_DIR))
    import store
    return store


def _now_ms():
    return time.time_ns() // 1_000_000


_last = [0, 0]  # last (ms, 80-bit random) handed out, so ids made in the same millisecond still sort in order


def _ulid():
    """(ULID string, its millisecond time). Monotonic within this process, even if the clock steps back."""
    ms = _now_ms()
    if ms <= _last[0]:
        ms, rnd = _last[0], _last[1] + 1
        if rnd >= 1 << 80:  # 2^80 ids in one millisecond: move to the next millisecond
            ms, rnd = ms + 1, secrets.randbits(79)
    else:
        rnd = secrets.randbits(79)  # top bit clear leaves room to count up within a millisecond
    _last[:] = [ms, rnd]
    n = (ms << 80) | rnd
    return "".join(_B32[(n >> (5 * i)) & 31] for i in range(25, -1, -1)), ms


def new_id():
    return _ulid()[0]


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def validate(rec):
    """Raise ValueError unless rec has the shared keys (and its type's keys) with usable values."""
    missing = [k for k in SHARED_KEYS if rec.get(k) in (None, "")]
    if missing:
        raise ValueError(f"record is missing {', '.join(missing)}")
    if rec["type"] not in TYPES:
        raise ValueError(f"unknown record type {rec['type']!r}")
    if not isinstance(rec["entity_id"], str) or not ENTITY_ID.match(rec["entity_id"]):
        raise ValueError(f"entity_id {rec['entity_id']!r} is not '<kind>:<id>'")
    if not isinstance(rec["source"], str):
        raise ValueError("source must be text")
    if not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$", str(rec["at"])):
        raise ValueError(f"at {rec['at']!r} is not a UTC ISO-8601 time ending in Z")
    if not re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", str(rec["record_id"])):
        raise ValueError(f"record_id {rec['record_id']!r} is not a ULID")
    gone = [k for k in TYPE_KEYS.get(rec["type"], ()) if k not in rec]
    if gone:
        raise ValueError(f"{rec['type']} record is missing {', '.join(gone)}")
    return rec


def new_record(type, entity_id, source, **fields):
    """A new ledger record: record_id and at are set here, never by the caller."""
    taken = [k for k in SHARED_KEYS if k in fields]
    if taken:
        raise ValueError(f"{', '.join(taken)} are set by the ledger, not passed in")
    rid, ms = _ulid()
    return validate({"record_id": rid, "type": type, "entity_id": entity_id, "at": _iso(ms), "source": source,
                     **fields})


# ---- where the ledger lives -------------------------------------------------------------------------------

class LocalSink:
    """The ledger in a folder on disk: <root>/watch/ledger/..."""

    def __init__(self, root):
        self.root = Path(root)

    def __repr__(self):
        return f"local:{self.root}"

    def keys(self):
        base = self.root / PREFIX
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*.jsonl")) if base.is_dir() else []

    def read(self, key):
        return (self.root / key).read_text(encoding="utf-8")

    def put_new(self, key, body):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"{path} already exists; ledger files are never replaced")
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(body, encoding="utf-8")
            os.link(tmp, path)  # fails if the file appeared meanwhile: no overwrite, and no half-written file
        except FileExistsError:
            raise FileExistsError(f"{path} already exists; ledger files are never replaced") from None
        finally:
            tmp.unlink(missing_ok=True)
        return str(path)


class StorageSink:
    """The ledger in object storage, through bot/store.r2() (R2, or B2 when STORAGE_ENDPOINT is set)."""

    def __init__(self, s3=None, bucket=None):
        if s3 is None:
            s3, bucket = _store().r2()
        self.s3, self.bucket = s3, bucket

    def __repr__(self):
        return f"storage:{self.bucket}"

    def keys(self):
        out = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=PREFIX):
            out += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".jsonl")]
        return sorted(out)

    def read(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode("utf-8")

    def _exists(self, key):
        """Like bot/store.exists(), but only "not found" means absent: a refused or throttled check raises,
        so it can never let a write replace a file."""
        from botocore.exceptions import ClientError
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if str(e.response.get("Error", {}).get("Code")) in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_new(self, key, body):
        if self._exists(key):
            raise FileExistsError(f"{key} already exists in storage; ledger files are never replaced")
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body.encode("utf-8"),
                           ContentType="application/x-ndjson")
        return f"{self.bucket}/{key}"


def open_sink(sink):
    """'local:<dir>', 'storage', or a sink object."""
    if not isinstance(sink, str):
        return sink
    if sink == "storage":
        return StorageSink()
    if sink.startswith("local:") and sink[6:]:
        return LocalSink(sink[6:])
    raise ValueError(f"sink must be 'local:<dir>' or 'storage', not {sink!r}")


# ---- writing and reading ----------------------------------------------------------------------------------

def check_run_id(run_id):
    if not isinstance(run_id, str) or not RUN_ID.match(run_id):
        raise ValueError(f"run_id {run_id!r} must be letters, digits, '.', '_' or '-'")
    return run_id


def key_for(run_id, at):
    check_run_id(run_id)
    return f"{PREFIX}{at[:4]}/{at[5:7]}/{at[8:10]}/{run_id}.jsonl"


def run_exists(run_id, sink):
    """True if any day of the ledger already has a file for this run_id."""
    return any(k.endswith(f"/{run_id}.jsonl") for k in open_sink(sink).keys())


def write(records, run_id, sink):
    """Write one run's records as one JSONL file, dated by the first record's UTC day.

    Returns where it went, or None when there is nothing to write. Raises FileExistsError if that file exists.
    """
    check_run_id(run_id)
    records = [validate(r) for r in records]
    if not records:
        return None
    sink = open_sink(sink)
    body = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
    return sink.put_new(key_for(run_id, records[0]["at"]), body)


def read_all(sink, type=None):
    """Every record in the ledger (optionally of one type), in file order."""
    sink = open_sink(sink)
    for key in sink.keys():
        for n, line in enumerate(sink.read(key).splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{key} line {n}: not JSON ({e})") from None
            if not isinstance(rec, dict):
                raise ValueError(f"{key} line {n}: not a record (a JSON object)")
            missing = [k for k in ("record_id", "type", "entity_id") if k not in rec]
            if missing:
                raise ValueError(f"{key} line {n}: record is missing {', '.join(missing)}")
            if type is None or rec.get("type") == type:
                yield rec


def read_latest(type, sink):
    """{entity_id: the newest record of this type for that entity}, newest by record_id (ULIDs sort by time)."""
    latest = {}
    for rec in read_all(sink, type):
        cur = latest.get(rec["entity_id"])
        if cur is None or rec["record_id"] > cur["record_id"]:
            latest[rec["entity_id"]] = rec
    return latest
