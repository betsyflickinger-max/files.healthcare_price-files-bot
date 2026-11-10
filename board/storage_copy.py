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
    sha = os.environ.get("GITHUB_SHA", "main")
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
# Nov 9: the machine's GitHub key can start workflows but can't comment on issues, so every update until now was
# silently dropped. say() now (1) keeps every update in Backblaze (bot/migration/logs/say-<issue>.log) and
# (2) starts copy-say.yml, which posts it to the issue with the workflow's own key.
say() {{ M=$(cat); printf '%s %s\\n\\n' "$(date -u +%Y-%m-%dT%H:%MZ)" "$M" >> /var/log/say.log
  rclone copyto /var/log/say.log "$DST/bot/migration/logs/say-{issue}.log" -q 2>/dev/null || true
  printf '%s' "$M" | python3 -c 'import json,sys; print(json.dumps({{"ref": "main", "inputs": {{"issue": "{issue}", "body": sys.stdin.read()[:60000]}}}}))' | \\
  curl -s -o /dev/null -X POST -H "Authorization: Bearer $GHT" -H "Accept: application/vnd.github+json" \\
  https://api.github.com/repos/{REPO}/actions/workflows/copy-say.yml/dispatches -d @- || true; }}
apt-get update -y && apt-get install -y curl unzip python3 python3-boto3
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
# Nov 9: the live website keeps writing visits, tester events and sign-ups to R2 (they stay there for good; see
# bot/site_r2.py), so those folders aren't part of the move and can't count against "R2 quiet" or "0 missing"
printf '%s\\n' 'logs/preview-visits/**' 'logs/preview-events/**' 'signups/**' > /root/site-writes.txt
OPTS="$OPTS --exclude-from /root/site-writes.txt"
KEEP='^(history/|raw/|research/|bot/migration/|bot/cutover-test/|migration/|logs/preview-visits/|logs/preview-events/|signups/)'
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
# ---- topup / final (Nov 9, 2026; independent review fixes) ----
finish() {{ kill $TICK 2>/dev/null; rclone copy /var/log "$DST/bot/migration/logs/$MODE-$(date -u +%Y%m%d-%H%M)" \\
  --include 'v*-missing.txt' --include 'v*-differ.txt' --include 'v*-extra*.txt' --include 'v*-summary.json' \\
  --include 'probe*-keys.txt' --include 'copy*.log' --include 'stale-*.txt' --include 'fix.txt' --include 'final-dryrun.log' -q || true; }}
export R2_ACCOUNT_ID='{v['R2_ACCOUNT_ID']}' R2_ACCESS_KEY_ID='{v['R2_ACCESS_KEY_ID']}' R2_SECRET_ACCESS_KEY='{v['R2_SECRET_ACCESS_KEY']}' R2_BUCKET='{v['R2_BUCKET']}'
if ! curl -sfL -H "Authorization: Bearer $GHT" "https://raw.githubusercontent.com/{REPO}/{sha}/board/storage_verify.py" -o /root/verify.py; then
  echo "Stopped before copying anything: couldn't download the checker (storage_verify.py at {sha})." | say; finish
else
T0=$(date +%s)
echo "Machine is up ($MODE). Step 1: listing both buckets in full (read only)." | say
V0=$(python3 /root/verify.py /var/log v0); V0RC=$?
# Step 2 (reviewer blocker 1): make sure the faster comparison won't re-copy files that haven't changed.
# Files last changed before Nov 1 13:44 UTC were already checked equal on Nov 1; they must not be re-copied.
probe() {{ rclone copy "$SRC" "$DST" $OPTS $MW --dry-run --log-file /var/log/probe$1.log --log-level NOTICE
  sed -n 's/^.*NOTICE: \\(.*\\): Skipped copy as --dry-run is set.*$/\\1/p' /var/log/probe$1.log > /var/log/probe$1-keys.txt
  python3 -c "
import sys
old = {{l.split('\\t')[0] for l in open('/var/log/v0-r2.tsv') if int(l.rstrip().split('\\t')[2]) < 1793540640}}
ks = [l.rstrip('\\n') for l in open('/var/log/probe$1-keys.txt')]
print(len(ks), sum(k in old for k in ks))"; }}
MW=""
read PN PO <<< "$(probe 1)"
if [ "${{PO:-999999}}" -gt 1000 ]; then MW="--modify-window 1s"; read PN PO <<< "$(probe 2)"; fi
if [ "$V0RC" != 0 ] || [ "${{PO:-999999}}" -gt 1000 ]; then
  echo "Stopped before copying anything. Listing ok: $([ "$V0RC" = 0 ] && echo yes || echo NO). Files the copy would redo although unchanged since Nov 1: ${{PO:-unknown}} (limit 1,000). Nothing was copied, moved or deleted." | say; finish
else
echo "Check passed: the copy would bring over $PN files, $PO of them older than Nov 1 (allowed up to 1,000). ${{MW:-No time tolerance needed.}} Step 3: copying." | say
rclone copy "$SRC" "$DST" $OPTS $MW --max-transfer 4T --cutoff-mode soft --log-file /var/log/copy.log; P1=$?
T1=$(date +%s)
V1=$(python3 /root/verify.py /var/log v1); V1RC=$?; read M D X K RN NEW ER <<< "$V1"
if [ "$MODE" = "topup" ]; then
  {{ echo "Top-up finished (the bot kept running). Copy: exit $P1, $(( (T1-T0)/60 )) min in all so far."
     echo "Right now Backblaze is missing $M files, has $D with a different size, and $X that R2 no longer has ($K more in history/raw/research, which are never moved). Listing errors: $ER. These are expected while the bot runs; the final pass during the pause fixes them."
     echo "Lists saved in Backblaze under bot/migration/logs/topup-<time>/."
     echo; echo '```'; grep -a 'Transferred\\|Errors\\|Checks' /var/log/copy.log | tail -4; echo '```'; }} | say
elif [ "$V1RC" != 0 ]; then
  echo "Final pass stopped: the first full check had listing errors ($ER), so nothing was re-copied, moved or hidden. **Ready to switch: no.** Run the final pass again." | say
else
  cat /var/log/v1-missing.txt /var/log/v1-differ.txt > /var/log/fix.txt; FX=0
  if [ -s /var/log/fix.txt ]; then rclone copy "$SRC" "$DST" $OPTS $MW --files-from-raw /var/log/fix.txt --no-traverse --log-file /var/log/copy-fix.log; FX=$?; fi
  STALE="migration/stale-$(date -u +%Y-%m-%d)/"; : > /var/log/stale-moved.txt; : > /var/log/stale-failed.txt
  if [ -s /var/log/v1-extra.txt ]; then STALE="$STALE" python3 - <<'PY'
import os, boto3, threading
from concurrent.futures import ThreadPoolExecutor
from botocore.config import Config
s3 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                  aws_access_key_id=os.environ["B2K"], aws_secret_access_key=os.environ["B2S"],
                  config=Config(retries={{"max_attempts": 10, "mode": "adaptive"}}, max_pool_connections=40))
r2 = boto3.client("s3", endpoint_url=f"https://{{os.environ['R2_ACCOUNT_ID']}}.r2.cloudflarestorage.com", region_name="auto",
                  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                  config=Config(retries={{"max_attempts": 10, "mode": "adaptive"}}, max_pool_connections=40))
B, P = os.environ["B2B"], os.environ["STALE"]
keys = [l.rstrip("\\n") for l in open("/var/log/v1-extra.txt") if l.rstrip("\\n")]
ok, bad, LK = open("/var/log/stale-moved.txt", "a"), open("/var/log/stale-failed.txt", "a"), threading.Lock()
def mv(k):   # copy, confirm same size, only then hide the original (its old version stays; nothing is deleted)
    try:
        # Nov 9 (reviewer): ask R2 about this exact file first; only a clear "not there" lets it move
        try:
            r2.head_object(Bucket=os.environ["R2_BUCKET"], Key=k)
            raise RuntimeError("still in R2: not moved")
        except r2.exceptions.ClientError as e:
            if e.response.get("Error", {{}}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        s3.copy({{"Bucket": B, "Key": k}}, B, P + k)
        if s3.head_object(Bucket=B, Key=P + k)["ContentLength"] != s3.head_object(Bucket=B, Key=k)["ContentLength"]:
            raise RuntimeError("copy size mismatch")
        s3.delete_object(Bucket=B, Key=k)
        with LK:
            ok.write(k + "\\n"); ok.flush()
    except Exception as e:
        with LK:
            bad.write(f"{{k}}\\t{{e!r}}"[:400] + "\\n"); bad.flush()
with ThreadPoolExecutor(32) as ex:
    list(ex.map(mv, keys))
PY
  fi
  SM=$(wc -l < /var/log/stale-moved.txt); SF=$(wc -l < /var/log/stale-failed.txt)
  V2=$(python3 /root/verify.py /var/log v2); V2RC=$?; read M2 D2 X2 K2 RN2 NEW2 ER2 <<< "$V2"
  # Same-size overwrites (size-only can't see them): a last dry-run comparing size AND time must find nothing to copy
  rclone copy "$SRC" "$DST" $OPTS $MW --dry-run --log-file /var/log/final-dryrun.log --log-level NOTICE; DR=$?
  DRN=$(grep -ac 'Skipped copy as --dry-run is set' /var/log/final-dryrun.log)
  QUIET=no; [ "${{NEW2:-9999999999}}" -lt "$T0" ] && QUIET=yes   # R2 got no new writes since this run started
  OK=yes
  for c in "$V1RC" "$V2RC" "$P1" "$FX" "$SF" "$M2" "$D2" "$X2" "$DR" "$DRN"; do [ "$c" = 0 ] || OK=no; done
  [ "$QUIET" = yes ] || OK=no
  # Nov 9: the website copier (bot/site_r2.py) treats R2 as up to date for everything written before this moment
  # (the time now, not T0: R2 is verified quiet, and files this pass copied must not look newer than R2's)
  [ "$OK" = yes ] && {{ date +%s | tr -d '\\n' | rclone rcat "$DST/bot/migration/switched-at.txt" || OK=no; }}
  {{ echo "Final pass finished."
     echo "- Copy: exit $P1. Re-copy of missing/different: $(wc -l < /var/log/fix.txt) files, exit $FX."
     echo "- Moved $SM files that R2 no longer has to $STALE (nothing deleted); $SF could not be moved."
     echo "- Independent check (both buckets listed in full): $M2 missing, $D2 size differences, $X2 stale, $ER2 listing errors. R2 has $RN2 files."
     echo "- Size-and-time dry run: $DRN files would still copy (exit $DR)."
     echo "- R2 quiet since start (bot really paused): $QUIET."
     echo "- Left as they are (never moved): $K2 Backblaze-only files in history/, raw/, research/."
     echo; echo "**Ready to switch: $OK.** Every line above must be 0 / exit 0 / yes for this to say yes."
     echo "Lists saved in Backblaze under bot/migration/logs/final-<time>/."; }} | say
fi
fi
finish
fi
fi
rclone copy /var/log "$DST/bot/migration/logs" --include 'copy*.log' --include 'check.log' || true
ID=$(curl -s http://169.254.169.254/metadata/v1/id)
curl -s -X DELETE -H "Authorization: Bearer $DOT" https://api.digitalocean.com/v2/droplets/$ID
"""


def switched():
    import boto3
    from botocore.exceptions import ClientError
    g = lambda k: "".join(os.environ.get(k, "").split())
    b2 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                      aws_access_key_id=g("B2_ACCESS_KEY_ID"), aws_secret_access_key=g("B2_SECRET_ACCESS_KEY"))
    try:
        b2.head_object(Bucket=g("B2_BUCKET"), Key="bot/migration/switched-at.txt")
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


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
    h0 = {"Authorization": f"Bearer {e('DIGITALOCEAN_TOKEN')}"}
    def tagged(tag):
        r = requests.get(f"{DO}/droplets", params={"tag_name": tag, "per_page": 200}, headers=h0, timeout=60)
        r.raise_for_status()
        return [d["name"] for d in r.json()["droplets"]]
    # Reviewer fix: never two copy machines at once (an old one could copy stale R2 files over new Backblaze ones)
    # Nov 9 (reviewer): once the final pass has said yes the bot writes to Backblaze, and copying R2 over it again
    # would put older files over newer ones. Refuse unless someone deliberately asks (AFTER_SWITCH=1).
    if os.environ.get("AFTER_SWITCH") != "1" and switched():
        sys.exit("refused: bot/migration/switched-at.txt exists in Backblaze, so the bot already uses it; copying R2 "
                 "over it again could replace newer files with older ones")
    if tagged("upfront-copy"):
        sys.exit(f"a copy machine is already running: {tagged('upfront-copy')}; not starting another")
    if mode == "final" and (tagged("upfront-bot") or tagged("site-build")):
        sys.exit("final pass refused: the bot isn't paused (rented machines still running: "
                 f"{tagged('upfront-bot') + tagged('site-build')})")
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
    # Nov 9 (reviewer): the full listing needs ~7 GB of memory, so the 8 GB size is only for the original copy
    for size in (SIZES if mode == "full" else [x for x in SIZES if "16gb" in x]):
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
