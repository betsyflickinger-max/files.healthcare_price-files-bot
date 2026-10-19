"""Price check for big builds (Oct 18, 2026, Betsy OK'd).

Why: the Oct 16 Colorado/Georgia/Missouri rebuild (st-2026-10b) started on its own and, at the speed it actually ran, needed
~20 more days and ~$2,000 of rented machines, more than the credit left. Nobody saw that until it had run 27 hours.

How: a build runs for CHECK_AFTER_H hours, then its real speed (work units finished per hour) gives a projection of the
hours and dollars still needed. If that is over LIMIT_USD or LIMIT_H, and Betsy hasn't approved this build for that much
in build_approvals.json, the build stops its machines (finished work stays in R2), opens a GitHub issue (Betsy gets the
email) and waits. To let it go on: add {"<build id>": {"usd": <most it may spend>, "why": "..."}} to build_approvals.json.
A projection measured from real speed is used instead of a guess from file sizes: Georgia's batches were 10x slower than
their size suggested.

Used by site/orchestrate_states.py (state Price Finder builds).
"""
import json, os, time

CHECK_AFTER_H = 2      # measure this long before projecting (at 24 machines, at most ~$12 spent before the check)
LIMIT_USD = 100        # projected remaining spend that needs Betsy's OK
LIMIT_H = 24           # ...or projected remaining time
READ_LIMIT_H = 6       # Oct 18: a first step (reading files) longer than this with no batch finished is held too
HERE = os.path.dirname(os.path.abspath(__file__))


def approved_usd(bid):
    try:
        a = json.load(open(os.path.join(HERE, "build_approvals.json"))).get(bid) or {}
        return float(a.get("usd") or 0)
    except Exception:
        return 0.0


def projection(t0, done0, done_now, left, machines, usd_hour, now=None):
    """(hours left, dollars left, units per hour) from the speed since t0; None until CHECK_AFTER_H has passed."""
    now = now or time.time()
    hrs = (now - t0) / 3600
    if hrs < CHECK_AFTER_H:
        return None
    rate = max(done_now - done0, 0) / hrs
    if rate <= 0:
        return float("inf"), float("inf"), 0.0
    h = left / rate
    return h, h * machines * usd_hour, rate


def verdict(bid, proj):
    """'ok' or a short reason to hold."""
    if proj is None:
        return "ok"
    h, usd, _ = proj
    ok_usd = approved_usd(bid)
    if ok_usd:
        return "ok" if usd <= ok_usd * 1.25 else f"projected ${usd:,.0f} is over the approved ${ok_usd:,.0f}"
    if usd > LIMIT_USD or h > LIMIT_H:
        return f"projected ${usd:,.0f} and {h:,.0f} more hours (limits ${LIMIT_USD} / {LIMIT_H} h)"
    return "ok"
