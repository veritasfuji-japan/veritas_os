#!/usr/bin/env bash
# Reviewer-owned, disposable synthetic Decision-to-Effect reproduction.
# A run on one Docker host does NOT establish independent administrative custody.
set -Eeuo pipefail
umask 077

if [[ $# -ne 2 ]]; then
  echo "USAGE: bash scripts/validation/run_reviewer_reproduction_v1.sh <out-of-band-40-hex-checkout-sha> <new-output-dir-outside-repo>" >&2
  exit 2
fi
SHA="$1"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "NO_GO_BAD_PIN" >&2
  exit 2
fi
for tool in git docker python3; do
  command -v "$tool" >/dev/null || { echo "NO_GO_MISSING_TOOL_$tool" >&2; exit 2; }
done
docker compose version >/dev/null || { echo "NO_GO_DOCKER_COMPOSE_REQUIRED" >&2; exit 2; }
docker info >/dev/null || { echo "NO_GO_DOCKER_DAEMON_UNAVAILABLE" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ "$(git -C "$ROOT" rev-parse --show-toplevel)" != "$ROOT" ]]; then
  echo "NO_GO_REPO_ROOT_MISMATCH" >&2
  exit 2
fi
if [[ "$(git -C "$ROOT" rev-parse HEAD)" != "$SHA" ]]; then
  echo "NO_GO_CHECKOUT_NOT_PINNED" >&2
  exit 2
fi
# A reviewer should use a fresh checkout. Refuse both tracked modifications
# and untracked files, which could shadow Python imports.
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]]; then
  echo "NO_GO_DIRTY_CHECKOUT_USE_FRESH_CLONE" >&2
  exit 2
fi

OUTPUT="$(python3 - "$ROOT" "$2" <<'PY'
from pathlib import Path
import sys
repo = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).expanduser().absolute()
if target.exists() or target.is_symlink():
    raise SystemExit("NO_GO_OUTPUT_MUST_NOT_EXIST")
if not target.parent.is_dir():
    raise SystemExit("NO_GO_OUTPUT_PARENT_MISSING")
resolved = (target.parent.resolve() / target.name)
if resolved == repo or repo in resolved.parents:
    raise SystemExit("NO_GO_OUTPUT_MUST_BE_OUTSIDE_CHECKOUT")
print(resolved)
PY
)"
mkdir -m 700 -- "$OUTPUT"
export REVIEWER_SOURCE_DIR="$ROOT"
export REVIEWER_OUTPUT_DIR="$OUTPUT"
export REVIEWER_EXPECTED_SHA="$SHA"
REVIEWER_HOST_UID="$(id -u)"
REVIEWER_HOST_GID="$(id -g)"
export REVIEWER_HOST_UID REVIEWER_HOST_GID

PROJECT="veritas-reviewer-$(date +%s)-$$"
COMPOSE="$ROOT/docker/reviewer-proof-v1/compose.yml"
cleanup() {
  docker compose -f "$COMPOSE" -p "$PROJECT" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Build can fetch public pinned dependencies. Runtime has an INTERNAL network,
# no published host ports and no Docker socket mounted into the proof container.
docker compose -f "$COMPOSE" -p "$PROJECT" up \
  --build --abort-on-container-exit --exit-code-from proof proof

# Host-side verifier needs Python stdlib only; pin supplied by the reviewer.
cd "$ROOT"
python3 -m scripts.validation.reviewer_reproduction_manifest_v1 verify \
  --bundle "$OUTPUT" --expected-checkout-sha "$SHA"
echo "PASS_BOUNDED_REVIEWER_OPERATED_REPRODUCTION_CONSISTENCY_ONLY"
echo "Evidence directory: $OUTPUT"
