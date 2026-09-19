# VERITAS / CAGE Phase 5D — ESCALATE / Human Review Runtime Proof

Status: **implementation candidate — merge requires green Phase 5D and inherited safety workflows**

## Purpose

Phase 5D proves the bounded runtime behavior of the Provider03 `ESCALATE` path
after the TASK-017 security gate was closed.

The proof is intentionally about **non-amplification of authority**.

A CAGE human-review quorum may resolve a CAGE queue state. It does not become
VERITAS AuthorityEvidence, a VERITAS Human Approval Receipt, a BindAuthorization,
or execution permission.

## Source pins

VERITAS baseline before Phase 5D:

`3ec803df325f0b16b0b3e3d47ba3b60f125f5c6e`

CAGE source pin:

`50b12e7d983db0e3d7faf206ac6aa600294f33ac`

The CAGE pin is the current reviewed main commit at Phase 5D implementation
start. It contains the current Provider03 ESCALATE mapping, Redis-backed
DeferQueue quorum implementation, and adaptive FRIA boundary.

## Runtime topology

~~~text
VERITAS stale-sanctions fixture
        ↓ loopback HTTP
real CAGE Provider03
        ↓ admitted=false + needs_human_review
real CAGE enforce_fria_boundary
        ↓ SYNC_GATE_REVIEW
real Redis-backed CAGE DeferQueue
        ↓ EXTERNAL_HOLD / quorum=3
three distinct synthetic operator approval records
        ↓ CAGE queue state RESOLVED
fresh Provider03 call against unchanged VERITAS stale evidence
        ↓
ESCALATE again / admitted=false / no BindReceipt
~~~

Redis is a real service in the CI job. The CAGE HTTP client is not mocked.

The operator approval records are synthetic CI records. This proof does not
claim live human identity verification or production WebAuthn/OIDC deployment.

## Required properties

The proof fails unless all of these remain true:

1. Provider03 maps VERITAS `ESCALATE` to `admitted=false`.
2. The result carries the explicit `needs_human_review` marker.
3. CAGE routes that result to `DEFER / SYNC_GATE_REVIEW`.
4. A real `EXTERNAL_HOLD` token is persisted in the Redis-backed DeferQueue.
5. The current CAGE `EXTERNAL_HOLD` contract requires three distinct approvers.
6. A duplicate approver cannot advance quorum.
7. Three distinct approval records resolve the CAGE queue state.
8. CAGE quorum does not create VERITAS admission.
9. Re-evaluating the unchanged stale VERITAS evidence still returns ESCALATE.
10. ESCALATE and post-quorum stale recheck expose no BindReceipt.
11. Missing VERITAS authority remains denied.
12. Missing VERITAS human approval remains denied.

Expected successful result:

`READY_FOR_PHASE5E`

## Important semantic boundary

Phase 5D does **not** feed CAGE approval records into VERITAS as authority or
human-approval evidence.

This is deliberate.

~~~text
CAGE queue resolution
!= VERITAS AuthorityEvidence
!= VERITAS Human Approval Receipt
!= BindAuthorization
!= execution permission
~~~

The underlying stale sanctions evidence must be independently refreshed through
a VERITAS-governed path before VERITAS can return a different decision.

## Explicit non-claims

This proof does not establish:

- an external business effect;
- production deployment;
- live customer infrastructure;
- live human identity verification;
- production OIDC or WebAuthn assurance;
- Google endorsement;
- commercial integration;
- regulatory approval or certification;
- TrustLog witness semantics;
- permission for CAGE to create VERITAS execution authority.

Phase 5D is a source-pinned interoperability proof only.
