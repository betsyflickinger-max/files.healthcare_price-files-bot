"""Local stand-in for files.healthcare (Nov 7, 2026), for the robot testers: serves the pulled site from disk and
answers the Price Finder's per-code rate requests (…/price-finder/pf/{t,h}/<code>.txt, st/, pf/g/) from R2 the same
way the site's Pages Functions do, by reading each function's R2 key. No password gate. Usage:
  python site/site_check/serve.py w 8765        (w = folder holding site/ and functions/ from site_files.py pull)
"""
import glob
import http.server
import os
import re
import sys
import urllib.parse

import boto3

W = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'w')
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
s3 = boto3.client('s3', endpoint_url=(os.environ.get('STORAGE_ENDPOINT') or f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                  aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                  region_name=(os.environ.get('STORAGE_REGION') or 'auto'))
B = E['R2_BUCKET']
CUR = None


def r2(key):
    try:
        return s3.get_object(Bucket=B, Key=key)['Body'].read()
    except Exception:
        return None


# route folder (e.g. "houston/price-finder/pf/t") -> function that turns the file name into an R2 key
ROUTES = {}
for f in glob.glob(os.path.join(W, 'functions', '**', '[[]*[]].js'), recursive=True):
    rel = os.path.relpath(os.path.dirname(f), os.path.join(W, 'functions')).replace(os.sep, '/')
    js = open(f, encoding='utf-8').read()
    m = re.search(r'const PREFIX = "([^"]+)"', js)
    get = re.search(r"PF\.get\(PREFIX \+ (.*?)\)", js)
    if m:
        pre, mid = m.group(1), ("t/" if get and "'t/'" in get.group(1) else "")
        ROUTES[rel] = (lambda pre, mid: lambda name: pre + mid + name)(pre, mid)
    elif "site/every/' + (await current" in js:
        sub = re.search(r"current\(ctx\.env\)\) \+ '([^']*)' \+ name", js)
        tail = re.search(r"current\(ctx\.env\)\) \+ '(/geo\.json)'", js)
        if sub:
            ROUTES[rel] = (lambda sub: lambda name: 'site/every/' + CURNOW() + sub + name)(sub.group(1))
        elif tail:
            ROUTES[rel] = lambda name: 'site/every/' + CURNOW() + '/geo.json'


def CURNOW():
    global CUR
    if CUR is None:
        CUR = (r2('site/every/CURRENT') or b'2026-10-08').decode().strip()
    return CUR


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(W, 'site'), **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.lstrip('/')
        d, name = os.path.dirname(path), os.path.basename(path)
        m = re.match(r'plan-calculator/own/t/([\w-]+)/([0-9A-Z]{1,5}\.txt)$', path)   # [build]/[code] route
        if m:
            body = r2(f'site/every/{m.group(1)}/t/{m.group(2)}')
            if body is None:
                self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
        if d in ROUTES and not os.path.isfile(os.path.join(W, 'site', path)):
            body = r2(ROUTES[d](name))
            if body is None:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json' if name.endswith('.json') else 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()


print(f'serving {W}/site on :{PORT} with {len(ROUTES)} rate routes', flush=True)
http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
