# External UTC Clock Evidence Boundary v1

## Status

Design-fixed, non-executing trust boundary.

This document defines the first production-hardening step for VERITAS external
UTC clock trust. It does not claim that VERITAS already has an independently
trusted production clock.

## Problem

The controlled Decision-to-Effect proof currently accepts clock callbacks as
trusted deployment inputs. That is sufficient for the frozen sandbox proof, but
it does not establish the separate future claim of **external UTC clock trust**.

A production-grade system must be able to answer:

- Which external clock source was trusted?
- Which verifier authenticated the provider artifact?
- Which trust policy approved that provider/verifier pair?
- Was the returned time bound to a fresh request rather than a replayed sample?
- What uncertainty bound did the provider assert?
- How much monotonic round-trip time elapsed?
- Can the proof be replayed and audited without turning serialized output into
  portable runtime trust?

## Boundary

The target flow is:

```text
caller-created freshness challenge
        ↓
external time provider artifact
        ↓
provider-specific authentication / normalization
        ↓
VERITAS-controlled provider + verifier allowlist
        ↓
challenge binding + uncertainty + monotonic RTT checks
        ↓
runtime-sealed VerifiedExternalClockEvidence
```

The result is **time evidence only**.

```text
VerifiedExternalClockEvidence
!= AuthorityEvidence
!= HumanApproval
!= BindAuthorization
!= execution permission
!= runtime clock replacement
```

## Freshness model

The v1 boundary must not use the local wall clock to prove freshness of the
external UTC evidence. That would make the proof circular.

Instead, freshness is challenge-bound:

1. The caller creates a high-entropy nonce and challenge identifier.
2. The challenge is registered in the current process with a monotonic start
   value.
3. The provider-specific verifier authenticates a native artifact that binds
   the challenge.
4. The normalized evidence carries the challenge identifier and nonce hash.
5. VERITAS compares those values with the registered challenge.
6. VERITAS checks monotonic elapsed time against a configured maximum RTT.
7. A successfully used challenge becomes single-use for this boundary.

Monotonic timing proves bounded local elapsed time only. It does not itself
prove UTC correctness.

## Normalized evidence contract

The first implementation should normalize at least:

- `evidence_id`
- `provider_id`
- `artifact_id`
- `artifact_type`
- `artifact_version`
- `payload_hash`
- `challenge_id`
- `challenge_nonce_hash`
- `utc_time`
- `uncertainty_ms`
- `source_clock_id`
- `provenance`
- `metadata`

`utc_time` must be timezone-aware and represent UTC. `uncertainty_ms` must be a
non-negative integer.

## Independent trust policy

The provider artifact must never define its own trust status.

VERITAS deployment policy must independently bind:

- provider identifier
- verifier identifier
- verifier trust level
- verifier policy identifier
- verifier policy hash
- maximum accepted uncertainty
- maximum accepted monotonic round-trip time

Changing any of these values changes the deterministic trust-policy identity.

## Provider-specific verifier seam

A provider adapter is responsible for native authentication and normalization.
The generic boundary should receive a result containing:

- verification success/failure
- normalized clock evidence
- verifier identity
- verifier trust level
- verifier policy identity/hash
- signing key identity / algorithm metadata where applicable
- semantic consistency result
- sanitized reason

The generic boundary must fail closed if the provider verification result is
unapproved, incomplete, inconsistent, or exceeds the independent policy.

## Runtime seal

A successful verification produces an in-memory sealed proof containing:

- normalized evidence + deterministic evidence hash
- verifier binding
- trust-policy identity/hash
- challenge identity/hash
- measured monotonic round-trip duration
- verification source/reason
- deterministic proof hash

Serialized JSON is audit output only. It must not be deserialized later and
silently treated as trusted runtime state.

## Required fail-closed cases

Focused tests must cover at least:

- provider verification failure
- semantic inconsistency
- unapproved provider/verifier
- verifier-policy binding mismatch
- missing signature identity metadata where required
- malformed payload hash
- missing/invalid challenge
- challenge identifier mismatch
- challenge nonce mismatch
- challenge replay
- non-UTC or timezone-naive time
- invalid or excessive uncertainty
- negative or excessive monotonic RTT
- trust-policy change after proof creation
- caller-mutated/forged verified proof

## Relationship to the frozen Decision-to-Effect architecture

This boundary is deliberately separate from the frozen controlled execution
proof.

This v1 work must not:

- change authorization issuance or consumption semantics
- change current governance rechecks
- change credential resolution
- change Bind dispatch
- change `EFFECT_UNKNOWN`
- change reconciliation
- change BindReceipt / Outcome semantics
- replace existing trusted clock callbacks
- add a new external-effect path

A later PR may propose composition with the frozen execution path only after the
standalone clock evidence boundary has deterministic tests and a source-bound
proof artifact.

## Non-claims

This specification does not establish:

- production external UTC clock trust
- live provider interoperability
- independent infrastructure ownership
- customer deployment
- regulatory or certification status
- exactly-once TrustLog publication

## Exit gate for implementation PR

The implementation PR is ready to merge when:

1. the provider-neutral boundary exists as a standalone module;
2. focused fail-closed tests pass;
3. no frozen execution semantics change;
4. no network dispatch is introduced;
5. no runtime clock is replaced;
6. the proof object remains evidence-only; and
7. repository CI is green.
