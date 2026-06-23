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
  - action-class mismatch,
  - explicit request/action context-binding mismatch.
- A compatibility helper that converts the receipt into the existing runtime `human_approval_state` shape.
- A signed approval artifact envelope for crossing external-review and secure/prod runtime trust boundaries.
- A sealed `VerifiedHumanApprovalReceipt` proof object emitted only after signed-artifact verification succeeds.
- An explicit `HumanApprovalSignatureVerifier` contract for production verifier implementations.

## Runtime posture trust boundary

Runtime approval validation is posture-aware:

- `HumanApprovalReceipt` is the local/offline receipt representation used after validation. It is not, by itself, a cross-process trust-boundary proof.
- A signed approval artifact is the preferred external-review and `secure`/`prod` trust-boundary format. It wraps the receipt payload, canonical `receipt_hash`, signature, signer metadata, and `signed_at` timestamp.
- `signature_verified=True` alone is not sufficient across `secure`/`prod` trust boundaries. Raw input is not allowed to self-assert signature verification.
- Signed artifact verification is the source of runtime approval trust for `secure`/`prod`. `verify_human_approval_receipt_artifact_to_proof()` recomputes the receipt hash, requires the injected verifier, rejects bad signatures, requires a structured `HumanApprovalSignatureVerificationResult` in `secure`/`prod`, treats verifier-derived key ID/algorithm/signer identity/signer role as authoritative, validates that verifier-derived signer metadata against `HumanApprovalSignerPolicy`, cross-checks any artifact signer metadata self-claims, validates scope/action/policy/expiry, and returns a `VerifiedHumanApprovalReceipt`.
- In `prod`, the verifier must positively identify production-grade provenance and a governance-approved verifier identity. `verifier_trust_level == "production"` is necessary but not sufficient: `verifier_id` must be present and listed in `HumanApprovalVerifierPolicy.approved_human_approval_verifiers`. If the policy configures a `verifier_key_id`, it must match verifier output; if both verifier output and policy provide a `verifier_policy_hash`, they must match. Missing trust level fails closed with `human_approval_production_verifier_required`, non-production trust fails with `human_approval_verifier_trust_level_not_allowed`, missing identity fails with `human_approval_verifier_id_required`, unapproved identity fails with `human_approval_verifier_not_allowed`, key mismatch fails with `human_approval_verifier_key_mismatch`, and policy-hash mismatch fails with `human_approval_verifier_policy_hash_mismatch`. A verifier implementation may also expose a production marker that the runtime converts into production verifier provenance. "Not a test verifier" is not sufficient in prod.
- `VerifiedHumanApprovalReceipt` is the runtime verified proof object. It carries the validated receipt plus verifier-derived signer metadata, signer policy provenance, `signature_verification_reason`, `verifier_trust_level`, verifier identity fields (`verifier_id`, optional `verifier_key_id`, optional `verifier_policy_id`, optional `verifier_policy_hash`), `verified_at`, `verification_source`, and `verification_proof_hash` computed over canonical verifier-derived proof fields including `signer_policy_hash`, `verifier_trust_level`, and verifier identity/policy fields. Artifact/envelope signer self-claims are never copied in as authorization truth.
- `secure` posture may retain the transitional direct `HumanApprovalReceipt` in-process registry provenance path during migration, but that compatibility path is not a production trust-boundary proof. Compatibility dictionaries alone are not authoritative in strict postures.
- `prod` posture is stricter than secure migration behavior: it does not accept direct `HumanApprovalReceipt` provenance, even when the receipt carries in-process verifier-derived provenance. Prod requires either a `VerifiedHumanApprovalReceipt` proof object or the signed artifact verification path with a production verifier, explicit production verifier provenance, and signer policy.
- A direct `HumanApprovalReceipt` is a local/offline representation, not a prod trust-boundary proof.
- `dev` and `test` style local workflows may use receipt-derived compatibility `human_approval_state` dictionaries produced by `build_human_approval_state()` for demos, fixtures, and migration.
- Cryptographic signature validity is necessary but not sufficient: signer authorization must also be policy-checked before a signed approval is admissible. The signer policy check depends on explicit verifier-returned key ID, algorithm, signer identity, signer role, and verification reason metadata rather than trusting unsigned artifact fields.
- An authorized signer is also not sufficient by itself: in `secure`/`prod`, the signed approval must be bound to the exact governed request/action context being evaluated. Runtime context binding compares `request_ref`, `ai_output_ref`, `execution_intent_id`, `decision_id`, `action_class`, `policy_snapshot_id`, `authority_evidence_id`, and `bind_context_hash` when those expected values are supplied. Replaying a valid signed approval across a different request, AI output, execution intent, action class, policy snapshot, authority evidence record, or bind context is rejected fail-closed.
- Legacy boolean verifier results are dev/test compatibility only. In `secure`/`prod`, a verifier returning bare `True` or `False` fails closed with `human_approval_structured_signature_result_required`; the verifier must return `HumanApprovalSignatureVerificationResult`.
- `VerifiedHumanApprovalReceipt` proves both receipt integrity/signature verification and signer admissibility under governance policy.
- `approval_validation_hash` is tamper-evident metadata for accidental/internal mutation detection. It is not cryptographically signed and is not a substitute for signed artifact verification across an external trust boundary.

