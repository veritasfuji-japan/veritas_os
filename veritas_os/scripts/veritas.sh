#!/bin/zsh
set -euo pipefail

# ===== ルート/ログ設定 =====
SCRIPT_DIR="${0:A:h}"                 # .../veritas_os/scripts
ROOT_DIR="${SCRIPT_DIR:h}"            # .../veritas_os

BASE="$SCRIPT_DIR"                    # Python スクリプト群
LOGDIR="${VERITAS_LOG_DIR:-$ROOT_DIR/scripts/logs}"

REPORT_JSON="$LOGDIR/doctor_report.json"
DASH="$LOGDIR/doctor_dashboard.html"
CERT_PATH="$LOGDIR/consistency_certificate.json"
TRUSTLOG_PATH="$LOGDIR/trust_log.json1"
WORLD_STATE="$LOGDIR/world_state.json"

# .env があれば読み込む
[[ -f "$ROOT_DIR/.env" ]] && set -a && . "$ROOT_DIR/.env" && set +a

# ===== Slack Utility =====
slack() {
  [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
  curl -sS -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"$*\"}" "$SLACK_WEBHOOK_URL" >/dev/null || true
}

ok()  { echo "✅ $*"; }
die() { msg="$1"; echo "❌ VERITAS: $msg"; slack "❌ VERITAS: $msg"; exit 1; }

# ===== ステップ群 =====
step_doctor() {
  echo "🩺 running doctor.py..."
  python3 "$BASE/doctor.py"
  [[ -f "$REPORT_JSON" ]] || die "doctor_report.json が見つかりません"
  ok "doctor done"
}

step_memory() {
  echo "🧠 syncing MemoryOS..."
  python3 "$BASE/memory_sync.py"
  ok "memory sync done"
}

step_report() {
  echo "📊 generating HTML dashboard..."
  mkdir -p "$LOGDIR"
  python3 "$BASE/generate_report.py"
  [[ -f "$DASH" ]] && ok "dashboard: $DASH" || die "dashboard not found"
}

step_alert() {
  echo "🔔 alert to Slack..."
  python3 "$BASE/alert_doctor.py" || true
  ok "alert done"
}

step_backup() {
  if [[ -x "$BASE/backup_logs.sh" ]]; then
    echo "💽 backup logs..."
    bash "$BASE/backup_logs.sh" || true
  fi
}

step_trustlog() {
  echo "🔐 verifying TrustLog chain..."
  (
    cd "$ROOT_DIR/.." || exit 1
    PYTHONPATH="$ROOT_DIR/..:${PYTHONPATH:-}" python3 -m veritas_os.scripts.verify_trust_log
  ) || die "TrustLog チェーンに異常あり"
  ok "TrustLog verified"
}

step_certificate() {
  echo "📜 generating consistency_certificate..."

  (
    cd "$ROOT_DIR/.." || exit 1
    PYTHONPATH="$ROOT_DIR/..:${PYTHONPATH:-}" python3 -m veritas_os.scripts.generate_consistency_certificate
  ) || die "consistency_certificate の生成に失敗しました"

  [[ -f "$CERT_PATH" ]] || die "consistency_certificate.json が生成されませんでした"
  ok "certificate generated: $CERT_PATH"
}

step_decide() {
  local q="$1"
  [[ -z "$q" ]] && die "質問が必要です"
  echo "💬 decide: $q"
  python3 "$BASE/decide.py" "$q" || die "decide.py error"
  ok "decide done"
}

step_analyze() {
  echo "🧾 analyzing logs..."
  python3 "$BASE/analyze_logs.py" || die "analyze_logs.py error"
  ok "analyze done"
}

# ===== コマンド分岐 =====
cmd="${1:-help}"
shift || true
start_epoch=$(date +%s)

case "$cmd" in
  full)
    slack "🚀 VERITAS Full Run 開始"
    mkdir -p "$LOGDIR"
    step_doctor
    step_memory
    step_report
    step_alert
    step_backup
    step_trustlog
    step_certificate
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

  trustlog)
    step_trustlog
    ;;

  cert|certificate)
    step_certificate
    ;;

  open)
    [[ -f "$DASH" ]] && open -a "Google Chrome" "$DASH" || die "dashboard not found"
    ;;

  logs)
    [[ -d "$LOGDIR" ]] || die "ログディレクトリがありません"
    ls -lt "$LOGDIR" | head -20
    ;;

  help|*)
    cat <<'EOF'
VERITAS CLI — Complete AGI Decision OS Runner

Usage:
  veritas full              # doctor → memory → report → alert → backup → trustlog → certificate
  veritas decide "Q"        # /v1/decide を CLI から実行
  veritas analyze           # ログ解析
  veritas doctor            # doctor_report.json 生成
  veritas report            # HTML dashboard 生成
  veritas memory            # memory_sync
  veritas alert             # Slack alert
  veritas trustlog          # TrustLog チェーン検証
  veritas cert              # consistency_certificate.json 生成
  veritas open              # dashboard を Chrome で開く
  veritas logs              # logs ディレクトリの最新 20 件を表示
EOF
    ;;
esac

dur=$(( $(date +%s) - start_epoch ))
slack "✅ VERITAS Run 完了（${dur}s）\n📄 Dashboard: $DASH"
ok "Run completed (${dur}s)"