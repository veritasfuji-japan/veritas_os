# ExecutionIntent Formation Readiness v1

## Purpose and safety boundary

The Canonical ExecutionIntent Formation Readiness Packet verifies that one
exact, content-addressed Guarded Promotion Eligibility Packet contains the
minimum deterministic source values needed by a **future** explicit
ExecutionIntent formation step. The builder verifies the embedded eligibility
packet; the readiness verifier independently verifies it again and recomputes
the complete mapping.

This artifact is deliberately narrower than promotion or execution:

- an Eligibility Packet is **not** an `ExecutionIntent`;
- formation readiness is **not** execution authorization;
- formation readiness is **not** Bind authorization;
- `semantic_match` is **not** Authority Evidence or Human Approval; and
- verified readiness is **not** an adapter call or external effect.

The packet maps only values already present in the verified eligibility
artifact. It does not infer or create actor identity, target, action, policy,
approval, authority, or expected state. `execution_intent_id` and `ttl_seconds`
are explicitly deferred. No `ExecutionIntent`, ExecutionIntent hash,
ExecutionIntent TrustLog entry, or `BindReceipt` is created, and Bind is never
invoked.

## Auditable sequence

1. Canonical Decision Artifact (CDA)
2. Trust Link
3. Replay Source and Replay Evidence
4. Replay Handoff Binding
5. `CanonicalDecisionHandoff` validation
6. Canonical Guarded Promotion Eligibility Packet v1
7. Canonical ExecutionIntent Formation Readiness Packet v1
8. **STOP**

Actual ExecutionIntent formation is intentionally deferred to a future,
explicitly reviewed PR. This module is a local library boundary and is not
automatically wired into API routes or pipeline stages.

## Integrity and semantic divergence

The format version is
`canonical-execution-intent-formation-readiness/v1`. Its identifier is
`eifr:v1:sha256:<64 lowercase hexadecimal characters>`. The packet hash
excludes only `readiness_id` and `readiness_hash`.

Separate domain strings protect the mapping, required-field contract, and
packet. The full Eligibility Packet is embedded as exact JSON, while compact
reviewer-facing identity and lineage summaries must exactly match it.

A verified Eligibility Packet may preserve `semantic_match: false` and its
exact `fields_changed`. Formation readiness does not hide or reverse that
divergence and does not turn semantic agreement or divergence into authority,
approval, execution permission, or a refusal policy. Any future
operation-specific replay-equivalence gate requires a separate change.
