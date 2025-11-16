#!/usr/bin/env bash
set -euo pipefail

# ====== 設定 ======
LOG_DIR="/Users/user/scripts/logs"
SRC_BACKUPS="/Users/user/scripts/backups"
DST_BACKUPS="veritas:VERITAS/backups"

RUN_LOG="${LOG_DIR}/rclone_sync.log"
STATUS_JSON="${LOG_DIR}/drive_sync_status.json"

mkdir -p "$LOG_DIR" "$SRC_BACKUPS"

# ====== ログ関数 ======
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$RUN_LOG"
}

log "=== rclone copy start ==="
log "src=${SRC_BACKUPS} -> dst=${DST_BACKUPS}"

START_TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
START_EPOCH=$(date +%s)
OK=false
TRANSFERRED=0

# ====== rclone 実行（1回だけ） ======
if rclone copy "$SRC_BACKUPS" "$DST_BACKUPS" \
  --create-empty-src-dirs \
  --exclude ".DS_Store" \
  --transfers 8 --checkers 8 \
  --retries 3 --low-level-retries 10 --retries-sleep 10s \
  --stats 1s --stats-one-line \
  --log-file="$RUN_LOG" --log-level INFO; then
  OK=true
  log "rclone copy finished successfully."
else
  OK=false
  log "rclone copy FAILED."
fi

END_TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
DUR=$(( $(date +%s) - START_EPOCH ))

# ====== 転送件数をログから概算抽出 ======
# 例: "Copied (12 files, 0 directories)" から 12 を取る
TRANSFERRED=$(grep -Eo 'Copied \([0-9]+ files' "$RUN_LOG" | tail -n1 | grep -Eo '[0-9]+' || echo 0)

# ====== ステータス JSON を1回だけ書き出し ======
cat > "$STATUS_JSON" <<JSON
{
  "started_at_utc": "$START_TS",
  "ended_at_utc": "$END_TS",
  "duration_sec": $DUR,
  "dst": "$DST_BACKUPS",
  "transferred_files": $TRANSFERRED,
  "ok": $OK
}
JSON

# ====== リモートの末尾 20 件をログに追記（任意） ======
{
  echo "--- remote listing (last 20) ---"
  rclone ls "$DST_BACKUPS" | tail -n 20 || true
} >> "$RUN_LOG"

# ====== Slack 通知（環境変数があれば） ======
if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
  STATUS_EMOJI=$([ "$OK" = true ] && echo "✅" || echo "❌")
  TEXT="$STATUS_EMOJI Drive Sync $(hostname) files=$TRANSFERRED sec=$DUR dst=$DST_BACKUPS"
  curl -s -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"$TEXT\"}" "$SLACK_WEBHOOK_URL" >/dev/null || true
fi

log "=== rclone copy done (ok=$OK, files=$TRANSFERRED, sec=$DUR) ==="