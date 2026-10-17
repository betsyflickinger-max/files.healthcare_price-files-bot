# Oct 16, 2026 one-off research script (CMS MLR 2024 -> master_insurers.csv, parents.csv). Paths point at the research
# folder it ran in (/home/claude/research/insurers/ with raw/mlr2024 unzipped from cms.gov mlr-public-use-file-2024.zip).
import pandas as pd
O='/home/claude/research/insurers/'
m=pd.read_pickle(O+'raw/master.pkl'); p=pd.read_pickle(O+'raw/parents.pkl')
V='opened 2026-10-16, HTTP 200, page is a TiC/MRF page'
TIC={
'Kaiser Permanente':('https://healthy.kaiserpermanente.org/front-door/machine-readable',V+' (regional variants exist per KP region)'),
'UnitedHealth Group':('https://transparency-in-coverage.uhc.com/',V),
'Health Care Service Corp (HCSC)':('https://www.bcbstx.com/member/machine-readable-files',V+'; BCBSTX page; IL equivalent https://www.bcbsil.com/member/machine-readable-files also opened'),
'Elevance Health (Anthem)':('https://www.anthem.com/machine-readable-file/search/',V),
'Centene (Ambetter)':('https://www.centene.com/price-transparency-files.html',V),
'CVS Health (Aetna)':('https://health1.aetna.com/app/public/#/one/insurerCode=AETNACVS_I&brandCode=ALICSI/machine-readable-transparency-in-coverage','from project insurer_tic_index.csv (Payerset docs); not re-opened: site sends incomplete TLS chain; other brandCodes: ALICFI, TEXASFI, AETNACVS'),
'Cigna Group':('https://www.cigna.com/legal/compliance/machine-readable-files',V),
'Florida Blue (GuideWell)':('https://www.floridablue.com/members/tools-resources/transparency/machine-readable-files',V),
'Blue Shield of California':('https://www.blueshieldca.com/en/home/help-and-resources/machine-readable-files',V),
'Oscar Health':('https://www.hioscar.com/transparency-in-coverage-files/oscar',V),
'Blue Cross Blue Shield of Michigan':('https://www.bcbsm.com/mrf/index/',V),
'CareFirst BlueCross BlueShield':('https://individual.carefirst.com/individuals-families/mandates-policies/machine-readable-data.page',V),
'Highmark Health':('https://mrfdata.hmhs.com/',V),
'Blue Cross and Blue Shield of North Carolina':('https://www.bluecrossnc.com/policies-best-practices/machine-readable-files',V),
'BCBS of Alabama':('https://www.bcbsal.org/web/transparency-in-coverage',V),
'BCBS of Massachusetts':('https://transparency-in-coverage.bluecrossma.com/','found by web search (title "Transparency in Coverage - Blue Cross Blue Shield"); not opened: incomplete TLS chain'),
'Independence Blue Cross':('https://www.ibx.com/resources/for-members/transparency-in-coverage.html',V+' (JS-rendered; file links not visible to plain fetch)'),
'Horizon BCBS of New Jersey':('https://horizonblue.sapphiremrfhub.com/',V+' (Sapphire MRF hub)'),
'BCBS of South Carolina':('https://www.southcarolinablues.com/en/home/about-us/privacy-and-legal/transparency-in-coverage.html',V),
'Intermountain (SelectHealth)':('https://selecthealth.org/transparency-in-coverage',V+'; open file folder https://ebu.intermountainhealthcare.org/selecthealth/transparencyincoverage/'),
'BCBS of Tennessee':('https://www.bcbst.com/tcr',V),
'Wellmark BCBS':('https://www.wellmark.com/transparency',V+' (JS-rendered)'),
'Corewell Health (Priority Health)':('https://www.priorityhealth.com/landing/transparency',V+'; links to S3 TableOfContents.html'),
'Premera Blue Cross':('https://www.premera.com/visitor/transparency',V),
'Medica':('https://www.medica.com/transparency-in-coverage','found by web search (title "Transparency in Coverage and machine readable files"); site returns bot challenge (403) to plain fetch'),
'HMSA (Hawaii Medical Service Association)':('https://www.hmsa.com/help-center/transparency-in-coverage-machine-readable-files/',V),
'Triple-S Salud Inc.':('https://salud.grupotriples.com/en/transparency-in-coverage-machine-readable-files/',V),
'Arkansas BCBS':('https://www.arkansasbluecross.com/policies/transparency/mrfs',V),
'Harvard Pilgrim (Point32Health)':('https://www.harvardpilgrim.org/public/machine-readable-files',V),
'Tufts Health Plan (Point32Health)':('https://tuftshealthplan.com/visitor/legal-notices/machine-readable-files',V),
'BCBS of Minnesota':('https://www.bluecrossmn.com/transparency-coverage-machine-readable-files','opened 2026-10-16, HTTP 200 (JS-rendered); title confirmed by web search'),
'Lifetime Healthcare (Excellus)':('https://news.excellusbcbs.com/developer-info/transparency-coverage-mrf',V),
'EmblemHealth (HIP)':('https://transparency.emblemhealth.com/','found by web search (title "Price Transparency Machine Readable - EmblemHealth"); plain fetch returned 406'),
'UPMC Health Plan':('https://www.upmchealthplan.com/transparency-in-coverage',V),
'BCBS of Kansas City':('https://www.bluekc.com/transparency-in-coverage/',V+'; files at https://bcbskc.sapphiremrfhub.com/'),
'Medical Mutual of Ohio':('https://www.medmutual.com/mrf','opened 2026-10-16; redirects to HealthSparq MRF portal (productCode=MRF)'),
'HealthPartners':('https://www.healthpartners.com/hp/legal-notices/disclosures/transparency/index.html',V+'; page links per-network MRF pages on Azure blob'),
'BCBS of Mississippi (Mississippi Ins Grp)':('https://www.bcbsms.com/about-us/transparency-in-coverage',V),
'BCBS of Kansas':('https://www.bcbsks.com/transparency-in-coverage',V),
'Baylor Scott & White Health Plan':('https://www.bswhealthplan.com/transparency',V),
'L.A. Care Health Plan':('https://lacare.org/transparency-coverage-machine-readable-files',V),
'Humana':('https://developers.humana.com/syntheticdata/healthplan-price-transparency','from project insurer_tic_index.csv; opened 2026-10-16 HTTP 200 but JS-only ("Loading...")'),
}
NOTFOUND={'Regence (Cambia)':'not found: regence.com CAA/TIC info page describes the rule but no file link found; old producer-news MRF page 404',
 'Molina Healthcare':'not found: Molina TiC/PricingTransparency pages return "Page Not Found" or redirect to /ifp (2026-10-16)',
 'Blue Cross and Blue Shield of Arizona, Inc.':'not found (only Medicaid Health Choice page surfaced)',
 'BCBS of Louisiana':'not found (guessed paths 404; search gave no landing page)',
 'University Health Care & Gundersen Lutheran Group':'not found (Quartz page 404; only a QHP PDF)'}
