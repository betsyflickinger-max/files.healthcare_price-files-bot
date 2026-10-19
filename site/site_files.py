"""Edit hand-written pages on the preview site safely (Price File Watch, Methodology, ...).

  python site/site_files.py pull DIR    # unpack the live site (R2 site/deploy/current.tgz) into DIR/site and DIR/functions
  python site/site_files.py push DIR    # deploy DIR with wrangler, then save it back as site/deploy/current.tgz

The live site's source of truth is R2 site/deploy/current.tgz (the monthly refresh and city pages deploy from it), so
always pull, edit, push in one go: a push replaces the whole site. push refuses if current.tgz changed since the pull.
Needs R2_* and CLOUDFLARE_API_TOKEN in the environment (Healthcare/r2.env.txt and cf.env.txt on Betsy's Mac).
"""
import os
import subprocess
import sys
import tarfile

import boto3

E = {k: "".join(os.environ.get(k, "").split()) for k in
     ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "CLOUDFLARE_API_TOKEN")}
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B, KEY = E["R2_BUCKET"], "site/deploy/current.tgz"


def pull(d):
    os.makedirs(d, exist_ok=True)
    s3.download_file(B, KEY, f"{d}/site.tgz")
    with tarfile.open(f"{d}/site.tgz") as t:
        t.extractall(d)
    etag = s3.head_object(Bucket=B, Key=KEY)["ETag"]
    open(f"{d}/.etag", "w").write(etag)
    print(f"pulled {KEY} ({etag}) into {d}")


def push(d):
    if s3.head_object(Bucket=B, Key=KEY)["ETag"] != open(f"{d}/.etag").read():
        sys.exit("STOP: the live site changed since the pull (a build deployed). Pull again and redo the edit.")
    if not os.path.isfile(f"{d}/site/price-finder/index.html") or not os.path.isdir(f"{d}/functions"):
        sys.exit("STOP: DIR is missing site/ or functions/; nothing deployed")
    env = dict(os.environ, **E, CLOUDFLARE_ACCOUNT_ID=E["R2_ACCOUNT_ID"])
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sitewide.py'), d], check=True)   # name, Units look, share image (Oct 18)
    r = subprocess.run(["npx", "--yes", "wrangler@3.114.0", "pages", "deploy", "site", "--project-name", "upfront-dfw-preview",
                        "--branch", "main", "--commit-dirty=true"], cwd=d, env=env, capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
    if r.returncode != 0:
        sys.exit("deploy failed; the preview site is unchanged")
    with tarfile.open(f"{d}/site.tgz", "w:gz") as t:
        for name in [n for n in os.listdir(d) if n not in ("site.tgz", ".etag")]:  # site, functions, README.txt
            t.add(f"{d}/{name}", arcname=f"./{name}")
    s3.upload_file(f"{d}/site.tgz", B, KEY)
    open(f"{d}/.etag", "w").write(s3.head_object(Bucket=B, Key=KEY)["ETag"])
    print("deployed and saved to", KEY)


if __name__ == "__main__":
    {"pull": pull, "push": push}[sys.argv[1]](sys.argv[2])
