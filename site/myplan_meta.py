"""Build the data file for the Plan Calculator's "plan through work or elsewhere" mode (My Plan).

  python site/myplan_meta.py SITE_DIR      # SITE_DIR = an unpacked live site (site_files.py pull DIR -> DIR/site)

Reads the DFW Price Finder's data block (SITE_DIR/price-finder/index.html) and the per-code rate files of the
build named in R2 site/every/CURRENT, then writes SITE_DIR/plan-calculator/own/meta.txt (gzip, base64):
  build  the rate build the page reads (pinned, so facility numbers always match; served by
         functions/plan-calculator/own/t/[build]/[code].js from R2 site/every/<build>/t/<code>.txt)
  codes  the 89 procedures the calculator offers {code: [name, category]}
  nets, urls, dates, labs  as in the Price Finder
  fac    {index: [name, city, kind]} for providers that have a rate for one of the 89 codes
  scope  {network: [codes]} for networks read for only some codes, limited to the 89
Re-run after every DFW Price Finder refresh (the page keeps working on the old build until then).
"""
import base64
import gzip
import json
import os
import sys

import boto3

# The 89 procedures of the original My Plan page (the 70 CMS shoppable services plus common visits, scans, labs and surgeries). Categories decide which line of the visitor's plan summary applies.
CODES = "90832 90834 90837 90846 90847 90853 99203 99204 99205 99243 99244 99385 99386 80048 80053 80055 80061 80069 80076 81000 81001 81002 81003 84153 84154 84443 85025 85027 85610 85730 88305 70450 70551 70553 72110 72148 72193 73721 74177 75571 76700 76805 76830 77065 77066 77067 216 460 470 473 743 19120 22551 27130 27447 29826 29827 29881 29888 42820 43235 43239 43644 43775 45378 45380 45385 45391 47562 49505 55250 55700 55866 59400 59510 59610 62322 62323 63030 64483 64721 66821 66984 93000 93452 95810 97110 00811 00812".split()


def r2():
    g = lambda k: "".join(os.environ[k].split())
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"),
                      aws_access_key_id=g("R2_ACCESS_KEY_ID"), aws_secret_access_key=g("R2_SECRET_ACCESS_KEY"), region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    return s3, g("R2_BUCKET")


def unpack(b):
    raw = base64.b64decode(b.strip())
    try:
        return json.loads(gzip.decompress(raw))
    except OSError:
        return json.loads(raw)


def main(site):
    s = open(f"{site}/price-finder/index.html", encoding="utf-8").read()
    tag = '<script type="application/json" id="data">'
    i = s.index(tag) + len(tag)
    D = json.loads(s[i:s.index("</script>", i)])
    s3, B = r2()
    build = s3.get_object(Bucket=B, Key="site/every/CURRENT")["Body"].read().decode().strip()
    codes = [c for c in CODES if c in D["codes"]]
    if len(codes) != len(CODES):
        sys.exit(f"STOP: the Price Finder lacks {sorted(set(CODES) - set(codes))}")
    used = set()
    for c in codes:
        f = unpack(s3.get_object(Bucket=B, Key=f"site/every/{build}/t/{c}.txt")["Body"].read())["f"]
        used.update(int(k) for k in f)
    if max(used) >= len(D["fac"]):
        sys.exit(f"STOP: build {build} names provider {max(used)}, but the Price Finder page lists {len(D['fac'])}: page and build don't match")
    M = {"build": build,
         "codes": {c: [D["codes"][c]["name"], D["codes"][c]["cat"]] for c in codes},
         "nets": D["nets"], "urls": D["urls"], "dates": D["dates"], "labs": D["labs"],
         "fac": {str(k): D["fac"][k][:3] for k in sorted(used)},
         "scope": {n: [c for c in v if c in set(codes)] for n, v in D.get("scope", {}).items() if len(v) < len(D["codes"])}}
    os.makedirs(f"{site}/plan-calculator/own", exist_ok=True)
    out = base64.b64encode(gzip.compress(json.dumps(M, separators=(",", ":")).encode(), 9)).decode()
    open(f"{site}/plan-calculator/own/meta.txt", "w").write(out)
    print(f"meta.txt: build {build}, {len(codes)} codes, {len(used):,} providers, {len(out) / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1])
