#!/bin/zsh
set -euo pipefail

# ===== ルート/ログ設定 =====
# このスクリプト自身の場所から veritas_os のルートを推定
SCRIPT_DIR="${0:A:h}"          # .../veritas_os/scripts
ROOT_DIR="${SCRIPT_DIR:h}"     # .../veritas_os

BASE="$SCRIPT_DIR"             # Python スクリプト群の場所
LOGDIR="${VERITAS_LOG_DIR:-$ROOT_DIR/scripts/logs}"
DASH="$LOGDIR/doctor_dashboard.html"        # ← ここだけを見る
REPORT_JSON="$LOGDIR/doctor_report.json"    # JSON も logs 配下に統一

# .env を読み込む（あれば）
[[ -f "$ROOT_DIR/.env" ]] && set -a && . "$ROOT_DIR/.env" && set +a

# ===== ユーティリティ =====
slack() {
  [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
  curl -sS -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"$*\"}" "$SLACK_WEBHOOK_URL" >/dev/null || true
}

ok()  { echo "✅ $*"; }
die() { msg="$1"; echo "❌ VERITAS: $msg"; slack "❌ VERITAS: $msg"; exit 1; }

# ===== 各ステップ =====
step_doctor() {
  echo "🩺 running doctor.py..."
  python3 "$BASE/doctor.py"
  [[ -f "$REPORT_JSON" ]] || die "doctor_report.json が見つかりません: $REPORT_JSON"
  ok "doctor done"
}

step_report() {
  echo "📊 generating HTML dashboard..."
  mkdir -p "$LOGDIR"
  python3 "$BASE/generate_report.py"
  [[ -f "$DASH" ]] && ok "dashboard: $DASH" || die "dashboard not found: $DASH"
}

step_memory() {
  echo "🧠 syncing MemoryOS..."
  python3 "$BASE/memory_sync.py"
  ok "memory sync done"
}

step_alert() {
  echo "🔔 alert to Slack (threshold check)..."
  python3 "$BASE/alert_doctor.py" || true
  ok "alert done"
}

step_backup() {
  if [[ -x "$BASE/backup_logs.sh" ]]; then
    echo "💽 backup logs..."
    bash "$BASE/backup_logs.sh" || true
  fi
}

step_decide() {
  local q="$1"
  [[ -z "$q" ]] && die "質問がありません 例: veritas decide \"明日の優先タスクは?\""
  echo "💬 decide: $q"
  python3 "$BASE/decide.py" "$q" || die "decide.py でエラー"
  ok "decide done"
}

step_analyze() {
  echo "🧾 analyzing logs..."
  python3 "$BASE/analyze_logs.py" || die "analyze_logs.py でエラー"
  ok "analyze done"
}

# ===== コマンド分岐 =====
cmd="${1:-help}"
shift || true
start_epoch=$(date +%s)

case "$cmd" in
  full)
    slack "🚀 VERITAS Full Run を開始します"
    mkdir -p "$LOGDIR"
    step_doctor
    step_memory
    step_report
    step_alert
    step_backup
    ;;

  decide)
    step_decide "${*:-}"
    ;;

  analyze)
    step_analyze
    ;;

  doctor)
    step_doctor
    ;;

  report)
    step_report
    ;;

  memory)
    step_memory
    ;;

  alert)
    step_alert
    ;;

  open)
    if [[ -f "$DASH" ]]; then
      open -a "Google Chrome" "$DASH"
    else
      die "dashboard not found: $DASH"
    fi
    ;;

  logs)
    [[ -d "$LOGDIR" ]] || die "ログディレクトリがありません: $LOGDIR"
    ls -lt "$LOGDIR" | head -20
    ;;

  help|*)
    cat <<'EOF'
VERITAS CLI — AI Decision Assistant

使い方:
  veritas full        # doctor → memory → report → alert → (backup)
  veritas decide "Q"  # /v1/decide を実行（CLIから）
  veritas analyze     # ログ要約
  veritas doctor      # 自己診断（JSON生成）
  veritas report      # HTMLダッシュボード生成
  veritas memory      # memory.json 連携
  veritas alert       # doctor_report.json を見てSlack通知
  veritas open        # ダッシュボードをブラウザで開く
  veritas logs        # 直近のログを一覧表示
EOF
    ;;
esac

dur=$(( $(date +%s) - start_epoch ))
slack "✅ VERITAS Run 完了（${dur}s）\n ダッシュボード: $DASH"
ok   "Run completed (${dur}s)"