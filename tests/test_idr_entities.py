"""IDR entity (arbitration firm) counts for Texas dispute lines, from a made-up saved quarter. Run: python -m pytest tests/"""
import io
import os
import sys

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nsa"))
import idr_files as I  # noqa: E402


class Mem:
    def __init__(self):
        self.d = {}

    def put(self, k, data=None, path=None):
        self.d[k] = data

    def get(self, k):
        return self.d.get(k)


def test_entity_col():
    assert I.entity_col(["dispute_number", "idre_compensation", "certified_idr_entity_name"]) == "certified_idr_entity_name"
    assert I.entity_col(["dispute_number", "idre_compensation", "idre_compensation_num"]) is None


def test_texas_lines_by_entity():
    st = Mem()
    t = pa.table({"location_of_service": ["TX", "TX", "TX", "FL"], "payment_determination_outcome": ["In Favor of Provider/Facility/AA Provider"] * 4,
                  "certified_idr_entity_name": ["Firm A", "Firm A", "Firm B", "Firm A"], "idre_compensation": ["$1"] * 4})
    buf = io.BytesIO(); pq.write_table(t, buf); st.d["data/idr/disputes/2025-q3.parquet"] = buf.getvalue()
    ent = {}
    c = I.extra_counts(st, "2025-q3", ent)
    assert c["tx"] == 3 and ent == {("2025-q3", "Firm A"): 2, ("2025-q3", "Firm B"): 1}
    I.save_entities(st, ent)
    assert I.load_entities(st) == ent
    sec = "\n".join(I.entity_section(ent))
    assert "dispute lines" in sec and "| Firm A | 2 |" in sec
