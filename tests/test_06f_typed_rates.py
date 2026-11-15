"""Nov 15, 2026: typed_rates() must return a pyarrow Table on the pinned DuckDB (1.5.6), where .arrow() became a reader."""
import importlib.util
from pathlib import Path

import duckdb
import pyarrow as pa


def _06f():
    p = Path(__file__).resolve().parent.parent / "insurers" / "pipeline" / "06f_full_extract.py"
    import sys
    sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location("f06_test", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_typed_rates_returns_a_table_with_numbers():
    m = _06f()
    tbl = pa.table({"billing_code": ["99213", "99214", "x"], "negotiated_rate": ["80.5", "N/A", "1234567890123456789"]})
    out = m.typed_rates(tbl, duckdb.connect())
    assert isinstance(out, pa.Table)
    assert out.schema.field("negotiated_rate").type == pa.float64()
    assert out.column("negotiated_rate").to_pylist()[0] == 80.5
    assert out.column("negotiated_rate_text").to_pylist() == [None, "N/A", "1234567890123456789"]
