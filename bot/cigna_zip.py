"""Cigna's table of contents, zip or not (Nov 2, 2026). No dependencies, so every reader can import it."""
import gzip
import io
import zipfile


def cigna_index_bytes(b):
    """Nov 2, 2026: from Nov 1 Cigna's table of contents is a .zip ("cigna-partners-toc-collection") holding five
    indexes: Cigna's own (cigna-health-life-insurance-company_index.json) and four partner plans' (HealthPartners, MVP,
    Priority Health, Sagamore). Until Oct it was one plain JSON file. Returns Cigna's own index either way.
    The bot had read the zip as text, found none of its networks, and marked them all 'not in Cigna's table of contents'."""
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    if b[:2] != b"PK":
        return b
    z = zipfile.ZipFile(io.BytesIO(b))
    name = next((n for n in z.namelist() if "cigna-health-life-insurance-company" in n), None)
    if not name:
        raise RuntimeError(f"Cigna's table-of-contents zip has no Cigna index: {z.namelist()}")
    return z.read(name)
