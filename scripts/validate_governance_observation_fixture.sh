#!/usr/bin/env bash
set -euo pipefail

echo "Validating VERITAS governance_observation sample fixture..."

pytest -q veritas_os/tests/test_governance_observation_evaluator.py
pytest -q veritas_os/tests/test_governance_observation_cli.py
pytest -q veritas_os/tests/test_observe_mode_wrapper.py
pytest -q veritas_os/tests/test_observe_mode_demo_snapshot_generator.py
pytest -q veritas_os/tests/test_governance_observation_fixture_drift.py
python scripts/check_governance_observation.py fixtures/governance_observation_live_snapshot.json
python scripts/check_governance_observation.py frontend/fixtures/governance_observation_live_snapshot.json
pnpm --filter frontend test components/mission-governance-adapter.test.ts
pnpm --filter frontend test components/mission-page.test.tsx

echo "governance_observation sample fixture validation completed."
