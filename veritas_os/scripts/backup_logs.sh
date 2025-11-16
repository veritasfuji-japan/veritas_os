#!/usr/bin/env bash
set -euo pipefail

##
# VERITAS v3 backup_logs.sh
# - decide.log / decide_*.json / doctor_report.json などを zip 化
# - 出力先: veritas_os/backups/
# - Slack 通知 & rclone 同期対応
##

# ----- パス解決 -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_DIR="${REPO_ROOT}/scripts/logs"
REPORT_DIR="${REPO_ROOT}/reports"
OUT_DIR="${REPO_ROOT}/backups"

TS="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${OUT_DIR}/veritas_logs_${TS}.zip"
RETENTION_DAYS=60          # 保持日数
HISTORY_FILE="${OUT_DIR}/backup_history.csv"
NOTIFY_PY="${SCRIPT_DIR}/notify_slack.py"

mkdir -p "${OUT_DIR}"

echo "[backup] === VERITAS Backup Start ==="
echo "[backup] LOG_DIR   : ${LOG_DIR}"
echo "[backup] REPORT_DIR: ${REPORT_DIR}"
echo "[backup] OUT_DIR   : ${OUT_DIR}"

# ----- バックアップ対象を収集 -----
cd "${REPO_ROOT}"

files=()

# decide.log / decide_*.json など
if compgen -G "scripts/logs/decide*" > /dev/null; then
  while IFS= read -r f; do files+=("$f"); done < <(compgen -G "scripts/logs/decide*")
fi

# summary.csv / *.png / *.html（あれば）
if compgen -G "scripts/logs/summary.csv" > /dev/null; then
  while IFS= read -r f; do files+=("$f"); done < <(compgen -G "scripts/logs/summary.csv")
fi
if compgen -G "scripts/logs/*.png" > /dev/null; then
  while IFS= read -r f; do files+=("$f"); done < <(compgen -G "scripts/logs/*.png")
fi
if compgen -G "scripts/logs/*.html" > /dev/null; then
  while IFS= read -r f; do files+=("$f"); done < <(compgen -G "scripts/logs/*.html")
fi

# doctor_report.json
if [ -f "reports/doctor_report.json" ]; then
  files+=("reports/doctor_report.json")
fi

if [ "${#files[@]}" -eq 0 ]; then
  echo "[backup] No files to archive under scripts/logs or reports."
  echo "[backup] === Nothing to do (Completed) ==="
  exit 0
fi

echo "[backup] Files to archive:"
printf '  - %s\n' "${files[@]}"

# ----- 圧縮 -----
mkdir -p "${OUT_DIR}"
if zip -r "${ARCHIVE}" "${files[@]}" >/dev/null 2>&1; then
  echo "[backup] Created: ${ARCHIVE}"
else
  echo "[backup] zip failed"
  if [ -n "${SLACK_WEBHOOK_URL:-}" ] && [ -f "${NOTIFY_PY}" ]; then
    python3 "${NOTIFY_PY}" "🛑 VERITAS Backup 失敗"
  fi
  exit 1
fi

# ----- チェックサム生成 -----
(
  cd "${OUT_DIR}"
  shasum -a 256 "$(basename "${ARCHIVE}")" > "${ARCHIVE}.sha256"
)
echo "[backup] Checksum: ${ARCHIVE}.sha256"

# ----- 履歴を記録 -----
DATE="$(date '+%Y-%m-%d %H:%M:%S')"
SIZE="$(du -h "${ARCHIVE}" | awk '{print $1}')"
CHECKSUM="$(shasum -a 256 "${ARCHIVE}" | awk '{print $1}')"

if [ ! -f "${HISTORY_FILE}" ]; then
  echo "datetime,archive,size,sha256" > "${HISTORY_FILE}"
fi
echo "${DATE},${ARCHIVE},${SIZE},${CHECKSUM}" >> "${HISTORY_FILE}"
echo "[backup] Logged to: ${HISTORY_FILE}"

# ----- 古いバックアップ削除 -----
find "${OUT_DIR}" -name 'veritas_logs_*.zip' -type f -mtime +${RETENTION_DAYS} -print -delete | \
  sed 's/^/[backup] Deleted old: /' || true

# ----- Slack通知（任意） -----
if [ -n "${SLACK_WEBHOOK_URL:-}" ] && [ -f "${NOTIFY_PY}" ]; then
  python3 "${NOTIFY_PY}" "📦 VERITAS Backup Completed ✅
🗄 Archive: $(basename "${ARCHIVE}")
📅 ${DATE}
💾 Size: ${SIZE}"
fi

# ----- rclone 同期（任意・あれば） -----
if command -v rclone >/dev/null 2>&1; then
  # remote 名 'veritas' は必要に応じて変更
  rclone sync "${OUT_DIR}" "veritas:VERITAS/backups" --checksum --exclude "*.sha256" || true
fi

echo "[backup] === Completed Successfully ==="
exit 0