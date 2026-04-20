# Bind-Boundary Governance Artifacts (Schema-First)

## What this PR adds

This change introduces two **native VERITAS governance artifacts** as first-class
contracts:

1. `ExecutionIntent`
2. `BindReceipt`

It also introduces `FinalOutcome` for bind-time terminal status.
In addition, bind-boundary artifacts are now appended to the existing TrustLog
path so auditors can traverse native lineage:

`decision artifact -> execution intent -> bind receipt`

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

## TrustLog and lineage integration

- `ExecutionIntent` appends as `kind=governance.execution_intent` via the
  existing `append_trust_log` implementation (same hash-chain/signing path).
- `BindReceipt` appends as `kind=governance.bind_receipt` via the same TrustLog
  append pipeline and receives the TrustLog chain hash in `trustlog_hash`.
- `prev_bind_hash` chaining is derived from prior bind receipts already stored
  in TrustLog (`bind_receipt_hash`), not from a new logging plane.
- Retrieval helpers resolve bind receipts by `bind_receipt_id`,
  `execution_intent_id`, or `decision_id` directly from TrustLog entries.

This keeps decision artifacts primary while extending native VERITAS governance
lineage toward bind-boundary control.

## Runtime behavior impact

Low and additive. Existing decision flows remain backward compatible, and no
execution adapter/orchestration behavior is introduced in this PR.
