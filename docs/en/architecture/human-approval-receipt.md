# Human Approval Receipt v1 (local/offline)

## Purpose

Human Approval Receipt v1 is a local/offline deterministic artifact that represents human approval as a reviewable governance record before execution.

It is designed to make approval:

- reviewable,
- hashable,
- scope-bound,
- expiry-aware, and
- fail-closed during runtime validation.

## What this v1 includes

- A deterministic `HumanApprovalReceipt` dataclass artifact.
- Deterministic canonical hashing (`receipt_hash`) with self-hash recursion excluded.
- Fail-closed validation helper for:
  - missing approval,
  - non-approved outcomes,
  - unverified signature flag,
  - missing approver identity/role,
  - expiry invalid/expired,
  - scope mismatch,
  - policy snapshot mismatch,
  - action-class mismatch.
- A compatibility helper that converts the receipt into the existing runtime `human_approval_state` shape.

## Explicit boundary (non-goals)

This is local/offline v1 only.

This does **not** include:

- live IdP integration,
- SSO/IAM integration,
- KMS/HSM integration,
- real e-signature verification,
- production approval workflow integration,
- network calls,
- credentials or SaaS bank integrations.

## Compliance and claims boundary

This artifact is an engineering governance control, not a legal or certification claim.

It is:

- not legal advice,
- not regulatory approval,
- not third-party certification,
- not production approval validation.
