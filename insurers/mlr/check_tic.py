# Oct 16, 2026 one-off research script (CMS MLR 2024 -> master_insurers.csv, parents.csv). Paths point at the research
# folder it ran in (/home/claude/research/insurers/ with raw/mlr2024 unzipped from cms.gov mlr-public-use-file-2024.zip).
import subprocess, re, sys, json, os, hashlib
C=[l.split('|',1) for l in open(sys.argv[1]).read().strip().splitlines()]
out=[]
for name,url in C:
    f='/home/claude/research/insurers/raw/tic_check/'+hashlib.md5(url.encode()).hexdigest()+'.html'
    r=subprocess.run(['curl','-sSL','-m','25','-A','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36','-o',f,'-w','%{http_code} %{url_effective}',url],capture_output=True,text=True)
    code=r.stdout.strip(); body=open(f,errors='ignore').read() if os.path.exists(f) else ''
    t=re.search(r'<title[^>]*>(.*?)</title>',body,re.S|re.I); t=re.sub(r'\s+',' ',t.group(1)).strip()[:80] if t else ''
    kw=bool(re.search(r'machine[- ]readable|transparency[- ]in[- ]coverage|in-network-rates|_index\.json',body,re.I))
    print(f'{name}\t{code}\tkw={kw}\t{t}\t{url}' + ('' if not r.stderr else '\tERR '+r.stderr.strip()[:80]))
