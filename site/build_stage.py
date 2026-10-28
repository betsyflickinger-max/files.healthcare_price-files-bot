"""Print the stage of a build from its R2 state.json (used by workflows that loop until a build is done)."""
import json, os, sys
import boto3
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"), aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
try: print(json.loads(s3.get_object(Bucket=E['R2_BUCKET'], Key=sys.argv[1])['Body'].read()).get('stage', ''))
except Exception: print('')
