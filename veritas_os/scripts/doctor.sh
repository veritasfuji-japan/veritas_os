#!/usr/bin/env bash
# VERITAS Doctor — 自動診断・レポート・同期ワンストップ
# 使い方:
#   ./doctor.sh --once            # 1回実行（デフォルト）
#   ./doctor.sh --watch 900       # 900秒ごとに常駐実行
#   ./doctor.sh --open            # 実行後にHTMLを開く（--once時）
#   ./doctor.sh --no-sync         # rclone 同期を無効化
#   ./doctor.sh --dry-run         # 実行はログだけ（外部変更なし）

set -Eeuo pipefail

# ====== 引数 ======
MODE="once"
INTERVAL=900
OPEN_HTML="no"
SYNC_ON="yes"
DRY_RUN="no"
while (( "$#" )); do
  case "$1" in
    --watch) MODE="watch"; INTERVAL="${2:-900}"; shift ;;
    --once)  MODE="once" ;;
    --open)  OPEN_HTML="yes" ;;
    --no-sync) SYNC_ON="no" ;;
    --dry-run) DRY_RUN="yes" ;;
    -h|--help)
      echo "Usage: $0 [--once|--watch SECS] [--open] [--no-sync] [--dry-run]"
      exit 0;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
  shift
done

# ====== 共通 util ======
ok(){ echo "✅ $1"; }
warn(){ echo "⚠️  $1"; }
ng(){ echo "🛑 $1"; exit 1; }
ts(){ date "+%Y-%m-%d %H:%M:%S"; }
have(){ command -v "$1" >/dev/null 2>&1; }

# ====== パス定義（veritas_os 用） ======
# このファイル: .../veritas_clean_test2/veritas_os/scripts/doctor.sh を想定
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"       # .../veritas_os/scripts
REPO_ROOT="$(cd "${SCRIPTS_DIR}/.." && pwd)"       # .../veritas_os

LOGS_DIR="${SCRIPTS_DIR}/logs"                     # decide_*.json / doctor_report.json など
BACKUPS_DIR="${REPO_ROOT}/backups"                 # バックアップzip置き場
RUNLOG_DIR="${REPO_ROOT}/reports"                  # doctor.sh 実行ログ

GEN_REPORT="${SCRIPTS_DIR}/generate_report.py"
MEM_SYNC="${SCRIPTS_DIR}/memory_sync.py"           # 任意（無ければスキップ）
ALERT_DOCTOR="${SCRIPTS_DIR}/alert_doctor.py"      # 任意（無ければスキップ）

REPORT_HTML="${LOGS_DIR}/doctor_dashboard.html"
REPORT_JSON="${LOGS_DIR}/doctor_report.json"

mkdir -p "$RUNLOG_DIR" "$LOGS_DIR" "$BACKUPS_DIR"

# rclone リモート（必要なら export RCLONE_REMOTE=… で上書き）
RCLONE_REMOTE="${RCLONE_REMOTE:-veritas:VERITAS/backups}"
RCLONE_FLAGS="${RCLONE_FLAGS:---checksum --progress}"

API_BASE="${VERITAS_API_BASE:-http://127.0.0.1:8000}"

# ====== 1. 環境チェック ======
[[ -n "${VERITAS_API_KEY:-}" ]] && ok "VERITAS_API_KEY: OK" || warn "VERITAS_API_KEY 未設定（必須APIには不要ならOK）"
[[ -n "${SLACK_WEBHOOK_URL:-}" ]] && ok "SLACK_WEBHOOK_URL: OK" || warn "Slack 通知未設定（alert_doctor.py はスキップの可能性あり）"

for d in "$SCRIPTS_DIR" "$LOGS_DIR" "$BACKUPS_DIR"; do
  [[ -d "$d" ]] || ng "ディレクトリがありません: $d"
  [[ -w "$d" ]] || ng "書き込み権限がありません: $d"
done
ok "ディレクトリ権限: OK"

