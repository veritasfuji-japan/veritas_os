#!/usr/bin/env python3
"""Send a Slack notification message via incoming webhook.

Security considerations:
- HTTP request timeout is always set to prevent indefinite hangs.
- Error logging never prints response body to avoid accidental data exposure.
"""

import datetime
import os
import re
import sys
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT_SEC = 10
ALLOWED_WEBHOOK_HOSTS = {"hooks.slack.com", "hooks.slack-gov.com"}
MAX_MESSAGE_LENGTH = 3000
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_message(message: str) -> str:
    """Normalize outgoing message text for safe Slack delivery.

    Security note:
        Control characters can pollute logs/terminals and oversized payloads
        can trigger downstream API errors. This helper strips control chars,
        trims surrounding whitespace, and enforces a bounded message size.
    """
    text = _RE_CONTROL_CHARS.sub("", str(message or "")).strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        return text[:MAX_MESSAGE_LENGTH]
    return text


def build_payload(message: str) -> dict[str, str]:
    """Build the Slack webhook payload for a user-facing notification."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_message = _sanitize_message(message)
    return {"text": f"🧠 *VERITAS通知*\n>{safe_message}\n🕒 {timestamp}"}


def is_allowed_slack_webhook_url(webhook_url: str) -> bool:
    """Validate Slack webhook URL to reduce SSRF and exfiltration risks.

    Allowed endpoints are limited to HTTPS webhook hosts managed by Slack.
    """
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment:
        return False
    if parsed.hostname not in ALLOWED_WEBHOOK_HOSTS:
        return False
    if parsed.port not in (None, 443):
        return False
    return parsed.path.startswith("/services/")


def send_slack_notification(webhook_url: str, message: str) -> int:
    """Send a Slack notification and return a process-compatible exit code."""
    if not is_allowed_slack_webhook_url(webhook_url):
        print("[ERROR] Invalid SLACK_WEBHOOK_URL. Only Slack HTTPS webhook URLs are allowed.")
        return 1

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
