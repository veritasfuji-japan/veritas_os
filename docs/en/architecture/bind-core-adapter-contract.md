# Bind Core / Adapter Contract (internal note)

This note documents the internal refactor that extracted reusable bind adjudication primitives from the policy-bundle promotion path.

## Added internal components

- `veritas_os.policy.bind_core.core.execute_bind_adjudication`
  - Common bind adjudication entrypoint.
  - Preserves existing receipt shape and TrustLog linkage behavior.
- `veritas_os.policy.bind_core.contracts.BindAdapterContract`
  - ABC for bind adapters.
- `veritas_os.policy.bind_core.normalizers`
  - Canonical helpers for `ExecutionIntent` and `BindReceipt` normalization.
- `veritas_os.policy.bind_core.constants`
  - Canonical `BindOutcome` and `BindReasonCode` constants.
  - Minimal retry/failure taxonomy:
    - `BindRetrySafety`: `SAFE` / `UNSAFE` / `REQUIRES_ESCALATION`
    - `BindFailureCategory`: `NONE` / `PRECONDITION` / `SNAPSHOT` /
      `ADMISSIBILITY` / `APPLY` / `POSTCONDITION` / `ROLLBACK`

## Standardized bind semantics (minimum)

- **Idempotency / repeated bind**
  - Adapter contract adds `build_idempotency_key(intent)` (default:
    `execution_intent_id`).
  - Bind core records idempotency key in `bind_receipt.revalidation_context` and
    `bind_receipt.idempotency_key`.
  - Repeated submissions with the same intent + idempotency key return the
    prior bind receipt (`idempotency_status=replayed`) and do not re-apply
    external effects.
- **Retry safety**
  - Every bind receipt includes `retry_safety`.
  - `COMMITTED` / `BLOCKED` / `ROLLED_BACK` are `SAFE`.
  - `SNAPSHOT_FAILED` / `PRECONDITION_FAILED` are `UNSAFE` until operator fixes
    input/state assumptions.
  - `APPLY_FAILED` / `ESCALATED` are `REQUIRES_ESCALATION`.
- **Rollback semantics**
  - Receipt includes `rollback_status`:
    `rolled_back` / `rollback_failed` / `rollback_not_attempted` /
    `manual_intervention_required` / `not_required`.
  - Apply failures roll back only when policy enables
    `rollback_on_apply_failure`; otherwise outcome stays `APPLY_FAILED`.
- **Failure taxonomy**
  - Receipt includes `failure_category`, derived from terminal outcome + failure
    context, for stable downstream handling and alert routing.

## Compatibility constraints

- Existing public contract fields (`bind_outcome`, `bind_reason_code`, lineage ids, receipt payload shape) remain compatible.
- `veritas_os.policy.bind_execution.execute_bind_boundary` remains as a compatibility alias.
- Policy bundle promotion continues using the same API route and response envelope, while internally routing through bind core.

## Explicit non-goals (deferred hardening)

- No claim of cross-system distributed transaction guarantees.
- No multi-resource two-phase commit or global dedupe service in this PR.
- Idempotency replay detection is TrustLog-local and scoped to existing bind
  lineage identifiers.
