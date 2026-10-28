#!/bin/bash
# One-time setup of an always-on server (Hetzner dedicated, Ubuntu 24.04), run by .github/workflows/setup-dedicated.yml
# over SSH. Oct 18, 2026 (Betsy: rent monthly servers instead of hourly machines).
# The server then reads insurer files from the same shared queue as the rented machines (insurers/worker.py), one
# worker per slot below, around the clock. Nothing deletes itself; the launcher stops renting a machine for a job an
# idle slot here can take (insurers/fleet.py idle_dedicated). Re-running this script is safe (it updates in place).
# env in: R2_*, DIGITALOCEAN_TOKEN (to see which website builds are running), BOT_GITHUB_TOKEN, IA_*, SERVER (short name, e.g. hz1), SLOTS (memory per worker, e.g. "32 32 16 16")
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y python3-venv git curl
[ -x /usr/local/go/bin/go ] || curl -sL https://go.dev/dl/go1.26.9.linux-amd64.tar.gz | tar -C /usr/local -xz
mkdir -p /opt/pfb
umask 077
cat > /opt/pfb/env <<ENV
R2_ACCOUNT_ID=$R2_ACCOUNT_ID
R2_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY
R2_BUCKET=$R2_BUCKET
STORAGE_ENDPOINT=${STORAGE_ENDPOINT:-}
STORAGE_REGION=${STORAGE_REGION:-}
BOT_GITHUB_TOKEN=${BOT_GITHUB_TOKEN:-}
DIGITALOCEAN_TOKEN=${DIGITALOCEAN_TOKEN:-}
IA_ACCESS_KEY=${IA_ACCESS_KEY:-}
IA_SECRET_KEY=${IA_SECRET_KEY:-}
NO_SELF_DELETE=1
ENV
umask 022
[ -d /opt/pfb/venv ] || python3 -m venv /opt/pfb/venv
i=0
for mem in $SLOTS; do
  i=$((i + 1)); d=/opt/pfb/w$i
  [ -d $d/.git ] || git clone --depth 1 https://github.com/betsyflickinger-max/price-files-bot.git $d
  git -C $d pull -q --ff-only || true
  (cd $d/insurers/pipeline/mrfrows && PATH=$PATH:/usr/local/go/bin go build -o mrfrows .)
  cat > /etc/systemd/system/pfb-w$i.service <<UNIT
[Unit]
Description=price-files-bot queue worker $i ($mem GB)
After=network-online.target
[Service]
EnvironmentFile=/opt/pfb/env
Environment=WORKER_NAME=$SERVER-w$i WORKER_MEM=$mem SLOT_DIR=$d
ExecStart=/bin/bash $d/dedicated/run_worker.sh
Restart=always
RestartSec=60
[Install]
WantedBy=multi-user.target
UNIT
done
/opt/pfb/venv/bin/pip install -q -r /opt/pfb/w1/insurers/requirements-worker.txt -r /opt/pfb/w1/requirements.txt
systemctl daemon-reload
for j in $(seq 1 $i); do systemctl enable --now pfb-w$j; systemctl restart pfb-w$j; done
sleep 5; systemctl --no-pager --lines=0 status 'pfb-w*' | grep -E "pfb-w|Active"
nproc; free -g | head -2; df -h / | tail -1
