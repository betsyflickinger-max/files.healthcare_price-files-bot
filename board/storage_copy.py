"""Copy everything in Cloudflare R2 to Backblaze B2 (Oct 28, 2026; Betsy said yes).

Why: R2 was switched off over a card problem (Oct 26) and B2 is about $82/month for the same ~11.8 TB vs ~$280+.
Plan: copy all of R2 to B2, then switch the bot over (repo variables STORAGE_ENDPOINT / STORAGE_REGION and the
storage keys). See claude/storage-options-oct27.md in the project.

What this does: rents ONE DigitalOcean machine (tag "upfront-copy", so the queue's cleanup never touches it) that runs
rclone COPY (never sync, never deletes anything on either side), twice: the second pass catches files the bot wrote
during the first. Then it compares both sides, posts the result on a GitHub issue and returns itself.
Nov 9, 2026 (Betsy OK'd, "no corners cut"): two more modes for the switch to Backblaze, chosen with MODE:
  topup  - while the bot keeps running: one copy pass + a report of what still differs. Fast because rclone reads
           each file's R2 time from the listing (--use-server-modtime) instead of asking R2 about every one of the
           7 million files (that per-file lookup is why the Nov 1 pass 2 took 7.5 hours).
  final  - during the pause (bot stopped): copy pass, then a TWO-WAY check. Anything missing or a different size
           in Backblaze is copied again. Anything in Backblaze that R2 no longer has (e.g. finished queue jobs,
           tables the bot moved to history/) is MOVED to migration/stale-<date>/ in Backblaze, never deleted, so the
           bot doesn't see old files after the switch. history/, raw/, research/ and the migration logs are never
           moved. Then the check runs again and must show 0 missing, 0 size differences, 0 stale.
Progress is posted on the issue every 2 hours. Started automatically by the storage alarm the first time R2 answers
again, or by hand (workflow "Copy storage to Backblaze").
"""
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
import store  # noqa: E402

REPO = os.environ["GITHUB_REPOSITORY"]
GH = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{REPO}"
DO = "https://api.digitalocean.com/v2"
TITLE = "Copying storage to Backblaze"
SIZES = ["s-8vcpu-16gb", "s-8vcpu-16gb-amd", "s-8vcpu-16gb-intel", "s-4vcpu-8gb"]
REGIONS = ["nyc3", "nyc1", "sfo3"]
e = store.env


def existing():
    r = requests.get(f"{API}/issues", headers=GH, params={"state": "all", "per_page": 100}, timeout=60)
    return next((i for i in r.json() if i.get("title", "").startswith(TITLE) and "pull_request" not in i), None)


