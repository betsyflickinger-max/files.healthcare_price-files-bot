"""Where the parsed hospital rows live, behind one setting (Nov 11, 2026; docs/hospital-rows-v2.md).

site/hosp_rows.json "use" picks the copy that readers prefer and that new parses are written to:
  v1  data/hosp_every/                  the rows the live site has always used (default; also used if the setting can't be read)
  v2  data/2026-11-11/hosp_every_v2/    the rebuild with the 2026 allowed-amount fields (site/hosp_rebuild.py)
With "use": "v1", every reader works exactly as before (one folder). With "use": "v2", readers take a file's v2 rows when
they exist and fall back to its v1 rows otherwise, so a state the rebuild hasn't covered yet keeps its pages and nothing is
parsed again just because of the switch. Both folders are kept; nothing here deletes anything.

Used by site/orchestrate.py, site/hosp_area.py, site/geo_build.py and analysis/medicare_multiple/run.py.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SETTING = os.path.join(HERE, "hosp_rows.json")
V1 = "data/hosp_every/"
V2 = "data/2026-11-11/hosp_every_v2/"


def setting(path=SETTING):
    """{"use": "v1"|"v2", "v1": prefix, "v2": prefix}. Anything unreadable or unknown means v1."""
    out = {"use": "v1", "v1": V1, "v2": V2}
    try:
        s = json.load(open(path))
        out.update({k: s[k] for k in ("use", "v1", "v2") if isinstance(s.get(k), str) and s[k].strip()})
    except Exception:
        pass
    if out["use"] not in ("v1", "v2"):
        out["use"] = "v1"
    for k in ("v1", "v2"):
        out[k] = out[k].rstrip("/") + "/"
    return out


def use(path=SETTING):
    return setting(path)["use"]


def write_prefix(path=SETTING):
    """The folder new parses go to (rows/, done/, logs): the one in use."""
    s = setting(path)
    return s[s["use"]]


def read_prefixes(path=SETTING):
    """Folders to look in for a file's rows, preferred first: [v1] while v1 is in use, [v2, v1] after the switch."""
    s = setting(path)
    return [s["v2"], s["v1"]] if s["use"] == "v2" else [s["v1"]]


def v2_prefix(path=SETTING):
    return setting(path)["v2"]


def rows_keys(list_keys, path=SETTING):
    """{sha16: (key, size)} for every file with parsed rows, each from the preferred folder that has it.
    list_keys(prefix) -> iterable of (key, size)."""
    out = {}
    for p in read_prefixes(path):
        for k, n in list_keys(p + "rows/"):
            if k.endswith(".parquet"):
                out.setdefault(k.rsplit("/", 1)[1][:-8], (k, n))
    return out
