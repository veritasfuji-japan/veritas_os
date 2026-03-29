#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
OUTPUT_PATH="${1:-$ROOT_DIR/artifacts/frontend-snapshot.png}"
URL="${2:-http://localhost:3000}"

mkdir -p "$(dirname "$OUTPUT_PATH")"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "[ERROR] pnpm が見つかりません。" >&2
  exit 1
fi

echo "[SECURITY WARNING] 外部バイナリ取得を伴う可能性があります。"
echo "[SECURITY WARNING] 信頼できるネットワーク/ミラーでのみ実行してください。"

echo "[INFO] Next.js 開発サーバーを起動します: $URL"
(
  cd "$ROOT_DIR"
  pnpm --filter frontend dev >/tmp/frontend-dev.log 2>&1
) &
DEV_PID=$!

cleanup() {
  if kill -0 "$DEV_PID" >/dev/null 2>&1; then
    kill "$DEV_PID" >/dev/null 2>&1 || true
    wait "$DEV_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Wait for the dev server
for _ in $(seq 1 60); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  echo "[ERROR] 開発サーバーに接続できません。/tmp/frontend-dev.log を確認してください。" >&2
  exit 1
fi

echo "[INFO] スクリーンショットを取得します: $OUTPUT_PATH"
(
  cd "$FRONTEND_DIR"
  pnpm exec playwright screenshot --device="Desktop Chrome" "$URL" "$OUTPUT_PATH"
)

echo "[DONE] スナップショット作成完了: $OUTPUT_PATH"
