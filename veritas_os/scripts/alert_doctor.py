#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, urllib.request, urllib.error, subprocess, shlex, time
from pathlib import Path

# ================================
# パス設定（プロジェクトローカル）
# ================================
# このファイル自体は veritas_os/scripts/alert_doctor.py にある想定
THIS_FILE   = Path(__file__).resolve()
SCRIPTS_DIR = THIS_FILE.parent                  # .../veritas_os/scripts
VERITAS_DIR = SCRIPTS_DIR.parent                # .../veritas_os

REPORT_JSON = VERITAS_DIR / "reports" / "doctor_report.json"
REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)

# 旧: ~/scripts / ~/veritas は使わない
# BASE         = os.path.expanduser("~/scripts")
# REPORT_JSON  = os.path.expanduser("~/veritas/reports/doctor_report.json")

# ================================
# 環境変数
# ================================
THRESH      = float(os.getenv("VERITAS_ALERT_UNC", "0.50"))
WEBHOOK     = os.getenv("SLACK_WEBHOOK_URL", "")
HEAL_ON_HIGH = os.getenv("VERITAS_HEAL_ON_HIGH", "1") == "1"
HEAL_SCRIPT = SCRIPTS_DIR / "heal.sh"          # プロジェクト内の heal.sh を使う

API_BASE   = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")
HEALTH_URL = f"{API_BASE}/health"


def post_slack(text: str, timeout_sec: int = 12, max_retry: int = 3) -> bool:
    """Slack Webhookに送信（リトライ付き）。成功ならTrue。"""
    if not WEBHOOK:
        print("⚠️ SLACK_WEBHOOK_URL 未設定のため通知せず。")
        return False

    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={"Content-Type": "application/json"}
    )

    for i in range(max_retry):
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as r:
                if r.status == 200:
                    print("✅ Slack通知成功")
                    return True
                else:
                    print(f"⚠️ Slack応答異常: status={r.status}")
        except urllib.error.URLError as e:
            print(f"⚠️ Slack送信失敗({i+1}/{max_retry}): {e.reason}")
        except Exception as e:
            print(f"⚠️ Slack送信例外({i+1}/{max_retry}): {type(e).__name__}: {e}")

        # 指数バックオフ（1s, 2s, ...）
        if i < max_retry - 1:
            time.sleep(2 ** i)

    return False


def http_get(url: str, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, str(e)


def run_heal():
    if not HEAL_SCRIPT.exists():
        msg = f"heal.sh not found at {HEAL_SCRIPT}"
        print(f"⚠️ {msg}")
        return False, msg

    try:
        # heal.sh は最後にログパスを1行出力する設計
        out = subprocess.check_output(
            shlex.split(str(HEAL_SCRIPT)),
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
        print(out)

        # 起動猶予 → /health を最大10秒ポーリング
        ok = False
        for _ in range(10):
            time.sleep(1)
            status, body = http_get(HEALTH_URL, timeout=2)
            if status == 200 and '"ok":true' in body.replace(" ", "").lower():
                ok = True
                break
        return ok, (out if out else "healed")

    except subprocess.CalledProcessError as e:
        return False, f"heal failed: rc={e.returncode}, out={e.output.strip()}"
    except Exception as e:
        return False, f"heal exception: {e}"


def main():
    if not REPORT_JSON.exists():
        print(f"⚠️ doctor_report.json が見つかりません: {REPORT_JSON}")
        print("    → 先に doctor.py を実行してレポートを生成してください。")
        return

    with REPORT_JSON.open(encoding="utf-8") as f:
        rep = json.load(f)

    total = int(rep.get("total_logs", 0))
    avg   = float(rep.get("avg_uncertainty", 0.0))
    last  = rep.get("last_check", "")
    kws   = rep.get("keywords", {}) or {}

    # レベル判定
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

    # 通知
    if level in ("HIGH", "WARN"):
        post_slack(summary)

    # HIGH のときだけ自己修復
    if level == "HIGH" and HEAL_ON_HIGH:
        ok, info = run_heal()
        post_slack(f"🛠 Self-Heal 実行結果: {'OK' if ok else 'FAIL'} — {info}")
        status, body = http_get(HEALTH_URL, timeout=2)
        post_slack(f"📡 /health: status={status}, body={body[:200]}")


if __name__ == "__main__":
    main()
