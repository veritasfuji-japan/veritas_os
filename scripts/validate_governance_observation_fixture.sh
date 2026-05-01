#!/usr/bin/env bash
set -euo pipefail

echo "Validating VERITAS governance_observation sample fixture..."

pytest -q veritas_os/tests/test_governance_observation_evaluator.py
pnpm --filter frontend test components/mission-governance-adapter.test.ts
pnpm --filter frontend test components/mission-page.test.tsx

echo "governance_observation sample fixture validation completed."
