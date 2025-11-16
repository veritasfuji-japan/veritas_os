#!/usr/bin/env python3
import os, sys, requests, datetime

WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
if not WEBHOOK_URL:
    print("[ERROR] Missing SLACK_WEBHOOK_URL in environment.")
    sys.exit(1)

msg = sys.argv[1] if len(sys.argv) > 1 else "VERITAS notification"
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

payload = {
    "text": f"🧠 *VERITAS通知*\n>{msg}\n🕒 {timestamp}"
}

res = requests.post(WEBHOOK_URL, json=payload)
if res.status_code == 200:
    print("[Slack] 通知送信成功")
else:
    print(f"[Slack] エラー: {res.status_code} - {res.text}")
