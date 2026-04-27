# WAT v1 Tightening Pass: Engineering Trade-offs

**Purpose:** Capture intentional trade-offs introduced by tightening the WAT v1 boundary so operators and implementers understand expected friction and complexity.

## Boundary-tightening trade-offs

1. **Explicit confirmation for confirmed revocation increases operator friction**
   - Tightening requires an explicit confirmation step after a confirmed revocation signal before boundary crossing.
   - Consequence: slower operator flow and extra click/ack overhead in edge-path incidents.
   - Why accepted: it reduces silent continuation risk on stale or ambiguous authority state.

2. **Lean primary audit path increases dependence on drill-down linkage**
   - v1 keeps the default audit path intentionally compact.
   - Consequence: deep verification relies more on drill-down navigation and separate-store linkage correctness.
   - Why accepted: keeps the top-level contract stable and reviewable while preserving depth off-path.

3. **Minimal default summary reduces immediate detail for operators**
   - The default summary returns only the fields required by the boundary contract.
   - Consequence: frontline operators may need an extra fetch to see full adjudication context.
   - Why accepted: minimizes accidental coupling between UI convenience fields and contract-critical semantics.

4. **Stronger retention separation introduces verification indirection**
   - Retention-critical records are separated more strictly from operator-facing summaries.
   - Consequence: verification and incident reconstruction involve more pointer-following across stores.
   - Why accepted: clearer data-lifecycle boundaries and lower risk of summary-path retention leakage.

5. **Expanded observability behind the contract increases engineering complexity**
   - Tightening pushes richer diagnostics behind the stable boundary contract rather than into default UI payloads.
   - Consequence: additional instrumentation, correlation IDs, and internal schema/version management for engineering teams.
   - Why accepted: observability can evolve without repeatedly reopening the v1 operator contract.

## Implementation guidance

- Treat these costs as **intentional consequences of boundary discipline**, not regressions.
- Optimize with tooling (better drill-down UX, correlation helpers, runbook shortcuts) without weakening the v1 contract.
- When proposing exceptions, require an explicit statement of which boundary guarantee would be relaxed.
