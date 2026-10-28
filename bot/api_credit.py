"""Flag for "the Anthropic API credit ran out" (added Oct 22, 2026).

The credit ran out on the evening of Oct 14 and nobody noticed for 8 days: the hospital web search, the insurer search
and the plain-names bot each printed a warning in their own logs and carried on with Claude switched off. Now each bot
calls out(bot) when the API answers "credit balance is too low" and ok(bot) after its first good answer. The flag is a
small file in R2 (bot/alerts/anthropic_credit_<bot>.json); board/control_watchdog.py turns any flag into its GitHub
issue, which emails Betsy. Never raises: a problem here must not stop the bot that called it.
"""
import json
import os
import time

PREFIX = "bot/alerts/anthropic_credit_"
_done = set()


def _r2():
    import boto3
    e = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    s3 = boto3.client("s3", endpoint_url=(os.environ.get("STORAGE_ENDPOINT") or f"https://{e['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"),
                      aws_access_key_id=e["R2_ACCESS_KEY_ID"], aws_secret_access_key=e["R2_SECRET_ACCESS_KEY"], region_name=(os.environ.get("STORAGE_REGION") or "auto"))
    return s3, e["R2_BUCKET"]


def out(bot):
    if ("out", bot) in _done:
        return
    _done.add(("out", bot))
    try:
        run = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        s3, b = _r2()
        s3.put_object(Bucket=b, Key=f"{PREFIX}{bot}.json",
                      Body=json.dumps({"bot": bot, "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "run": run}).encode())
    except Exception as e:  # noqa: BLE001
        print("  (could not save the API-credit flag:", str(e)[:120], ")", flush=True)


def ok(bot):
    if ("ok", bot) in _done:
        return
    _done.add(("ok", bot))
    try:
        s3, b = _r2()
        s3.delete_object(Bucket=b, Key=f"{PREFIX}{bot}.json")
    except Exception:  # noqa: BLE001
        pass
