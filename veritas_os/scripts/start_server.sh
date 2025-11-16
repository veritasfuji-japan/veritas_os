#!/usr/bin/env bash
set -euo pipefail

BASE="$HOME/scripts"
LOG_DIR="$BASE/logs"
mkdir -p "$LOG_DIR"

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[start] server already running on :8000"
  exit 0
fi

[[ -f "$HOME/.zshrc" ]] && source "$HOME/.zshrc" || true
[[ -f "$HOME/.env"   ]] && set -a && source "$HOME/.env" && set +a || true

# ★ここを変更
cd "$HOME/veritas_clean_test2"

echo "[start] launching uvicorn: veritas_os.api.server:app"

nohup python3 -m uvicorn veritas_os.api.server:app --port 8000 \
  >> "$LOG_DIR/server.log" 2>&1 & echo $! > "$LOG_DIR/server.pid"

for i in {1..20}; do
  if curl -sS http://127.0.0.1:8000/health | grep -q '"status":"ok"'; then
    echo "[start] server launched successfully"
    exit 0
  fi
  sleep 1
done

echo "[start] server failed to start"
exit 1