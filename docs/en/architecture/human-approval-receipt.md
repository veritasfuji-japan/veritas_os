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
- A sealed `VerifiedHumanApprovalReceipt` proof object emitted only after signed-artifact verification succeeds.
- An explicit `HumanApprovalSignatureVerifier` contract for production verifier implementations.

## Runtime posture trust boundary

Runtime approval validation is posture-aware:

- `HumanApprovalReceipt` is the local/offline receipt representation used after validation. It is not, by itself, a cross-process trust-boundary proof.
- A signed approval artifact is the preferred external-review and `secure`/`prod` trust-boundary format. It wraps the receipt payload, canonical `receipt_hash`, signature, signer metadata, and `signed_at` timestamp.
- `signature_verified=True` alone is not sufficient across `secure`/`prod` trust boundaries. Raw input is not allowed to self-assert signature verification.
- Signed artifact verification is the source of runtime approval trust for `secure`/`prod`. `verify_human_approval_receipt_artifact_to_proof()` recomputes the receipt hash, requires the injected verifier, rejects bad signatures, requires a structured `HumanApprovalSignatureVerificationResult` in `secure`/`prod`, validates signer key ID/algorithm/role/action-class/policy-snapshot authorization against `HumanApprovalSignerPolicy`, validates scope/action/policy/expiry, and returns a `VerifiedHumanApprovalReceipt`.
- `VerifiedHumanApprovalReceipt` is the runtime verified proof object. It carries the validated receipt plus signer metadata, signer policy provenance, `signature_verification_reason`, `verified_at`, `verification_source`, and `verification_proof_hash` computed over canonical verifier-derived proof fields including `signer_policy_hash`.
- `secure` and `prod` posture should use either a `VerifiedHumanApprovalReceipt` proof object or the signed artifact verification path. A direct `HumanApprovalReceipt` is accepted only under the transitional in-process registry provenance path. Compatibility dictionaries alone are not authoritative in those postures.
- A direct `HumanApprovalReceipt` without verifier-derived provenance is a local/offline representation, not a secure/prod trust-boundary proof.
- `dev` and `test` style local workflows may use receipt-derived compatibility `human_approval_state` dictionaries produced by `build_human_approval_state()` for demos, fixtures, and migration.
- Cryptographic signature validity is necessary but not sufficient: signer authorization must also be policy-checked before a signed approval is admissible. The signer policy check depends on explicit verifier-returned key ID, algorithm, signer identity, signer role, and verification reason metadata rather than trusting unsigned artifact fields.
- Legacy boolean verifier results are dev/test compatibility only. In `secure`/`prod`, a verifier returning bare `True` or `False` fails closed with `human_approval_structured_signature_result_required`; the verifier must return `HumanApprovalSignatureVerificationResult`.
- `VerifiedHumanApprovalReceipt` proves both receipt integrity/signature verification and signer admissibility under governance policy.
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
    "algorithm": "ed25519|ecdsa-p256|test-only",
    "identity": "operator:approver-1",
    "role": "risk_manager"
  },
  "signed_at": "2026-05-01T00:00:00+00:00"
}
```

Verification is fail-closed: runtime recomputes `receipt_hash`, requires an explicit verifier and `HumanApprovalSignerPolicy` for signed artifacts, rejects boolean verifier output in `secure`/`prod`, rejects bad signatures, rejects incomplete structured verification metadata with deterministic reasons (`human_approval_signature_verification_failed`, `human_approval_signature_key_id_missing`, `human_approval_signature_algorithm_missing`, `human_approval_signature_signer_identity_missing`, `human_approval_signature_signer_role_missing`), rejects signer policy violations with deterministic reasons (`human_approval_signer_key_not_allowed`, `human_approval_signer_algorithm_not_allowed`, `human_approval_signer_role_not_allowed`, `human_approval_signer_action_class_not_allowed`, `human_approval_signer_policy_snapshot_not_allowed`), verifies `verification_proof_hash` for proof objects, requires verifier-derived provenance for transitional direct receipts in `secure`/`prod`, and propagates expiry, scope, policy-snapshot, and action-class validation failures.

Successful artifact verification returns a proof object similar to:

```json
{
  "receipt": { "...": "validated HumanApprovalReceipt" },
  "artifact_type": "human_approval_receipt",
  "artifact_version": "v1",
  "receipt_hash": "canonical sha256 of the receipt payload",
  "signer_key_id": "review-key-id",
  "signer_algorithm": "ed25519",
  "signer_identity": "operator:approver-1",
  "signer_role": "risk_manager",
  "signer_policy_id": "approval-signer-policy-v1",
  "signer_policy_hash": "canonical sha256 of signer policy",
  "signature_verification_reason": "kms_signature_valid",
  "signed_at": "2026-05-01T00:00:00+00:00",
  "verified_at": "2026-05-01T00:00:01+00:00",
  "verification_source": "signed_human_approval_artifact",
  "verification_proof_hash": "canonical sha256 of proof metadata"
}
```

For backward compatibility, `verify_human_approval_receipt_artifact()` still returns the validated receipt from this proof. That receipt includes verifier-derived metadata similar to:

```json
{
  "verification_source": "signed_human_approval_artifact",
  "artifact_type": "human_approval_receipt",
  "artifact_version": "v1",
  "signer_key_id": "review-key-id",
  "signer_algorithm": "ed25519",
  "signer_identity": "operator:approver-1",
  "signer_role": "risk_manager",
  "signer_policy_id": "approval-signer-policy-v1",
  "signer_policy_hash": "canonical sha256 of signer policy",
  "signature_verification_reason": "kms_signature_valid",
  "signed_at": "2026-05-01T00:00:00+00:00",
  "verified_at": "2026-05-01T00:00:01+00:00",
  "receipt_hash_verified": true,
  "signature_verified_by_runtime": true
}
```

These fields are verifier-derived only when set through signed-artifact verification. Caller-supplied copies are stripped from raw signed payload metadata before verification and are not treated as cryptographic proof on their own. Current direct-receipt provenance still uses an in-process verification registry as a transitional compatibility control; it rejects simple forged metadata in one runtime process, but it should not be treated as cross-process cryptographic sealing. Cross-process callers should pass `VerifiedHumanApprovalReceipt` or the original signed artifact plus verifier. Production security still depends on real key management, KMS/HSM or equivalent verifier implementation, key rotation, and operational controls outside this local/offline helper.


## Verifier contract

VERITAS defines an explicit `HumanApprovalSignatureVerifier` interface:

```python
class HumanApprovalSignatureVerifier(Protocol):
    def verify(
        self,
        artifact: dict[str, Any],
    ) -> HumanApprovalSignatureVerificationResult: ...
```

Production deployments must bind this contract to deployment-controlled cryptographic infrastructure, such as KMS, HSM, or trusted public-key verification. The verifier must return verifier-derived `verified`, `key_id`, `algorithm`, `signer_identity`, `signer_role`, and `reason` metadata. `RuntimeAuthorityValidator` remains implementation agnostic: it can use `human_approval_signature_verifier` or the older `verify_human_approval_signature_fn`, but `secure`/`prod` should prefer the interface and still rejects bare boolean results.

No production verifier is provided or assumed by default. Production deployments must provide their own `HumanApprovalSignatureVerifier` bound to deployment-controlled KMS, HSM, or trusted public-key infrastructure. `TestHumanApprovalSignatureVerifier` is a deterministic test/dev-only helper for fixtures and demos; it is explicitly marked test-only and `RuntimeAuthorityValidator` blocks it in `secure`/`prod` posture with `human_approval_test_signature_verifier_not_allowed`. Local/dev demos may use the test verifier only outside strict posture; it is not production assurance and must not be treated as evidence of real cryptographic verification.

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
