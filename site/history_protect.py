"""Keep every replaced insurer table permanently (Nov 6, 2026; Betsy: keep past data for change over time in cost, price, access).

Before Oct 15, 2026 the insurer bot moved replaced tables to work/retired/<month>/. Storage has a 60-day cleanup rule on work/
(insurers/worker.py), so those tables would be deleted. This copies anything under work/retired/ to
history/insurers/<month>/work-retired/<rest of the path>, checks the copy is the same size, and never deletes the original
(the cleanup rule does that later). Already-copied files are skipped, so it is safe to run every month.

Usage: python site/history_protect.py [--dry-run]
"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    A = ap.parse_args()
    import procedure_pages as pp
    from boto3.s3.transfer import TransferConfig
    st = pp.Store('/tmp')
    s3, B = st.s3, st.B
    big = TransferConfig(multipart_threshold=1024 ** 3, multipart_chunksize=512 * 1024 ** 2, max_concurrency=8)
    have = {}
    tok = None
    while True:
        kw = dict(Bucket=B, Prefix='history/insurers/')
        if tok:
            kw['ContinuationToken'] = tok
        r = s3.list_objects_v2(**kw)
        have.update({o['Key']: o['Size'] for o in r.get('Contents', [])})
        if not r.get('IsTruncated'):
            break
        tok = r['NextContinuationToken']
    copied = skipped = 0
    gb = 0.0
    tok = None
    while True:
        kw = dict(Bucket=B, Prefix='work/retired/')
        if tok:
            kw['ContinuationToken'] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get('Contents', []):
            rest = o['Key'][len('work/retired/'):]
            month, _, path = rest.partition('/')
            dst = f'history/insurers/{month}/work-retired/{path}'
            if have.get(dst) == o['Size']:
                skipped += 1
                continue
            print(('would copy ' if A.dry_run else 'copy ') + o['Key'] + ' -> ' + dst, f"({o['Size'] / 1e9:.2f} GB)", flush=True)
            if not A.dry_run:
                s3.copy({'Bucket': B, 'Key': o['Key']}, B, dst, Config=big)
                if s3.head_object(Bucket=B, Key=dst)['ContentLength'] != o['Size']:
                    sys.exit(f'STOP: copy of {o["Key"]} came out a different size')
            copied += 1
            gb += o['Size'] / 1e9
        if not r.get('IsTruncated'):
            break
        tok = r['NextContinuationToken']
    print(f'history protect: {copied} copied ({gb:.1f} GB), {skipped} already kept')


if __name__ == '__main__':
    main()
