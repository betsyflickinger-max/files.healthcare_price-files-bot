"""Copy dashboard data files to R2 control/data/ for Betsy's private control center (files.healthcare/control).

Usage: python board/to_r2_control.py <folder> <glob> [<glob> ...]
The site's Pages Function reads them from there (R2 binding PF), so the control center is always current
without a Claude upload step. Never stops the workflow: errors are printed and the script exits 0.
"""
import glob
import os
import sys

import boto3


def env(name):
    """A secret, minus any spaces or line breaks that came along when it was pasted in (as bot/store.py does)."""
    return "".join(os.environ.get(name, "").split())


def main():
    folder, pats = sys.argv[1], sys.argv[2:]
    s3 = boto3.client("s3", endpoint_url=f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                      aws_access_key_id=env("R2_ACCESS_KEY_ID"), aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"),
                      region_name="auto")
    n = 0
    for pat in pats:
        for f in sorted(glob.glob(os.path.join(folder, pat))):
            s3.upload_file(f, env("R2_BUCKET"), "control/data/" + os.path.basename(f),
                           ExtraArgs={"ContentType": "application/json", "CacheControl": "no-cache"})
            n += 1
    print(f"control center: copied {n} files to R2 control/data/")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # the control center is a convenience; never fail the bot over it
        print(f"::warning::control center copy failed: {e}")
