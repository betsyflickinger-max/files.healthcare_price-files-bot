# Oct 16, 2026 one-off research script (CMS MLR 2024 -> master_insurers.csv, parents.csv). Paths point at the research
# folder it ran in (/home/claude/research/insurers/ with raw/mlr2024 unzipped from cms.gov mlr-public-use-file-2024.zip).
import pandas as pd, sys
R='/home/claude/research/insurers/raw/mlr2024/'
h=pd.read_csv(R+'MR_Submission_Template_Header.csv',dtype=str)
h=h[h.business_state!='Grand Total'].copy()
p=pd.read_csv(R+'Part1_2_Summary_Data_Premium_Claims.csv',low_memory=False)
cols={'cmm_individual_yearly':'individual','cmm_small_group_yearly':'small_group','cmm_large_group_yearly':'large_group','uninsured_plans_yearly':'uninsured'}
def piv(code,suf):
    s=p[p.row_lookup_code==code][['mr_submission_template_id']+list(cols)].rename(columns={k:v+suf for k,v in cols.items()})
    s['mr_submission_template_id']=s.mr_submission_template_id.astype(str); return s
df=h.merge(piv('NUMBER_OF_COVERED_LIVES','_lives'),on='mr_submission_template_id',how='left').merge(piv('TOTAL_DIRECT_PREMIUM_EARNED','_premium'),on='mr_submission_template_id',how='left')
df.to_pickle('/home/claude/research/insurers/raw/joined.pkl')
u=df[df.group_affiliation.isna()|(df.group_affiliation=='00000')].copy()
u['lives']=u[['individual_lives','small_group_lives','large_group_lives']].fillna(0).sum(axis=1)
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
print(u.sort_values('lives',ascending=False)[['business_state','company_name','naic_company_code','naic_group_code','lives']].head(80).to_string())
