"""Add, change or remove a preview tester login (Nov 12, 2026; the "Tester logins" job, .github/workflows/tester-logins.yml).

After the storage move (Nov 11) logins are no longer edited by hand with site_files.py from a laptop: this job does the
same pull, edit, push, but holds the deploy lock the whole time and saves to the bot's storage, so nothing is undone.

Only the SHA-256 of "name:password" is given to the job and kept in functions/_middleware.js. The password itself
never goes into GitHub: Claude (or Betsy) makes the hash in chat and passes only that.

  python site/testers.py run add|change|remove NAME [HASH]     # the whole job: lock, pull, edit, deploy, save, check
  python site/testers.py edit DIR add|change|remove NAME [HASH] # just the edit, on an unpacked site (tests use this)
"""
import io
import json
import re
import sys
import tarfile

PAT = re.compile(r"const TESTERS = (\{[^}]*\});")


def _read(js):
    m = PAT.search(js)
    if not m:
        sys.exit("STOP: could not find the TESTERS list in functions/_middleware.js; nothing changed")
    return m, json.loads(m.group(1))


def edit_js(js, action, name, h=""):
    """Return (new_js, count). Never prints a hash."""
    name, h = name.strip().lower(), (h or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{1,40}", name):
        sys.exit("STOP: the name must be one word of letters or numbers (e.g. sarah); nothing changed")
    if action in ("add", "change") and not re.fullmatch(r"[0-9a-f]{64}", h):
        sys.exit("STOP: login_hash must be the 64-character SHA-256 of name:password; nothing changed")
    m, t = _read(js)
    have = [k for k, v in t.items() if v == name]
    if action == "add":
        if have:
            sys.exit(f"STOP: '{name}' already has a login. Use 'change' to give them a new password; nothing changed")
        if h in t:
            sys.exit("STOP: that login hash is already in use; nothing changed")
        t[h] = name
    elif action == "change":
        if not have:
            sys.exit(f"STOP: '{name}' has no login yet. Use 'add'; nothing changed")
        if h in t:
            sys.exit("STOP: that is already their password (or another tester's); nothing changed")
        for k in have:
            del t[k]
        t[h] = name
    elif action == "remove":
        if not have:
            sys.exit(f"STOP: '{name}' has no login; nothing changed")
        for k in have:
            del t[k]
    else:
        sys.exit("STOP: action must be add, change or remove")
    new = "const TESTERS = " + json.dumps(t) + ";"
    return js[:m.start()] + new + js[m.end():], len(t)


def edit(d, action, name, h=""):
    p = f"{d}/functions/_middleware.js"
    js, n = edit_js(open(p, encoding="utf-8").read(), action, name, h)
    open(p, "w", encoding="utf-8").write(js)
    print(f"{action} '{name.strip().lower()}': {n} tester logins after the change")


def check(js, action, name, h=""):
    """True when the saved site shows the change."""
    _, t = _read(js)
    name, h = name.strip().lower(), (h or "").strip().lower()
    if action == "remove":
        return name not in t.values()
    return t.get(h) == name and list(t.values()).count(name) == 1


def run(action, name, h=""):
    import deploy_lock
    import site_files
    s3, B = site_files.s3, site_files.B
    deploy_lock.acquire(s3, B, "tester logins")   # held from the pull to the save; push() reuses it
    d = "w"
    site_files.pull(d)
    edit(d, action, name, h)
    site_files.push(d)
    body = s3.get_object(Bucket=B, Key=site_files.KEY)["Body"].read()
    with tarfile.open(fileobj=io.BytesIO(body)) as t:
        m = next(x for x in t.getmembers() if x.name.endswith("functions/_middleware.js"))
        js = t.extractfile(m).read().decode()
    if not check(js, action, name, h):
        sys.exit("CHECK FAILED: the saved site does not show the change. Tell Claude.")
    print(f"checked: the saved site shows the {action} for '{name.strip().lower()}'")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run":
        run(a[1], a[2], a[3] if len(a) > 3 else "")
    elif a and a[0] == "edit":
        edit(a[1], a[2], a[3], a[4] if len(a) > 4 else "")
    else:
        sys.exit(__doc__)
