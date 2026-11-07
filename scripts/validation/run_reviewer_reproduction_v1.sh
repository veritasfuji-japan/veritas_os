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
# Never mount a tree with changed/untracked/ignored files, including
# .env, key files, local runtime data, caches or tool-created Python files.
# A disposable reviewer clone is still created below as a second boundary.
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]]; then
  echo "NO_GO_DIRTY_CHECKOUT_USE_FRESH_CLONE" >&2
  exit 2
fi
if [[ -n "$(git -C "$ROOT" ls-files --others --ignored --exclude-standard)" ]]; then
  echo "NO_GO_IGNORED_FILES_PRESENT_USE_FRESH_CLONE" >&2
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
# The Docker daemon must never receive the entire host checkout as
# build context. Clone only Git-tracked content into a fresh isolated source,
# and stage exactly two nonsecret files as the build context.
PROJECT="veritas-reviewer-$(date +%s)-$"
COMPOSE="$ROOT/docker/reviewer-proof-v1/compose.yml"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/veritas-reviewer-v1.XXXXXXXX")"
cleanup() {
  docker compose -f "$COMPOSE" -p "$PROJECT" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "$STAGING"
}
trap cleanup EXIT

git clone --quiet --local --no-hardlinks --no-checkout "$ROOT" "$STAGING/source"
git -C "$STAGING/source" -c advice.detachedHead=false checkout --quiet --detach "$SHA"
if [[ "$(git -C "$STAGING/source" rev-parse HEAD)" != "$SHA" ]] ||
   [[ -n "$(git -C "$STAGING/source" status --porcelain --untracked-files=all)" ]]; then
  echo "NO_GO_STAGED_CHECKOUT_MISMATCH" >&2
  exit 2
fi
mkdir -m 700 -- "$STAGING/build"
mkdir -m 700 -- "$STAGING/build/veritas_os"
cp -- "$ROOT/docker/reviewer-proof-v1/Dockerfile" "$STAGING/build/Dockerfile"
cp -- "$ROOT/veritas_os/requirements.txt" "$STAGING/build/veritas_os/requirements.txt"
chmod 600 -- "$STAGING/build/Dockerfile" "$STAGING/build/veritas_os/requirements.txt"

export REVIEWER_SOURCE_DIR="$STAGING/source"
export REVIEWER_BUILD_CONTEXT="$STAGING/build"
export REVIEWER_OUTPUT_DIR="$OUTPUT"
export REVIEWER_EXPECTED_SHA="$SHA"
REVIEWER_HOST_UID="$(id -u)"
REVIEWER_HOST_GID="$(id -g)"
export REVIEWER_HOST_UID REVIEWER_HOST_GID

# Build can fetch pinned public dependencies. Proof and database attach only
# to an INTERNAL network with no host ports or mounted Docker socket.
docker compose -f "$COMPOSE" -p "$PROJECT" up \
  --build --abort-on-container-exit --exit-code-from proof proof

# Host-side verifier needs Python stdlib only; pin supplied by the reviewer.
cd "$ROOT"
python3 -m scripts.validation.reviewer_reproduction_manifest_v1 verify \
  --bundle "$OUTPUT" --expected-checkout-sha "$SHA"
echo "PASS_BOUNDED_REVIEWER_OPERATED_REPRODUCTION_CONSISTENCY_ONLY"
echo "Evidence directory: $OUTPUT"
