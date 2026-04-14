#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS health_check.py（veritas_clean_test2 用）

・/health を叩いて API の生存確認
・ログ / レポートファイルの更新日時チェック
・結果を JSON に保存（~/scripts/logs/health_*.json）
・異常があれば notify_slack.py（あれば）で Slack 通知
"""

import os
import json
import subprocess
import re
import importlib.util
import ipaddress
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

# requests ライブラリ（セキュリティ向上のため curl subprocess を置換）
HAS_REQUESTS = importlib.util.find_spec("requests") is not None
if HAS_REQUESTS:
    import requests

# ===== パス設定 =====
# Canonical runtime paths — all outputs go to runtime/<namespace>/
from veritas_os.scripts._runtime_paths import (  # noqa: E402
    LOG_DIR as _CANONICAL_LOG_DIR,
    DOCTOR_DIR,
    DOCTOR_REPORT_JSON,
    DOCTOR_DASHBOARD_HTML,
    ensure_dirs as _ensure_runtime_dirs,
)

HERE = Path(__file__).resolve().parent  # .../veritas_os/scripts
VERITAS_DIR = HERE.parent  # .../veritas_os

# Scripts use canonical runtime paths (not scripts/logs)
SCRIPTS_BASE = HERE
LOGS_DIR = _CANONICAL_LOG_DIR
BACKUPS_DIR = SCRIPTS_BASE / "backups"

# Doctor reports go to the canonical doctor directory
REPORT_DIR = DOCTOR_DIR
REPORT_HTML  = DOCTOR_DASHBOARD_HTML
REPORT_JSON  = DOCTOR_REPORT_JSON

# 旧来ファイルもあればついでに見る
SUMMARY_CSV  = LOGS_DIR / "summary.csv"

# 出力 JSON（1回ごと）
OUT_JSON = LOGS_DIR / f"health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

SLACK_NOTIFY = SCRIPTS_BASE / "notify_slack.py"

NOW = datetime.now()
WITHIN = timedelta(days=1)   # 「最近」の基準（24h 以内）


# ===== セキュリティ: URL バリデーション =====
def _is_valid_ipv4(hostname: str) -> bool:
    """IPv4 アドレス形式とオクテット範囲を検証する。"""
    if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", hostname):
        return False
    octets = hostname.split(".")
    return all(0 <= int(octet) <= 255 for octet in octets)


def _is_valid_hostname(hostname: str) -> bool:
    """RFC に準拠した安全なホスト名かどうかを検証する。"""
    if len(hostname) > 253:
        return False

    labels = hostname.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not re.match(r"^[a-zA-Z0-9-]+$", label):
            return False

    return True


def _validate_url(url: str) -> Optional[str]:
    """
    ★ セキュリティ修正: URL を検証し、安全な場合のみ返す。

    - http:// または https:// スキームのみ許可
    - ホスト名は英数字、ハイフン、ドットのみ
    - 危険な文字（シェルメタキャラクター）を拒否
    - ポート番号は 1-65535 の範囲のみ

    Returns:
        検証済みの URL（安全な場合）、または None（不正な場合）
    """
    if not url or not isinstance(url, str):
        return None

    # 前後空白および制御文字混入を禁止（ログ混乱や解析の曖昧化を防止）
    if url != url.strip() or re.search(r"[\x00-\x1f\x7f\s]", url):
        return None

    # パーセントエンコードされた制御文字を禁止（例: %0a, %0d）
    # requests / curl がそのまま送信しても、下流ログ解析や中間プロキシで
    # 予期しない解釈をされるリスクを下げるために拒否する。
    if re.search(r"%(?:0[0-9a-fA-F]|1[0-9a-fA-F]|7f)", url):
        return None

    # 危険な文字を検出（コマンドインジェクション防止）
    dangerous_chars = [";", "|", "&", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r", "\\"]
    for char in dangerous_chars:
        if char in url:
            return None

    parsed = urlparse(url)

    # スキームの検証（http/https のみ）
    if parsed.scheme not in ("http", "https"):
        return None

    # 認証情報付き URL を禁止（資格情報漏えい防止）
    if parsed.username or parsed.password:
        return None

    # クエリ/フラグメントは不要なため禁止（予期しない挙動を防止）
    if parsed.query or parsed.fragment:
        return None

    # ホスト名の検証
    hostname = parsed.hostname
    if not hostname:
        return None

    if not _is_allowed_health_host(hostname):
        return None

    # IPv4 風（数字とドットのみ）の場合はオクテット範囲を厳密検証
    if re.match(r"^[0-9.]+$", hostname):
        if not _is_valid_ipv4(hostname):
            return None
    # ホスト名を RFC 準拠で厳密検証
    elif not _is_valid_hostname(hostname):
        return None

    # ポートの検証
    try:
        port = parsed.port
    except ValueError:
        return None

    if port is not None and not (1 <= port <= 65535):
        return None

    # パスに危険な文字がないか再確認
    path = parsed.path or ""
    for char in dangerous_chars:
        if char in path:
            return None

    return url


def _is_allowed_health_host(hostname: str) -> bool:
    """ヘルスチェック先として許可するホストかを判定する。

    セキュリティ上の理由から、デフォルトでは loopback / private /
    localhost のみ許可する。
    `VERITAS_HEALTH_ALLOW_PUBLIC=1` の場合のみ公開ホストを許可する。
    """
    allow_public = os.getenv("VERITAS_HEALTH_ALLOW_PUBLIC", "0") == "1"
    if allow_public:
        return True

    lower_host = hostname.lower().rstrip(".")
    if lower_host == "localhost" or lower_host.endswith(".localhost"):
        return True

    try:
        ip_value = ipaddress.ip_address(lower_host)
    except ValueError:
        # DNS 名はデフォルト拒否（SSRF 影響の縮小）
        return False

    return (
        ip_value.is_loopback
        or ip_value.is_private
        or ip_value.is_link_local
    )


API_BASE = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")

# ★ セキュリティ修正: API_BASE を検証
_validated_api_base = _validate_url(API_BASE)
if _validated_api_base is None:
    print(f"⚠️ SECURITY WARNING: Invalid VERITAS_API_BASE: {API_BASE!r}")
    print("   Using default: http://127.0.0.1:8000")
    API_BASE = "http://127.0.0.1:8000"

HEALTH_URL = f"{API_BASE}/health"


# ===== ユーティリティ =====
def run(cmd: List[str], timeout: int = 8):
    """サブプロセス実行（Slack 通知など用）"""
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 99, "", str(e)


def mtime_ok(p: Path, within: timedelta) -> bool:
    return p.exists() and datetime.fromtimestamp(p.stat().st_mtime) >= NOW - within


# ===== チェック群 =====
def check_server() -> Dict[str, Any]:
    """
    FastAPI /health を確認

    ★ セキュリティ修正:
    - curl subprocess の代わりに requests ライブラリを使用（コマンドインジェクション防止）
    - URL は事前に検証済み
    - requests がない場合はフォールバック（検証済み URL のみ許可）
    """
    url = HEALTH_URL

    # URL 再検証（念のため）
    if _validate_url(url) is None:
        return {
            "name": "api_health",
            "ok": False,
            "status_code": -1,
            "detail": f"Invalid URL: {url}",
            "url": url,
        }

    # requests ライブラリを優先使用（セキュリティ向上）
    if HAS_REQUESTS:
        try:
            # Redirect 追従を無効化し、検証済み URL 以外への遷移を防止する。
            resp = requests.get(url, timeout=3, allow_redirects=False)
            body = resp.text
            ok = resp.ok and ('"ok":true' in body.replace(" ", "").lower())
            return {
                "name": "api_health",
                "ok": ok,
                "status_code": resp.status_code,
                "detail": body[:500] if body else "",
                "url": url,
            }
        except requests.RequestException as e:
            return {
                "name": "api_health",
                "ok": False,
                "status_code": -1,
                "detail": f"Request failed: {e}",
                "url": url,
            }

    # フォールバック: curl（URL は検証済み）
    code, out, err = run(["curl", "-m", "3", "-sS", url])
    ok = (code == 0) and ('"ok":true' in out.replace(" ", "").lower())
    return {
        "name": "api_health",
        "ok": ok,
        "status_code": code,
        "detail": out or err,
        "url": url,
    }

def check_logs() -> Dict[str, Any]:
    """ログ類の存在と更新日時をざっくり確認"""
    items = []

    # decide_*.json のうち新しいものが1つでもあれば OK
    recent_decide = False
    if LOGS_DIR.exists():
        for p in LOGS_DIR.glob("decide_*.json"):
            if mtime_ok(p, WITHIN):
                recent_decide = True
                break
    items.append({"item": "decide_logs_recent", "ok": recent_decide})

    # doctor_report.json / doctor_dashboard.html
    items.append({"item": "doctor_report_json_recent",
                  "ok": mtime_ok(REPORT_JSON, WITHIN),
                  "path": str(REPORT_JSON)})
    items.append({"item": "doctor_dashboard_html_recent",
                  "ok": mtime_ok(REPORT_HTML, WITHIN),
                  "path": str(REPORT_HTML)})

    # summary.csv（あれば）
    if SUMMARY_CSV.exists():
        items.append({"item": "summary_csv_recent",
                      "ok": mtime_ok(SUMMARY_CSV, WITHIN),
                      "path": str(SUMMARY_CSV)})

    all_ok = all(i["ok"] for i in items)
    return {
        "name": "logs_and_reports",
        "ok": all_ok,
        "items": items,
        "logs_dir": str(LOGS_DIR),
        "report_dir": str(REPORT_DIR),
    }

def check_backups() -> Dict[str, Any]:
    """バックアップ zip が一定期間内にあるかを確認"""
    recent = False
    latest = None
    if BACKUPS_DIR.exists():
        zips = sorted(BACKUPS_DIR.glob("veritas_logs_*.zip"),
                      key=lambda p: p.stat().st_mtime,
                      reverse=True)
        if zips:
            latest = zips[0]
            recent = mtime_ok(latest, timedelta(days=7))  # 1週間以内ならOKとみなす

    return {
        "name": "backups",
        "ok": recent,
        "latest": str(latest) if latest else None,
        "backups_dir": str(BACKUPS_DIR),
    }

# ===== Slack 通知 =====
def notify_slack(summary: str):
    """notify_slack.py を安全な Python 実行ファイルで起動する。"""
    if not SLACK_NOTIFY.exists():
        return

    python_executable = _resolve_python_executable()
    try:
        # notify_slack.py "<message>"
        run([python_executable, str(SLACK_NOTIFY), summary], timeout=10)
    except Exception:
        pass


def _resolve_python_executable() -> str:
    """サブプロセス用 Python 実行ファイルを安全寄りに選択する。"""
    candidate = (sys.executable or "").strip()
    if candidate:
        candidate_path = Path(candidate)
        if candidate_path.is_absolute() and candidate_path.exists() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)

    print("⚠️ SECURITY WARNING: sys.executable is invalid; falling back to python3 from PATH")
    return "python3"

# ===== main =====
def main():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    checks = [
        check_server(),
        check_logs(),
        check_backups(),
    ]
    all_ok = all(c.get("ok") for c in checks)

    result = {
        "checked_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "api_base": API_BASE,
        "overall_ok": all_ok,
        "checks": checks,
    }

    # 標準出力
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # ファイル保存
    try:
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ failed to write {OUT_JSON}: {e}")

    # 異常時だけ Slack に軽めの要約を送る
    if not all_ok:
        bad = [c["name"] for c in checks if not c.get("ok")]
        summary = f"🛑 VERITAS health_check: NG → {', '.join(bad)}"
        notify_slack(summary)

if __name__ == "__main__":
    main()
