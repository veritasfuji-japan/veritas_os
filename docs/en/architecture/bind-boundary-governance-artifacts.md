# Bind-Boundary Governance Artifacts

## Implemented scope

VERITAS includes two **native governance artifacts** as first-class contracts:

1. `ExecutionIntent`
2. `BindReceipt`

`FinalOutcome` models bind-time terminal status.
Bind-boundary artifacts append to the existing TrustLog path so auditors can
traverse native lineage:

`decision artifact -> execution intent -> bind receipt`

## Why these artifacts exist

VERITAS already treats the decision artifact as the primary governance record.
This extension keeps that architecture intact and adds bind-boundary lineage:

- `ExecutionIntent` links an execution attempt directly to a `decision_id` and
  governance lineage (`policy_snapshot_id`, `actor_identity`, `decision_hash`).
- `BindReceipt` records bind-time checks (authority/constraint/drift/risk/
  admissibility), links back to both decision and execution intent, and carries
  TrustLog chain linkage (`trustlog_hash`, `prev_bind_hash`).
- `BindReceipt` also stores minimal replay/revalidation metadata:
  `bind_receipt_hash`, `execution_intent_hash`, copied governance identity,
  and a compact `revalidation_context` used for admissibility replay.

This provides explicit governance-native artifacts at the decision → bind
boundary without creating a parallel subsystem.

## Current boundary and caveats

Implemented in this repository:

- bind-time admissibility adjudication inputs on bind receipts
- bind terminal outcomes (`COMMITTED`, `BLOCKED`, `ESCALATED`, `ROLLED_BACK`)
- TrustLog lineage pointers and bind receipt retrieval endpoints
- Mission Control bind-phase rendering on decision results

Not guaranteed by this document alone:

- tenant-specific external side-effect adapter coverage
- environment-specific production hardening and operational controls
- universal production-readiness claims across every deployment context

## TrustLog and lineage integration

- `ExecutionIntent` appends as `kind=governance.execution_intent` via the
  existing `append_trust_log` implementation (same hash-chain/signing path).
- `BindReceipt` appends as `kind=governance.bind_receipt` via the same TrustLog
  append pipeline and receives the TrustLog chain hash in `trustlog_hash`.
- `prev_bind_hash` chaining is derived from prior bind receipts already stored
  in TrustLog (`bind_receipt_hash`), not from a new logging plane.
- Retrieval helpers resolve bind receipts by `bind_receipt_id`,
  `execution_intent_id`, or `decision_id` directly from TrustLog entries.
- Internal helper `veritas_os.policy.bind_revalidation.revalidate_bind_receipt`
  can re-run admissibility from receipt-contained context and verify lineage/hash
  linkage against an optional execution intent payload.

This keeps decision artifacts primary while extending native VERITAS governance
lineage toward bind-boundary control.

## Runtime behavior impact

Additive to existing decision flows. Decision-phase semantics remain primary;
bind-phase semantics add an explicit boundary between approval and commitment.

## Operator interpretation in Mission Control

Mission Control keeps the decision artifact as the primary record and now shows
bind-phase as a lower-layer execution-governance outcome:

- Decision approved + `bind_outcome=COMMITTED`: approved and applied.
- Decision approved + `bind_outcome=BLOCKED`: approved but bind checks blocked.
- Decision approved + `bind_outcome=ESCALATED`: approved but requires escalation.
- Decision approved + `bind_outcome=ROLLED_BACK`: approved, attempted, then rolled back.

This distinction prevents operators from misreading decision-phase approval as
bind-phase commitment.

## Minimal API example

`GET /v1/governance/decisions/export?limit=1`

```json
{
  "ok": true,
  "items": [
    {
      "decision_id": "dec-9001",
      "decision_status": "allow",
      "bind_outcome": "BLOCKED",
      "bind_receipt_id": "br-9001",
      "execution_intent_id": "ei-9001",
      "bind_failure_reason": "Constraint mismatch",
      "bind_reason_code": "CONSTRAINT_MISMATCH"
    }
  ]
}
```

`GET /v1/governance/bind-receipts/br-9001` returns the linked bind receipt
artifact with authority/constraint/drift/risk check payloads.
