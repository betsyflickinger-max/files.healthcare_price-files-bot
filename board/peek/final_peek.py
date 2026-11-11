import os, boto3, collections
b2 = boto3.client("s3", endpoint_url="https://s3.us-east-005.backblazeb2.com", region_name="us-east-005",
                  aws_access_key_id=os.environ["B2K"], aws_secret_access_key=os.environ["B2S"])
B = os.environ["B2B"].strip(); D = "bot/migration/logs/final-20261111-2002/"
def lines(n): return [l for l in b2.get_object(Bucket=B, Key=D+n)["Body"].read().decode(errors="replace").splitlines() if l.strip()]
dif = lines("v2-differ.txt")
dry = [l.split("NOTICE: ",1)[1].rsplit(": Skipped copy",1)[0] for l in lines("final-dryrun.log") if "Skipped copy as --dry-run" in l]
for name, ks in (("differ", dif), ("dry-run", dry)):
    c = collections.Counter(k.split("/")[0] + "/" + (k.split("/")[1] if "/" in k else "") for k in ks)
    print(name, len(ks), dict(c))
    print("  not site/:", [k for k in ks if not k.startswith("site/")][:20])
