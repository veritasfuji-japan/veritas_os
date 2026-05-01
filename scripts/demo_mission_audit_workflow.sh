#!/usr/bin/env bash
set -euo pipefail

echo "Running VERITAS Mission Control → Audit workflow demo checks..."

pnpm --filter frontend test components/mission-page.test.tsx
pnpm --filter frontend test app/audit/page.test.tsx
pnpm --filter frontend test app/audit/hooks/useAuditData.test.ts
pnpm --filter frontend test lib/governance-link-utils.test.ts

echo "Mission Control → Audit workflow demo checks completed."