def user_data(issue, mode="full"):
    v = {k: e(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "B2_BUCKET",
                           "B2_ACCESS_KEY_ID", "B2_SECRET_ACCESS_KEY", "DIGITALOCEAN_TOKEN", "BOT_GITHUB_TOKEN")}
    return f"""#!/bin/bash
exec > /var/log/copy-setup.log 2>&1
export HOME=/root
export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
export RCLONE_CONFIG_R2_ENDPOINT='https://{v['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com'
export RCLONE_CONFIG_R2_ACCESS_KEY_ID='{v['R2_ACCESS_KEY_ID']}' RCLONE_CONFIG_R2_SECRET_ACCESS_KEY='{v['R2_SECRET_ACCESS_KEY']}'
export RCLONE_CONFIG_B2_TYPE=b2 RCLONE_CONFIG_B2_ACCOUNT='{v['B2_ACCESS_KEY_ID']}' RCLONE_CONFIG_B2_KEY='{v['B2_SECRET_ACCESS_KEY']}'
SRC='r2:{v['R2_BUCKET']}'; DST='b2:{v['B2_BUCKET']}'
GHT='{v['BOT_GITHUB_TOKEN']}'; DOT='{v['DIGITALOCEAN_TOKEN']}'
export B2K='{v['B2_ACCESS_KEY_ID']}' B2S='{v['B2_SECRET_ACCESS_KEY']}' B2B='{v['B2_BUCKET']}'
say() {{ python3 -c 'import json,sys; print(json.dumps({{"body": sys.stdin.read()}}))' | \\
  curl -s -o /dev/null -X POST -H "Authorization: Bearer $GHT" -H "Accept: application/vnd.github+json" \\
  https://api.github.com/repos/{REPO}/issues/{issue}/comments -d @-; }}
apt-get update -y && apt-get install -y curl unzip python3
curl -s https://rclone.org/install.sh | bash
OPTS="--transfers 48 --checkers 64 --retries 10 --low-level-retries 20 --b2-chunk-size 96M --stats 10m --stats-one-line --stats-log-level NOTICE --log-level NOTICE"
# Oct 30: progress also saved to Backblaze (bot/migration/logs/) every 2 hours, so it can be read even if the GitHub
# comment can't be posted (the first copy, Oct 29, posted nothing and stopped when Backblaze's free 10 GB cap was hit)
( while sleep 7200; do echo "Still copying. Latest: $(grep -a 'Transferred' /var/log/copy.log | tail -1)" | say;
  rclone copy /var/log "$DST/bot/migration/logs" --include 'copy*.log' --include 'check.log' -q || true; done ) &
TICK=$!
rclone copy /var/log "$DST/bot/migration/logs" --include 'copy-setup.log' -q || true
MODE='{mode}'
OPTS="$OPTS --use-server-modtime"   # Nov 9: R2 times from the listing, no per-file lookups (same comparison, much faster)
KEEP='^(history/|raw/|research/|bot/migration/|bot/cutover-test/|migration/)'
if [ "$MODE" = "full" ]; then
echo "Machine is up; copy pass 1 starting (copy only: nothing is deleted on either side)." | say
rclone copy "$SRC" "$DST" $OPTS --log-file /var/log/copy.log; P1=$?
echo "Pass 1 finished (exit $P1): $(grep -a 'Transferred' /var/log/copy.log | tail -2 | tr '\\n' ' '). Pass 2 catches anything written meanwhile." | say
rclone copy "$SRC" "$DST" $OPTS --log-file /var/log/copy2.log; P2=$?
kill $TICK
rclone check "$SRC" "$DST" --one-way --size-only --checkers 64 --log-file /var/log/check.log --log-level NOTICE; C=$?
MISS=$(grep -ac 'not in' /var/log/check.log); DIFF=$(grep -ac 'sizes differ' /var/log/check.log)
{{ echo "Copy finished. Pass 2: exit $P2. Check (every R2 file is in Backblaze with the same size): exit $C, $MISS missing, $DIFF size differences."
   echo; echo '```'; grep -a 'Transferred\\|Errors\\|Checks' /var/log/copy2.log | tail -4; tail -5 /var/log/check.log; echo '```'
   echo; echo "Next: switch the bot to Backblaze (repo variables STORAGE_ENDPOINT / STORAGE_REGION and the storage keys)."; }} | say
else
T0=$(date +%s)
echo "Machine is up ($MODE). Copy pass starting: copy only, nothing deleted." | say
rclone copy "$SRC" "$DST" $OPTS --log-file /var/log/copy.log; P1=$?
T1=$(date +%s)
twoway() {{  # $1 = label; writes /var/log/$1-{{missing,extra,differ}}.txt
  rclone check "$SRC" "$DST" --size-only --checkers 64 --missing-on-dst /var/log/$1-missing.txt \\
    --missing-on-src /var/log/$1-extra-all.txt --differ /var/log/$1-differ.txt --log-file /var/log/$1-check.log --log-level NOTICE
  grep -Ev "$KEEP" /var/log/$1-extra-all.txt > /var/log/$1-extra.txt || true
  echo "$(wc -l < /var/log/$1-missing.txt) $(wc -l < /var/log/$1-differ.txt) $(wc -l < /var/log/$1-extra.txt)"
}}
read M D X <<< "$(twoway check1)"
T2=$(date +%s)
if [ "$MODE" = "topup" ]; then
  kill $TICK
  {{ echo "Top-up finished (bot kept running). Copy pass: exit $P1, $(( (T1-T0)/60 )) min. Check: $(( (T2-T1)/60 )) min."
     echo "Right now Backblaze is missing $M files, has $D with a different size, and has $X that R2 no longer has. These are expected while the bot runs; the final pass during the pause fixes them."
     echo; echo '```'; grep -a 'Transferred\\|Errors\\|Checks' /var/log/copy.log | tail -4; echo '```'; }} | say
else
  cat /var/log/check1-missing.txt /var/log/check1-differ.txt > /var/log/fix.txt
  [ -s /var/log/fix.txt ] && rclone copy "$SRC" "$DST" $OPTS --files-from /var/log/fix.txt --no-traverse --log-file /var/log/copy-fix.log
  STALE="migration/stale-$(date -u +%Y-%m-%d)/"
  if [ -s /var/log/check1-extra.txt ]; then
    pip install -q boto3 --break-system-packages >/dev/null 2>&1 || pip install -q boto3
    STALE="$STALE" python3 - <<'PY'
import os, boto3
from concurrent.futures import ThreadPoolExecutor
s3 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                  aws_access_key_id=os.environ["B2K"], aws_secret_access_key=os.environ["B2S"])
B, P = os.environ["B2B"], os.environ["STALE"]
keys = [l.rstrip("\\n") for l in open("/var/log/check1-extra.txt") if l.strip()]
def mv(k):   # copy first, confirm the copy, only then hide the original (its old version stays until the 30-day rule)
    s3.copy({{"Bucket": B, "Key": k}}, B, P + k)   # managed copy: works for files over 5 GB too
    if s3.head_object(Bucket=B, Key=P + k)["ContentLength"] != s3.head_object(Bucket=B, Key=k)["ContentLength"]:
        raise RuntimeError("copy size mismatch " + k)
    s3.delete_object(Bucket=B, Key=k)
    return k
with ThreadPoolExecutor(32) as ex:
    done = list(ex.map(mv, keys))
open("/var/log/stale-moved.txt", "w").write("\\n".join(done) + "\\n")
print("moved", len(done))
PY
  fi
  read M2 D2 X2 <<< "$(twoway check2)"
  kill $TICK
  OK=no; [ "$M2" = 0 ] && [ "$D2" = 0 ] && [ "$X2" = 0 ] && OK=yes
  {{ echo "Final pass finished. Copy pass: exit $P1, $(( (T1-T0)/60 )) min."
     echo "First check: $M missing, $D size differences, $X stale (in Backblaze only). Fixed: copied $(( M + D )) again; moved $X stale files to $STALE (nothing deleted)."
     echo "**Second check: $M2 missing, $D2 size differences, $X2 stale. Ready to switch: $OK.**"
     echo; echo "Lists kept in Backblaze under bot/migration/logs/ (check1-*, check2-*, stale-moved.txt)."; }} | say
  rclone copy /var/log "$DST/bot/migration/logs" --include 'check*' --include 'stale-moved.txt' --include 'fix.txt' --include 'copy-fix.log' || true
fi
fi
rclone copy /var/log "$DST/bot/migration/logs" --include 'copy*.log' --include 'check.log' || true
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DOT" https://api.digitalocean.com/v2/droplets/$ID
"""


