# Canonical Live Adapter Bind Authorization v1

## Boundary

This document defines the first **real Bind authorization** contract, but the
current scaffold deliberately cannot issue one. The deterministic,
content-addressed model is intended to grant governance permission for one
exact future Bind attempt under the exact verified source context only after
the proof gap below is closed.

```text
Final Bind Authorization Readiness
        ↓
Bind Authorization Gate Review (#2130)
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

The builder independently verifies the complete
`CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket`. It accepts only a
passed, non-fail-closed review that explicitly accepts future real authorization
and records no dispatch, invocation, receipt, TrustLog, credential, network, or
adapter effect. It then binds the verified execution intent, request, adapter
contract, endpoint, credential scope, AuthorityEvidence and human-approval
linkage, final readiness, mappings, evidence lineage, replay summary, and every
upstream hash into the new artifact contract.

## Current fail-closed proof gap

The #2130 source chain embeds caller-declared `AuthorityEvidenceReferenceBundle`
and `HumanApprovalReferenceBundle` metadata. Its linkage reviews explicitly do
not retrieve or verify the referenced `AuthorityEvidence` or
`HumanApprovalReceipt`, and the source does not preserve enough first-class
inputs to rerun `RuntimeAuthorityValidator`. Hash-perfect linkage is not real
authority verification. Consequently the builder always stops with
`LABA_ARCHITECTURE_GAP_UNVERIFIED_REAL_GOVERNANCE_PROOF` after source
verification and creates no authorization artifact.

This fail-closed behavior is intentional. A follow-up must add the smallest
closed proof bundle containing verifiable real governance artifacts and all
deterministic validator inputs. Only then may the final builder path be enabled
and its round-trip authorization tests activated. Declared booleans or metadata
must never substitute for that proof.

Inspection also found no first-class proof that authorizes crossing the future
credential-resolution and Authorization-header construction boundaries. The
dry-run credential review proves non-access and metadata linkage, not permission
to cross either boundary. Those two #2130 requirements therefore remain gaps as
well; neither a review hash nor an authorizer acknowledgement may satisfy them.

`AuthorityEvidence` remains evidence of organizational/runtime authority. The
new authorization is a derived, explicit, context-bound permission for one
exact future Bind attempt. The gate reviewer is not implicitly the Bind
authorizer: a separate closed `BindAuthorizationDecision` with an explicit
`GO_AUTHORIZED` confirmation and boundary acknowledgements is required.

## Validity and consumption

The authorization has timezone-aware `authorized_at`, `valid_from`, and
`valid_until` values. Its window must be ordered, contain the authorization
instant, and cannot exceed the `ExecutionIntent` lifetime when `decision_ts` and
`ttl_seconds` provide one. Structural/content verification is deterministic and
does not consult the clock. The future invocation gate must call the separate
temporal validation boundary at its supplied invocation time.

The proposed artifact is single-use, binds a deterministic idempotency identity, requires
consumption and replay protection, prohibits duplicate dispatch, and remains
`NOT_CONSUMED`. This version does not provide a registry and never marks an
authorization consumed. Before the **Bind Authorization Consumption / Bind
Invocation Gate**, a focused proof-boundary PR must provide independently
re-verifiable AuthorityEvidence, conditional signed Human Approval,
RuntimeAuthorityValidator inputs/results, and credential/header-boundary
permission. Only after authorization issuance is safely enabled may the
consumption gate enforce atomic single use.

## Non-effects and invariants

Authorization artifact creation is governance permission; it does not create an
execution capability. Credential references and scope digests are bound without
resolving credential material or constructing an Authorization header. No Bind,
dispatch, endpoint resolution, DNS, network, Webhook, adapter call, filesystem,
database, provider, subprocess, operation commit, BindReceipt, or TrustLog write
occurs here.

The following separations remain mandatory:

- **AI Intelligence ≠ Execution Authority**
- **Gate Review ≠ Bind Authorization**
- **Bind Authorization ≠ Bind Invocation**
- **Bind Invocation ≠ Successful External Effect**
- **BindReceipt ≠ Authorization**
- `semantic_match ≠ Human Approval ≠ Authority Evidence ≠ Bind Authorization ≠ Execution Authority`

Semantic similarity, model output, confidence, recommendations, and AI-generated
approval text can never promote themselves into authorization. This contract
does not claim production certification, customer deployment, external effect,
or successful Bind execution.
