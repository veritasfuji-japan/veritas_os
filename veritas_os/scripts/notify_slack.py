#!/usr/bin/env python3
"""Send a Slack notification message via incoming webhook.

Security considerations:
- HTTP request timeout is always set to prevent indefinite hangs.
- Error logging never prints response body to avoid accidental data exposure.
"""

import datetime
import os
import sys

import requests

DEFAULT_TIMEOUT_SEC = 10


def build_payload(message: str) -> dict[str, str]:
    """Build the Slack webhook payload for a user-facing notification."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"text": f"🧠 *VERITAS通知*\n>{message}\n🕒 {timestamp}"}


def send_slack_notification(webhook_url: str, message: str) -> int:
    """Send a Slack notification and return a process-compatible exit code."""
    payload = build_payload(message)

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=DEFAULT_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        print(f"[Slack] 通知送信失敗: network_error={exc.__class__.__name__}")
        return 1

    if response.status_code == 200:
        print("[Slack] 通知送信成功")
        return 0

    print(f"[Slack] エラー: status_code={response.status_code}")
    return 1


def main() -> int:
    """CLI entrypoint for Slack notification dispatch."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[ERROR] Missing SLACK_WEBHOOK_URL in environment.")
        return 1

    message = sys.argv[1] if len(sys.argv) > 1 else "VERITAS notification"
    return send_slack_notification(webhook_url, message)


if __name__ == "__main__":
    sys.exit(main())
