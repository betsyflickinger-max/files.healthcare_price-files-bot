"""Storage alarm (Oct 28, 2026, Betsy OK'd Oct 26): one cheap storage call every 15 minutes.

Storage switched off (Cloudflare R2 "NotEntitled" on Oct 26, after a card-validation failure), every bot job failed and
Betsy got dozens of GitHub failure emails that never said why. Now:
  * storage refuses us  -> pause every scheduled workflow that needs storage, power off rented machines, and open ONE
                           issue that says what's wrong and where to fix it (one email instead of dozens).
  * storage answers again -> turn those same workflows back on, return the powered-off machines (their jobs were never
                           saved; the queue puts them back in line on its own), and close the issue.
Only workflows this alarm paused are turned back on, so anything Betsy switched off herself stays off.
Network blips (timeouts, 5xx) never trigger it; only a clear "account/keys refused" answer does.
Never deletes data: machine disks hold only temporary downloads; everything kept lives in storage.
"""
import json
import os
import re
import sys
from pathlib import Path

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

REPO = os.environ["GITHUB_REPOSITORY"]
GH = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{REPO}"
DO = "https://api.digitalocean.com/v2"
TITLE = "Storage is switched off"
ME = "storage-alarm.yml"
KEEP_RUNNING = {ME, "r2-cost.yml", "calculator.yml"}  # cost check reads Cloudflare billing, not storage; the
# calculator check only touches storage once new plan files are out, and must not miss them (Nov 1 deadline)
OFF_CODES = {"NotEntitled", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "NoSuchBucket",
             "AccountProblem", "AllAccessDisabled", "Unauthorized", "Forbidden", "403", "401"}
MARK = re.compile(r"<!-- paused: (\{.*?\}) -->", re.S)


def env(k):
    return "".join(os.environ.get(k, "").split())


def where():
    ep = env("STORAGE_ENDPOINT")
    if ep:
        return ep, "Backblaze B2" if "backblaze" in ep else "storage", "your storage company's billing page"
    return (f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", "Cloudflare R2",
            "https://dash.cloudflare.com/?to=/:account/billing/payment-info")


