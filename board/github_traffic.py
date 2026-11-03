"""Who's looking at Betsy's GitHub (Nov 3, 2026, Betsy): daily save of GitHub's traffic numbers, kept past 14 days.

GitHub never says WHO viewed a profile or repo, so nothing here can name a viewer. What it does give, and this keeps:
  - views and copies (clones) per day, with unique counts: GitHub keeps only the last 14 days, so each run merges them
    into a running history (a day's newest numbers win; today's are partial until tomorrow's run)
  - where visitors came from (referring sites) and which pages they read: 14-day totals, saved once a day
  - people who left a trace: who starred or forked a repo (with the date), who watches it, who follows Betsy
    (GitHub gives no follow date, so "first seen" is the day this job first saw them)
Clones are mostly the bot's own machines copying the code; the page says so.

Repos: every public repo Betsy owns (forks left out), plus any named in GITHUB_TRAFFIC_REPOS (comma-separated, e.g. a
private one the token can see). Traffic numbers need a token with "Administration: Read-only" on that repo
(fine-grained) or "repo" scope (classic); a repo the token can't read is listed with "no access" and the job goes on.
Token: GH_TRAFFIC_TOKEN (the workflow passes secrets.TRAFFIC_TOKEN, falling back to secrets.BOT_GITHUB_TOKEN).

Writes R2 control/data/github_traffic.json (read by the control center's Visitors tab card, site/control_github.py) and
a dated copy at logs/github-traffic/<date>.json (never deleted). Never stops the workflow on an API or storage error.

Usage:  python board/github_traffic.py              fetch, merge with the saved history, write to R2
        python board/github_traffic.py --dry-run    fetch and merge, write out/board/github_traffic.json only
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = os.environ.get("GITHUB_TRAFFIC_OWNER", "betsyflickinger-max")
OUT = "out/board"
KEY = "control/data/github_traffic.json"
TOKEN = "".join(os.environ.get("GH_TRAFFIC_TOKEN", "").split())
BASIC = "".join(os.environ.get("GH_BASIC_TOKEN", "").split())   # the workflow's own key
BOTKEY = "".join(os.environ.get("GH_BOT_TOKEN", "").split())     # the machines' key (Actions on this repo)
NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")


def gh(path, accept="application/vnd.github+json", auth=True, key=None):
    """(status, data) for one GitHub API GET; status 0 = network error. Follows Link pages for lists (up to 10)."""
    url, out = f"https://api.github.com/{path}", None
    for _ in range(10):
        req = urllib.request.Request(url, headers={"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
                                                   "User-Agent": "files-healthcare-traffic"})
        if auth and (key or TOKEN):
            req.add_header("Authorization", f"Bearer {key or TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data, link = json.loads(r.read() or b"null"), r.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception as e:   # noqa: BLE001
            print("network error:", path, e)
            return 0, None
        if not isinstance(data, list):
            return 200, data
        out = (out or []) + data
        nxt = [p.split(";")[0].strip(" <>") for p in link.split(",") if 'rel="next"' in p]
        if not nxt:
            break
        url = nxt[0]
    return 200, out


def s3_client():
    import boto3
    e = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    c = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{e['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                     aws_access_key_id=e["R2_ACCESS_KEY_ID"], aws_secret_access_key=e["R2_SECRET_ACCESS_KEY"],
                     region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    return c, e["R2_BUCKET"]


def load_previous(dry):
    """The saved history (R2 in a real run; out/board in a dry run), or an empty one."""
    try:
        if dry:
            return json.load(open(f"{OUT}/github_traffic.json"))
        c, b = s3_client()
        return json.loads(c.get_object(Bucket=b, Key=KEY)["Body"].read())
    except Exception:   # noqa: BLE001 (first run, or storage down: start fresh, the dated copies keep older runs)
        return {}


def repos():
    st, data = gh_public(f"users/{OWNER}/repos?per_page=100&type=owner")
    names = [r["name"] for r in (data or []) if not r.get("fork") and not r.get("private")] if st == 200 else []
    extra = [n.strip().split("/")[-1] for n in os.environ.get("GITHUB_TRAFFIC_REPOS", "").split(",") if n.strip()]
    return sorted(set(names) | set(extra)) or ["files.healthcare_price-files-bot"]


def gh_public(path, accept="application/vnd.github+json"):
    """A public list (stars, watchers, followers, repos): tries the traffic key, the machines' key, the workflow's own
    key, then no key, and logs what each got (Nov 3: GitHub answered 403 to the traffic key and 401 with no key on
    stargazers and subscribers)."""
    tried = []
    for label, key, auth in (("traffic key", TOKEN, True), ("bot key", BOTKEY, True), ("workflow key", BASIC, True), ("no key", None, False)):
        if auth and not key:
            continue
        st, data = gh(path, accept, auth=auth, key=key)
        tried.append(f"{label} {st}")
        if st == 200:
            break
    if st != 200:
        print("  could not read", path.split("?")[0], "->", ", ".join(tried))
    return st, data


def main():
    dry = "--dry-run" in sys.argv
    prev = load_previous(dry)
    daily = {(r["repo"], r["date"]): r for r in prev.get("daily", [])}
    people = {(p["who"], p["what"], p.get("repo", "")): p for p in prev.get("people", [])}
    summary, referrers, paths, notes = [], [], [], []

    for name in repos():
        full = f"repos/{OWNER}/{name}"
        st_v, views = gh(f"{full}/traffic/views")
        st_c, clones = gh(f"{full}/traffic/clones")
        st_r, refs = gh(f"{full}/traffic/popular/referrers")
        st_p, pops = gh(f"{full}/traffic/popular/paths")
        _, info = gh(full)
        access = st_v == 200
        if not access:
            notes.append(f"{name}: no traffic access (HTTP {st_v}); the token needs Administration: Read-only on this repo")
        for kind, d in (("views", views), ("clones", clones)):
            for x in (d or {}).get(kind, []):
                day = x["timestamp"][:10]
                row = daily.setdefault((name, day), {"repo": name, "date": day, "views": 0, "view_uniques": 0, "clones": 0, "clone_uniques": 0})
                row[kind], row["view_uniques" if kind == "views" else "clone_uniques"] = x["count"], x["uniques"]
        referrers += [{"repo": name, "site": r["referrer"], "views": r["count"], "uniques": r["uniques"]} for r in (refs or [])] if st_r == 200 else []
        paths += [{"repo": name, "page": p["path"], "title": p.get("title", ""), "views": p["count"], "uniques": p["uniques"]} for p in (pops or [])] if st_p == 200 else []
        # people who left a trace (public: works with any token)
        st_s, stars = gh_public(f"{full}/stargazers?per_page=100", accept="application/vnd.github.star+json")
        for s in stars or []:
            people.setdefault((s["user"]["login"], "starred", name), {"who": s["user"]["login"], "what": "starred", "repo": name, "when": s["starred_at"][:10], "first_seen": TODAY})
        st_k, forks = gh_public(f"{full}/forks?per_page=100")
        for f in forks or []:
            people.setdefault((f["owner"]["login"], "forked", name), {"who": f["owner"]["login"], "what": "forked", "repo": name, "when": f["created_at"][:10], "first_seen": TODAY})
        st_w, subs = gh_public(f"{full}/subscribers?per_page=100")
        for s in subs or []:
            people.setdefault((s["login"], "watching", name), {"who": s["login"], "what": "watching", "repo": name, "when": "", "first_seen": TODAY})
        print(f"{name}: traffic HTTP {st_v}; stargazers HTTP {st_s} ({len(stars or [])}), forks HTTP {st_k} ({len(forks or [])}), watchers HTTP {st_w} ({len(subs or [])})")
        summary.append({"repo": name, "access": access,
                        "views_14d": (views or {}).get("count"), "view_uniques_14d": (views or {}).get("uniques"),
                        "clones_14d": (clones or {}).get("count"), "clone_uniques_14d": (clones or {}).get("uniques"),
                        "stars": (info or {}).get("stargazers_count"), "forks": (info or {}).get("forks_count"),
                        "watchers": (info or {}).get("subscribers_count")})

    st_f, followers = gh_public(f"users/{OWNER}/followers?per_page=100")
    for f in followers or []:
        people.setdefault((f["login"], "follows you", ""), {"who": f["login"], "what": "follows you", "repo": "", "when": "", "first_seen": TODAY})
    # Betsy's own stars/watches aren't visitors
    people = {k: v for k, v in people.items() if v["who"].lower() != OWNER.lower()}

    out = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "owner": OWNER, "history_since": prev.get("history_since") or TODAY,
           "repos": summary, "followers": len(followers or []) if st_f == 200 else None,
           "daily": sorted(daily.values(), key=lambda r: (r["date"], r["repo"]), reverse=True),
           "referrers": sorted(referrers, key=lambda r: -r["views"]), "paths": sorted(paths, key=lambda r: -r["views"]),
           "people": sorted(people.values(), key=lambda p: (p.get("when") or p["first_seen"]), reverse=True), "notes": notes}
    body = json.dumps(out, separators=(",", ":")).encode()
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/github_traffic.json", "wb").write(body)
    v = sum(r["views_14d"] or 0 for r in summary); u = sum(r["view_uniques_14d"] or 0 for r in summary)
    print(f"github traffic: {len(summary)} repos, {v} views from {u} unique visitors in 14 days, "
          f"{len(out['daily'])} days of history, {len(out['people'])} people who left a trace")
    for n in notes:
        print("NOTE:", n)
    if dry:
        return
    try:
        c, b = s3_client()
        c.put_object(Bucket=b, Key=KEY, Body=body, ContentType="application/json", CacheControl="no-cache")
        c.put_object(Bucket=b, Key=f"logs/github-traffic/{TODAY}.json", Body=body, ContentType="application/json")
        print("saved to R2", KEY, "and logs/github-traffic/" + TODAY + ".json")
    except Exception as e:   # noqa: BLE001
        print("could not save to storage:", e)


if __name__ == "__main__":
    main()
