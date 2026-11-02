"""Change ledger (Nov 2, 2026; Betsy: "an interesting data point that I don't want us to lose").

Six Cigna networks dropped out of Cigna's table of contents on Nov 2. The bot kept their last good tables and opened a
problem issue, but nothing remembered the change itself. This keeps that memory: one append-only list of every big
change in what insurers publish, read from what the other jobs already record. It downloads no insurer files.

Where each kind of change comes from (all already in storage):
  pick-list networks  every area's manifest (bot/insurers/**/manifest.csv, checked every 6 hours by bot.py):
                      a network whose file vanished from the insurer's list ("gone from index") or came back,
                      a new file a third smaller or half again bigger than the last one, a big jump in its rate count
  whole indexes       the monthly insurer file catalog (catalog.py: Anthem, Cigna, UnitedHealthcare, Aetna, HCSC):
                      networks new or dropped since last month, files that shrank, grew or went empty
  every index/page    the daily index watch (index_watch.py): an index or price-file page that stopped answering, or
                      answers again

On top of that:
  possible renames    a network that disappears and a new one from the same insurer within 31 days, with similar names,
                      are marked as a possible rename of each other (a hint for Betsy to check, never merged)
  evidence            the day a network or index disappears, the insurer's public index/price-file page is saved to the
                      Wayback Machine, so there is a dated public record of what it said that day
                      (the monthly archive.org copy of every index on the 3rd keeps the before and after)

Nothing is ever deleted (Betsy's Oct 15 rule): rows are only added. The first run records where things stand and logs
no changes, except the catalog's own month-over-month lists, which are already changes.

Storage: bot/watch/changes/ledger.csv (every change), bot/watch/changes/state.json (last look at each source)
Control center: control/data/changes.json (the ledger, newest first) and control/data/changes_gone.json (networks
missing from their insurer's list right now), shown on the "Changes" tab (site/control_changes.py).
Run:  python insurers/change_ledger.py [--dry-run] [--no-wayback]
"""
import argparse
import csv
import io
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bot"))
sys.path.insert(0, str(HERE))
import store  # noqa: E402

C = "bot/watch/changes/"
FIELDS = ["id", "seen_on", "seen_at", "insurer", "area", "network", "kind", "big", "before", "after", "detail",
          "possible_rename", "evidence", "source"]
GONE_SIGN = "keeping the last good tables"
SHRINK, GROW = 0.67, 1.5          # the same lines catalog.py uses for "shrank" and "grew"
RENAME_DAYS, RENAME_SIM = 31, 0.6
WAYBACK_CAP = 12                  # pages saved per run at most
AREAS = {  # the bot's area codes (bot.py SCOPES) in words
    "dfw": "Dallas-Fort Worth", "tx": "Texas", "s7": "TN, CO, OK, AL, MS, MO, GA", "nc": "North Carolina",
    "ct": "Connecticut", "il": "Illinois", "n5": "NY, CA, VA, DC, FL, WI", "nyhf": "New York (Healthfirst)",
    "ar": "Arkansas", "b1": "MD, NM, MT", "la": "Louisiana", "b4": "IN, KY, OH", "az": "Arizona",
    "c1": "MI, ND, SD, IA, MN, NE, KS", "c2": "PA, DE, WV, NJ, MA, RI, VT, NH, ME, SC", "c3": "WA, OR, ID, UT, AK, NV, HI, WY",
    "skipil": "Illinois (skipped-network check)",
}
BIG = {"gone from index", "dropped from index", "index stopped answering", "file shrank", "file went empty", "rate count fell"}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_json(s3, b, key, default):
    try:
        return json.loads(s3.get_object(Bucket=b, Key=key)["Body"].read())
    except Exception:
        return default


def keys(s3, b, prefix, suffix):
    out, tok = [], None
    while True:
        kw = dict(Bucket=b, Prefix=prefix)
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        out += [o["Key"] for o in r.get("Contents", []) if o["Key"].endswith(suffix)]
        if not r.get("IsTruncated"):
            return out
        tok = r["NextContinuationToken"]


