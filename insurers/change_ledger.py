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
  every other index   the monthly deep check (index_watch.py --deep, the 3rd) reads every index under 400 MB and keeps a
                      receipt of every file it names (bot/receipts/<month>/watch/). Each month's receipts are compared
                      with the month before: files dropped from or new in an index, an index a third smaller or half
                      again bigger, an index that went empty, and an index we read last month but can't read now
                      ("index format changed?", the Cigna zip of Nov 1, 2026)

  by hand             insurers/change_ledger_notes.csv: changes a person spotted that no check sees on its own (e.g. an
                      insurer changing the format of its index). Each row is added to the ledger once, by its id.

On top of that:
  possible renames    a network that disappears and a new one from the same insurer within 31 days, with similar names,
                      are marked as a possible rename of each other (a hint for Betsy to check, never merged)
  evidence            the day a network or index disappears, the insurer's public index/price-file page is saved to the
                      Wayback Machine, so there is a dated public record of what it said that day
                      (the monthly archive.org copy of every index on the 3rd keeps the before and after)

Check our reader first (Nov 2, 2026; Betsy: "I'm just trying to do this the right way and not miss anything"):
  when half or more of an insurer's networks (at least 3), or of an index's files, vanish at once, that is more often our
  reader breaking than the insurer dropping them (Cigna, Nov 1, 2026: a new zip format made all 139 networks look gone).
  Those rows get a "check" note, and every run with such a row writes out/change_alerts.md, which opens a GitHub issue.

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
          "possible_rename", "evidence", "source", "check"]
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
BIG = {"gone from index", "dropped from index", "index stopped answering", "file shrank", "file went empty", "rate count fell",
       "index shrank", "index went empty", "index format changed?"}
DROPS = ("gone from index", "dropped from index")
MASS_SHARE, MASS_MIN = 0.5, 3     # "check our reader first": half or more of an insurer's networks (at least 3) at once
FILE_ROWS = 25                    # an index that drops/adds more files than this gets one summary row, not one per file
LINK_CAP = 20000                  # index_watch.py checks (and keeps receipts for) at most this many files per index
CHECK = ("Check our reader first: {n} of {total} {what} vanished at once. That is more often our reader breaking (Cigna "
         "changed its index to a zip on Nov 1, 2026 and every network looked gone) than the insurer dropping them. "
         "Confirm before citing.")


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
                detail=detail[:300], possible_rename="", evidence="", source=source, check="")


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


def catalogs(s3, b, seen_ids, mass):
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
        cnt = ch.get("counts") or {}
        if cnt.get("before") and len(ch.get("dropped", [])) >= max(MASS_MIN, MASS_SHARE * cnt["before"]):
            mass[name] = (len(ch["dropped"]), cnt["before"])
        for kind, label in (("new", "new in index"), ("dropped", "dropped from index"), ("newly_empty", "file went empty")):
            for net in ch.get(kind, []):
                out.append(ev(label, name, "all states", net, source=src, key=f"cat|{ins}|{month}|{kind}|{net}"))
        for kind, label in (("shrank", "file shrank"), ("grew", "file grew")):
            for x in ch.get(kind, []):
                out.append(ev(label, name, "all states", x["network"], before=f"{x['before_gb']} GB", after=f"{x['now_gb']} GB",
                              source=src, key=f"cat|{ins}|{month}|{kind}|{x['network']}"))
    out = [e for e in out if e["id"] not in seen_ids]
    for e in out:
        if e["kind"] == "dropped from index" and e["insurer"] in mass:
            n, total = mass[e["insurer"]]
            e["check"] = CHECK.format(n=n, total=total, what=f"{e['insurer']} networks")
    return out


