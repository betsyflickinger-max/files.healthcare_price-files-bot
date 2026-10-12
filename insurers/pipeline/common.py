"""Shared paths and helpers for the Upfront DFW data pipeline (test copy)."""
import csv
import gzip
import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "raw"
CODES_FILE = Path(__file__).resolve().parent / "codes.csv"
csv.field_size_limit(sys.maxsize)
USER_AGENT = "UpfrontDFW-research/0.1 (price transparency research)"


def load_codes():
    with open(CODES_FILE, newline="", encoding="utf-8") as f:
        return {r["code"].strip(): r["plain_name"].strip() for r in csv.DictReader(f)}


def open_binary(path):
    path = str(path)
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    if path.endswith(".zip"):
        z = zipfile.ZipFile(path)
        inner = [n for n in z.namelist() if not n.endswith("/")][0]
        return z.open(inner)
    return open(path, "rb")


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    if s == "" or s.lower() in ("n/a", "na", "null", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# Rate tables come in two layouts (Oct 12, 2026). "flat": one row per NPI x price (npi column). "lines": one row per
# price x provider group (npiset + n_npi columns, no npi), with each distinct NPI list stored once in a matching
# npisets/<same name>.parquet. Joining the two gives back exactly the flat rows, so nothing is averaged or dropped.
FLAT_COLS = ["reporting_entity_name", "file_label", "last_updated_on", "billing_code_type", "billing_code", "name",
             "negotiation_arrangement", "npi", "tin", "tin_type", "negotiated_type", "negotiated_rate", "billing_class",
             "setting", "service_code", "billing_code_modifier", "expiration_date", "source_file", "source_url", "checked_on"]


def is_lines(con, rates):
    return "npiset" in {r[0] for r in con.execute(f"describe select * from read_parquet('{rates}')").fetchall()}


def rates_sql(con, rates, npisets):
    """A FROM-able query giving flat rows (FLAT_COLS) for either layout."""
    if not is_lines(con, rates):
        return f"read_parquet('{rates}')"
    cols = ", ".join("s.npi" if c == "npi" else f"l.{c}" for c in FLAT_COLS)
    return (f"(select {cols} from read_parquet('{rates}') l join "
            f"(select npiset, unnest(npis) npi from read_parquet('{npisets}')) s using (npiset))")