p['tic_landing_page']=p.parent_group.map(lambda g:TIC.get(g,('',''))[0])
p['tic_note']=p.parent_group.map(lambda g:TIC[g][1] if g in TIC else NOTFOUND.get(g,''))
p['rank_by_lives']=range(1,len(p)+1)
assert all(g in set(p.parent_group) for g in TIC), [g for g in TIC if g not in set(p.parent_group)]
m['tic_landing_page']=m.parent_group.map(lambda g:TIC.get(g,('',''))[0])
p=p[['rank_by_lives','parent_group','states','states_filed','issuers','total_lives','individual_lives','small_group_lives','large_group_lives','total_premium','top5_states','scope','tic_landing_page','tic_note']]
for c in ['total_lives','individual_lives','small_group_lives','large_group_lives','total_premium']: p[c]=p[c].astype('Int64')
p.to_csv(O+'parents.csv',index=False)
m.to_csv(O+'master_insurers.csv',index=False)
print(len(m),len(p),(p.tic_landing_page!='').sum(), p.scope.value_counts().to_dict())
print('issuers w/ lives>0:',(m.total_lives>0).sum(),'unique naic:',m.naic_code.nunique(),'unique issuer names:',m.issuer_name.nunique())
print('totals',int(m.individual_lives.sum()),int(m.small_group_lives.sum()),int(m.large_group_lives.sum()),int(m.total_lives.sum()))
print(m.parent_source.value_counts().to_dict())
print(p.head(15)[['rank_by_lives','parent_group','states','total_lives','scope']].to_string(index=False))
top40=p.head(40); print('top40 with tic:',(top40.tic_landing_page!='').sum(), list(top40[top40.tic_landing_page==''].parent_group))
