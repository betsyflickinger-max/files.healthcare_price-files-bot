"""Launch fixes (Nov 4, 2026; Betsy's "do now" list). Ports the shared data fixes from the V2 Redesign review (Oct 31,
branch v2-redesign, never merged) to the live site:

  F01  the Perry, Iowa "Dallas County Hospital" price file (dallascohospital.org, CCN 161322) was tied to Parkland by name.
       site/source_quarantine.csv + site/hospital_file_ccn.csv now say so; this rebuilds /hospitals/ so Parkland's profile
       stops showing that file's $788. (Maps and procedure pages pick it up at their next build.)
  F02  Compare-view bill slips follow the payment choice (cash shows cash prices): site/assets/pf-table.js, shipped by
       sitewide.apply().
  F03  Plan Calculator tab counts = distinct providers after the same exclusions as the list, and the page renders again
       once /calc-link.js (deferred) has loaded, so the first view matches later ones (was 60 vs 58, 19 vs 10).

  My Plan  re-pins the "plan through work" mode to the live build (site/myplan_meta.py; it was pinned to Oct 12 and older
           builds get deleted). site/orchestrate.py now does this on every monthly refresh.

  python site/launch_fixes.py DIR      # DIR from site_files.py pull; then site_files.py push DIR
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OLD_TABS = ("const all=D.rates.filter(r=>r[0]===p.k&&r[1]===pi);const nPro=all.filter(isPro).length;\n"
            "  $('kfac').textContent=`Facility fees (${all.length-nPro})`;$('kpro').textContent=`Doctor fees (${nPro})`;")
NEW_TABS = ("const all=D.rates.filter(r=>r[0]===p.k&&r[1]===pi);"
            "/*F03 Oct 31: tab counts = distinct providers after the same exclusions as the list*/"
            "const okR=r=>(!window.__calcSkip||!window.__calcSkip(D.prov[r[2]][0],D.proc[pi]&&D.proc[pi][1]))&&!!p.cs[r[5]];"
            "const nU=f=>new Set(all.filter(r=>f(r)&&okR(r)).map(r=>r[2])).size;\n"
            "  $('kfac').textContent=`Facility fees (${nU(r=>!isPro(r))})`;$('kpro').textContent=`Doctor fees (${nU(isPro)})`;")
TAIL = "fillIns();fillPlans();fillProcs();render();"
TAIL_FIX = "/*F03b*/document.addEventListener('DOMContentLoaded',function(){try{render()}catch(e){}});"


def calculator(site):
    p = os.path.join(site, 'plan-calculator', 'index.html')
    s = open(p, encoding='utf-8').read()
    done = []
    if '/*F03 Oct 31' not in s:
        if OLD_TABS not in s:
            raise SystemExit('STOP: calculator tab-count code changed; F03 not applied (check the page by hand)')
        s = s.replace(OLD_TABS, NEW_TABS, 1); done.append('tab counts')
    if '/*F03b*/' not in s:
        if TAIL not in s:
            raise SystemExit('STOP: calculator render line changed; F03b not applied')
        s = s.replace(TAIL, TAIL + TAIL_FIX, 1); done.append('second render')
    open(p, 'w', encoding='utf-8').write(s)
    return done or ['already']


def main(w):
    site = os.path.join(w, 'site')
    import sitewide
    sitewide.apply(w)                                   # ships site/assets/pf-table.js (F02) like every deploy path
    pf = open(os.path.join(site, 'pf-table.js'), encoding='utf-8').read()
    assert 'lowest to highest cash price' in pf, 'F02 not in the shipped pf-table.js'
    print('F02 cash slips: shipped')
    import hospital_profiles
    hospital_profiles.main(w, os.path.join(w, '.hosp_cache'))
    bad = [d for d in os.listdir(os.path.join(site, 'hospitals')) if 'parkland' in d
           and '$788' in open(os.path.join(site, 'hospitals', d, 'index.html'), encoding='utf-8').read()]
    assert not bad, f'Parkland still shows $788: {bad}'
    print('F01 hospital profiles: rebuilt; Parkland no longer shows $788')
    print('F03 calculator:', ', '.join(calculator(site)))
    import myplan_meta
    myplan_meta.main(site)


if __name__ == '__main__':
    main(sys.argv[1])
