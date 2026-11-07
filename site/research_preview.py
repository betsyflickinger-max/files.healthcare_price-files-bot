"""Before/after preview of the Nov 7, 2026 research text (site/research_text.py). Deploys nothing.

  python site/research_preview.py              reads the live site bundle (R2 site/deploy/current.tgz, read only) and writes
                                               reports/research-preview/<page>-before.html and -after.html for the
                                               methodology page, the employer plans page, the insurers page and ONE DFW
                                               hospital page (default Baylor University Medical Center, CCN 450021) with
                                               the quality strip
  python site/research_preview.py --strip-only only the quality strip, from reports/care-compare/dfw-measures.csv
                                               (no storage keys needed): reports/research-preview/quality-strip-<ccn>.html
Nothing here changes the live site or R2. To go live, the calls move into site/ux_polish.py / site/hospital_profiles.py.
"""
import argparse
import csv
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import research_text as RT  # noqa: E402

OUT = ROOT / "reports" / "research-preview"
MEASURES = ROOT / "reports" / "care-compare" / "dfw-measures.csv"
PAGES = {"methodology": ("site/methodology/index.html", RT.methodology),
         "employer-plans": ("site/employer-plans/index.html", RT.employer_plans),
         "insurers": ("site/insurers/index.html", RT.insurer_page)}
SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Quality strip preview · {ccn}</title>
<style>:root{{--ink:#151515;--paper:#f6f1e7;--rule:#cfc6b4;--brick:#9b3a2a}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 "Public Sans",system-ui,sans-serif;padding:24px 16px}}
main{{max-width:760px;margin:0 auto}}h2{{font:700 24px/1.2 Georgia,serif;margin:0 0 6px}}.sub{{font-size:14px;opacity:.85}}
.tw{{overflow-x:auto}}.tbl{{border-collapse:collapse;width:100%;font-size:15px}}.tbl th,.tbl td{{text-align:left;padding:8px 10px 8px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.note{{font:12px monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--brick);margin:0 0 18px}}</style></head>
<body><main><p class="note">Preview only · not on the site · fragment shown without the page around it</p>
{strip}
</main></body></html>
"""


def strip_rows(ccn):
    return [r for r in csv.DictReader(open(MEASURES)) if r["ccn"] == ccn and r["kind"] == "hospital"]


def strip_only(ccn):
    rows = strip_rows(ccn)
    if not rows:
        sys.exit(f"no rows for CCN {ccn} in {MEASURES}")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"quality-strip-{ccn}.html"
    p.write_text(SHELL.format(ccn=ccn, strip=RT.quality_strip(rows)), encoding="utf-8")
    print(f"-> {p.relative_to(ROOT)}")


def full(ccn):
    sys.path.insert(0, str(ROOT / "bot"))
    import store
    s3, b = store.r2()
    d = Path("/tmp/research_preview")
    d.mkdir(parents=True, exist_ok=True)
    s3.download_file(b, "site/deploy/current.tgz", str(d / "site.tgz"))
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    with tarfile.open(d / "site.tgz") as t:
        mem = {m.name.lstrip("./"): m for m in t.getmembers() if m.isfile()}
        for name, (path, fn) in PAGES.items():
            if path not in mem:
                print(f"  {path} not in the bundle; skipped")
                continue
            before = t.extractfile(mem[path]).read().decode("utf-8")
            after = fn(before)
            (OUT / f"{name}-before.html").write_text(before, encoding="utf-8")
            (OUT / f"{name}-after.html").write_text(after, encoding="utf-8")
            done.append((name, before != after))
        hosp = None
        for name, m in mem.items():
            if name.startswith("site/hospitals/") and name.endswith("/index.html") and name != "site/hospitals/index.html":
                s = t.extractfile(m).read().decode("utf-8", "replace")
                if f"CCN {ccn}" in s or f">{ccn}<" in s or f"ccn={ccn}" in s or f"/{ccn}/" in s or f"CMS Certification Number {ccn}" in s:
                    hosp = (name, s)
                    break
        if hosp:
            after = RT.add_strip(hosp[1], RT.quality_strip(strip_rows(ccn)))
            (OUT / f"hospital-{ccn}-before.html").write_text(hosp[1], encoding="utf-8")
            (OUT / f"hospital-{ccn}-after.html").write_text(after, encoding="utf-8")
            done.append((f"hospital {ccn} ({hosp[0]})", hosp[1] != after))
        else:
            print(f"  no hospital page names CCN {ccn}; quality strip written on its own")
            strip_only(ccn)
    L = ["# Research text preview (nothing deployed)", "",
         "Before/after copies of live pages with site/research_text.py applied. Open the -after.html files in a browser.", "",
         "| Page | Changed |", "|---|---|"] + [f"| {n} | {'yes' if c else 'no (marker or anchor not found)'} |" for n, c in done]
    (OUT / "README.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccn", default="450021")
    ap.add_argument("--strip-only", action="store_true")
    a = ap.parse_args()
    strip_only(a.ccn) if a.strip_only else full(a.ccn)


if __name__ == "__main__":
    main()
