"""Turn the bot's hospital list into File Watch `entity` records (Story 1.2).

The list is data/hospitals.csv: every hospital CMS's Provider Data Catalog says must post a price file (VA and
DoD left out), kept current by bot/refresh_list.py. Each hospital becomes entity h:<CCN>. Only hospitals that
are new, or whose attributes changed since their latest record, get a record; nothing is ever edited.

A hospital with no known site gets location_status "unknown" (never a failure). Nothing is fetched here: the
expected cms-hpt.txt location comes from bot/discover.index_domain().

    python -m watch.pipeline.discover_hospitals                      # writes to out/watch/ledger/...
    python -m watch.pipeline.discover_hospitals --sink storage       # the shared ledger in R2/B2
"""
import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "bot", ROOT):  # bot/ the way the bot's scripts import it; ROOT so this also runs as a script
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from discover import index_domain  # noqa: E402
from watch import ledger  # noqa: E402

DEFAULT_CSV = ROOT / "data" / "hospitals.csv"
SOURCE = "CMS Provider Data Catalog via {}"
# The attributes compared between runs. source/source_commit/run_id are provenance, not attributes.
COMPARED = ("ccn", "name", "city", "state", "hospital_type", "expected_index_url", "location_status")


def source_commit(path):
    """The git commit that last changed the list (marked if the file has uncommitted edits).

    Falls back to GITHUB_SHA, then 'unknown', when git can't say (no git, or the file isn't committed)."""
    path = Path(path).resolve()

    def git(*args):
        try:
            return subprocess.run(["git", "-C", str(path.parent), *args], capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    commit = git("log", "-1", "--format=%H", "--", path.name) or os.environ.get("GITHUB_SHA", "") or "unknown"
    if commit != "unknown" and git("status", "--porcelain", "--", path.name):
        commit += "+uncommitted"
    return commit


def _shown(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def entity_fields(row):
    domain = index_domain({k: ("" if v is None else v) for k, v in row.items()})  # short rows give None
    return {
        "ccn": row["ccn"].strip(),
        "name": (row.get("name") or "").strip(),
        "city": (row.get("city") or "").strip(),
        "state": (row.get("state") or "").strip(),
        "hospital_type": (row.get("type") or "").strip(),
        "expected_index_url": f"https://{domain}/cms-hpt.txt" if domain else None,
        # "expected": we know where cms-hpt.txt should be but haven't looked yet (Story 1.4 looks).
        "location_status": "expected" if domain else "unknown",
    }


def build(csv_path, sink, run_id, commit=None, warn=print):
    """Read the list and work out which records to write. Returns (records, counts)."""
    csv_path = Path(csv_path)
    commit = commit or source_commit(csv_path)
    source = SOURCE.format(_shown(csv_path))
    latest = ledger.read_latest("entity", sink)
    counts = dict(rows=0, new=0, changed=0, unchanged=0, bad_ccn=0, duplicate=0, unknown=0)
    seen, records = set(), []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:  # -sig: a BOM must not hide the ccn column
        reader = csv.DictReader(f)
        if "ccn" not in (reader.fieldnames or []):
            raise ValueError(f"{csv_path} has no 'ccn' column")
        for n, row in enumerate(reader, 2):  # line 1 is the header
            counts["rows"] += 1
            ccn = (row.get("ccn") or "").strip()
            if not re.fullmatch(r"[0-9A-Z]{6}", ccn):
                counts["bad_ccn"] += 1
                warn(f"warning: line {n}: skipped, CCN {ccn!r} is not 6 digits/capital letters "
                     f"({row.get('name', '')!r})")
                continue
            eid = f"h:{ccn}"
            if eid in seen:
                counts["duplicate"] += 1
                warn(f"warning: line {n}: skipped, CCN {ccn} already listed above")
                continue
            seen.add(eid)
            fields = entity_fields(row)
            counts["unknown"] += fields["location_status"] == "unknown"
            prev = latest.get(eid)
            if prev is not None and all(prev.get(k) == fields[k] for k in COMPARED):
                counts["unchanged"] += 1
                continue
            counts["changed" if prev is not None else "new"] += 1
            records.append(ledger.new_record("entity", eid, source, **fields, source_commit=commit, run_id=run_id))
    counts["not_in_list"] = sum(1 for e in set(latest) - seen if e.startswith("h:"))
    return records, counts


def summary(counts):
    s = (f"{counts['new']} new, {counts['changed']} changed, {counts['unchanged']} unchanged "
         f"({counts['rows']} rows; {counts['unknown']} with location unknown; "
         f"{counts['bad_ccn']} skipped for a bad CCN")
    if counts["duplicate"]:
        s += f"; {counts['duplicate']} skipped as repeats"
    if counts["not_in_list"]:
        s += f"; {counts['not_in_list']} in the ledger but no longer on the list, left as they are"
    return s + ")"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="hospital list (default data/hospitals.csv)")
    ap.add_argument("--sink", default=f"local:{ROOT / 'out'}", help="'local:<dir>' (default <repo>/out) or 'storage'")
    ap.add_argument("--run-id", default=None, help="names the ledger file (default discover-hospitals-<ULID>)")
    a = ap.parse_args(argv)
    run_id = a.run_id or f"discover-hospitals-{ledger.new_id()}"
    try:
        ledger.check_run_id(run_id)
        sink = ledger.open_sink(a.sink)
    except Exception as e:  # bad run id, bad --sink, or storage credentials missing
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        if ledger.run_exists(run_id, sink):
            print(f"error: the ledger already has a file for run {run_id}; ledger files are never replaced",
                  file=sys.stderr)
            return 1
        records, counts = build(a.csv, sink, run_id, warn=lambda m: print(m, file=sys.stderr))
        if counts["rows"] and counts["bad_ccn"] + counts["duplicate"] == counts["rows"]:
            print(f"error: all {counts['rows']} rows were skipped; is this the hospital list?", file=sys.stderr)
            return 1
        where = ledger.write(records, run_id, sink)
    except Exception as e:  # FileExistsError, unreadable list, storage errors: one line, not a traceback
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(summary(counts))
    print(f"wrote {len(records)} records to {where}" if where else "nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
