"""Price File Watch: check each flagged insurer file's own dates (Oct 19, 2026).

One-off check, run by .github/workflows/watch-dates.yml. Changes no data. For every network of the insurers named
below (from the bot's own manifests in R2), it records:
  - the date in the file's name (url_date),
  - the "last_updated_on" date the bot saved when it last read the file, and when it last saw the file change,
  - a fresh read of the top of the file right now (first 256 KB only): its size and its own "last_updated_on".
It also opens BCBS North Carolina's current table of contents and lists every "Local" network file with its size,
to confirm the empty "Blue Local with Atrium" file.
Writes reports/watch/file-dates-<date>.md and .csv.
"""
import csv
import re
import sys
import zlib
from datetime import date
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bot")]
import check  # noqa: E402
import find_links  # noqa: E402
import store  # noqa: E402

WANT = {"bot/insurers/s7/": ("BCBS Alabama", "BCBS Mississippi"), "bot/insurers/nc/": ("BCBSNC",)}
NC_TOC = ("https://mrfmftprod.bcbsnc.com/prod/etl/outbound/table-of-contents/non-aso/"
          "{date}_blue-cross-and-blue-shield-of-north-carolina_index.json")
PEEK = 256 * 1024
OUT = HERE.parent / "reports" / "watch"


def peek(url):
    """Size and the file's own last_updated_on, from the first 256 KB. Never downloads the whole file."""
    try:
        with requests.get(url, headers={"User-Agent": check.UA, "Range": f"bytes=0-{PEEK - 1}"},
                          stream=True, timeout=60, allow_redirects=True) as r:
            if r.status_code >= 400:
                return dict(http=str(r.status_code), size="", inside="")
            head = r.raw.read(PEEK, decode_content=False)
            cr = r.headers.get("Content-Range", "")
            size = cr.rsplit("/", 1)[1] if "/" in cr else r.headers.get("Content-Length", "")
            http = str(r.status_code)
    except Exception as e:  # noqa: BLE001
        return dict(http=f"error: {type(e).__name__}", size="", inside="")
    if head[:2] == b"\x1f\x8b":
        try:
            head = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(head)
        except zlib.error:
            head = b""
    m = re.search(rb'"last_updated_on"\s*:\s*"([^"]*)"', head)
    return dict(http=http, size=size, inside=m.group(1).decode() if m else "(not found in first 256 KB)")


def main():
    s3, b = store.r2()
    today = date.today()
    rows = []
    for prefix, insurers in WANT.items():
        for m in store.read_csv(s3, b, prefix + "manifest.csv"):
            if m.get("insurer") not in insurers:
                continue
            url = m.get("url", "")
            now = peek(url) if url else dict(http="no link", size="", inside="")
            rows.append(dict(insurer=m["insurer"], network=m.get("network_label", ""), file=url.split("/")[-1].split("?")[0],
                             date_in_name=m.get("url_date", ""), saved_last_updated_on=m.get("file_last_updated_on", ""),
                             bot_last_changed=m.get("last_changed", ""), bot_last_checked=m.get("last_checked", ""),
                             today_http=now["http"], today_size=now["size"], today_last_updated_on=now["inside"], url=url))
    # BCBS NC: every "Local" network in the current table of contents
    local = []
    try:
        toc = find_links._toc_url(NC_TOC, today)
        text = find_links._get(toc)
        for u in sorted(set(re.findall(r'"location"\s*:\s*"([^"]+)"', text))):
            u = u.replace("\\/", "/")
            if "local" in u.split("?")[0].rsplit("/", 1)[-1].lower():
                p = peek(u)
                local.append(dict(file=u.split("?")[0].rsplit("/", 1)[-1], **p))
        toc_name = toc.rsplit("/", 1)[-1]
    except Exception as e:  # noqa: BLE001
        toc_name = f"could not open: {type(e).__name__}: {str(e)[:120]}"

    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / f"file-dates-{today.isoformat()}"
    with open(stem.with_suffix(".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["insurer"])
        w.writeheader()
        w.writerows(rows)
    lines = [f"# Price File Watch: file dates checked {today.isoformat()}", "",
             "date in name = from the link; saved = the file's own last_updated_on when the bot last read it; "
             "today = read fresh from the top of the file now.", "",
             "| Insurer | Network | Date in name | Saved last_updated_on | Bot saw it change | Today: HTTP | Today: size | Today: last_updated_on |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['insurer']} | {r['network']} | {r['date_in_name']} | {r['saved_last_updated_on']} | "
                     f"{r['bot_last_changed']} | {r['today_http']} | {r['today_size']} | {r['today_last_updated_on']} |")
    lines += ["", f"## BCBS North Carolina: 'Local' network files in {toc_name}", "",
              "| File | HTTP | Size (bytes) | last_updated_on |", "|---|---|---|---|"]
    lines += [f"| {x['file']} | {x['http']} | {x['size']} | {x['inside']} |" for x in local] or ["| (none found) | | | |"]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
