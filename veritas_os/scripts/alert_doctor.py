#!/usr/bin/env python3
"""Alerting utility for doctor reports with optional self-healing.

Security notes:
- Slack webhook URLs are strictly validated before network access.
- Self-heal script paths are resolved and validated to avoid path traversal.
- Command outputs are truncated before notification to reduce sensitive leakage.
"""

import os
import json
import stat
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ================================
# パス設定（scripts/logs に統一）
# ================================
THIS_FILE = Path(__file__).resolve()
SCRIPTS_DIR = THIS_FILE.parent  # .../veritas_os/scripts
VERITAS_DIR = SCRIPTS_DIR.parent  # .../veritas_os
LOG_DIR = SCRIPTS_DIR / "logs"  # ★ 新しい正規パス
REPORT_JSON = LOG_DIR / "doctor_report.json"  # ★ ここだけを使用

LOG_DIR.mkdir(parents=True, exist_ok=True)

# ================================
# 環境変数
# ================================
THRESH = float(os.getenv("VERITAS_ALERT_UNC", "0.50"))
WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
HEAL_ON_HIGH = os.getenv("VERITAS_HEAL_ON_HIGH", "1") == "1"
HEAL_SCRIPT = SCRIPTS_DIR / "heal.sh"  # プロジェクト内 heal.sh

API_BASE = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")
HEALTH_URL = f"{API_BASE}/health"
MAX_HEAL_OUTPUT_CHARS = 400


def _validate_webhook_url(webhook_url: str) -> bool:
    """Validate Slack webhook URL format and trusted host.

    Security constraints:
    - HTTPS only.
    - Host must be an official Slack webhook domain.
    - No explicit port/userinfo/query/fragment.
    - Path must start with ``/services/``.
    """
    if not webhook_url:
        return False
    try:
        parsed = urllib.parse.urlparse(webhook_url)
    except ValueError:
        return False

    if parsed.scheme != "https":
        return False

    try:
        parsed_port = parsed.port
    except ValueError:
        return False

    if parsed_port is not None:
        return False

    if parsed.username or parsed.password:
        return False

    hostname: Optional[str] = parsed.hostname
    if not hostname:
        return False

    allowed_hosts = {
        "hooks.slack.com",
        "hooks.slack-gov.com",
    }
    if hostname.lower() not in allowed_hosts:
        return False

    if parsed.query or parsed.fragment:
        return False

    return parsed.path.startswith("/services/")


def _safe_snippet(text: str, max_chars: int = MAX_HEAL_OUTPUT_CHARS) -> str:
    """Return a single-line, length-limited snippet for logs/notifications."""
    one_line = " ".join(text.split())
    if len(one_line) <= max_chars:
        return one_line
    return f"{one_line[:max_chars]}..."


def _validate_health_url(url: str) -> bool:
    """Validate health-check URL to avoid accidental SSRF.

    The alerting workflow should only probe a local Veritas API endpoint.
    Allowed destinations are loopback hosts over HTTP/HTTPS without
    embedded credentials. To avoid broad localhost access, only the
    ``/health`` endpoint is permitted and query/fragment parts are denied.
    """
    if not url:
        return False

    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    if parsed.username or parsed.password:
        return False

    if parsed.query or parsed.fragment:
        return False

    try:
        parsed.port
    except ValueError:
        return False

    hostname: Optional[str] = parsed.hostname
    if not hostname:
        return False

    normalized_path = parsed.path or "/"
    if normalized_path != "/health":
        return False

    return hostname.lower() in {"localhost", "127.0.0.1", "::1"}


