#!/usr/bin/env bash
# ==========================================
# VERITAS Monitor - 自動監視 & 自動復旧（現行環境用）
# ==========================================
set -euo pipefail

APP_PORT=8000
CHECK_URL="http://127.0.0.1:${APP_PORT}/health"

LOG_DIR="$HOME/scripts/logs"
LOG_FILE="${LOG_DIR}/monitor.log"

# ★ start_server.sh は ~/scripts/ にあるシンボリックリンクを想定
START_SCRIPT="$HOME/scripts/start_server.sh"

mkdir -p "$LOG_DIR"

DATE="$(date '+%Y-%m-%d %H:%M:%S')"

# ---- ヘルスチェック ----
STATUS="$(curl -s -o /dev/null -w '%{http_code}' "$CHECK_URL" || echo 000)"

if [ "$STATUS" = "200" ]; then
  echo "[$DATE] ✅ OK ($STATUS)" >> "$LOG_FILE"
  exit 0
fi

echo "[$DATE] ⚠️ API DOWN (status=$STATUS)" >> "$LOG_FILE"

# ---- Python バイナリ決定（venv優先）----
if [ -x "$HOME/.venv/bin/python3" ]; then
  PYTHON_BIN="$HOME/.venv/bin/python3"
else
  PYTHON_BIN="python3"
fi

# ---- Slack 通知（ダウン検知）----
if [ -f "$HOME/scripts/notify_slack.py" ]; then
  "$PYTHON_BIN" "$HOME/scripts/notify_slack.py" \
    "⚠️ VERITAS Monitor: API停止を検出 (status=$STATUS)。自動復旧を実行します。" \
    || true
fi

# ---- サーバープロセス停止 ----
pkill -f "uvicorn veritas_os.api.server:app" || true

# ---- サーバー再起動（統一 start_script 経由）----
nohup "$START_SCRIPT" >> "$LOG_DIR/server_restart.log" 2>&1 &

# 少し待ってから再チェック
sleep 10
NEW_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "$CHECK_URL" || echo 000)"

# ---- Slack 復旧通知 ----
if [ -f "$HOME/scripts/notify_slack.py" ]; then
  "$PYTHON_BIN" "$HOME/scripts/notify_slack.py" \
    "🩵 VERITAS自動復旧完了 (before=$STATUS, after=$NEW_STATUS)" \
    || true
fi

echo "[$DATE] 🔁 Restarted automatically (before=$STATUS after=$NEW_STATUS)" >> "$LOG_FILE"