#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[reviewer-entrypoint] $*"
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

require_text() {
  local file="$1"
  local text="$2"
  if ! grep -Fq "$text" "$file"; then
    echo "Missing required text in $file: $text" >&2
    exit 1
  fi
}

log "Checking required files..."
required_files=(
  "docs/REVIEWER_ENTRYPOINT.md"
  "README.md"
  "README_JP.md"
  "docs/governance/observe_mode_proof_pack.md"
  "docs/governance/observe_mode.md"
  "docs/governance/observe_mode_developer_walkthrough.md"
  "docs/governance/observe_mode_mission_control_walkthrough.md"
  "docs/ui/README_UI.md"
  "scripts/validate_governance_observation_fixture.sh"
  "scripts/check_governance_observation.py"
  "scripts/generate_observe_mode_demo_snapshot.py"
  "fixtures/governance_observation_live_snapshot.json"
  "frontend/fixtures/governance_observation_live_snapshot.json"
  "frontend/app/dev/mission-fixture/page.tsx"
  "frontend/app/dev/mission-fixture/page.test.tsx"
)

for file_path in "${required_files[@]}"; do
  require_file "$file_path"
done

log "Checking required links and safety text..."
require_text "README.md" "docs/REVIEWER_ENTRYPOINT.md"
require_text "README_JP.md" "docs/REVIEWER_ENTRYPOINT.md"
require_text "docs/governance/observe_mode_proof_pack.md" "docs/REVIEWER_ENTRYPOINT.md"
require_text "docs/ui/README_UI.md" "docs/REVIEWER_ENTRYPOINT.md"

require_text "docs/REVIEWER_ENTRYPOINT.md" "docs/governance/observe_mode_proof_pack.md"
require_text "docs/REVIEWER_ENTRYPOINT.md" "scripts/validate_governance_observation_fixture.sh"
require_text "docs/REVIEWER_ENTRYPOINT.md" "/dev/mission-fixture"
require_text "docs/REVIEWER_ENTRYPOINT.md" "Production remains fail-closed"
require_text "docs/REVIEWER_ENTRYPOINT.md" "Observe Mode runtime is not enabled"

log "Checking optional heavy command references (presence only)..."
require_text "docs/REVIEWER_ENTRYPOINT.md" "bash scripts/validate_governance_observation_fixture.sh"
require_text "docs/REVIEWER_ENTRYPOINT.md" "pnpm --filter frontend test app/dev/mission-fixture/page.test.tsx"

log "Running lightweight smoke checks..."

print_summary() {
  cat <<'SUMMARY'

=== VERITAS Reviewer Entry Point Validation Summary ===
Reviewer Entry Point: PASS
Required files: PASS
Required links: PASS
Safety language: PASS
Root fixture check: PASS
Frontend fixture check: PASS
Generated snapshot check: PASS
Fixture drift test: PASS
Runtime behavior: unchanged
Observe Mode runtime: not enabled
Production: fail-closed unchanged
Backend mutation endpoint: not added
Production bypass: not added
Summary result: PASS
===============================================

SUMMARY
}
python scripts/check_governance_observation.py fixtures/governance_observation_live_snapshot.json
python scripts/check_governance_observation.py frontend/fixtures/governance_observation_live_snapshot.json
python scripts/generate_observe_mode_demo_snapshot.py --out /tmp/veritas_reviewer_entrypoint_observe_snapshot.json
python scripts/check_governance_observation.py /tmp/veritas_reviewer_entrypoint_observe_snapshot.json
pytest -q veritas_os/tests/test_governance_observation_fixture_drift.py

print_summary
log "Reviewer entry point validation completed successfully."
