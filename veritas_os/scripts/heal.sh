#!/usr/bin/env bash
set -euo pipefail

# ==== 設定 ====
API_BASE="${VERITAS_API_BASE:-http://127.0.0.1:8000}"
APP_IMPORT="${VERITAS_APP_IMPORT:-api.server:app}"
PORT="${VERITAS_PORT:-8000}"
LOG_DIR="$HOME/scripts/logs"
LOCK_FILE="/tmp/veritas_heal.lock"
COOLDOWN_SEC="${VERITAS_HEAL_COOLDOWN:-300}"  # 連続再起動防止（秒）

mkdir -p "$LOG_DIR"

ts(){ date "+%Y-%m-%d %H:%M:%S"; }
say(){ echo "[$(ts)] $*"; }
ok(){ say "✅ $*"; }
ng(){ say "🛑 $*"; exit 1; }

notify(){
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -s -X POST -H 'Content-type: application/json' \
      --data "{\"text\":\"$1\"}" \
      "$SLACK_WEBHOOK_URL" >/dev/null || true
  fi
}

health(){
  curl -sS --max-time 2 "$API_BASE/health" | head -c 200 || true
}

# ==== 連続実行ガード ====
now=$(date +%s)
if [[ -f "$LOCK_FILE" ]]; then
  last=$(cat "$LOCK_FILE" || echo 0)
  if (( now - last < COOLDOWN_SEC )); then
    remain=$((COOLDOWN_SEC - (now - last)))
    ok "cooldown中のためスキップ（${remain}s 残り）"
    notify "🟡 VERITAS Heal: cooldown中のためスキップ（${remain}s 残り）"
    exit 0
  fi
fi
echo "$now" > "$LOCK_FILE"

say "🩹 VERITAS Self-heal: 開始"
notify "🩹 VERITAS Heal: 開始"

# ==== 1. 健康チェック ====
if out="$(health)"; then
  if [[ "$out" =~ "ok" || "$out" =~ "OK" ]]; then
    ok "すでにhealthy。処置不要"
    notify "🟢 VERITAS Heal: 既にhealthy（処置不要）"
    exit 0
  fi
fi
say "health NG → 再起動へ"

# ==== 2. 既存プロセス停止 ====
if pgrep -f "uvicorn .*${APP_IMPORT}" >/dev/null 2>&1; then
  say "uvicorn停止中..."
  pkill -f "uvicorn .*${APP_IMPORT}" || true
  sleep 2
fi

# ==== 3. 起動 ====
OUT_LOG="$LOG_DIR/heal_$(date +%Y%m%d_%H%M%S).log"
say "uvicorn起動: ${APP_IMPORT} :${PORT}"
nohup python3 -m uvicorn "${APP_IMPORT}" --port "${PORT}" --reload >"$OUT_LOG" 2>&1 &
sleep 2

# ==== 4. 起動後ヘルスチェック（最大30秒） ====
for i in {1..30}; do
  if out="$(health)"; then
    if [[ "$out" =~ "ok" || "$out" =~ "OK" ]]; then
      ok "ヘルスOK（${i}s）"
      notify "🟢 VERITAS Heal: 成功（${i}s）"
      exit 0
    fi
  fi
  sleep 1
done

ng "ヘルス回復せず。ログ: $OUT_LOG"