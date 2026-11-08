"""Nov 7, 2026: after a build machine's script fails, save the end of its run log and the kernel's out-of-memory notes
next to its log.txt (OUTP + 'runlog.txt'), so a crash can be read from storage instead of being lost with the machine.
Georgia, North Carolina and California's final steps restarted for hours with no error anywhere we could read."""
import os, subprocess, time
import boto3
E = os.environ
if E.get('OUTP') and E.get('R2_BUCKET'):
    try:
        s3 = boto3.client('s3', endpoint_url=(E.get('STORAGE_ENDPOINT') or 'https://' + E['R2_ACCOUNT_ID'] + '.r2.cloudflarestorage.com'),
                          aws_access_key_id=E['R2_ACCESS_KEY_ID'], aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'],
                          region_name=(E.get('STORAGE_REGION') or 'auto'))
        try: tail = open('/root/run.log', 'rb').read()[-30000:].decode('utf-8', 'replace')
        except Exception as e: tail = f'(no run.log: {e})'
        try: oom = subprocess.run('dmesg | grep -i -E "out of memory|killed process|oom" | tail -20', shell=True, capture_output=True, text=True, timeout=20).stdout
        except Exception as e: oom = f'(dmesg failed: {e})'
        try: mem = subprocess.run('free -m', shell=True, capture_output=True, text=True, timeout=10).stdout
        except Exception: mem = ''
        body = f"saved {time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n== kernel out-of-memory notes ==\n{oom}\n== memory now ==\n{mem}\n== end of run.log ==\n{tail}"
        s3.put_object(Bucket=E['R2_BUCKET'], Key=E['OUTP'] + 'runlog.txt', Body=body.encode())
    except Exception as e: print('save_runlog failed', e)
