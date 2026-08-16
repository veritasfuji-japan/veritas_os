# Canonical Guarded Promotion Eligibility Packet v1

## Purpose and boundary

The packet freezes one exact `CanonicalDecisionHandoff`, its independently
trusted validation context, the caller-supplied evaluation time, and the exact
`READY_FOR_GUARDED_PROMOTION` validator result into a content-addressed local
artifact. Verification reconstructs the context, reruns the handoff validator,
and checks every digest and reviewer-facing summary.

This is a pre-execution integrity artifact, not a new authority source:

- `READY_FOR_GUARDED_PROMOTION` **is not** an `ExecutionIntent`.
- A verified packet **is not** execution authorization or permission to Bind.
- `semantic_match` **is not** Authority Evidence.
- Replay evidence **is not** Human Approval.
- Packet verification **is not** a Bind receipt or an external effect.

Semantic divergence is reported exactly. A false `semantic_match` and nonempty
`fields_changed` remain valid packet content when the independent handoff
validator returns READY; packet integrity does not imply semantic agreement.

## Sequence

1. Canonical Decision Artifact (CDA)
2. Trust Link
3. Replay Source and Replay Evidence
4. Replay Handoff Binding
5. `CanonicalDecisionHandoff` validation
6. Canonical Guarded Promotion Eligibility Packet v1
7. **STOP**

ExecutionIntent formation is intentionally deferred. The builder and verifier
perform no API auto-wiring, filesystem or network access, provider calls,
adapter calls, subprocesses, Bind invocation, or external effects.

## Content addressing

The format is `canonical-guarded-promotion-eligibility-packet/v1`; identifiers
are `gpe:v1:sha256:<64 lowercase hexadecimal characters>`. Separate domains bind
the source handoff, trusted context, validation result, and packet. The packet
hash excludes only its own `eligibility_id` and `eligibility_hash` fields.
