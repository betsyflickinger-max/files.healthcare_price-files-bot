"""A/B test of the insurer reader layouts on one real file (Oct 15, 2026). Runs on a rented machine.

1. Mississippi providers, flat layout (today's reader) and lines layout (each price once per provider group): times both,
   then checks they hold the same rows: per billing code, row count and an order-free checksum of every column;
   membership and contract-end tables row for row; census JSON key by key.
2. All seven states' providers, lines layout only: time and size, to set against the fleet's flat read of the same file.
Results: R2 work/test-reader/<file stem>/report.json (+ the lines tables, for later tests).
Env: R2_*, TEST_URL, TEST_LABEL."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
import boto3, duckdb

E = os.environ
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B = E["R2_BUCKET"]
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
URL, LABEL = E["TEST_URL"], E.get("TEST_LABEL", "")
NAME = URL.split("?")[0].rsplit("/", 1)[1]
STEM = NAME[:-8] if NAME.endswith(".json.gz") else NAME
OUT = f"work/test-reader/{STEM}/"
W = Path("/d"); W.mkdir(exist_ok=True); DATA.mkdir(parents=True, exist_ok=True); (W / "spill").mkdir(exist_ok=True)
rep = {"file": URL, "network": LABEL, "runs": {}}
def save(): s3.put_object(Bucket=B, Key=OUT + "report.json", Body=json.dumps(rep, indent=1, default=str).encode())

src = W / NAME
t = time.time()
subprocess.run(["curl", "-sSfL", "--retry", "5", "-o", str(src), URL], check=True)
rep["download_min"] = round((time.time() - t) / 60, 1); rep["file_bytes"] = src.stat().st_size; save()
s3.download_file(B, "data/s7/state/mississippi/npis.parquet", str(W / "ms.parquet"))
s3.download_file(B, "data/scope/s7_npis_all.parquet", str(W / "s7.parquet"))

def run(name, scope, layout):
    for sub in ("rates", "npisets", "membership", "codes", "census", "ends"):
        shutil.rmtree(DATA / sub, ignore_errors=True)
    t0 = time.time()
    p = subprocess.run([sys.executable, str(HERE / "06f_full_extract.py"), str(src), "--network", LABEL, "--scope", str(W / scope),
                        "--source-url", URL.split("?")[0]], cwd=HERE, capture_output=True, text=True, env=dict(E, RATES_LAYOUT=layout))
    mins = round((time.time() - t0) / 60, 1)
    log = (p.stdout + p.stderr).splitlines()
    dest = W / "out" / name; shutil.rmtree(dest, ignore_errors=True); dest.mkdir(parents=True)
    for sub in ("rates", "npisets", "membership", "census", "ends"):
        if (DATA / sub).exists(): shutil.copytree(DATA / sub, dest / sub)
    size = lambda sub: sum(f.stat().st_size for f in (dest / sub).glob("*.parquet")) if (dest / sub).exists() else 0
    rep["runs"][name] = {"layout": layout, "scope": scope, "exit": p.returncode, "total_min": mins,
                         "read_line": [l for l in log if "done:" in l or "lines layout" in l or "wrote" in l][-4:],
                         "rates_bytes": size("rates"), "npisets_bytes": size("npisets"), "log_tail": log[-6:]}
    save()
    return dest

a = run("ms-flat", "ms.parquet", "flat")
b = run("ms-lines", "ms.parquet", "lines")

# ---------- compare ----------
sys.path.insert(0, str(HERE)); sys.argv = ["x"]
import importlib.util
spec = importlib.util.spec_from_file_location("f6", HERE / "06f_full_extract.py"); f6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(f6)
c = duckdb.connect(); c.execute("set memory_limit='8GB'; set threads=6; set preserve_insertion_order=false; set temp_directory='/d/spill'")
fa = next((a / "rates").glob("*.parquet")); fb = next((b / "rates").glob("*.parquet"))
FA, FB = f"read_parquet('{fa}')", f6.flat_sql(fb, b / "npisets" / fb.name)
ca = [r[0] for r in c.execute(f"describe select * from {FA}").fetchall()]; cb = [r[0] for r in c.execute(f"describe select * from {FB}").fetchall()]
cmp = {"columns_same": ca == cb}
hs = "hash(" + ", ".join(f'"{x}"' for x in ca) + ")"
q = lambda T: {r[0]: (r[1], int(r[2])) for r in c.execute(f"select billing_code, count(*), sum({hs}::hugeint) from {T} group by 1").fetchall()}
ka, kb = q(FA), q(FB)
cmp.update(codes_flat=len(ka), codes_lines=len(kb), rows_flat=sum(v[0] for v in ka.values()), rows_lines=sum(v[0] for v in kb.values()),
           codes_differ=sorted(k for k in set(ka) | set(kb) if ka.get(k) != kb.get(k))[:50])
for sub in ("membership", "ends"):
    pa_, pb_ = list((a / sub).glob("*.parquet")), list((b / sub).glob("*.parquet"))
    if pa_ and pb_:
        A_, B_ = f"read_parquet('{pa_[0]}')", f"read_parquet('{pb_[0]}')"
        cmp[sub] = c.execute(f"select (select count(*) from {A_}), (select count(*) from (select * from {A_} except all select * from {B_})), "
                             f"(select count(*) from (select * from {B_} except all select * from {A_}))").fetchone()
ja, jb = list((a / "census").glob("*.json")), list((b / "census").glob("*.json"))
if ja and jb:
    x, y = json.loads(ja[0].read_text()), json.loads(jb[0].read_text())
    cmp["census_keys_differ"] = sorted(k for k in set(x) | set(y) if k != "checked_on" and x.get(k) != y.get(k))
cmp["result"] = "PASS" if (cmp["columns_same"] and not cmp["codes_differ"] and cmp["rows_flat"] == cmp["rows_lines"]
                           and all(cmp.get(s_, (0, 0, 0))[1:] == (0, 0) for s_ in ("membership", "ends")) and not cmp.get("census_keys_differ")) else "FAIL"
rep["ms_compare"] = cmp; save()
for sub in ("rates", "npisets"):
    for f in (b / sub).glob("*.parquet"): s3.upload_file(str(f), B, f"{OUT}ms-lines/{sub}/{f.name}")
shutil.rmtree(W / "out" / "ms-flat", ignore_errors=True)

d = run("s7-lines", "s7.parquet", "lines")
for sub in ("rates", "npisets", "membership"):
    for f in (d / sub).glob("*.parquet"): s3.upload_file(str(f), B, f"{OUT}s7-lines/{sub}/{f.name}")
rep["done"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()); save()
print(json.dumps(rep, indent=1, default=str))
