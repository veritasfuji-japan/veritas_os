# Canonical Reference Adapter In-Memory Rehearsal v1

## Boundary

The Canonical Reference Adapter In-Memory Rehearsal Packet records that an
exact, verified Adapter Dry-Run Fixture Result Packet was passed through seven
deterministic methods on a dedicated local rehearsal object. It is a no-effect
artifact, not an execution artifact.

These distinctions are mandatory:

- Fixture Result **is not** Reference Adapter In-Memory Rehearsal.
- Reference Adapter In-Memory Rehearsal **is not** live adapter dry-run
  execution, Bind authorization, a BindReceipt, or a TrustLog write.
- Reference adapter rehearsal signals **are not** Authority Evidence.
- `semantic_match` **is not** Human Approval. Both `true` and `false` are
  preserved without turning either value into execution authority.

The dedicated adapter exists only inside the rehearsal module, holds only
JSON-compatible values in memory, and is not registered with Bind execution.
It cannot perform operation commit. The seven calls, in order, are
`describe_target`, `build_idempotency_key`, `snapshot`, `fingerprint_state`,
`validate_authority`, `validate_constraints`, and `assess_runtime_risk`.
`apply`, postcondition verification, and rollback are excluded.

## Artifact sequence

The auditable chain is:

1. CDA
2. Trust Link
3. Replay Source/Evidence
4. Replay Handoff Binding
5. CanonicalDecisionHandoff validation
6. Guarded Promotion Eligibility Packet
7. ExecutionIntent Formation Readiness Packet
8. Canonical ExecutionIntent Formation Packet
9. ExecutionIntent Pre-Bind Validation Packet
10. Canonical Bind Preflight Adjudication Packet
11. Canonical Bind Adapter Contract Selection Packet
12. Canonical Adapter Dry-Run Plan Packet
13. Canonical Adapter Dry-Run Fixture Result Packet
14. Canonical Reference Adapter In-Memory Rehearsal Packet
15. **STOP**

The packet embeds the complete verified fixture-result packet. Its verifier
re-verifies that source, reconstructs and hashes the ExecutionIntent, checks
descriptor and lineage preservation, and recomputes every output, result, and
packet digest. Compact summaries never replace source verification.

## Deferred work and security non-claims

Live adapter dry-run, a real adapter instance, the Webhook adapter, Bind
adjudication, BindReceipt creation, TrustLog writes, network or filesystem
access, external effects, live state and runtime-risk checks, `apply`,
postconditions, rollback, and operation commit are intentionally deferred to
future explicit PRs. Human Approval and Authority Evidence also remain future
Bind-side requirements.

This artifact makes no production, customer, or regulatory certification
claim. Human review remains required for this governance-sensitive boundary.
