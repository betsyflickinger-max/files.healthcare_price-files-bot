"""Plain-language summary (reports/medicare-multiple/<st>/summary.md) from the summarize.py tables."""
from datetime import date

from sources import PUBLISHED
from summarize import ALL, EVIDENCE, RANGE

STATE = {"TX": "Texas"}


def x(v):
    return "—" if v is None else f"{v:.2f}×"


def n(v):
    return "—" if v is None else f"{int(v):,}"


def write_md(out, state, code_rows, bucket_rows, total_rows, coverage, providers, seg_rows=(), tails=(), methods=(), anes=()):
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
         f"- Every figure is shown three ways. **{ALL}**. **{EVIDENCE}** (the main view): the rate is at a provider that billed "
         "Medicare for that code in 2024 (or another clinician in the same practice did), or at a hospital whose own price file lists "
         "the code (or, for the hospital file's own rates, counts paid claims for it in 2026). High prices stay in this view. "
         f"**{RANGE}** (secondary): leaves out rates labeled \"may never be used\" (below 0.5× or above 8× Medicare, one amount for "
         "many unrelated codes, a kind of clinician that almost never bills the code; `docs/rate-labels.md`), so it is narrower by construction.",
         "- Rates under 0.5× and over 8× Medicare are listed in their own table below (`tails.csv`). Nothing is dropped or deleted.",
         "- Medicare billing data under-represents children's and pregnancy care (few Medicare patients), so for those the hospital's "
         "own file is the evidence that counts; doctor fees for them can look \"without evidence\" when they are real.",
         "- In-network, out-of-network and unclear plans are never mixed.", ""]
    L += ["## The two totals", "",
          "| Figure | Rates | (a) Weighted by Medicare's mix of care, which skews older | (b) Equal weight: middle of all codes' middles | Codes (b) | Codes with a Medicare volume (a) |",
          "|---|---|---|---|---|---|"]
    for f in figs:
        for which in (ALL, EVIDENCE, RANGE):
            r = T.get((f, which, ""))
            if r:
                L.append(f"| {f} | {which} | {x(r['medicare_use_weighted'])} | {x(r['equal_weight'])} | {n(r['codes'])} | {n(r['codes_weighted'])} |")
    L += ["", "Totals leave out facility fees at places not matched to a Medicare hospital or surgery center, and codes with no "
          "Medicare benchmark (both are counted below). The weighted total leaves out surgery centers (no Medicare surgery-center "
          "volume file was in scope). Anesthesia is in it per unit: its conversion-factor multiple, weighted by Medicare's "
          "allowed dollars for each anesthesia code in the state.", ""]
    # one table per bucket
    L += ["## By kind of care", ""]
    buckets = sorted({r["bucket"] for r in bucket_rows}, key=lambda b: (b.startswith("No Medicare"), b))
    B = {(r["bucket"], r["figure"], r["rates"]): r for r in bucket_rows}
    for b in buckets:
        L += [f"### {b}", "", "| Figure | Middle of code middles: all rates | evidence of use | range check | Weighted by Medicare use: all | evidence of use | range check | Codes with a figure | Codes with too few providers | Listed rates |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for f in figs:
            a, e, k = B.get((b, f, ALL)), B.get((b, f, EVIDENCE)), B.get((b, f, RANGE))
            if not a and not k and not e:
                continue
            a, e, k = a or {}, e or {}, k or {}
            L.append(f"| {f} | {x(a.get('middle_of_code_middles'))} | {x(e.get('middle_of_code_middles'))} | {x(k.get('middle_of_code_middles'))} | "
                     f"{x(a.get('medicare_use_weighted'))} | {x(e.get('medicare_use_weighted'))} | {x(k.get('medicare_use_weighted'))} | "
                     f"{n(a.get('codes_with_figure'))} | {n(a.get('codes_too_few_providers'))} | {n(a.get('units'))} |")
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
    # rates far from Medicare: their own table (never dropped)
    if tails:
        L += ["## Rates under 0.5× or over 8× Medicare", "",
              "Left out of the range check, kept everywhere else. \"With evidence\" = at a provider with evidence it does the service.", "",
              "| Source | Network status | Plans | Side | Listed rates | With evidence | Codes |", "|---|---|---|---|---|---|---|"]
        agg = {}
        for t in tails:
            k = (t["source"], t["status"], t["program"], t["side"])
            a = agg.setdefault(k, [0, 0, set()])
            a[0] += t["units"] or 0
            a[1] += t["units_with_evidence"] or 0
            a[2].add(t["code"])
        for (src, st, pg, side), (u, ev, cs) in sorted(agg.items()):
            L.append(f"| {src} | {st} | {pg} | {side} | {n(u)} | {n(ev)} | {n(len(cs))} |")
        top = sorted([t for t in tails if t["side"] == "over 8×" and t["source"] == "insurer"], key=lambda t: -(t["units"] or 0))[:10]
        if top:
            L += ["", "Insurer files, the 10 codes with the most rates over 8× Medicare:", "",
                  "| Code | Kind of care | Network status | Listed rates | With evidence | Highest multiple | Highest listed amount |",
                  "|---|---|---|---|---|---|---|"]
            for t in top:
                L.append(f"| {t['code']} | {t['bucket']} | {t['status']} | {n(t['units'])} | {n(t['units_with_evidence'])} | "
                         f"{x(t['highest_multiple'])} | ${t['highest_listed_amount']:,.2f} |")
        L += ["", "Every code and side: `tails.csv`.", ""]
    L += ["## Check against published studies", "",
          "| Published figure | Published | Ours (insurer files, in-network, weighted, all rates) | evidence of use | range check | Ours (hospital files, commercial in-network, weighted) |",
          "|---|---|---|---|---|---|"]
    sub = {"professional": "Doctor and clinician fees (all RBCS categories)", "inpatient": "Hospital stays (inpatient)",
           "outpatient": "Hospital outpatient facility fees", "hospital": "Hospitals: inpatient + outpatient"}
    for p in PUBLISHED:
        s = sub[p["kind"]]
        a = T.get(("Insurer files, in-network", ALL, s), {})
        e = T.get(("Insurer files, in-network", EVIDENCE, s), {})
        k = T.get(("Insurer files, in-network", RANGE, s), {})
        h = T.get(("Hospital files, commercial in-network", ALL, s), {})
        L.append(f"| [{p['name']}]({p['url']}) | {p['multiple']:.2f}× | {x(a.get('medicare_use_weighted'))} | {x(e.get('medicare_use_weighted'))} | "
                 f"{x(k.get('medicare_use_weighted'))} | {x(h.get('medicare_use_weighted'))} |")
    L += ["", "Why the numbers can differ (read before quoting any gap):", "",
          "- Published studies use **paid claims**: each price counts as often as it was used. Price files list every rate in every "
          "contract, used or not. Our weighted figure uses Medicare's own mix of care in this state to stand in for use.",
          "- RAND and KFF compare whole hospital stays and visits, including outlier payments and everything billed on the claim. "
          "We compare one code at a time and leave out Medicare's outlier payments.",
          "- Different years (RAND: 2022 claims; KFF: studies from 2010s-2020) and different places (most published figures are national).",
          "- Doctor fees: where the insurer's file doesn't say where the service happens, Medicare's amount is a blend of its "
          "facility and office rates in the proportions Medicare itself sees for that code in this state; `codes.csv` shows "
          "each code's middle against the facility rate and against the office rate (the low-high range).",
          "- Earlier DFW snapshot: insurer-file middles near 1.0× for outpatient facility fees and 0.88× for doctor fees, counting every "
          "listed rate once. Compare the equal-weight and weighted columns, and all rates vs evidence of use, to see how much "
          "of that came from counting rates that are never used.", ""]
    if anes:
        L += ["## Anesthesia amounts that look like a whole case", "",
              "Up to $200 is read as a per-unit conversion factor and compared with Medicare's; $400 and up as a whole case. "
              "Whole-case amounts are counted here, in dollars, with no multiple: Medicare pays per unit (base units plus time), "
              "and no public CMS source gives the typical time per code.", "",
              "| Source | Network status | Plans | Code | Listed rates | Middle listed amount | Lowest | Highest |", "|---|---|---|---|---|---|---|---|"]
        for a in anes[:25]:
            L.append(f"| {a['source']} | {a['status']} | {a['program']} | {a['code']} | {n(a['listed_rates'])} | ${a['middle_listed_amount']:,.2f} | "
                     f"${a['lowest']:,.2f} | ${a['highest']:,.2f} |")
        L += ["", f"All {len(anes)} rows: `anesthesia_per_case.csv`.", ""]
    if methods:
        L += ["## How each rate was handled", "", "| Question | Source | Network status | Method | Listed rates | Codes |", "|---|---|---|---|---|---|"]
        for m in methods:
            L.append(f"| {m['question']} | {m['source']} | {m['status']} | {m['method']} | {n(m['units'])} | {n(m['codes'])} |")
        L += ["", "Same table: `methods.csv`.", ""]
    # coverage
    L += ["## What went in, and what didn't", "",
          "| Source | Network status | Plans | What | Codes | Listed rates | With evidence of use | of which: billed Medicare | Range check |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in coverage:
        L.append(f"| {c['source']} | {c['status']} | {c['program']} | {c['what']} | {n(c['codes'])} | {n(c['units'])} | "
                 f"{n(c.get('units_with_evidence'))} | {n(c.get('evidence_medicare_billing'))} | {n(c.get('units_range_check'))} |")
    L += ["", "| Source | Network status | Plans | Kind of care | Providers (all rates) | with evidence of use | range check |", "|---|---|---|---|---|---|---|"]
    for p in providers:
        L.append(f"| {p['source']} | {p['status']} | {p['program']} | {p['bucket']} | {n(p['providers'])} | {n(p.get('providers_evidence'))} | {n(p.get('providers_range_check'))} |")
    L += ["", "Files next to this one: `codes.csv` (every code: 10th, middle and 90th percentile, providers, Medicare volume), "
          "`buckets.csv`, `totals.csv`, `tails.csv`, `coverage.csv`, `providers.csv`, `no_benchmark_codes.csv` (every code with no Medicare "
          "benchmark, with the reason), `medicare_sources.csv` (every CMS file used, with its year and SHA-256).", ""]
    (out / "summary.md").write_text("\n".join(L))
