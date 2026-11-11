import os, boto3
b2 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                  aws_access_key_id=os.environ["B2K"], aws_secret_access_key=os.environ["B2S"])
r2 = boto3.client("s3", endpoint_url=f"https://{os.environ['R2A'].strip()}.r2.cloudflarestorage.com", region_name="auto",
                  aws_access_key_id=os.environ["R2K"], aws_secret_access_key=os.environ["R2S"])
B, R = os.environ["B2B"].strip(), os.environ["R2B"].strip()
print("B2 LOCK.json:", b2.get_object(Bucket=B, Key="site/deploy/LOCK.json")["Body"].read().decode())
for pre in ("site/deploy/", "logs/deploy", "site/.deploy", "control/"):
    for p in r2.get_paginator("list_objects_v2").paginate(Bucket=R, Prefix=pre):
        for o in p.get("Contents", []):
            if str(o["LastModified"]) > "2026-11-11 16:00":
                print("R2", o["Key"], o["Size"], o["LastModified"])
                if o["Size"] < 3000 and not o["Key"].endswith((".tgz",)):
                    print("   ", r2.get_object(Bucket=R, Key=o["Key"])["Body"].read().decode(errors="replace")[:1500])
