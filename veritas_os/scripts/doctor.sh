#!/usr/bin/env bash
# VERITAS Doctor Enhanced — 自動診断・レポート・同期ワンストップ
# v2.0: TrustLog検証機能追加
#
# 使い方:
#   ./doctor.sh --once            # 1回実行（デフォルト）
#   ./doctor.sh --watch 900       # 900秒ごとに常駐実行
#   ./doctor.sh --open            # 実行後にHTMLを開く（--once時）
#   ./doctor.sh --no-sync         # rclone 同期を無効化
#   ./doctor.sh --dry-run         # 実行はログだけ（外部変更なし）
#   ./doctor.sh --skip-trustlog   # TrustLog検証をスキップ

set -Eeuo pipefail

# ====== 引数 ======
MODE="once"
INTERVAL=900
OPEN_HTML="no"
SYNC_ON="yes"
DRY_RUN="no"
SKIP_TRUSTLOG="no"

while (( "$#" )); do
  case "$1" in
    --watch) MODE="watch"; INTERVAL="${2:-900}"; shift ;;
    --once)  MODE="once" ;;
    --open)  OPEN_HTML="yes" ;;
    --no-sync) SYNC_ON="no" ;;
    --dry-run) DRY_RUN="yes" ;;
    --skip-trustlog) SKIP_TRUSTLOG="yes" ;;
    -h|--help)
      cat << 'HELP'
VERITAS Doctor Enhanced v2.0

Usage: ./doctor.sh [OPTIONS]

Modes:
  --once             Run once and exit (default)
  --watch SECS       Run continuously every SECS seconds (default: 900)

Options:
  --open             Open HTML dashboard after execution
  --no-sync          Disable rclone cloud sync
  --dry-run          Log only, no external changes
  --skip-trustlog    Skip TrustLog validation
  -h, --help         Show this help message

Features:
  ✅ TrustLog hash chain validation
  ✅ Comprehensive system diagnosis
  ✅ HTML dashboard generation
  ✅ Cloud backup sync (rclone)
  ✅ Slack alerts (optional)

Environment Variables:
  VERITAS_API_KEY       API authentication key
  SLACK_WEBHOOK_URL     Slack notification webhook
  RCLONE_REMOTE         Cloud sync destination (default: veritas:VERITAS/backups)
  VERITAS_API_BASE      API base URL (default: http://127.0.0.1:8000)

Examples:
  ./doctor.sh --once --open
  ./doctor.sh --watch 3600
  ./doctor.sh --dry-run
HELP
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

DOCTOR_PY="${SCRIPTS_DIR}/doctor.py"               # 🆕 TrustLog検証付き診断
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
echo ""
echo "=== VERITAS Doctor Enhanced v2.0 ==="
echo "Time: $(ts)"
echo ""

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
[[ -f "$DOCTOR_PY" ]] && ok "doctor.py: found (TrustLog validation enabled)" || warn "doctor.py なし → TrustLog検証スキップ"
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

echo ""

# ====== 実行関数 ======

# 🆕 Doctor診断（TrustLog検証含む）
run_doctor_diagnosis(){
  if [[ "$SKIP_TRUSTLOG" == "yes" ]]; then
    warn "TrustLog検証はスキップされました (--skip-trustlog)"
    return 0
  fi

  if [[ ! -f "$DOCTOR_PY" ]]; then
    warn "doctor.py が見つかりません → TrustLog検証スキップ"
    return 0
  fi

  echo "=== 1. Doctor診断 (TrustLog検証) ==="
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) Doctor診断は実行しません"
  else
    if python3 "$DOCTOR_PY"; then
      ok "Doctor診断完了"
      
      # TrustLog異常検出時のアラート
      if [[ -f "$REPORT_JSON" ]]; then
        local CHAIN_VALID=$(python3 -c "import json; print(json.load(open('$REPORT_JSON')).get('trustlog', {}).get('chain_valid', True))" 2>/dev/null || echo "true")
        
        if [[ "$CHAIN_VALID" == "False" ]] || [[ "$CHAIN_VALID" == "false" ]]; then
          warn "🚨 TrustLog chain integrity issue detected!"
          warn "   Check: $REPORT_JSON"
          
          # Slack通知（オプション）
          if [[ -n "${SLACK_WEBHOOK_URL:-}" ]] && have curl; then
            local STATUS=$(python3 -c "import json; print(json.load(open('$REPORT_JSON')).get('trustlog', {}).get('status', 'unknown'))" 2>/dev/null)
            local ENTRIES=$(python3 -c "import json; print(json.load(open('$REPORT_JSON')).get('trustlog', {}).get('entries', 0))" 2>/dev/null)
            local BREAKS=$(python3 -c "import json; print(json.load(open('$REPORT_JSON')).get('trustlog', {}).get('chain_breaks', 0))" 2>/dev/null)
            
            curl -X POST "$SLACK_WEBHOOK_URL" \
              -H 'Content-Type: application/json' \
              -d "{\"text\":\"🚨 *VERITAS TrustLog Alert*\n- Status: $STATUS\n- Entries: $ENTRIES\n- Chain breaks: $BREAKS\n- Time: $(ts)\n- Check: \`doctor_report.json\`\"}" \
              >/dev/null 2>&1 || warn "Slack通知に失敗"
          fi
        else
          ok "TrustLog: ✅ ハッシュチェーン正常"
        fi
      fi
    else
      warn "Doctor診断に失敗しました"
    fi
  fi
  echo ""
}