def file_key(name):
    """A rate file's name without what changes every month (dates, part numbers, hashes): the same network's file gets
    the same key in October and November."""
    s = (name or "").lower()
    for _ in range(2):
        s = re.sub(r"\.(json|gz|zip|csv)$", "", s)
    s = re.sub(r"20\d\d[-_]?\d\d(?:[-_]?\d\d)?", " ", s)
    s = re.sub(r"(?:part[-_]?)?\d+[-_]of[-_]\d+", " ", s)
    s = re.sub(r"[_-]\d{2}[_-]\d{2}$", " ", s)
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{16,}\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def receipts(s3, b, st):
    """Every other index, month over month, from the monthly deep check's receipts. Runs once per deep check (its
    summary file, deep/<month>.csv, is written last, so a run that is still going is never half compared)."""
    deep_keys = sorted(k for k in keys(s3, b, "bot/watch/indexes/deep/", ".csv")
                       if re.fullmatch(r"bot/watch/indexes/deep/\d{4}-\d{2}\.csv", k))
    if len(deep_keys) < 2:
        return [], st
    cur_k, prev_k = deep_keys[-1], deep_keys[-2]
    cur_m, prev_m = cur_k[-11:-4], prev_k[-11:-4]
    tag = f"{cur_m}|{s3.head_object(Bucket=b, Key=cur_k).get('ETag', '')}"
    if st == tag:
        return [], st
    deep = {m: {r["url"].split("?")[0]: r for r in store.read_csv(s3, b, k)} for m, k in ((cur_m, cur_k), (prev_m, prev_k))}

    def load(m):
        idx = {}
        for k in keys(s3, b, f"bot/receipts/{m}/watch/", ".csv"):
            for r in store.read_csv(s3, b, k):
                i = idx.setdefault(r["index_url"], dict(insurer=r["insurer"], state=r["state"], files={}))
                i["files"].setdefault(file_key(r["file_name"]), r["file_name"])
        return idx
    cur, prev = load(cur_m), load(prev_m)
    src = f"monthly deep check of every index, {cur_m} vs {prev_m}"
    out = []

    def add(kind, i, url, network, key, **kw):
        e = ev(kind, i["insurer"], i["state"] or "all states", network, source=src, key=f"rcpt|{cur_m}|{url}|{key}", **kw)
        out.append(e)
        return e

    for url, d in deep[cur_m].items():   # an index we could read last month and can't now: usually a format change
        p = deep[prev_m].get(url)
        if p and d.get("error", "").startswith("index unreadable") and not p.get("error") and (num(p.get("links")) or 0) > 0:
            e = add("index format changed?", dict(insurer=d["insurer"], state=d["state"]), url, "index file", "format",
                    before=f"{num(p['links']):,.0f} files named", after="unreadable",
                    detail=f"Read fine in {prev_m}; in {cur_m}: {d['error'][:150]}. {url}")
            e["check"] = ("Check our reader first: last month we could read this index and now we can't. Usually the "
                          "insurer changed its format; until our reader is fixed, nothing from this index is compared.")
    for url, p in prev.items():
        base = url.split("#")[0]
        d = deep[cur_m].get(base)
        if not d or d.get("error"):
            continue   # didn't answer or unreadable this month: the daily check and the row above cover it
        c = cur.get(url)
        n0 = len(p["files"])
        n1 = len(c["files"]) if c else 0
        sampled = (num(d.get("links")) or 0) > LINK_CAP or (num((deep[prev_m].get(base) or {}).get("links")) or 0) > LINK_CAP
        if sampled and "#" not in url:   # only a sample of the names was kept: compare the full counts instead
            n0, n1 = num(deep[prev_m][base]["links"]) or 0, num(d["links"]) or 0
        i = c or p
        if n0 and not n1:
            add("index went empty", i, url, "index file", "empty", before=f"{n0:,.0f} files named", after="none",
                detail=f"The index answers but names no files. {base}")
            continue
        if n0 and (n1 / n0 < SHRINK or n1 / n0 > GROW):
            e = add("index shrank" if n1 < n0 else "index grew", i, url, "index file", "size", before=f"{n0:,.0f} files named",
                    after=f"{n1:,.0f} files named", detail=f"{n1 / n0:.0%} of last month's count. {base}")
            if n1 / n0 <= 1 - MASS_SHARE and n0 >= MASS_MIN:
                e["check"] = CHECK.format(n=f"{n0 - n1:,.0f}", total=f"{n0:,.0f}", what="files in this index")
        if sampled or not c:
            continue
        gone = sorted(set(p["files"]) - set(c["files"]))
        born = sorted(set(c["files"]) - set(p["files"]))
        if len(gone) > len(p["files"]) / 2 and len(born) > len(c["files"]) / 2 and SHRINK <= n1 / n0 <= GROW:
            print(f"receipts: {i['insurer']}: file names change every month, compared by count only ({base})")
            continue
        mass_e = len(gone) >= max(MASS_MIN, MASS_SHARE * len(p["files"]))
        for kind, names, files in (("dropped from index", gone, p["files"]), ("new in index", born, c["files"])):
            if not names:
                continue
            if len(names) <= FILE_ROWS:
                rows = [add(kind, i, url, files[k], f"{kind}|{k}") for k in names]
            else:
                rows = [add(kind, i, url, f"{len(names):,} files", f"{kind}|many",
                            detail="e.g. " + ", ".join(files[k] for k in names[:5]))]
            if mass_e and kind == "dropped from index":
                for e in rows:
                    e["check"] = CHECK.format(n=len(gone), total=len(p["files"]), what="files in this index")
    return out, tag