def check():
    """'ok', 'off' (with the error), or 'unsure' (a blip; try again next time)."""
    ep, _, _ = where()
    s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id=env("R2_ACCESS_KEY_ID"),
                      aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"), region_name=env("STORAGE_REGION") or "auto",
                      config=Config(retries={"max_attempts": 3}, connect_timeout=20, read_timeout=30))
    try:
        s3.list_objects_v2(Bucket=env("R2_BUCKET"), MaxKeys=1)
        return "ok", ""
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        status = str(e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
        if code in OFF_CODES or status in OFF_CODES:
            return "off", f"{code}: {e.response.get('Error', {}).get('Message', '')}"
        return "unsure", f"{code or status}: {e}"
    except Exception as e:  # timeouts, DNS, connection resets
        return "unsure", repr(e)[:300]


def gh(method, path, **kw):
    r = requests.request(method, path if path.startswith("http") else API + path, headers=GH, timeout=60, **kw)
    if r.status_code >= 300 and r.status_code != 404:
        print(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
    return r


def open_issue():
    for i in gh("GET", "/issues", params={"state": "open", "per_page": 100}).json():
        if i.get("title", "").startswith(TITLE) and "pull_request" not in i:
            return i
    return None


def storage_workflows():
    """Active workflows that run on a schedule and use storage."""
    out = []
    for w in gh("GET", "/actions/workflows", params={"per_page": 100}).json().get("workflows", []):
        f = Path(w["path"])
        if w["state"] != "active" or f.name in KEEP_RUNNING or not f.exists():
            continue
        text = f.read_text()
        if re.search(r"^\s*schedule:", text, re.M) and "secrets.R2_" in text:
            out.append({"id": w["id"], "file": f.name, "name": w["name"]})
    return out


def do_h():
    tok = env("DIGITALOCEAN_TOKEN")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"} if tok else None


def bot_machines():
    h = do_h()
    if not h:
        return []
    seen = {}
    for tag in ("upfront-bot", "site-build"):
        r = requests.get(f"{DO}/droplets", params={"tag_name": tag, "per_page": 200}, headers=h, timeout=60)
        if r.ok:
            for d in r.json()["droplets"]:
                seen[d["id"]] = d
    return list(seen.values())


def go_off(err):
    _, name, fix = where()
    paused = []
    for w in storage_workflows():
        if gh("PUT", f"/actions/workflows/{w['id']}/disable").status_code == 204:
            paused.append(w)
    machines = []
    for d in bot_machines():
        if d["status"] == "active":
            r = requests.post(f"{DO}/droplets/{d['id']}/actions", json={"type": "power_off"}, headers=do_h(), timeout=60)
            if r.ok:
                machines.append({"id": d["id"], "name": d["name"]})
    state = {"workflows": paused, "machines": machines}
    body = (
        f"**{name} is refusing the bot**, so nothing can be read or saved. Most often this is billing: a card that "
        f"couldn't be charged or validated.\n\n"
        f"**What to do:** check billing and the payment method here: {fix}\n\n"
        f"**What I did so you don't get dozens of failure emails:**\n"
        f"- Paused {len(paused)} scheduled jobs that need storage" +
        ("".join(f"\n  - {w['name']}" for w in paused) if paused else "") +
        f"\n- Powered off {len(machines)} rented machines (they can't do anything without storage)\n\n"
        f"**Nothing is lost.** Everything already saved stays in storage. Files that were mid-read get read again.\n\n"
        f"This issue closes itself, and the paused jobs turn back on, within 15 minutes of storage answering again.\n\n"
        f"Error: `{err[:300]}`\n\n<!-- paused: {json.dumps(state)} -->")
    gh("POST", "/issues", json={"title": f"{TITLE} — check {name} billing", "body": body})
    print(f"storage OFF: paused {len(paused)} workflows, powered off {len(machines)} machines")


def go_on(issue):
    m = MARK.search(issue.get("body") or "")
    state = json.loads(m.group(1)) if m else {"workflows": [], "machines": []}
    back = [w["name"] for w in state["workflows"]
            if gh("PUT", f"/actions/workflows/{w['id']}/enable").status_code == 204]
    # A powered-off machine won't restart its worker on boot, so return it; its job goes back in line on its own
    # (insurers/fleet.py reap) and the next fill rents a fresh machine running current code.
    gone = 0
    ids = {x["id"] for x in state["machines"]}
    for d in bot_machines():
        if d["id"] in ids and d["status"] == "off":
            if requests.delete(f"{DO}/droplets/{d['id']}", headers=do_h(), timeout=60).status_code in (204, 404):
                gone += 1
    gh("POST", f"/issues/{issue['number']}/comments", json={"body":
        f"Storage is answering again. Turned {len(back)} paused jobs back on and returned {gone} powered-off machines "
        f"(their files go back in the queue automatically). Closing."})
    gh("PATCH", f"/issues/{issue['number']}", json={"state": "closed"})
    print(f"storage back: re-enabled {len(back)}, returned {gone} machines")
    # Oct 28, 2026 (Betsy OK'd): while the bot is still on R2, the first time R2 answers again, start the one-time copy
    # to Backblaze B2 right away. storage_copy.py skips itself if a copy was already started.
    if not env("STORAGE_ENDPOINT"):
        r = gh("POST", "/actions/workflows/storage-copy.yml/dispatches", json={"ref": "main"})
        print(f"started the R2 -> B2 copy workflow: HTTP {r.status_code}")


def main():
    status, err = check()
    issue = open_issue()
    print(f"storage: {status} {err[:200]}")
    if status == "off" and not issue:
        go_off(err)
    elif status == "ok" and issue:
        go_on(issue)
    return 0


if __name__ == "__main__":
    sys.exit(main())