run_generate_report(){
  echo "=== 2. HTMLレポート生成 ==="
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) レポート生成は実行しません"
  else
    if PYTHONIOENCODING=UTF-8 python3 "$GEN_REPORT"; then
      ok "HTMLレポート生成完了"
    else
      warn "HTMLレポート生成に失敗しました"
    fi
  fi
  echo ""
}

run_memory_sync(){
  [[ -f "$MEM_SYNC" ]] || return 0
  
  echo "=== 3. MemoryOS同期 ==="
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) Memory 同期は実行しません"
  else
    if python3 "$MEM_SYNC"; then
      ok "MemoryOS同期完了"
    else
      warn "MemoryOS 同期に失敗しました"
    fi
  fi
  echo ""
}

run_alerts(){
  [[ -f "$ALERT_DOCTOR" ]] || return 0
  
  echo "=== 4. アラート処理 ==="
  if [[ "$DRY_RUN" == "yes" ]]; then
    warn "(dry-run) アラート送出は実行しません"
  else
    if python3 "$ALERT_DOCTOR"; then
      ok "アラート処理完了"
    else
      warn "Slack アラート処理に失敗しました"
    fi
  fi
  echo ""
}

open_html(){
  if [[ "$OPEN_HTML" == "yes" && -f "$REPORT_HTML" ]]; then
    echo "=== Opening Dashboard ==="
    if open "$REPORT_HTML" 2>/dev/null || xdg-open "$REPORT_HTML" 2>/dev/null; then
      ok "Dashboard opened: $REPORT_HTML"
    else
      warn "Dashboard open failed: $REPORT_HTML"
    fi
    echo ""
  fi
}

sync_drive(){
  [[ "$SYNC_ON" == "yes" ]] || { warn "同期は無効 (--no-sync)"; return; }
  
  echo "=== 5. クラウド同期 (rclone) ==="
  if have rclone; then
    if [[ "$DRY_RUN" == "yes" ]]; then
      warn "(dry-run) rclone 同期は実行しません"
    else
      # logs と backups をそれぞれ同期
      if rclone copy "$LOGS_DIR" "$RCLONE_REMOTE" $RCLONE_FLAGS; then
        ok "rclone sync (logs) → $RCLONE_REMOTE"
      else
        warn "rclone(copy logs) 失敗"
      fi
      
      if rclone copy "$BACKUPS_DIR" "$RCLONE_REMOTE" $RCLONE_FLAGS; then
        ok "rclone sync (backups) → $RCLONE_REMOTE"
      else
        warn "rclone(copy backups) 失敗"
      fi
    fi
  else
    warn "rclone 未インストール → 同期スキップ"
  fi
  echo ""
}

run_once(){
  local RUNLOG="${RUNLOG_DIR}/doctor_run_$(date +%Y%m%d_%H%M%S).log"
  
  {
    echo "=========================================="
    echo "VERITAS Doctor Enhanced - Run Report"
    echo "=========================================="
    echo "Start time: $(ts)"
    echo "API_BASE: ${API_BASE}"
    echo "SCRIPTS_DIR: ${SCRIPTS_DIR}"
    echo "Mode: ${MODE}"
    echo "Dry run: ${DRY_RUN}"
    echo "Skip TrustLog: ${SKIP_TRUSTLOG}"
    echo ""
    
    run_doctor_diagnosis     # 🆕 TrustLog検証
    run_memory_sync
    run_generate_report
    run_alerts
    sync_drive
    
    echo "=========================================="
    echo "End time: $(ts)"
    echo "Status: Complete"
    echo "=========================================="
  } | tee "$RUNLOG"
  
  open_html
  
  # 完了サマリ
  echo ""
  echo "✅ Doctor run complete!"
  echo "   Log: $RUNLOG"
  if [[ -f "$REPORT_JSON" ]]; then
    echo "   Report: $REPORT_JSON"
  fi
  if [[ -f "$REPORT_HTML" ]]; then
    echo "   Dashboard: $REPORT_HTML"
  fi
  echo ""
}

# ====== 実行 ======
if [[ "$MODE" == "once" ]]; then
  run_once
  
  # 最終ステータス表示
  if [[ -f "$REPORT_JSON" ]]; then
    echo "=== Final Status ==="
    
    # TrustLog状態を表示
    if python3 -c "import json; data=json.load(open('$REPORT_JSON')); print('TrustLog:', data.get('trustlog', {}).get('status', 'N/A'))" 2>/dev/null; then
      :
    fi
    
    # 決定ログ数を表示
    if python3 -c "import json; data=json.load(open('$REPORT_JSON')); print('Parsed logs:', data.get('parsed_logs', 'N/A'))" 2>/dev/null; then
      :
    fi
    echo ""
  fi
  
else
  echo "👀 Watch mode: every ${INTERVAL}s (Ctrl+C to stop)"
  echo ""
  while true; do
    run_once
    echo "⏳ Waiting ${INTERVAL}s until next run..."
    sleep "$INTERVAL"
  done
fi
