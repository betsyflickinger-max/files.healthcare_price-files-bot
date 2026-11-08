"""Nov 8, 2026 (Betsy OK'd): one status note every morning, so she doesn't have to ask. It runs the every-area check
(site/build_check.py all), adds the month's machine spend against her card limit and any open "Build stuck" alarms, and
posts it as a comment on the "Daily build status" issue, mentioning her so GitHub emails it. Changes nothing else."""
import json, os, re, subprocess, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "betsyflickinger-max/files.healthcare_price-files-bot")
H = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
TITLE = "Daily build status"
WHO = "@betsyflickinger-max"


def gh(method, path, **kw):
    return requests.request(method, f"https://api.github.com/repos/{REPO}{path}", headers=H, timeout=60, **kw)


def main():
    month = time.strftime("%Y-%m")
    out = subprocess.run([sys.executable, str(ROOT / "site" / "build_check.py"), "all", month], capture_output=True, text=True, timeout=1500).stdout
    lines = out.splitlines()
    dfw = next((l for l in lines if l.startswith("DFW:")), "DFW: (no reading)")
    tx = [(m.group(1), m.group(2)) for m in (re.match(r"Texas (\S+): newest live (\S+)", l) for l in lines) if m]
    st = [(m.group(1), m.group(2)) for m in (re.match(r"\s+(\S+): newest live ([^;]+);", l) for l in lines) if m]
    builds = [l.strip() for l in lines if l.startswith("[")]
    tx_behind = [a for a, m in tx if m != month]
    st_behind = [a for a, m in st if m != month]
    parts = [f"{WHO} status for {time.strftime('%a %b %d')} ({month})", "",
             f"**DFW:** {dfw[4:].strip()}",
             f"**Texas:** {len(tx) - len(tx_behind)} of {len(tx)} areas on {month}" + (f"; still behind: {', '.join(tx_behind)}" if tx_behind else ""),
             f"**States:** {len(st) - len(st_behind)} of {len(st)} on {month}" + (f"; still behind: {', '.join(st_behind)}" if st_behind else "")]
    busy = [b for b in builds if "stage live" not in b and "no build" not in b and any(s in b for s in ("stage build", "stage split", "stage hosp", "stage wait"))]
    if busy: parts += ["", "**Builds still running:**"] + [f"- {b[:220]}" for b in busy]
    try:
        sys.path.insert(0, str(ROOT / "insurers"))
        import droplets
        card, mtd, credit = droplets.card_spend()
        cap = droplets.card_cap()
        ms = requests.get(f"{droplets.API}/droplets", params={"per_page": 200}, headers=droplets._h(), timeout=60).json().get("droplets", [])
        hr = sum(float(d.get("size", {}).get("price_hourly") or 0) for d in ms)
        parts += ["", f"**Money:** ${card:,.2f} of the ${cap:,.0f} card limit this month (machine total ${mtd:,.2f}); "
                      f"{len(ms)} machines running, about ${hr:,.2f} an hour."]
    except Exception as e:
        parts += ["", f"**Money:** couldn't read DigitalOcean ({repr(e)[:120]})"]
    stuck = [i for i in gh("GET", "/issues", params={"state": "open", "per_page": 100}).json()
             if isinstance(i, dict) and i.get("title", "").startswith(("Build stuck", "Card spending", "Price check"))]
    if stuck: parts += ["", "**Needs you:**"] + [f"- #{i['number']} {i['title']}" for i in stuck]
    else: parts += ["", "Nothing needs you today."]
    body = "\n".join(parts)
    print(body)
    issue = next((i for i in gh("GET", "/issues", params={"state": "open", "per_page": 100}).json()
                  if isinstance(i, dict) and i.get("title") == TITLE), None)
    if not issue:
        issue = gh("POST", "/issues", json={"title": TITLE, "body": "One comment a morning: what's live, what's building, what's stuck, money spent. Written by board/daily_status.py."}).json()
    r = gh("POST", f"/issues/{issue['number']}/comments", json={"body": body})
    print("posted:", r.status_code)


if __name__ == "__main__":
    main()