have python3 && ok "python3: OK" || ng "python3 が見つかりません"
python3 -c "import matplotlib" >/dev/null 2>&1 && ok "matplotlib: OK" || ng "matplotlib が不足（pip3 install matplotlib）"

[[ -f "$GEN_REPORT" ]] && ok "generate_report.py: OK" || ng "ファイルがありません: $GEN_REPORT"
[[ -f "$MEM_SYNC" ]] && ok "memory_sync.py: found" || warn "memory_sync.py なし → スキップ"
[[ -f "$ALERT_DOCTOR" ]] && ok "alert_doctor.py: found" || warn "alert_doctor.py なし → スキップ"

# ====== 2. API到達性チェック ======
if have curl; then
  if curl -m 3 -fsS "${API_BASE}/api/status" >/dev/null || \
     curl -m 3 -fsS "${API_BASE}/v1/status"  >/dev/null || \
     curl -m 3 -fsS "${API_BASE}/health"     >/dev/null; then
     ok "API 疎通: ${API_BASE}"
  else
     warn "API ステータス取得に失敗（処理は続行）: ${API_BASE}"
  fi
else
  warn "curl が無いので API 疎通確認をスキップ"
fi

# ====== 実行関数 ======
run_generate_report(){
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) レポート生成は実行しません"
  else
    PYTHONIOENCODING=UTF-8 python3 "$GEN_REPORT" || warn "HTMLレポート生成に失敗しました"
  fi
}

run_memory_sync(){
  [[ -f "$MEM_SYNC" ]] || return 0
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) Memory 同期は実行しません"
  else
    python3 "$MEM_SYNC" || warn "MemoryOS 同期に失敗しました"
  fi
}

run_alerts(){
  [[ -f "$ALERT_DOCTOR" ]] || return 0
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) アラート送出は実行しません"
  else
    python3 "$ALERT_DOCTOR" || warn "Slack アラート処理に失敗しました"
  fi
}

open_html(){
  if [[ "$OPEN_HTML" == "yes" && -f "$REPORT_HTML" ]]; then
    open "$REPORT_HTML" || true
  fi
}

sync_drive(){
  [[ "$SYNC_ON" == "yes" ]] || { warn "同期は無効 (--no-sync)"; return; }
  if have rclone; then
    if [[ "$DRY_RUN" == "yes" ]]; then
      warn "(dry-run) rclone 同期は実行しません"
    else
      # logs と backups をそれぞれ同期
      rclone copy "$LOGS_DIR"    "$RCLONE_REMOTE" $RCLONE_FLAGS || warn "rclone(copy logs) 失敗"
      rclone copy "$BACKUPS_DIR" "$RCLONE_REMOTE" $RCLONE_FLAGS || warn "rclone(copy backups) 失敗"
      ok "rclone 同期完了 → $RCLONE_REMOTE"
    fi
  else
    warn "rclone 未インストール → 同期スキップ"
  fi
}

run_once(){
  local RUNLOG="${RUNLOG_DIR}/doctor_run_$(date +%Y%m%d_%H%M%S).log"
  {
    echo "== VERITAS Doctor run @ $(ts) =="
    echo "API_BASE=${API_BASE}"
    echo "SCRIPTS_DIR=${SCRIPTS_DIR}"
    run_memory_sync
    run_generate_report      # decide_*.json → doctor_report.json → doctor_dashboard.html
    run_alerts               # Slack 通知 & heal
    sync_drive               # logs/backups を rclone で同期
    echo "== done @ $(ts) =="
  } | tee "$RUNLOG"
  open_html
}

# ====== 実行 ======
if [[ "$MODE" == "once" ]]; then
  run_once
  echo "✅ Doctor → MemoryOS → HTML → Sync/Alert まで完了"
else
  echo "👀 watch mode: every ${INTERVAL}s"
  while true; do
    run_once
    sleep "$INTERVAL"
  done
fi