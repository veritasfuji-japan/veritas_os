# Human Approval Receipt v1

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
- A signed approval artifact envelope for crossing external-review and secure/prod runtime trust boundaries.

## Runtime posture trust boundary

Runtime approval validation is posture-aware:

- `HumanApprovalReceipt` is the local/offline receipt representation used after validation.
- A signed approval artifact is the preferred external-review and `secure`/`prod` trust-boundary format. It wraps the receipt payload, canonical `receipt_hash`, signature, signer metadata, and `signed_at` timestamp.
- `signature_verified` must be derived by `verify_human_approval_receipt_artifact()` or an equivalent verifier-controlled path. Raw input is not allowed to self-assert this value across the `secure`/`prod` boundary.
- `secure` and `prod` posture prefer a signed approval artifact plus verifier. A direct `HumanApprovalReceipt` is accepted only when its `signature_verified` field is already true. Compatibility dictionaries alone are not authoritative in those postures.
- `dev` and `test` style local workflows may use receipt-derived compatibility `human_approval_state` dictionaries produced by `build_human_approval_state()` for demos, fixtures, and migration.
- `approval_validation_hash` is tamper-evident metadata for accidental/internal mutation detection. It is not cryptographically signed and is not a substitute for signed artifact verification across an external trust boundary.

A signed approval artifact has this deterministic v1 envelope shape:

```json
{
  "artifact_type": "human_approval_receipt",
  "artifact_version": "v1",
  "receipt": { "...": "HumanApprovalReceipt fields except receipt_hash" },
  "receipt_hash": "canonical sha256 of the receipt payload",
  "signature": "external signature bytes or encoding",
  "signer": {
    "key_id": "review-key-id",
    "algorithm": "ed25519|ecdsa-p256|test-only"
  },
  "signed_at": "2026-05-01T00:00:00+00:00"
}
```

Verification is fail-closed: runtime recomputes `receipt_hash`, requires an explicit verifier for signed artifacts, rejects bad signatures, and propagates expiry, scope, policy-snapshot, and action-class validation failures.

## Explicit boundary (non-goals)

This is local/offline v1 only.

This does **not** include:

- live IdP integration,
- SSO/IAM integration,
- KMS/HSM integration,
- built-in real e-signature verification (callers inject the verifier),
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
