# Bind-Boundary Governance Artifacts (Schema-First)

## What this PR adds

This change introduces two **native VERITAS governance artifacts** as first-class
contracts:

1. `ExecutionIntent`
2. `BindReceipt`

It also introduces `FinalOutcome` for bind-time terminal status.

## Why these artifacts exist

VERITAS already treats the decision artifact as the primary governance record.
This extension keeps that architecture intact and adds bind-boundary lineage:

- `ExecutionIntent` links an execution attempt directly to a `decision_id` and
  governance lineage (`policy_snapshot_id`, `actor_identity`, `decision_hash`).
- `BindReceipt` records bind-time checks (authority/constraint/drift/risk/
  admissibility), links back to both decision and execution intent, and carries
  TrustLog chain linkage (`trustlog_hash`, `prev_bind_hash`).

This provides explicit governance-native artifacts at the decision → bind
boundary without creating a parallel subsystem.

## Intentionally deferred

This PR is **schema-first only** and does not introduce:

- external side-effect adapters
- runtime bind orchestration
- rollback engine implementation
- Mission Control UI workflow rewiring
- broad pipeline behavior changes

## Runtime behavior impact

None. Existing decision flows remain backward compatible.
