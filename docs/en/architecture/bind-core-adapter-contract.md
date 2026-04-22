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

## Compatibility constraints

- Existing public contract fields (`bind_outcome`, `bind_reason_code`, lineage ids, receipt payload shape) remain compatible.
- `veritas_os.policy.bind_execution.execute_bind_boundary` remains as a compatibility alias.
- Policy bundle promotion continues using the same API route and response envelope, while internally routing through bind core.
