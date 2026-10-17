# Oct 16, 2026 one-off research script (CMS MLR 2024 -> master_insurers.csv, parents.csv). Paths point at the research
# folder it ran in (/home/claude/research/insurers/ with raw/mlr2024 unzipped from cms.gov mlr-public-use-file-2024.zip).
import pandas as pd, re
OUT='/home/claude/research/insurers/'
df=pd.read_pickle(OUT+'raw/joined.pkl')
df.loc[df.group_affiliation=='00000','group_affiliation']=None
df['gcode']=pd.to_numeric(df.naic_group_code,errors='coerce').astype('Int64')
# group names without code -> code (same entity, name-only variants present in file)
NAME_TO_CODE={'Medica':1552}
# explicit brand-name rules for rows with no group affiliation and no group code
NAME_RULES=[(r'\boscar\b','Oscar Health Group'),(r'\bambetter\b','CENTENE CORP GRP'),(r'\bmolina\b','Molina Healthcare Inc GRP'),
 (r'\baetna\b','CVS Health Group'),(r'unitedhealthcare|\buhc\b|united healthcare','UNITEDHEALTH GRP'),(r'\bcigna\b','Cigna Hlth Grp'),
 (r'\bkaiser\b','KAISER FOUNDATION GRP'),(r'\bhumana\b','HUMANA GRP'),(r'\bwellcare\b','CENTENE CORP GRP')]
# documented, publicly known subsidiaries (company name does not carry the parent brand)
KNOWN_SUBS={'Absolute Total Care, Inc':'CENTENE CORP GRP','SilverSummit Healthplan, Inc.':'CENTENE CORP GRP',
 'Western Sky Community Care, Inc.':'CENTENE CORP GRP','Pennsylvania Health & Wellness, Inc.':'CENTENE CORP GRP',
 'Blue Cross of California':'Elevance Hlth Inc Grp'}
name2code=df.dropna(subset=['gcode','group_affiliation']).groupby('group_affiliation').gcode.agg(lambda s:s.mode()[0]).to_dict()
src=[];grpname=[];code=[]
for _,r in df.iterrows():
    c=r.gcode; g=r.group_affiliation; s=None
    if pd.notna(c): s='mlr_group_code'
    elif pd.notna(g):
        s='mlr_group_affiliation'; c=NAME_TO_CODE.get(g, name2code.get(g))
    else:
        nm=r.company_name
        if nm in KNOWN_SUBS: g=KNOWN_SUBS[nm]; s='manual_known_subsidiary'
        else:
            for pat,gg in NAME_RULES:
                if re.search(pat,nm,re.I): g=gg; s='company_name_brand_rule'; break
        if g is not None: c=name2code.get(g)
        else: s='none_self'
    src.append(s); grpname.append(g); code.append(c)
df['parent_source']=src; df['grp_raw']=grpname; df['gcode2']=pd.array(code,dtype='Int64')
# parent key
def key(r):
    if pd.notna(r.gcode2): return 'G%d'%r.gcode2
    if isinstance(r.grp_raw,str): return 'N:'+r.grp_raw
    return 'S:'+re.sub(r'[^a-z0-9]+',' ',r.company_name.lower()).strip()
df['pkey']=df.apply(key,axis=1)
# raw display name: most common group_affiliation within key, else company name
raw=df.groupby('pkey').apply(lambda x: (x.grp_raw[x.grp_raw.map(lambda v:isinstance(v,str))].mode().iloc[0] if x.grp_raw.map(lambda v:isinstance(v,str)).any() else x.company_name.mode().iloc[0]))
CLEAN={'UNITEDHEALTH GRP':'UnitedHealth Group','Elevance Hlth Inc Grp':'Elevance Health (Anthem)','CVS Health Group':'CVS Health (Aetna)',
 'Cigna Hlth Grp':'Cigna Group','CENTENE CORP GRP':'Centene (Ambetter)','HCSC GRP':'Health Care Service Corp (HCSC)',
 'KAISER FOUNDATION GRP':'Kaiser Permanente','HUMANA GRP':'Humana','Molina Healthcare Inc GRP':'Molina Healthcare',
 'Oscar Health Group':'Oscar Health','HIGHMARK GRP':'Highmark Health','BCBS OF MI GRP':'Blue Cross Blue Shield of Michigan',
 'Blue Cross and Blue Shield of Florida, Inc.':'Florida Blue (GuideWell)','INDEPENDENCE BLUE CROSS GRP':'Independence Blue Cross',
 'CAREFIRST INC GRP':'CareFirst BlueCross BlueShield','BCBS OF NJ GRP':'Horizon BCBS of New Jersey','REGENCE GRP':'Regence (Cambia)',
 'Premera Blue Cross Group':'Premera Blue Cross','HIP INS GRP':'EmblemHealth (HIP)','HARVARD PILGRIM HTH CARE GRP':'Harvard Pilgrim (Point32Health)',
 'Tufts Health Plan':'Tufts Health Plan (Point32Health)','Medica Grp':'Medica','BCBS of MA Grp':'BCBS of Massachusetts','BCBS of MN Grp':'BCBS of Minnesota',
 'BCBS OF AL GRP':'BCBS of Alabama','BCBS of TN Inc':'BCBS of Tennessee','BCBS of SC Grp':'BCBS of South Carolina','BCBS OF KC GRP':'BCBS of Kansas City',
 'BCBS of KS GRP':'BCBS of Kansas','ARKANSAS BCBS GRP':'Arkansas BCBS','LOUISIANA HLTH SERV GRP':'BCBS of Louisiana','Wellmark Group':'Wellmark BCBS',
 'Blue Shield of California Group':'Blue Shield of California','CAPITAL BLUE CROSS GRP':'Capital Blue Cross','Lifetime HlthCare Grp':'Lifetime Healthcare (Excellus)',
 'UPMC HLTH SYSTEM GRP':'UPMC Health Plan','HEALTHPARTNERS GRP':'HealthPartners','Medical Mutual of Ohio':'Medical Mutual of Ohio',
 'IHC Inc Grp':'Intermountain (SelectHealth)','Sentara Health Management Group':'Sentara Health Plans','CareSource Management Group':'CareSource',
 'Corewell Health Group':'Corewell Health (Priority Health)','Scott & White GRP':'Baylor Scott & White Health Plan','Firstcare Grp':'FirstCare (Baylor Scott & White)',
 'GEISINGER INS GRP':'Geisinger Health Plan','MVP GRP':'MVP Health Care','PacificSource Hlth Plan Grp':'PacificSource','Presbyterian Hlthcare Serv Grp':'Presbyterian Health Plan',
 'HEALTH PLAN GRP':'The Health Plan (WV)','BCS INS GRP':'BCS Insurance','MISSISSIPPI INS GRP':'BCBS of Mississippi (Mississippi Ins Grp)','Hawaii Medical Service Association':'HMSA (Hawaii Medical Service Association)','WellCare Management Group':'WellCare Management Group (Centene)'}
