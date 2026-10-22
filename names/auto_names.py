"""Write plain-English names for Price Finder CPT codes that still show the insurer's wording.

Uses the Anthropic API (secret ANTHROPIC_API_KEY) with a small model. Reads the live Price Finder page from R2,
picks unnamed CPT codes (most prices first), asks for names in batches, checks them, and appends to
site/plain_names_auto.tsv. Hand-written names in site/plain_names_cpt.tsv always win.
Then patches the live page (site/deploy/price-finder.html + current.tgz in R2) so the names show right away.
env: MAX_CODES (default 20000), WORKERS (default 6), STOP_AFTER_MIN (default 300), BATCH (default 40), MODEL (default claude-haiku-5-5),
     FALLBACK_MODEL (default claude-sonnet-5-5; second try for codes MODEL declined; blank = off), APPLY (1 = patch live page)
"""
import io, json, os, re, sys, tarfile, time, urllib.request
import boto3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot'))
import api_credit  # noqa: E402

E = {k: v.strip() for k, v in os.environ.items()}
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
HAND, AUTO = f"{ROOT}/site/plain_names_cpt.tsv", f"{ROOT}/site/plain_names_auto.tsv"
DECLINED = f"{ROOT}/site/plain_names_declined.tsv"   # code<TAB>date both models declined; retried after RETRY_DAYS
MAX, BATCH, MODEL = int(E.get("MAX_CODES", "20000")), int(E.get("BATCH", "40")), E.get("MODEL", "claude-haiku-5-5")
s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                  aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
B = E["R2_BUCKET"]

def load(p):
    return dict(l.rstrip("\n").split("\t", 1) for l in open(p) if "\t" in l) if os.path.exists(p) else {}

def page_data(s):
    i = s.find('id="data"'); a = s.find(">", i) + 1; b = s.find("</script>", i)
    return a, b, json.loads(s[a:b])

PROMPT = """You write short plain-English names for US medical billing codes (CPT) for a public healthcare price website.
Each input line is: code<TAB>insurer's abbreviated description.
Rules:
- Write each name in your own everyday words that a patient understands (e.g. "Knee MRI without contrast", "Rapid strep test").
- Keep important details that change the price: body part, with/without contrast, under anesthesia, size ranges, number of levels or segments, number of views, first vs each extra (add-on), age group, time.
- Never copy the official CPT descriptor wording; never use ALL CAPS abbreviations.
- 3 to 12 words, at most 90 characters. No trailing period.
- If you are not confident what the code is, return null for it.
Return ONLY a JSON object mapping each code to its name or null."""

def ask(lines):
    body = json.dumps({"model": MODEL, "max_tokens": 16000, "system": PROMPT,
                       "messages": [{"role": "user", "content": "\n".join(lines)}]}).encode()
    for attempt in range(8):
        try:
            r = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                "x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"})
            out = json.load(urllib.request.urlopen(r, timeout=300))
            api_credit.ok("plain_names")
            txt = "".join(c.get("text", "") for c in out["content"])
            m = re.search(r"\{.*\}", txt, re.S)
            if not m:
                raise ValueError(f"no JSON in reply (stop={out.get('stop_reason')}, model={out.get('model')}): {txt[:300]!r}")
            return json.loads(m.group(0)), out.get("usage", {})
        except urllib.error.HTTPError as e:
            if e.code == 400:
                msg = e.read()[:600]
                if b"credit balance" in msg:   # Oct 22: stop instead of retrying 8 times per batch, and raise the flag
                    api_credit.out("plain_names")
                    print("  Anthropic API credit ran out; no names this run", flush=True)
                    return {}, {}
                print("  retry", attempt + 1, e.code, msg[:300], flush=True); time.sleep(10 * (attempt + 1)); continue
            wait = float(e.headers.get("retry-after") or 10 * (attempt + 1)) if e.code in (429, 529) else 10 * (attempt + 1)
            if e.code not in (429, 529): print("  retry", attempt + 1, e.code, e.read()[:300], flush=True)
            time.sleep(min(wait, 120))
        except Exception as e:
            print("  retry", attempt + 1, str(e)[:200], flush=True); time.sleep(10 * (attempt + 1))
    return {}, {}

def ok(code, name, insurer):
    if not isinstance(name, str): return False
    n = name.strip()
    return (8 <= len(n) <= 90 and not n.isupper() and n.upper() != (insurer or "").upper()
            and not re.search(r"\b(W/O|W/|EA|ADDL|SQ CM/<)\b", n))

