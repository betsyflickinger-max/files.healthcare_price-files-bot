#!/bin/bash
# One worker slot on an always-on server (dedicated/setup.sh): take the newest bot code, check in, read files from the
# shared queue until none fit, check in every minute while idle, repeat. systemd restarts it if it stops.
cd "$SLOT_DIR"
PY=/opt/pfb/venv/bin/python
checkin() {
  $PY - <<'PYEOF' || true
import os, json, time, boto3
g = lambda k: ''.join(os.environ[k].split())
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"), aws_access_key_id=g('R2_ACCESS_KEY_ID'),
                  aws_secret_access_key=g('R2_SECRET_ACCESS_KEY'), region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
n = 'upfront-fleet-' + os.environ['WORKER_NAME']
s3.put_object(Bucket=g('R2_BUCKET'), Key=f'bot/fleet/dedicated/{os.environ["WORKER_NAME"]}.json',
              Body=json.dumps(dict(name=n, mem=int(os.environ['WORKER_MEM']), at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))).encode())
PYEOF
}
while true; do
  git pull -q --ff-only || true
  (cd insurers/pipeline/mrfrows && PATH=$PATH:/usr/local/go/bin go build -o mrfrows . 2>/dev/null) || true
  checkin
  $PY insurers/worker.py || true
  for k in 1 2 3 4 5; do checkin; sleep 60; done
done