A signed approval artifact has this deterministic v1 envelope shape:

```json
{
  "artifact_type": "human_approval_receipt",
  "artifact_version": "v1",
  "receipt": {
    "...": "HumanApprovalReceipt fields except receipt_hash",
    "request_ref": "request-001",
    "ai_output_ref": "ai-output-001",
    "execution_intent_id": "intent-001",
    "decision_id": "decision-001",
    "approved_action_class": "wire_transfer",
    "policy_snapshot_id": "policy-001",
    "authority_evidence_id": "aev-001",
    "bind_context_hash": "canonical bind context hash"
  },
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

Verification is fail-closed: runtime recomputes `receipt_hash`, requires an explicit verifier and `HumanApprovalSignerPolicy` for signed artifacts, rejects boolean verifier output in `secure`/`prod`, requires positive production verifier provenance in `prod`, rejects bad signatures, rejects incomplete structured verification metadata with deterministic reasons (`human_approval_signature_verification_failed`, `human_approval_signature_key_id_missing`, `human_approval_signature_algorithm_missing`, `human_approval_signature_signer_identity_missing`, `human_approval_signature_signer_role_missing`), rejects artifact signer metadata contradictions with deterministic reasons (`human_approval_signer_key_mismatch`, `human_approval_signer_algorithm_mismatch`, `human_approval_signer_identity_mismatch`, `human_approval_signer_role_mismatch`), rejects signer policy violations with deterministic reasons (`human_approval_signer_key_not_allowed`, `human_approval_signer_algorithm_not_allowed`, `human_approval_signer_role_not_allowed`, `human_approval_signer_action_class_not_allowed`, `human_approval_signer_policy_snapshot_not_allowed`), verifies `verification_proof_hash` for proof objects, requires verifier-derived provenance for transitional direct receipts in `secure`, rejects direct receipts in `prod` with `human_approval_direct_receipt_not_allowed_in_prod`, rejects context-binding mismatch with deterministic reasons (`human_approval_request_ref_mismatch`, `human_approval_ai_output_ref_mismatch`, `human_approval_execution_intent_mismatch`, `human_approval_decision_id_mismatch`, `human_approval_action_class_mismatch`, `human_approval_policy_snapshot_mismatch`, `human_approval_authority_evidence_mismatch`, `human_approval_bind_context_hash_mismatch`), and propagates expiry, scope, policy-snapshot, and action-class validation failures.

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
  "verifier_trust_level": "production",
  "verifier_id": "veritas-human-approval-verifier-v1",
  "verifier_key_id": "optional-key-id",
  "verifier_policy_id": "human-approval-verifier-policy-v1",
  "verifier_policy_hash": "canonical sha256 of verifier policy snapshot",
  "signed_at": "2026-05-01T00:00:00+00:00",
  "verified_at": "2026-05-01T00:00:01+00:00",
  "verification_source": "signed_human_approval_artifact",
  "request_ref": "request-001",
  "ai_output_ref": "ai-output-001",
  "execution_intent_id": "intent-001",
  "action_class": "wire_transfer",
  "policy_snapshot_id": "policy-001",
  "authority_evidence_id": "aev-001",
  "bind_context_hash": "canonical bind context hash",
  "verification_proof_hash": "canonical sha256 of proof metadata and context binding provenance"
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
  "verifier_trust_level": "production",
  "verifier_id": "veritas-human-approval-verifier-v1",
  "verifier_key_id": "optional-key-id",
  "verifier_policy_id": "human-approval-verifier-policy-v1",
  "verifier_policy_hash": "canonical sha256 of verifier policy snapshot",
  "signed_at": "2026-05-01T00:00:00+00:00",
  "verified_at": "2026-05-01T00:00:01+00:00",
  "receipt_hash_verified": true,
  "signature_verified_by_runtime": true
}
```

