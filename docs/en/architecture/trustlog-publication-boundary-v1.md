# TrustLog Publication Boundary v1

## Status

Design-fixed, non-executing architecture boundary.

This document defines a separate proof track for TrustLog publication semantics. It does not modify the frozen controlled Decision-to-Effect claim and does not claim production exactly-once delivery.

## Purpose

The current TrustLog path preserves deterministic evidence lineage, ordering, encryption/signing posture, mirror/anchor configuration, and fail-closed behavior, but `trustlog_exactly_once_publication` remains an explicit non-claim of the controlled execution proof.

This boundary separates three different properties that must not be conflated:

1. one logical TrustLog entry is accepted at most once into the primary durable ledger;
2. the same logical publication may be retried toward mirrors or transparency anchors without changing its identity or payload;
3. an external mirror/anchor actually accepted the publication exactly once.

Only the first property is in scope for a future v1 implementation proof. The third property requires an independently verifiable destination contract and is not implied by this boundary.

## Core invariant

```text
logical TrustLog uniqueness
!= cross-system atomicity
!= exactly-once external delivery
!= execution authority
```

A TrustLog publication record is retrospective evidence only. It must never create AuthorityEvidence, Human Approval, BindAuthorization, execution permission, or external-effect confirmation.

## Logical publication identity

Every publishable TrustLog object must be bound to a deterministic publication identity derived from immutable inputs:

- `entry_type`;
- stable logical `entry_id`;
- canonical payload hash;
- publication schema/version.

The resulting `publication_key` is deterministic and content-bound.

Two attempts with the same `publication_key` and the same canonical payload are the same logical publication.

Two attempts that reuse the same logical identity with a different canonical payload are a collision and must fail closed. They must never be treated as an update, replacement, or successful duplicate.

## Primary durable-ledger semantics

A future v1 implementation may claim `primary_logical_exactly_once` only when PostgreSQL enforces a uniqueness constraint for the deterministic publication identity and the implementation proves all of the following:

- first insert commits one logical entry;
- duplicate same-key/same-payload publication returns the already committed logical entry rather than creating a second row;
- same-key/different-payload publication fails closed;
- process retry after an ambiguous client response cannot create a second logical row;
- crash recovery resolves from durable database state rather than from in-memory success flags;
- the returned receipt identifies whether the caller created the row or observed an already committed equivalent publication.

This guarantee is about the primary durable ledger only.

## Secondary publication semantics

Mirror and transparency-anchor publication are separate destination-specific state machines.

A durable secondary publication state must preserve at minimum:

- `publication_key`;
- destination class and destination identifier;
- canonical payload hash;
- attempt count;
- last attempt result;
- destination acknowledgement/receipt when available;
- terminal/non-terminal state.

Permitted states are conceptually:

```text
PENDING
ATTEMPTED_UNKNOWN
ACKNOWLEDGED
FAILED_TERMINAL
```

Retries may only resend the exact same publication identity and exact same canonical payload. A retry must never mint a new logical TrustLog entry merely because the external destination response was lost.

`ATTEMPTED_UNKNOWN` is not equivalent to failure and is not proof that the destination did not accept the publication.

## Destination guarantees

VERITAS must not claim exactly-once publication to a mirror or transparency anchor unless the destination contract provides independently verifiable idempotency/deduplication semantics tied to the same publication identity.

Without that destination contract, the strongest valid statement is:

```text
primary logical uniqueness is proven;
secondary delivery is retry-safe for the same immutable publication identity;
external exactly-once acceptance is not proven.
```

## Crash and retry rules

- A committed primary logical entry is never re-created under a new publication identity during retry.
- A lost caller response after primary commit is resolved by lookup using the deterministic publication identity.
- An ambiguous secondary delivery result enters `ATTEMPTED_UNKNOWN` or equivalent durable state.
- Secondary recovery may retry only the identical publication identity/payload when the destination contract permits idempotent retry.
- Recovery must never rewrite the canonical TrustLog payload to force a retry to succeed.
- TrustLog publication failures must not retroactively change the governed action's authorization, effect, receipt, or reconciliation state.

## Relationship to the frozen execution proof

This is a separate evidence-publication proof track.

It must not change:

- authorization issuance or consumption;
- pre-effect current rechecks;
- credential resolution;
- external-effect dispatch;
- `EFFECT_UNKNOWN` semantics;
- reconciliation;
- BindReceipt / Outcome semantics;
- confirmed-effect semantics;
- the frozen Decision-to-Effect architecture.

A future implementation must produce its own deterministic proof before any TrustLog exactly-once language is added to the frozen controlled-execution claim.

## Minimum future machine contract

A future implementation should expose concepts equivalent to:

- `TrustLogPublicationIdentity`;
- `TrustLogPrimaryPublicationResult`;
- `TrustLogSecondaryPublicationState`;
- `TrustLogPublicationReceipt`.

The implementation must preserve deterministic hashes and must never store plaintext secrets or credentials in publication metadata.

## Proof exit criteria

A future `primary_logical_exactly_once` proof is not closed until all of the following are demonstrated against real PostgreSQL:

1. concurrent same-key/same-payload attempts produce one logical row;
2. same-key/different-payload collision fails closed;
3. response loss after commit followed by retry resolves to the original committed row;
4. process restart does not permit duplicate logical insertion;
5. publication receipts are deterministic and replay-reviewable;
6. mirror/anchor uncertainty cannot be misreported as confirmed failure or confirmed absence;
7. no execution-authority semantics are introduced.

## Explicit non-claims

This v1 design does not claim:

- production readiness;
- cross-system distributed transactions;
- exactly-once mirror delivery;
- exactly-once transparency-anchor delivery;
- independently operated external TrustLog infrastructure;
- external destination authenticity;
- regulatory approval or certification;
- that a TrustLog receipt proves a real-world effect occurred.