# ================================
# Slack 通知
# ================================
def post_slack(text: str, timeout_sec: int = 12, max_retry: int = 3) -> bool:
    """Post a text message to Slack with retry support."""
    if not WEBHOOK:
        print("⚠️ SLACK_WEBHOOK_URL 未設定のため通知スキップ")
        return False

    if not _validate_webhook_url(WEBHOOK):
        print("🚫 セキュリティ警告: SLACK_WEBHOOK_URL が不正なため通知を中断")
        return False

    body = json.dumps({"text": text}).encode("utf-8")

    for i in range(max_retry):
        try:
            req = urllib.request.Request(
                WEBHOOK,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as r:
                if r.status == 200:
                    print("✅ Slack通知成功")
                    return True
                print(f"⚠️ Slack応答異常 status={r.status}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"⚠️ Slack送信失敗({i+1}/{max_retry}): {e}")

        if i < max_retry - 1:
            time.sleep(2 ** i)

    return False


# ================================
# HTTP チェック
# ================================
def http_get(url: str, timeout: int = 3):
    """Run a lightweight local HTTP GET and return ``(status, body_or_error)``."""
    if not _validate_health_url(url):
        return None, "health URL blocked by security policy"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, str(e)


# ================================
# Self-Heal
# ================================
def _validate_heal_script_path(script_path: Path) -> bool:
    """
    ★ セキュリティ修正: heal.shのパスを厳密に検証
    - スクリプトがSCRIPTS_DIR内に存在することを確認
    - シンボリックリンク攻撃を防止
    - パス走査（..）攻撃を防止
    - クロスプラットフォーム対応（Windows含む）
    - world/group writable なスクリプトを拒否
    """
    try:
        # resolve() でシンボリックリンクを解決し、実際のパスを取得
        resolved_script = script_path.resolve(strict=True)
        resolved_scripts_dir = SCRIPTS_DIR.resolve(strict=True)

        # ★ クロスプラットフォーム対応: is_relative_to() を使用 (Python 3.9+)
        # これはWindowsのcase-insensitivityとドライブレター問題を正しく処理
        try:
            if not resolved_script.is_relative_to(resolved_scripts_dir):
                return False
        except AttributeError:  # pragma: no cover
            # Python 3.8以前のフォールバック
            try:
                resolved_script.relative_to(resolved_scripts_dir)
            except ValueError:
                return False

        # ファイル名が期待通りであることを確認
        if resolved_script.name != "heal.sh":
            return False

        # 通常ファイルのみ許可（デバイスファイルやディレクトリを除外）
        if not resolved_script.is_file():
            return False

        # Unix では group/other writable を拒否し、改ざんリスクを下げる
        mode = resolved_script.stat().st_mode
        if os.name != "nt" and mode & (stat.S_IWGRP | stat.S_IWOTH):
            return False

        return True
    except (OSError, ValueError):
        return False


def run_heal():
    """Execute heal.sh and verify /health turns healthy."""
    if not HEAL_SCRIPT.exists():
        msg = f"heal.sh not found at {HEAL_SCRIPT}"
        print(f"⚠️ {msg}")
        return False, msg

    # ★ セキュリティ修正: パスを厳密に検証
    if not _validate_heal_script_path(HEAL_SCRIPT):
        msg = "Security check failed: heal.sh path validation failed"
        print(f"🚫 {msg}")
        return False, msg

    try:
        # ★ セキュリティ修正: shlex.split()を使わず、直接リストで渡す
        # これにより、シェルメタ文字の解釈を防止
        out = subprocess.check_output(
            ["/bin/bash", str(HEAL_SCRIPT.resolve())],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        print(out)

        # /health を10秒以内にチェック
        ok = False
        for _ in range(10):
            time.sleep(1)
            status, body = http_get(HEALTH_URL, timeout=2)
            if status == 200 and '"ok":true' in body.replace(" ", "").lower():
                ok = True
                break

        return ok, _safe_snippet(out if out else "healed")

    except subprocess.CalledProcessError as e:
        safe_output = _safe_snippet((e.output or "").strip())
        return False, f"heal failed: rc={e.returncode}, out={safe_output}"
    except (OSError, ValueError) as e:
        return False, f"heal exception: {e}"


# ================================
# MAIN
# ================================
def main():
    """Run doctor report alert flow and optional recovery."""
    # doctor_report.json の存在確認（scripts/logs）
    if not REPORT_JSON.exists():
        print(f"⚠️ doctor_report.json が見つかりません: {REPORT_JSON}")
        print("    → 先に doctor.py を実行してください。")
        return

    with REPORT_JSON.open(encoding="utf-8") as f:
        rep = json.load(f)

    # レポート内容取得
    total = int(rep.get("total_logs", 0))
    avg = float(rep.get("avg_uncertainty", 0.0))
    last = rep.get("last_check", "")
    kws = rep.get("keywords", {}) or {}

    # 判定
    emoji, level = "🟢", "OK"
    if avg >= THRESH:
        emoji, level = "🔴", "HIGH"
    elif avg >= THRESH * 0.8:
        emoji, level = "🟠", "WARN"

    summary = (
        f"{emoji} *VERITAS Doctor* [{level}]\n"
        f"• 平均不確実性: *{avg:.3f}*（しきい値 {THRESH:.2f}）\n"
        f"• ログ総数: {total}\n"
        f"• 最終診断: {last}\n"
        f"• キーワード: "
        f"{', '.join([f'{k}:{v}' for k, v in kws.items()]) or 'なし'}"
    )
    print(summary)

    # Slack 通知
    if level in ("HIGH", "WARN"):
        post_slack(summary)

    # Self-Heal（HIGH のとき）
    if level == "HIGH" and HEAL_ON_HIGH:
        ok, info = run_heal()
        post_slack(f"🛠 Self-Heal: {'OK' if ok else 'FAIL'} — {info}")

        status, body = http_get(HEALTH_URL)
        post_slack(f"📡 /health: status={status}, body={body[:200]}")


if __name__ == "__main__":
    main()
