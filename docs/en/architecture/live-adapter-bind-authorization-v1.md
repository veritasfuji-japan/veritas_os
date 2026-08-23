# Canonical Live Adapter Bind Authorization v1

## Boundary

This contract defines VERITAS's first **real Bind Authorization artifact**. It
sits after the verified Bind Authorization Gate Review and before any future
authorization-consumption or Bind-invocation boundary.

```text
Final Bind Authorization Readiness
        ↓
Bind Authorization Gate Review
        ↓
REAL Bind Authorization Artifact (this boundary)
        ↓
future Authorization Consumption / Bind Invocation Gate
        ↓
Bind execution
        ↓
BindReceipt
        ↓
TrustLog
```

Issuing this artifact creates governance permission for one exact future Bind
attempt. It does **not** create an execution capability and does not consume the
authorization.

## What must be verified before issuance

The builder independently re-verifies the complete Gate Review packet, then
requires first-class authenticated governance inputs rather than promoting the
dry-run chain's declared linkage metadata into authority.

For AuthorityEvidence, the builder receives the original signed artifact and
re-runs `verify_authority_evidence_artifact_to_proof(...)` against the exact
Action Class Contract, actor, requested scope, policy snapshot, deployment-owned
signer/verifier policy, and revocation policy. The resulting process-local proof
is validated again before issuance. A serialized `VerifiedAuthorityEvidence`
object is not accepted as portable trust.

When the Action Class Contract requires human approval, the original signed
`HumanApprovalReceipt` artifact must also be supplied. The builder verifies its
signature through a production-trust verifier policy and checks exact binding to
the request, decision, execution intent, action class, policy snapshot,
AuthorityEvidence, and Bind context. When the contract does not require human
approval, the requirement is recorded as `NOT_REQUIRED`; a caller-provided
approval cannot silently change that contract decision.

The exact verified inputs are then evaluated by `RuntimeAuthorityValidator`.
Issuance is possible only when the result is `status=pass` and
`recommended_outcome=commit`. Action contracts that require arbitrary evidence
not represented by a first-class proof at this boundary fail closed with
`LABA_REQUIRED_EVIDENCE_PROOF_UNAVAILABLE`.

## Explicit human GO and signer separation

Gate Review is not Bind Authorization. A separate
`SignedBindAuthorizationDecisionArtifact` is required for the explicit human
`GO_AUTHORIZED` decision. It is bound to the exact Gate Review hash,
ExecutionIntent identity/hash, adapter contract identity/hash, endpoint binding,
credential reference/scope binding, policy snapshot, and validity window.

The Bind authorizer is authenticated through a deployment-controlled verifier
and signer policy. The Gate Reviewer and Bind Authorizer must be different
identities. The verifier policy identity is bound to the trusted public-key
bytes, so reusing the same key ID with different key material does not preserve
trust.

After the authorization body is assembled, a separate authorization issuer signs
the complete content-addressed artifact. Verification re-runs the source,
governance, authorizer, grants, requirement proofs, content address, and final
issuer-signature checks.

## Credential and Authorization-header permissions

The artifact contains two narrow future grants:

- `CredentialResolutionGrant`
- `AuthorizationHeaderConstructionGrant`

They bind permission to the exact credential reference, credential scope,
ExecutionIntent, adapter contract, endpoint binding, policy snapshot, Gate
Review, and Bind context. Both state `consumption_required=true`.

These grants are **permission to cross those boundaries later**. Artifact
creation does not resolve a credential, access secret material, embed a token,
or construct an Authorization header.

## Validity, idempotency, and replay

`authorized_at`, `valid_from`, and `valid_until` are timezone-aware. The window
must contain the authorization instant, must not precede Gate Review, and cannot
outlive the ExecutionIntent TTL, AuthorityEvidence validity, or verified human
approval expiry when those limits apply.

The artifact is content-addressed, single-use, requires authorization
consumption, binds a deterministic idempotency key, requires replay protection,
and prohibits duplicate dispatch. This version does not implement the atomic
consumption registry or invocation gate; the issued state remains
`NOT_CONSUMED`.

## Non-effects and invariants

At this boundary all effect-bearing state remains false:

- no credential material access or embedding;
- no Authorization-header construction;
- no endpoint or DNS resolution;
- no network or Webhook call;
- no live adapter creation or method call;
- no request dispatch;
- no Bind invocation;
- no operation commit;
- no BindReceipt creation;
- no TrustLog write.

The mandatory separations remain:

- **AI Intelligence ≠ Execution Authority**
- **Gate Review ≠ Bind Authorization**
- **Bind Authorization ≠ Authorization Consumption**
- **Bind Authorization ≠ Bind Invocation**
- **Bind Invocation ≠ Successful External Effect**
- **BindReceipt ≠ Authorization**
- `semantic_match ≠ Human Approval ≠ Authority Evidence ≠ Bind Authorization ≠ Execution Authority`

This artifact establishes authenticated governance permission for one exact
future attempt. It does not claim production certification, customer deployment,
regulatory approval, or successful external execution.
