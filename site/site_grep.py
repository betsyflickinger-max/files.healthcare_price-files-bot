"""Read-only: print lines around a pattern in a file of the live site (R2 site/deploy/current.tgz) or any R2 text object.

  python site/site_grep.py PATH_IN_SITE PATTERN [CONTEXT_CHARS]
  e.g. site/price-finder/index.html 'URLSearchParams|location\\.hash'   (run by .github/workflows/site-grep.yml)
"""
import io, os, re, sys, tarfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot"))
import store  # noqa: E402

s3, B = store.r2()
path, pat = sys.argv[1], sys.argv[2]
ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 300
if path.startswith("r2:"):
    text = s3.get_object(Bucket=B, Key=path[3:])["Body"].read().decode("utf-8", "replace")
else:
    t = tarfile.open(fileobj=io.BytesIO(s3.get_object(Bucket=B, Key="site/deploy/current.tgz")["Body"].read()))
    m = next(x for x in t.getmembers() if x.name.lstrip("./") == path.lstrip("./"))
    text = t.extractfile(m).read().decode("utf-8", "replace")
print(f"{path}: {len(text):,} chars")
for i, mm in enumerate(re.finditer(pat, text)):
    if i >= 40: print("... more"); break
    a, b = max(0, mm.start() - ctx), min(len(text), mm.end() + ctx)
    print(f"--- match {i + 1} at {mm.start():,}\n{text[a:b]}\n")
