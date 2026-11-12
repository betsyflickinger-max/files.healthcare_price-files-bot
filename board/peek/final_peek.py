# read only: has anything in the website's R2 files changed since the final pass started (20:10Z Nov 11)?
import os, boto3, datetime as dt
g=lambda k: os.environ[k].strip()
r2=boto3.client('s3',endpoint_url=f"https://{g('R2A')}.r2.cloudflarestorage.com",aws_access_key_id=g('R2K'),aws_secret_access_key=g('R2S'),region_name='auto')
b2=boto3.client('s3',endpoint_url='https://s3.us-east-005.backblazeb2.com',aws_access_key_id=g('B2K'),aws_secret_access_key=g('B2S'),region_name='us-east-005')
R,B=g('R2B'),g('B2B')
cut=dt.datetime(2026,11,11,20,10,tzinfo=dt.timezone.utc)
for k in ['site/deploy/current.tgz','site/deploy/LOCK.json']:
    for n,c,bk in [('R2',r2,R),('B2',b2,B)]:
        try: h=c.head_object(Bucket=bk,Key=k); print(n,k,h['ContentLength'],h['LastModified'].isoformat(),h['ETag'])
        except Exception as e: print(n,k,'none',type(e).__name__)
newer=[];total=0
for p in ['site/','control/','signups/','logs/']:
    for pg in r2.get_paginator('list_objects_v2').paginate(Bucket=R,Prefix=p):
        for o in pg.get('Contents',[]):
            total+=1
            if o['LastModified']>cut: newer.append((o['LastModified'].isoformat(),o['Key']))
newer.sort()
print('R2 objects listed under site/ control/ signups/ logs/:',total)
print('changed after 20:10Z:',len(newer))
for t,k in newer[-40:]: print(t,k)
