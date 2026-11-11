"""Backblaze compatibility test for the storage move (Nov 9, 2026). Read-mostly; writes only under bot/cutover-test/
and removes its own test files afterwards. Uses the same storage calls the bot uses, pointed at Backblaze."""
import io, os, sys, time, json, datetime as dt
import boto3, duckdb
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

g = lambda k: "".join(os.environ.get(k, "").split())
EP, B, REG = g("STORAGE_ENDPOINT"), g("R2_BUCKET"), g("STORAGE_REGION") or "us-east-005"
s3 = boto3.client("s3", endpoint_url=EP, aws_access_key_id=g("R2_ACCESS_KEY_ID"), aws_secret_access_key=g("R2_SECRET_ACCESS_KEY"),
                  region_name=REG, config=Config(retries={"max_attempts": 5}))
T = f"bot/cutover-test/{dt.datetime.utcnow():%Y%m%dT%H%M%S}/"
res = []


def check(name, fn):
    t0 = time.time()
    try:
        out = fn(); ok = True
    except Exception as e:
        out, ok = f"{type(e).__name__}: {str(e)[:300]}", False
    res.append((name, ok, out, round(time.time() - t0, 1)))
    print(("PASS " if ok else "FAIL ") + name, "|", out, f"({res[-1][3]}s)", flush=True)


def write_if_new():
    """Job claiming on Backblaze: 4 machines race for the same claim; exactly one must win (fleet.create_only)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "insurers"))
    import fleet
    from concurrent.futures import ThreadPoolExecutor
    k = T + "claim.json"
    def go(i):
        me = {"name": f"m{i}", "droplet_id": i}
        return fleet.create_only(s3, B, k, json.dumps(me).encode(), lambda c: c.get("name") == me["name"])
    rounds = []
    for r in range(3):
        kk = k.replace(".json", f"{r}.json")
        def go2(i, kk=kk):
            me = {"name": f"m{i}", "droplet_id": i}
            return fleet.create_only(s3, B, kk, json.dumps(me).encode(), lambda c: c.get("name") == me["name"])
        with ThreadPoolExecutor(4) as ex:
            wins = sum(ex.map(go2, range(4)))
        rounds.append(wins)
    if rounds != [1, 1, 1]:
        raise RuntimeError(f"winners per round {rounds} (must be exactly 1 each)")
    return f"3 races of 4 machines: exactly one winner each time {rounds}"


def big_copy():
    src, dst = T + "big_src.bin", T + "big_dst.bin"
    data = os.urandom(80 << 20)
    s3.upload_fileobj(io.BytesIO(data), B, src, Config=TransferConfig(multipart_threshold=16 << 20, multipart_chunksize=16 << 20))
    big = TransferConfig(multipart_threshold=16 << 20, multipart_chunksize=32 << 20, max_concurrency=4)  # forces multipart copy
    s3.copy({"Bucket": B, "Key": src}, B, dst, Config=big)
    a, b = s3.head_object(Bucket=B, Key=src)["ContentLength"], s3.head_object(Bucket=B, Key=dst)["ContentLength"]
    if a != b:
        raise RuntimeError(f"sizes differ {a} vs {b}")
    s3.delete_object(Bucket=B, Key=src)
    return f"80 MB multipart copy OK, sizes match ({a:,}); source removed like worker.move()"


def copy_object_small():
    k1, k2 = T + "small.txt", T + "small_copy.txt"
    s3.put_object(Bucket=B, Key=k1, Body=b"hello")
    s3.copy_object(Bucket=B, Key=k2, CopySource={"Bucket": B, "Key": k1})
    return s3.get_object(Bucket=B, Key=k2)["Body"].read().decode()


def range_read():
    k = T + "small.txt"
    return s3.get_object(Bucket=B, Key=k, Range="bytes=1-3")["Body"].read().decode()


def list_rates():
    n, pages, kw = 0, 0, {"Bucket": B, "Prefix": "data/full/rates/"}
    while True:
        r = s3.list_objects_v2(**kw); pages += 1; n += r.get("KeyCount", 0)
        if not r.get("IsTruncated"): break
        kw["ContinuationToken"] = r["NextContinuationToken"]
    return f"{n} tables in {pages} page(s)"


def duck_read():
    k = s3.list_objects_v2(Bucket=B, Prefix="data/full/rates/", MaxKeys=1)["Contents"][0]["Key"]
    con = duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs;")
    host = EP.split("://")[-1].rstrip("/")
    con.execute(f"create or replace secret store (type s3, key_id '{g('R2_ACCESS_KEY_ID')}', secret '{g('R2_SECRET_ACCESS_KEY')}', "
                f"endpoint '{host}', region '{REG}', url_style 'path')")
    rows = con.execute(f"select sum(num_rows) from (select distinct row_group_id, row_group_num_rows as num_rows "
                       f"from parquet_metadata('s3://{B}/{k}'))").fetchone()[0]
    one = con.execute(f"select billing_code from read_parquet('s3://{B}/{k}') limit 1").fetchone()
    return f"{k.split('/')[-1]}: {rows:,} rows from footer; first row read OK ({one[0] if one else '-'})"


def delete_batch():
    ks = [o["Key"] for o in s3.list_objects_v2(Bucket=B, Prefix=T).get("Contents", [])]
    r = s3.delete_objects(Bucket=B, Delete={"Objects": [{"Key": k} for k in ks]})
    if r.get("Errors"):
        raise RuntimeError(r["Errors"][:3])
    return f"removed {len(ks)} test files (hidden copies expire via the bot/ 30-day rule)"


check("1. job claiming (create-only, Backblaze method)", write_if_new)
check("2. multipart copy of a big file (table moves)", big_copy)
check("3. small copy_object", copy_object_small)
check("4. range read", range_read)
check("5. list data/full/rates/", list_rates)
check("6. DuckDB read over S3 (Backblaze)", duck_read)
check("7. batch delete of test files", delete_batch)

summ = os.environ.get("GITHUB_STEP_SUMMARY")
if summ:
    with open(summ, "a") as f:
        f.write("## Backblaze compatibility test\n\n| Test | Result | Detail | Seconds |\n|---|---|---|---:|\n")
        for n, ok, out, s in res:
            f.write(f"| {n} | {'✅' if ok else '❌'} | {str(out).replace('|', '/')} | {s} |\n")
sys.exit(0 if all(r[1] for r in res) else 1)
