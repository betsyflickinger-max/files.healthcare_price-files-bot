"""Read-only: explain why the final copy pass said 'Ready to switch: no'."""
import os, json, collections, boto3
b2 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                  aws_access_key_id=os.environ["B2K"], aws_secret_access_key=os.environ["B2S"])
r2 = boto3.client("s3", endpoint_url=f"https://{os.environ['R2A']}.r2.cloudflarestorage.com", region_name="auto",
                  aws_access_key_id=os.environ["R2K"], aws_secret_access_key=os.environ["R2S"])
B, R = os.environ["B2B"], os.environ["R2B"]
objs = []
for p in b2.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix="bot/migration/logs/final-"):
    objs += p.get("Contents", [])
for o in objs: print(o["Key"], o["Size"])
def body(k): return b2.get_object(Bucket=B, Key=k)["Body"].read().decode(errors="replace")
def pref(k, n=2): return "/".join(k.split("/")[:n])
for o in objs:
    k = o["Key"]
    if k.endswith("summary.json"): print("==", k); print(body(k)[:1500])
for name in ("v2-differ.txt", "v2-extra.txt", "v2-missing.txt", "v1-differ.txt"):
    for o in objs:
        if o["Key"].endswith("/" + name):
            ks = [l for l in body(o["Key"]).splitlines() if l.strip()]
            print(f"== {name}: {len(ks)}")
            for p, c in collections.Counter(pref(k, 3) for k in ks).most_common(25): print(f"  {c:7d} {p}")
            for k in ks[:12]:
                try: a = r2.head_object(Bucket=R, Key=k); ra = (a["ContentLength"], str(a["LastModified"]))
                except Exception as e: ra = ("R2 err", type(e).__name__)
                try: b = b2.head_object(Bucket=B, Key=k); bb = (b["ContentLength"], str(b["LastModified"]))
                except Exception as e: bb = ("B2 err", type(e).__name__)
                print("   ", k, "R2", ra, "B2", bb)
for o in objs:
    if o["Key"].endswith("final-dryrun.log"):
        ks = [l.split("NOTICE: ", 1)[1].rsplit(": Skipped copy", 1)[0] for l in body(o["Key"]).splitlines() if "Skipped copy as --dry-run" in l]
        print(f"== dry-run would copy: {len(ks)}")
        for p, c in collections.Counter(pref(k, 3) for k in ks).most_common(25): print(f"  {c:7d} {p}")
        for k in ks[:8]:
            a = r2.head_object(Bucket=R, Key=k); b = b2.head_object(Bucket=B, Key=k)
            print("   ", k, "R2", a["ContentLength"], a["LastModified"], "B2", b["ContentLength"], b["LastModified"])