def num(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def gb(x):
    return f"{x / 1e9:.2f} GB" if x else ""


def norm(name, insurer=""):
    s = re.sub(r"\b20\d\d(-\d\d){0,2}\b", " ", (name or "").lower())
    for w in re.split(r"\W+", (insurer or "").lower()):
        if len(w) > 2:
            s = s.replace(w, " ")
    s = re.sub(r"in-network-rates|in network rates|insurance|company|health|life|of|the|inc", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def ev(kind, insurer, area, network, before="", after="", detail="", source="", key=""):
    today = date.today().isoformat()
    return dict(id=key or f"{kind}|{insurer}|{area}|{network}|{today}", seen_on=today, seen_at=now_iso(), insurer=insurer,
                area=area, network=network, kind=kind, big="yes" if kind in BIG else "", before=before, after=after,
                detail=detail[:300], possible_rename="", evidence="", source=source)


def manifests(s3, b, st, first):
    """Pick-list networks, every area: gone/back, file size and rate-count jumps."""
    out, seen = [], {}
    for k in keys(s3, b, "bot/insurers/", "manifest.csv"):
        scope = k[len("bot/insurers/"):-len("manifest.csv")].strip("/") or "dfw"
        area = AREAS.get(scope, scope)
        for m in store.read_csv(s3, b, k):
            if not m.get("slot"):
                continue
            nk = f"{scope}|{m['slot']}"
            cur = dict(insurer=m.get("insurer", ""), network=m.get("network_label") or m["slot"], area=area,
                       missing=GONE_SIGN in (m.get("detail") or ""), url_date=m.get("url_date", ""),
                       size=num(m.get("size")), rows=num(m.get("rows")), how=(m.get("detail") or "").split(";")[0],
                       enabled=m.get("enabled", "yes"))
            seen[nk] = cur
            p = st.get(nk)
            I, A, N = cur["insurer"], area, cur["network"]
            if first and cur["missing"]:   # already gone when the ledger started (e.g. Cigna's six on Nov 2): log it once
                out.append(ev("gone from index", I, A, N, before=f"last good file {cur['url_date'] or '?'}",
                              detail=f"Already missing when the change ledger started. {cur['how']}. The site keeps showing the last good rates.",
                              source="pick-list check (every 6 hours)"))
            if first or not p:
                continue
            if cur["missing"] and not p.get("missing"):
                out.append(ev("gone from index", I, A, N, before=f"last good file {p.get('url_date') or '?'}",
                              detail=f"{cur['how']}. The site keeps showing the last good rates.", source="pick-list check (every 6 hours)"))
            elif p.get("missing") and not cur["missing"]:
                out.append(ev("back in index", I, A, N, after=f"file dated {cur['url_date'] or '?'}", source="pick-list check (every 6 hours)"))
            if cur["url_date"] and p.get("url_date") and cur["url_date"] != p["url_date"] and cur["size"] and p.get("size"):
                r = cur["size"] / p["size"]
                if r < SHRINK or r > GROW:
                    out.append(ev("file shrank" if r < 1 else "file grew", I, A, N, before=f"{gb(p['size'])} ({p['url_date']})",
                                  after=f"{gb(cur['size'])} ({cur['url_date']})", detail=f"{r:.0%} of the last file's size",
                                  source="pick-list check (every 6 hours)"))
            if cur["rows"] and p.get("rows") and cur["rows"] != p["rows"]:
                r = cur["rows"] / p["rows"]
                if r < SHRINK or r > GROW:
                    out.append(ev("rate count fell" if r < 1 else "rate count rose", I, A, N, before=f"{p['rows']:,.0f} rates",
                                  after=f"{cur['rows']:,.0f} rates", detail=f"{r:.0%} of the last read (local providers only)",
                                  source="file read"))
    return out, seen


def catalogs(s3, b, seen_ids):
    """Whole-index changes from the monthly insurer file catalog (already month-over-month lists)."""
    out = []
    for k in keys(s3, b, "bot/catalog/", "/latest.json"):
        ins = k.split("/")[2]
        lat = get_json(s3, b, k, {})
        month = lat.get("month")
        if not month:
            continue
        ch = get_json(s3, b, f"bot/catalog/{ins}/{month}/changes.json", {})
        name = lat.get("name") or ins
        src = f"insurer file catalog, {month} vs last month"
        for kind, label in (("new", "new in index"), ("dropped", "dropped from index"), ("newly_empty", "file went empty")):
            for net in ch.get(kind, []):
                out.append(ev(label, name, "all states", net, source=src, key=f"cat|{ins}|{month}|{kind}|{net}"))
        for kind, label in (("shrank", "file shrank"), ("grew", "file grew")):
            for x in ch.get(kind, []):
                out.append(ev(label, name, "all states", x["network"], before=f"{x['before_gb']} GB", after=f"{x['now_gb']} GB",
                              source=src, key=f"cat|{ins}|{month}|{kind}|{x['network']}"))
    return [e for e in out if e["id"] not in seen_ids]


def indexes(s3, b, st, first):
    """Every known index and price-file page (daily index watch): stopped answering / answering again."""
    out, cur = [], {}
    for r in store.read_csv(s3, b, "bot/watch/indexes/latest.csv"):
        u = r.get("url")
        if not u:
            continue
        cur[u] = dict(status=r.get("status", ""), insurer=r.get("insurer", ""), state=r.get("state", ""), kind=r.get("kind", ""))
        p = st.get(u)
        if first or not p or p.get("status") == cur[u]["status"]:
            continue
        what = "index file" if r.get("kind") in ("index", "evidence") else "price-file page"
        if cur[u]["status"] != "ok" and p.get("status") == "ok":
            out.append(ev("index stopped answering", r.get("insurer", ""), r.get("state") or "all states", what,
                          after=cur[u]["status"], detail=f"HTTP {r.get('http') or '-'} {u}", source="index watch (daily)"))
        elif cur[u]["status"] == "ok" and p.get("status") != "ok":
            out.append(ev("index answering again", r.get("insurer", ""), r.get("state") or "all states", what,
                          before=p.get("status", ""), detail=u, source="index watch (daily)"))
    return out, cur


def mark_renames(new, ledger):
    """A disappearing network and a new one from the same insurer, close in time and name: a possible rename."""
    cutoff = (date.today() - timedelta(days=RENAME_DAYS)).isoformat()
    pool = [e for e in ledger + new if e["seen_on"] >= cutoff]
    gone = [e for e in pool if e["kind"] in ("gone from index", "dropped from index")]
    born = [e for e in pool if e["kind"] == "new in index"]
    for e in new:
        if e["kind"] in ("gone from index", "dropped from index"):
            others = born
        elif e["kind"] == "new in index":
            others = gone
        else:
            continue
        first_word = (e["insurer"].split() or [""])[0].lower()
        best, score = None, 0
        for o in others:
            if (o["insurer"].split() or [""])[0].lower() != first_word:
                continue
            sc = SequenceMatcher(None, norm(e["network"], e["insurer"]), norm(o["network"], o["insurer"])).ratio()
            if sc > score:
                best, score = o, sc
        if best and score >= RENAME_SIM:
            e["possible_rename"] = f"{best['network']} ({best['kind']} {best['seen_on']}; {score:.0%} alike)"


def save_evidence(new, idx, wayback):
    """The day something disappears: save the insurer's public index/price-file pages to the Wayback Machine."""
    if not wayback:
        return
    from index_watch import wayback_save
    done, n = {}, 0
    for e in new:
        if e["kind"] not in ("gone from index", "dropped from index", "index stopped answering"):
            continue
        first_word = (e["insurer"].split() or [""])[0].lower()
        urls = [u for u, r in idx.items() if first_word and r["insurer"].lower().startswith(first_word)
                and r["status"] == "ok" and "Signature=" not in u and "sig=" not in u][:2]
        if first_word == "cigna":
            urls = ["https://www.cigna.com/static/mrf/latest.json"] + urls[:1]
        got = []
        for u in urls:
            if u not in done:
                if n >= WAYBACK_CAP:
                    break
                done[u] = wayback_save(u)
                n += 1
            if done[u] == "wayback":
                got.append(f"https://web.archive.org/web/{date.today():%Y%m%d}/{u}")
        e["evidence"] = " ".join(got)


def to_control(s3, b, ledger, nets):
    cutoff = (date.today() - timedelta(days=400)).isoformat()
    rows = sorted((e for e in ledger if e["seen_on"] >= cutoff), key=lambda e: (e["seen_at"], e["id"]), reverse=True)
    gone = sorted(([dict(insurer=v["insurer"], area=v["area"], network=v["network"], last_good_file=v["url_date"], why=v["how"])
                    for v in nets.values() if v["missing"] and v.get("enabled", "yes") == "yes"]),
                  key=lambda r: (r["insurer"], r["network"], r["area"]))
    since = {}
    for e in ledger:   # when each still-missing network was first logged gone
        if e["kind"] == "gone from index":
            since[(e["insurer"], e["area"], e["network"])] = e["seen_on"]
    for g in gone:
        g["missing_since"] = since.get((g["insurer"], g["area"], g["network"]), "before Nov 2, 2026")
    for name, data in (("changes", rows), ("changes_gone", gone)):
        s3.put_object(Bucket=b, Key=f"control/data/{name}.json", Body=json.dumps(data, separators=(",", ":")).encode(),
                      ContentType="application/json", CacheControl="no-cache")
    return rows, gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="work it out and print; write nothing")
    ap.add_argument("--no-wayback", action="store_true", help="don't save evidence pages to the Wayback Machine")
    a = ap.parse_args()
    s3, b = store.r2()
    st = get_json(s3, b, C + "state.json", {})
    first = not st
    ledger = store.read_csv(s3, b, C + "ledger.csv")
    ids = {e["id"] for e in ledger}

    new_m, nets = manifests(s3, b, st.get("nets", {}), first)
    new_i, idx = indexes(s3, b, st.get("idx", {}), first)
    new_c = catalogs(s3, b, ids)
    new = [e for e in new_m + new_i + new_c if e["id"] not in ids]
    mark_renames(new, ledger)
    if not a.dry_run:
        save_evidence(new, idx, not a.no_wayback)

    print(("First run: recorded where every source stands. " if first else "") +
          f"{len(nets):,} pick-list networks, {len(idx):,} index files/pages watched; {len(new)} new changes "
          f"({sum(1 for e in new if e['big'])} big, {sum(1 for e in new if e['possible_rename'])} possible renames)")
    lines = []
    for e in sorted(new, key=lambda e: (not e["big"], e["insurer"], e["network"])):
        lines.append(f"| {e['kind']} | {e['insurer']} | {e['network']} | {e['area']} | "
                     f"{' → '.join(x for x in (e['before'], e['after']) if x)} | {e['possible_rename']} |")
    summary = ["## Change ledger", "", f"{len(new)} new changes this run."]
    if lines:
        summary += ["", "| Change | Insurer | Network | Area | Before → after | Possible rename of |", "|---|---|---|---|---|---|"] + lines[:200]
    Path("out").mkdir(exist_ok=True)
    Path("out/change_summary.md").write_text("\n".join(summary) + "\n")
    print("\n".join(lines[:60]))
    if a.dry_run:
        return
    ledger += new
    store.write_csv(s3, b, C + "ledger.csv", ledger, FIELDS)   # rows are only ever added
    s3.put_object(Bucket=b, Key=C + "state.json", Body=json.dumps(dict(at=now_iso(), nets=nets, idx=idx)).encode())
    rows, gone = to_control(s3, b, ledger, nets)
    print(f"control center: {len(rows)} changes, {len(gone)} networks missing from their insurer's list right now")


if __name__ == "__main__":
    main()
