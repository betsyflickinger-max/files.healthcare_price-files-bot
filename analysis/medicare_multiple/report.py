"""Plain-language summary (reports/medicare-multiple/<st>/summary.md) from the summarize.py tables."""
from datetime import date

from sources import PUBLISHED

STATE = {"TX": "Texas"}


def x(v):
    return "—" if v is None else f"{v:.2f}×"


def n(v):
    return "—" if v is None else f"{int(v):,}"


def write_md(out, state, code_rows, bucket_rows, total_rows, coverage, providers, seg_rows=()):
    name = STATE.get(state, state)
    figs = []
    for r in total_rows:
        if not r.get("subtotal") and r["figure"] not in figs:
            figs.append(r["figure"])
    T = {(r["figure"], r["rates"], r.get("subtotal") or ""): r for r in total_rows}
    L = [f"# Private prices as a multiple of Medicare: {name}", "",
         f"Built {date.today().isoformat()} by `analysis/medicare_multiple/` (method: `docs/medicare-multiple.md`). "
         "Each figure compares a negotiated rate with what Medicare pays for the same service, at the same kind of place, "
         f"in the same part of {name} (2026 Medicare rates; fiscal 2027 for hospital stays). "
         "1.50× means the private rate is one and a half times Medicare's.", "",
         "How to read it:", "",
         "- **Middle** is the middle listed rate, not an average. Every figure is an actual rate at that rank.",
         "- **Without likely-unused rates** leaves out rates labeled \"may never be used\" (far from Medicare, one amount for many "
         "unrelated codes, a kind of clinician that almost never bills the code; see `docs/rate-labels.md`). Those rates stay in the data. "
         "Because one label is \"below half or above 8 times Medicare\", this view is narrower by construction.",
         "- In-network, out-of-network and unclear plans are never mixed.", ""]
    L += ["## The two totals", "",
          "| Figure | Rates | (a) Weighted by Medicare's mix of care, which skews older | (b) Equal weight: middle of all codes' middles | Codes (b) | Codes with a Medicare volume (a) |",
          "|---|---|---|---|---|---|"]
    for f in figs:
        for which in ("all rates", "without likely-unused rates"):
            r = T.get((f, which, ""))
            if r:
                L.append(f"| {f} | {which} | {x(r['medicare_use_weighted'])} | {x(r['equal_weight'])} | {n(r['codes'])} | {n(r['codes_weighted'])} |")
    L += ["", "Totals leave out facility fees at places not matched to a Medicare hospital or surgery center, and codes with no "
          "Medicare benchmark (both are counted below). The weighted total also leaves out anesthesia (Medicare counts cases, "
          "the benchmark is per unit) and surgery centers (no Medicare surgery-center volume file was in scope).", ""]
    # one table per bucket
    L += ["## By kind of care", ""]
    buckets = sorted({r["bucket"] for r in bucket_rows}, key=lambda b: (b.startswith("No Medicare"), b))
    B = {(r["bucket"], r["figure"], r["rates"]): r for r in bucket_rows}
    for b in buckets:
        L += [f"### {b}", "", "| Figure | Middle of code middles: all rates | without likely-unused | Weighted by Medicare use: all | without likely-unused | Codes with a figure | Codes with too few providers | Listed rates |",
              "|---|---|---|---|---|---|---|---|"]
        for f in figs:
            a, k = B.get((b, f, "all rates")), B.get((b, f, "without likely-unused rates"))
            if not a and not k:
                continue
            a = a or {}
            k = k or {}
            L.append(f"| {f} | {x(a.get('middle_of_code_middles'))} | {x(k.get('middle_of_code_middles'))} | {x(a.get('medicare_use_weighted'))} | "
                     f"{x(k.get('medicare_use_weighted'))} | {n(a.get('codes_with_figure'))} | {n(a.get('codes_too_few_providers'))} | {n(a.get('units'))} |")
        L.append("")
    # market segment (only what the network's own name says)
    segs = [r for r in seg_rows if r["bucket"] == "(all kinds of care: equal weight)"]
    if segs:
        L += ["## By market segment (insurer files, in-network)", "",
              "The files don't carry a market segment field; a network counts as individual (marketplace) only when its own "
              "name says so (marketplace, exchange, individual, Ambetter, Oscar...). Everything else is \"not stated in file\".", "",
              "| Segment | Rates | Middle of code middles | Codes |", "|---|---|---|---|"]
        for r in segs:
            L.append(f"| {r['segment']} | {r['rates']} | {x(r['middle_of_code_middles'])} | {n(r['codes_with_figure'])} |")
        L += ["", "By kind of care: `buckets_by_segment.csv`.", ""]
    # sanity check
    L += ["## Check against published studies", "",
          "| Published figure | Published | Ours (insurer files, in-network, weighted, all rates) | without likely-unused | Ours (hospital files, commercial in-network, weighted) |",
          "|---|---|---|---|---|"]
    sub = {"professional": "Doctor and clinician fees (all RBCS categories)", "inpatient": "Hospital stays (inpatient)",
           "outpatient": "Hospital outpatient facility fees", "hospital": "Hospitals: inpatient + outpatient"}
    for p in PUBLISHED:
        s = sub[p["kind"]]
        a = T.get(("Insurer files, in-network", "all rates", s), {})
        k = T.get(("Insurer files, in-network", "without likely-unused rates", s), {})
        h = T.get(("Hospital files, commercial in-network", "all rates", s), {})
        L.append(f"| [{p['name']}]({p['url']}) | {p['multiple']:.2f}× | {x(a.get('medicare_use_weighted'))} | {x(k.get('medicare_use_weighted'))} | {x(h.get('medicare_use_weighted'))} |")
    L += ["", "Why the numbers can differ (read before quoting any gap):", "",
          "- Published studies use **paid claims**: each price counts as often as it was used. Price files list every rate in every "
          "contract, used or not. Our weighted figure uses Medicare's own mix of care in this state to stand in for use.",
          "- RAND and KFF compare whole hospital stays and visits, including outlier payments and everything billed on the claim. "
          "We compare one code at a time and leave out Medicare's outlier payments.",
          "- Different years (RAND: 2022 claims; KFF: studies from 2010s-2020) and different places (most published figures are national).",
          "- Doctor fees: a rate whose place of service isn't stated is compared with Medicare's office rate (the higher one), which "
          "makes our doctor figure lower than a study that knows where each visit happened.",
          "- Earlier DFW snapshot: insurer-file middles near 1.0× for outpatient facility fees and 0.88× for doctor fees, counting every "
          "listed rate once. Compare the equal-weight and weighted columns, and all rates vs without likely-unused, to see how much "
          "of that came from counting rates that are never used.", ""]
    # coverage
    L += ["## What went in, and what didn't", "",
          "| Source | Network status | Plans | What | Codes | Listed rates |", "|---|---|---|---|---|---|"]
    for c in coverage:
        L.append(f"| {c['source']} | {c['status']} | {c['program']} | {c['what']} | {n(c['codes'])} | {n(c['units'])} |")
    L += ["", "| Source | Network status | Plans | Kind of care | Providers (all rates) | Providers (without likely-unused) |", "|---|---|---|---|---|---|"]
    for p in providers:
        L.append(f"| {p['source']} | {p['status']} | {p['program']} | {p['bucket']} | {n(p['providers'])} | {n(p['providers_keep'])} |")
    L += ["", "Files next to this one: `codes.csv` (every code: 10th, middle and 90th percentile, providers, Medicare volume), "
          "`buckets.csv`, `totals.csv`, `coverage.csv`, `providers.csv`, `no_benchmark_codes.csv` (every code with no Medicare "
          "benchmark, with the reason), `medicare_sources.csv` (every CMS file used, with its year and SHA-256).", ""]
    (out / "summary.md").write_text("\n".join(L))