def mark_mass(new, nets):
    """Pick-list networks: half or more of an insurer's (at least 3) gone in one run -> "check our reader first"."""
    total = {}
    for v in nets.values():
        total.setdefault(v["insurer"], set()).add(v["network"])
    gone = {}
    for e in new:
        if e["kind"] == "gone from index" and e["source"].startswith("pick-list"):
            gone.setdefault(e["insurer"], set()).add(e["network"])
    for ins, g in gone.items():
        t = len(total.get(ins, ()))
        if len(g) >= MASS_MIN and t and len(g) >= MASS_SHARE * t:
            for e in new:
                if e["kind"] == "gone from index" and e["insurer"] == ins and not e["check"]:
                    e["check"] = CHECK.format(n=len(g), total=t, what=f"{ins} pick-list networks")


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


def notes(seen_ids):
    p = HERE / "change_ledger_notes.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if r.get("id") and r["id"] not in seen_ids:
            e = ev(r.get("kind", "note"), r.get("insurer", ""), r.get("area", ""), r.get("network", ""), key=r["id"],
                   before=r.get("before", ""), after=r.get("after", ""), detail=r.get("detail", ""), source="logged by hand")
            e.update(seen_on=r.get("seen_on") or e["seen_on"], big=r.get("big", ""), evidence=r.get("evidence", ""))
            out.append(e)
    return out


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
    new_c = catalogs(s3, b, ids, {})
    new_r, rtag = receipts(s3, b, st.get("receipts", ""))
    new = [e for e in new_m + new_i + new_c + new_r + notes(ids) if e["id"] not in ids]
    mark_mass(new, nets)
    mark_renames(new, ledger)
    if not a.dry_run:
        save_evidence(new, idx, not a.no_wayback)

    print(("First run: recorded where every source stands. " if first else "") +
          f"{len(nets):,} pick-list networks, {len(idx):,} index files/pages watched; {len(new)} new changes "
          f"({sum(1 for e in new if e['big'])} big, {sum(1 for e in new if e['possible_rename'])} possible renames, "
          f"{sum(1 for e in new if e['check'])} to check)")
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
    chk = [e for e in new if e["check"]]
    if chk:   # the workflow opens a GitHub issue from this file
        groups = {}
        for e in chk:
            groups.setdefault((e["insurer"], e["kind"], e["check"]), []).append(e)
        body = [f"The change ledger found {len(chk)} change(s) on {date.today()} that look more like our reader breaking "
                f"than the insurer changing something. Check these before citing them. Nothing was deleted: the site "
                f"keeps the last good rates.", ""]
        for (ins, kind, why), es in groups.items():
            body += [f"### {ins}: {kind} ({len(es)})", "", why, "",
                     ", ".join(sorted({x['network'] for x in es}))[:1500], ""]
        body += ["Control center: https://files.healthcare/control#changes"]
        Path("out/change_alerts.md").write_text("\n".join(body) + "\n")
    if a.dry_run:
        return
    ledger += new
    store.write_csv(s3, b, C + "ledger.csv", ledger, FIELDS)   # rows are only ever added
    s3.put_object(Bucket=b, Key=C + "state.json",
                  Body=json.dumps(dict(at=now_iso(), nets=nets, idx=idx, receipts=rtag)).encode())
    rows, gone = to_control(s3, b, ledger, nets)
    print(f"control center: {len(rows)} changes, {len(gone)} networks missing from their insurer's list right now")


if __name__ == "__main__":
    main()