def main():
    force = os.environ.get("FORCE") == "true"
    mode = (os.environ.get("MODE") or "full").strip()
    if mode not in ("full", "topup", "final"):
        sys.exit(f"unknown MODE {mode}")
    if mode != "full":
        force = True   # top-up and final passes always start (each gets its own issue)
    missing = [k for k in ("B2_BUCKET", "B2_ACCESS_KEY_ID", "B2_SECRET_ACCESS_KEY", "DIGITALOCEAN_TOKEN") if not e(k)]
    if missing:
        sys.exit(f"missing secrets: {missing}")
    old = existing()
    if old and not force:
        print(f"Already started (issue #{old['number']}); run with force to start again.")
        return
    s3, b = store.r2()
    try:
        s3.list_objects_v2(Bucket=b, MaxKeys=1)
    except Exception as ex:
        sys.exit(f"R2 isn't answering yet, so there's nothing to copy: {ex}")
    issue = requests.post(f"{API}/issues", headers=GH, timeout=60, json={"title": f"{TITLE} (R2 → B2)" + ("" if mode == "full" else f": {mode} pass"), "assignees": [REPO.split("/")[0]], "body": (
        "Copying everything in Cloudflare R2 to Backblaze B2 on one rented machine. **Copy only: nothing is deleted "
        "on either side.** Two passes (the second catches files written during the first), then a check that every "
        "R2 file is in Backblaze. Expect about 1–2 days for ~11.8 TB. Progress is posted here every 2 hours; the "
        "machine returns itself when done.")}).json()["number"]
    h = {"Authorization": f"Bearer {e('DIGITALOCEAN_TOKEN')}", "Content-Type": "application/json"}
    r = None
    for size in SIZES:
        for region in REGIONS:
            r = requests.post(f"{DO}/droplets", headers=h, timeout=60, json=dict(
                name=f"upfront-copy-r2-b2-{issue}", region=region, size=size, image="ubuntu-24-04-x64",
                tags=["upfront", "upfront-copy"], user_data=user_data(issue, mode), monitoring=True))
            if r.status_code != 422:
                break
        if r.status_code != 422:
            break
    if r.status_code >= 300:
        requests.post(f"{API}/issues/{issue}/comments", headers=GH, timeout=60,
                      json={"body": f"Couldn't rent the copy machine: DigitalOcean {r.status_code} {r.text[:200]}"})
        sys.exit(f"DigitalOcean {r.status_code}: {r.text[:300]}")
    d = r.json()["droplet"]
    requests.post(f"{API}/issues/{issue}/comments", headers=GH, timeout=60, json={
        "body": f"Rented machine `{d['name']}` ({d['size_slug']}, {d['region']['slug']}). Setting up rclone now."})
    print(f"copy started: issue #{issue}, machine {d['name']}")


if __name__ == "__main__":
    main()