s = s3.get_object(Bucket=B, Key="site/deploy/price-finder.html")["Body"].read().decode()
a, b, D = page_data(s)
hand, auto = load(HAND), load(AUTO)
import datetime as _dt
_cut = (_dt.date.today() - _dt.timedelta(days=int(E.get("RETRY_DAYS", "30")))).isoformat()
declined = {c: d for c, d in load(DECLINED).items() if d >= _cut}   # declined recently: don't pay to ask again yet
todo = sorted([(v.get("n") or 0, c, v["name"]) for c, v in D["codes"].items()
               if "name as written" in v.get("cat", "") and v["type"] == "CPT" and c not in hand and c not in auto
               and c not in declined],
              key=lambda x: -int(x[0] or 0))[:MAX]
print(f"unnamed CPT codes to try: {len(todo)}", flush=True)
new, skipped, tin, tout = {}, 0, 0, 0
import threading, concurrent.futures as cf
lock, t0 = threading.Lock(), time.time()
asked = set()
WORKERS, STOP = int(E.get("WORKERS", "6")), float(E.get("STOP_AFTER_MIN", "300")) * 60
def work(k):
    global skipped, tin, tout
    if time.time() - t0 > STOP: return
    chunk = todo[k:k + BATCH]
    res, use = ask([f"{c}\t{nm}" for _, c, nm in chunk])
    with lock:
        tin += use.get("input_tokens", 0); tout += use.get("output_tokens", 0)
        if res: asked.update(c for _, c, _n in chunk)
        got = {}
        for _, c, nm in chunk:
            v = res.get(c)
            if ok(c, v, nm): got[c] = v.strip().rstrip(".")
            else: skipped += 1
        new.update(got)
        with open(AUTO, "a") as f:   # save as we go so a stop never loses work
            for c, v in got.items(): f.write(f"{c}\t{v}\n")
        print(f"batch {k // BATCH + 1}: {len(new)} named so far, {skipped} left as is", flush=True)
with cf.ThreadPoolExecutor(WORKERS) as ex:
    list(ex.map(work, range(0, len(todo), BATCH)))
# Second pass (Oct 14): codes the small model wasn't sure about get one try with a stronger model (FALLBACK_MODEL,
# blank = off). Same rules and checks; it still returns null when unsure, so those keep the insurer's wording.
FALLBACK = E.get("FALLBACK_MODEL", "claude-sonnet-5-5")
if FALLBACK and FALLBACK != MODEL and time.time() - t0 < STOP:
    todo = [t for t in todo if t[1] not in new]
    print(f"second pass with {FALLBACK}: {len(todo)} codes", flush=True)
    MODEL, skipped, t0 = FALLBACK, 0, time.time()
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, range(0, len(todo), BATCH)))
print(f"named {len(new)}, left {skipped} with the insurer's wording; tokens in {tin}, out {tout}")
_today = _dt.date.today().isoformat()
_keep = {c: d for c, d in load(DECLINED).items() if c not in new}
_keep.update({c: _today for _, c, _n in todo if c in asked and c not in new})
with open(DECLINED, "w") as f:
    for c, d in sorted(_keep.items()): f.write(f"{c}\t{d}\n")
summ = os.environ.get("GITHUB_STEP_SUMMARY")
if summ:
    open(summ, "a").write(f"Named {len(new)} codes, {skipped} left with the insurer's wording. Tokens: {tin} in, {tout} out.\n")

# Oct 14: also patch names added by hand to plain_names_auto.tsv (or written by an earlier run) that the live page doesn't show yet
_named = {**load(AUTO), **load(HAND)}
_pending = [c for c, C in D["codes"].items() if c in _named and "name as written" in C.get("cat", "")]
if _pending: print(f"{len(_pending)} names on file not yet on the live page; patching them too", flush=True)
if E.get("APPLY") == "1" and (new or _pending):
    hand = load(HAND); names = {**load(AUTO), **hand}
    def patch(html):
        a, b, D = page_data(html); n = 0
        for c, C in D["codes"].items():
            if c in names and ("name as written" in C.get("cat", "") or (c in hand and C.get("name") != hand[c])):
                C["name"] = names[c]; C["cat"] = C["cat"].replace(" · name as written in the insurer file", ""); C.pop("d", None); n += 1
        return html[:a] + json.dumps(D, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/") + html[b:], n
    s2, n = patch(s)
    s3.put_object(Bucket=B, Key="site/deploy/price-finder.html", Body=s2.encode(), ContentType="text/html")
    tgz = s3.get_object(Bucket=B, Key="site/deploy/current.tgz")["Body"].read()
    os.makedirs("/tmp/site", exist_ok=True)
    tarfile.open(fileobj=io.BytesIO(tgz)).extractall("/tmp/site")
    open("/tmp/site/site/price-finder/index.html", "w").write(s2)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name in sorted(os.listdir("/tmp/site")): t.add(f"/tmp/site/{name}", arcname=name)
    s3.put_object(Bucket=B, Key="site/deploy/current.tgz", Body=buf.getvalue())
    print(f"patched live page: {n} codes renamed; deploy next", flush=True)