disp=raw.map(lambda x: CLEAN.get(x,x))
df['parent_group']=df.pkey.map(disp)
assert df.groupby('parent_group').pkey.nunique().max()==1, df.groupby('parent_group').pkey.nunique().sort_values().tail()
for m in ['individual','small_group','large_group','uninsured']:
    df[m+'_lives']=pd.to_numeric(df[m+'_lives']); df[m+'_premium']=pd.to_numeric(df[m+'_premium'])
L=['individual_lives','small_group_lives','large_group_lives']
df['total_lives']=df[L].fillna(0).sum(axis=1)
df['total_premium']=df[['individual_premium','small_group_premium','large_group_premium']].fillna(0).sum(axis=1)
nstates=df[df.total_lives>0].groupby('pkey').business_state.nunique().reindex(df.pkey.unique()).fillna(0).astype(int)
nfiled=df.groupby('pkey').business_state.nunique()
df['parent_states_filed']=df.pkey.map(nfiled)
df['parent_state_count']=df.pkey.map(nstates)
df['scope']=df.parent_state_count.map(lambda n:'national' if n>=20 else ('multi_state' if n>=2 else 'single_state'))
out=df.rename(columns={'company_name':'issuer_name','naic_company_code':'naic_code','business_state':'state','group_affiliation':'mlr_group_affiliation_raw','naic_group_code':'naic_group_code_raw'})
cols=['parent_group','issuer_name','naic_code','hios_issuer_id','state','individual_lives','small_group_lives','large_group_lives','total_lives',
 'scope','parent_state_count','parent_states_filed','uninsured_lives','individual_premium','small_group_premium','large_group_premium','total_premium',
 'mlr_group_affiliation_raw','naic_group_code_raw','parent_source','dba_marketing_name','domiciliary_state','not_for_profit','mr_submission_template_id']
out=out[cols].sort_values(['parent_group','state','issuer_name'])
for c in L+['total_lives','uninsured_lives']: out[c]=out[c].round(0).astype('Int64')
for c in ['individual_premium','small_group_premium','large_group_premium','total_premium']: out[c]=out[c].round(0).astype('Int64')
out.to_pickle(OUT+'raw/master.pkl')
# parents
def top5(x):
    s=x.groupby('state').total_lives.sum().sort_values(ascending=False)
    s=s[s>0].head(5); return '; '.join(f'{k} ({int(v):,})' for k,v in s.items())
g=out.groupby('parent_group')
par=pd.DataFrame({'states':g.parent_state_count.first(),'states_filed':g.state.nunique(),'issuers':g.issuer_name.nunique(),'total_lives':g.total_lives.sum(),
 'individual_lives':g.individual_lives.sum(),'small_group_lives':g.small_group_lives.sum(),'large_group_lives':g.large_group_lives.sum(),
 'total_premium':g.total_premium.sum(),'top5_states':g.apply(top5),'scope':g.scope.first()}).reset_index()
par=par.sort_values('total_lives',ascending=False)
par.to_pickle(OUT+'raw/parents.pkl')
print(len(out), out.parent_group.nunique(), out.parent_source.value_counts().to_dict())
pd.set_option('display.width',250)
print(par.head(45)[['parent_group','states','total_lives','scope','top5_states']].to_string())
print(par.scope.value_counts())
