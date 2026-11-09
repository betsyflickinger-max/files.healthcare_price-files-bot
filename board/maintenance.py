"""Maintenance pause for the storage move (Nov 9, 2026; Betsy OK'd the R2 -> Backblaze cutover plan).

The final copy pass only says "Ready to switch: yes" if NOTHING writes to storage while it runs. This stops the writers
without cutting anything off mid-file, and undoes exactly what it did:

  ACTION=pause   1. hold every insurer area and the hospital queue (writes a hold.txt that machines check between files;
                    a hold that was already there is left alone and not removed later)
                 2. turn off every workflow that uses storage, scheduled or not (machines and the Cloudflare timer start
                    workflows too), except the ones the move itself needs (KEEP_ON)
                 3. open ONE issue that records what was paused, then report what is still running
  ACTION=status  what is still running: rented machines, GitHub runs, files being read, always-on servers.
                 "Ready for the final pass: yes" only when all are zero.
  ACTION=resume  turn back on exactly the workflows this paused, remove only the hold files this wrote (in whichever
                 storage the bot uses now, and in R2 too after the switch, so switching back is clean), close the issue.

Never deletes data and never stops a machine: machines finish the file they are reading, then return themselves.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import boto3
import requests
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "insurers"))
import fleet  # noqa: E402

REPO = os.environ["GITHUB_REPOSITORY"]
GH = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{REPO}"
DO = "https://api.digitalocean.com/v2"
TITLE = "Bot paused for maintenance"
ME = "maintenance.yml"
KEEP_ON = {ME, "storage-copy.yml", "copy-say.yml", "storage-alarm.yml", "r2-cost.yml"}
HOSPITAL_HOLD = "bot/fleet/hold_hospitals.txt"
MARK = re.compile(r"<!-- maintenance: (\{.*?\}) -->", re.S)
STAMP = "maintenance pause"


def env(k):
    return "".join(os.environ.get(k, "").split())


def store():
    """The storage the bot uses right now (Backblaze once STORAGE_ENDPOINT is set, else R2)."""
    ep = env("STORAGE_ENDPOINT")
    if ep and "://" not in ep:
        ep = "https://" + ep
    s3 = boto3.client("s3", endpoint_url=ep or f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                      aws_access_key_id=env("R2_ACCESS_KEY_ID"), aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"),
                      region_name=env("STORAGE_REGION") or "auto")
    return s3, env("R2_BUCKET"), ("Backblaze" if ep else "R2")


def r2_direct():
    """R2 itself, even after the switch (only for removing this tool's own hold files)."""
    if not (env("R2X_KEY") and env("R2X_SECRET") and env("R2X_BUCKET")):
        return None
    return boto3.client("s3", endpoint_url=f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com", region_name="auto",
                        aws_access_key_id=env("R2X_KEY"), aws_secret_access_key=env("R2X_SECRET")), env("R2X_BUCKET")


def gh(method, path, **kw):
    r = requests.request(method, path if path.startswith("http") else API + path, headers=GH, timeout=60, **kw)
    if r.status_code >= 300 and r.status_code != 404:
        print(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
    return r


def pages(path, key, **params):
    out, page = [], 1
    while True:
        r = gh("GET", path, params={**params, "per_page": 100, "page": page})
        items = r.json().get(key, []) if r.ok else []
        out += items
        if len(items) < 100:
            return out
        page += 1


def open_issue():
    for i in gh("GET", "/issues", params={"state": "open", "per_page": 100}).json():
        if i.get("title", "").startswith(TITLE) and "pull_request" not in i:
            return i
    return None


def storage_workflows():
    """Active workflows that use storage keys (any trigger), minus KEEP_ON."""
    out = []
    for w in pages("/actions/workflows", "workflows"):
        f = ROOT / w["path"]
        if w["state"] != "active" or f.name in KEEP_ON or not f.exists():
            continue
        text = f.read_text()
        if re.search(r"secrets\.(R2_|B2_)|STORAGE_ENDPOINT", text):
            out.append({"id": w["id"], "file": f.name, "name": w["name"]})
    return out


def hold_keys(s3, b):
    """Every hold switch the machines check: each insurer area's, the hospital queue's, and any other a queued job names."""
    keys = {HOSPITAL_HOLD}
    keys |= {m.group(1) + "hold.txt" for m in re.finditer(r'^\s*"\w+": \("(bot/insurers/(?:\w+/)?)"',
                                                          (ROOT / "insurers" / "bot.py").read_text(), re.M)}
    keys |= {j["hold_key"] for j in fleet.jobs(s3, b).values() if j.get("hold_key")}
    return sorted(keys)


def read(s3, b, k):
    try:
        return s3.get_object(Bucket=b, Key=k)["Body"].read().decode("utf-8", "replace").strip()
    except ClientError:
        return ""


def do_h():
    return {"Authorization": f"Bearer {env('DIGITALOCEAN_TOKEN')}"} if env("DIGITALOCEAN_TOKEN") else None


def machines():
    h, out = do_h(), []
    if not h:
        return ["(no DigitalOcean key: couldn't check)"]
    for tag in ("upfront-bot", "site-build"):
        r = requests.get(f"{DO}/droplets", params={"tag_name": tag, "per_page": 200}, headers=h, timeout=60)
        out += [d["name"] for d in r.json().get("droplets", [])] if r.ok else [f"(couldn't list {tag})"]
    return sorted(set(out))


def running_runs():
    out = []
    for st in ("in_progress", "queued", "waiting"):
        for r in pages("/actions/runs", "workflow_runs", status=st):
            f = Path(r.get("path") or "").name
            if f not in KEEP_ON:
                out.append(f"{r['name']} (#{r['run_number']}, {st})")
    return out


def status(s3, b):
    """(ready, lines)"""
    ms, runs = machines(), running_runs()
    cl = fleet.claims(s3, b)
    live = []
    try:
        for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=fleet.D):
            for o in pg.get("Contents", []):
                if time.time() - o["LastModified"].timestamp() < 600:
                    live.append(o["Key"].split("/")[-1].removesuffix(".json"))
    except ClientError:
        pass
    lines = [f"- Rented machines still on: {len(ms)}" + (f" ({', '.join(ms)})" if ms else ""),
             f"- GitHub jobs still running or queued: {len(runs)}" + ("".join(f"\n  - {x}" for x in runs[:30]) if runs else ""),
             f"- Files being read right now (claims): {len(cl)}",
             f"- Always-on servers that checked in during the last 10 minutes: {len(live)}" + (f" ({', '.join(live)})" if live else "")]
    # A claim only matters while something that could hold it is still running; once machines, GitHub jobs and
    # servers are all gone, leftover claims are stale and the queue puts those files back in line after the resume.
    ready = not ms and not runs and not live
    if ready and cl:
        lines[2] += " (stale: nothing is running that could be reading them; they go back in line after the resume)"
    lines.append(f"\n**Ready for the final pass: {'yes' if ready else 'no'}.**" +
                 ("" if ready else " Machines finish the file they're on and return themselves; check again later."))
    return ready, lines


def pause(s3, b, where):
    if open_issue():
        print("already paused; status only")
        return
    issue = gh("POST", "/issues", json={"title": f"{TITLE}: storage move to Backblaze", "assignees": [REPO.split("/")[0]],
                                        "body": "Pausing now; details follow."}).json()["number"]
    note = f"{STAMP} {fleet.iso()}: storage move to Backblaze (issue #{issue})"
    wrote, kept = [], []
    for k in hold_keys(s3, b):
        if read(s3, b, k):
            kept.append(k)
            continue
        s3.put_object(Bucket=b, Key=k, Body=note.encode())
        wrote.append(k)
    paused = [w for w in storage_workflows() if gh("PUT", f"/actions/workflows/{w['id']}/disable").status_code == 204]
    state = {"workflows": paused, "holds": wrote, "store": where}
    body = (f"Paused for the move from Cloudflare R2 to Backblaze. **Nothing is deleted and no machine is stopped:** "
            f"machines finish the file they're reading, then return themselves.\n\n"
            f"- Put {len(wrote)} queues on hold in {where} (machines check between files)" +
            (f"; {len(kept)} were already on hold and are left as they are" if kept else "") +
            f"\n- Turned off {len(paused)} workflows that use storage:" + "".join(f"\n  - {w['name']}" for w in paused) +
            f"\n- Left on: {', '.join(sorted(KEEP_ON))}\n\n"
            f"To undo: run the **Maintenance** workflow with `resume`. It turns back on only these workflows and removes "
            f"only these hold files.\n\n<!-- maintenance: {json.dumps(state)} -->")
    gh("PATCH", f"/issues/{issue}", json={"body": body})
    print(f"paused: issue #{issue}, {len(paused)} workflows off, {len(wrote)} holds written, {len(kept)} already held")
    return issue


def resume(s3, b):
    issue = open_issue()
    if not issue:
        print("nothing to resume: no open maintenance issue")
        return
    m = MARK.search(issue.get("body") or "")
    state = json.loads(m.group(1)) if m else {"workflows": [], "holds": []}
    back = [w["name"] for w in state["workflows"] if gh("PUT", f"/actions/workflows/{w['id']}/enable").status_code == 204]
    stores = [(s3, b)] + ([r2_direct()] if env("STORAGE_ENDPOINT") and r2_direct() else [])
    removed, left = 0, []
    for c, bk in stores:
        for k in state["holds"]:
            txt = read(c, bk, k)
            if txt.startswith(STAMP):
                c.delete_object(Bucket=bk, Key=k)
                removed += 1
            elif txt:
                left.append(k)   # someone changed it since: not ours to remove
    gh("POST", f"/issues/{issue['number']}/comments", json={"body":
        f"Resumed: turned {len(back)} of {len(state['workflows'])} workflows back on and lifted {removed} hold files."
        + (f" Left alone (changed since the pause): {', '.join(sorted(set(left)))}." if left else "") + " Closing."})
    gh("PATCH", f"/issues/{issue['number']}", json={"state": "closed"})
    print(f"resumed: {len(back)} workflows on, {removed} holds removed, {len(left)} left alone")


def main():
    action = (os.environ.get("ACTION") or "status").strip()
    s3, b, where = store()
    if action == "pause":
        pause(s3, b, where)
    elif action == "resume":
        resume(s3, b)
        return 0
    elif action != "status":
        sys.exit(f"unknown ACTION {action}")
    ready, lines = status(s3, b)
    text = "\n".join(lines)
    print(text)
    issue = open_issue()
    if issue:
        gh("POST", f"/issues/{issue['number']}/comments", json={"body": f"Status at {fleet.iso()}:\n\n{text}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