These fields are verifier-derived only when set through signed-artifact verification. Caller-supplied copies are stripped from raw signed payload metadata before verification and are not treated as cryptographic proof on their own. If an artifact or envelope also contains signer metadata such as `key_id`, `signer_key_id`, `algorithm`, `signer_algorithm`, `signer_identity`, or `signer_role`, VERITAS treats those values as cross-checks only: missing artifact metadata is allowed, matching metadata may pass, but contradictory metadata fails closed and no `VerifiedHumanApprovalReceipt` is emitted. Artifact/envelope self-claims cannot authorize a signer or override verifier-derived key, algorithm, identity, or role. Current secure-only direct-receipt provenance still uses an in-process verification registry as a transitional compatibility control; it rejects simple forged metadata in one runtime process, but it should not be treated as cross-process cryptographic sealing. Prod rejects this direct receipt path entirely. Cross-process and prod callers should pass `VerifiedHumanApprovalReceipt` or the original signed artifact plus verifier. Production security still depends on real key management, KMS/HSM or equivalent verifier implementation, key rotation, and operational controls outside this local/offline helper.


A production verifier allowlist follows the same explicit policy-object style as signer policy configuration. A minimal equivalent shape is:

```yaml
approved_human_approval_verifiers:
  - verifier_id: veritas-human-approval-verifier-v1
    trust_level: production
    verifier_key_id: optional-key-id
    policy_id: human-approval-verifier-policy-v1
    policy_hash: canonical-sha256-of-policy-snapshot
```

Reviewers and auditors can now answer which verifier produced the proof by inspecting `verifier_id` and can determine whether that verifier was authorized by comparing it to the configured `HumanApprovalVerifierPolicy`.

## Verifier contract

VERITAS defines an explicit `HumanApprovalSignatureVerifier` interface:

```python
class HumanApprovalSignatureVerifier(Protocol):
    def verify(
        self,
        artifact: dict[str, Any],
    ) -> HumanApprovalSignatureVerificationResult: ...
```

Production deployments must bind this contract to deployment-controlled cryptographic infrastructure, such as KMS, HSM, or trusted public-key verification. The verifier must return verifier-derived `verified`, `key_id`, `algorithm`, `signer_identity`, `signer_role`, `reason`, verifier identity fields, and in prod `verifier_trust_level="production"` metadata (or expose a production verifier marker on the implementation). `RuntimeAuthorityValidator` remains implementation agnostic: it can use `human_approval_signature_verifier` or the older `verify_human_approval_signature_fn`, but `secure`/`prod` should prefer the interface and still rejects bare boolean results. Secure may retain missing `verifier_trust_level` migration compatibility; prod must not.

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
