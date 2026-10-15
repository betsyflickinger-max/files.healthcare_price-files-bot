"""Whose mistake is each "wrong hospital's file"? (Oct 15, 2026) See bot/identity.py.

Usage: python bot/wrong_files_sort.py     writes reports/wrong_files_sorted.csv (+ R2 bot/reports/wrong_files_sorted.csv)

For every hospital ruled to be on another hospital's file, reads the hospital's own price-file listing (cms-hpt.txt, the
index every hospital must post) and sorts it into:
  check by hand        a listing that names exactly this hospital (both names match word for word, abbreviations allowed)
                       gives it a file whose address is elsewhere in its own state: the hospital points the public to
                       another location's prices, or posts one system file with its headquarters' address. Check each by
                       hand before calling it out on the Price File Watch (evidence: the listing and the line).
  our match            everything else: a namesake hospital's listing or file (often another state), a file the listing
                       gives to another location, or a link from the starting list or a search. The bot's mistake.
For each, says whether the hospital's listing has an entry under its own name with a different file (the daily run
switches to that one by itself now that the wrong link is ruled out) and gives that link.
"""
import csv
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover  # noqa: E402
import identity  # noqa: E402
import store  # noqa: E402
from name_ok import name_ok  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["who", "hospital", "city", "state", "ccn", "file_link", "file_says", "listing", "listed_as", "right_file_in_listing",
          "how_we_got_the_link", "reason"]


def ours(h, loc):
    return bool(loc) and (name_ok(h["name"], loc) or discover.score(h["name"], loc) >= 85)


def exactly(names, loc):   # word for word both ways (name_ok), so "Huntsville Hospital" is not "Huntsville Memorial Hospital"
    return bool(loc) and any(n and name_ok(n, loc) and name_ok(loc, n) for n in names)


def one(args):
    h, r = args
    url = r["mrf_url"]
    dom = discover.index_domain(h)
    idx, ents = discover.fetch_index(dom) if dom else ("", None)
    ents = ents or []
    hit = [e for e in ents if discover.clean(e["mrf-url"]) == discover.clean(url)]
    # only when the listing names exactly this hospital (Oct 15: Baptist Hospital Pensacola was offered South Miami Hospital's
    # file from Baptist Health South Florida's listing); the daily run's check still has the last word
    med0 = identity.medicare().get(h["ccn"], {})
    mine = [e for e in ents if exactly([h["name"], med0.get("name", "")], e.get("location-name", ""))
            and discover.clean(e["mrf-url"]) != discover.clean(url)]
    med = identity.medicare().get(h["ccn"], {})
    same_state = any(st == h["state"] for st, _ in identity.places(r.get("file_address", "")))
    if hit and same_state and any(exactly([h["name"], med.get("name", "")], e.get("location-name", "")) for e in hit):
        who = "check by hand"
    else:
        who = "our match"
    how = ("found by web search " + h["found_by"].split()[-1]) if (h.get("found_by") or "").startswith("web") else \
          "hospital's listing gives it to another location" if hit else \
          "hospital's listing doesn't include it" if ents else \
          "no listing found; link from the starting hospital list" if not h.get("found_by") else "site finder " + h["found_by"]
    return dict(who=who, hospital=h["name"].title(), city=h["city"].title(), state=h["state"], ccn=h["ccn"], file_link=url,
                file_says=r.get("file_address", "")[:150], listing=idx if ents else (idx + " (none)" if idx else ""),
                listed_as=" | ".join(e.get("location-name", "") for e in hit)[:150],
                right_file_in_listing=mine[0]["mrf-url"] if mine else "", how_we_got_the_link=how, reason=r.get("reason", "")[:200])


def main():
    s3, bucket = store.r2()
    wrong = [r for r in identity.load(s3, bucket).values() if r.get("verdict") == "wrong"]
    H = {h["ccn"]: h for h in csv.DictReader(open(ROOT / "data" / "hospitals.csv"))}
    jobs = [(H[r["ccn"]], r) for r in wrong if r["ccn"] in H]
    with ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(one, jobs))
    rows.sort(key=lambda r: (r["who"] != "check by hand", r["state"], r["hospital"]))
    out = io.StringIO()
    w = csv.DictWriter(out, FIELDS); w.writeheader(); w.writerows(rows)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "wrong_files_sorted.csv").write_text(out.getvalue())
    s3.put_object(Bucket=bucket, Key="bot/reports/wrong_files_sorted.csv", Body=out.getvalue().encode(), ContentType="text/csv")
    n = sum(r["who"] == "check by hand" for r in rows)
    print(f"{len(rows)} hospitals on another hospital's file: {len(rows) - n} the bot's own mismatch, {n} named exactly in a listing (check by hand); "
          f"{sum(bool(r['right_file_in_listing']) for r in rows)} have their own file in their listing", flush=True)


if __name__ == "__main__":
    main()
