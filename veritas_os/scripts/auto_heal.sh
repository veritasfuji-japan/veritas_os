#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="$HOME/scripts"
LOG_DIR="$SCRIPTS_DIR/logs"
mkdir -p "$LOG_DIR"

notify() {  # Slack通知（失敗しても処理継続）
  python3 "$SCRIPTS_DIR/notify_slack.py" "$1" 2>/dev/null || true
}

# 1) ヘルスチェック
if veritas health >/tmp/veritas_health.out 2>&1; then
  echo "[heal] health OK"
  exit 0
fi

echo "[heal] health FAIL — starting recovery…"
notify "🚨 VERITAS Health FAIL — 自動復旧を開始"

# 2) 代表的な復旧手順
# 2-1) APIサーバ停止/未起動に備えて起動
"$SCRIPTS_DIR/start_server.sh" || true

# 2-2) 生成物欠損などに備えて daily を回復実行
if veritas daily >/tmp/veritas_daily.out 2>&1; then
  echo "[heal] daily re-run OK"
else
  echo "[heal] daily re-run FAILED" >&2
fi

# 3) 再チェック
if veritas health >/tmp/veritas_health_after.out 2>&1; then
  echo "[heal] recovered"
  notify "✅ 自動復旧完了（Health OK）\n• report: $LOG_DIR/report.html\n• backups: $HOME/scripts/backups"
  exit 0
else
  echo "[heal] still failing" >&2
  notify "❌ 自動復旧失敗 — 手動対応が必要です\nログ: $LOG_DIR/cron.log"
  exit 2
fi
