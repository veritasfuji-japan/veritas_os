# Canonical ExecutionIntent Formation v1

## Purpose and boundary

Canonical ExecutionIntent Formation v1 is a deterministic, local library
boundary between a verified ExecutionIntent Formation Readiness Packet and a
new `ExecutionIntent`. It records one narrow claim: **this exact verified
Readiness Packet was used to deterministically form this exact ExecutionIntent
artifact**.

A Readiness Packet is not an `ExecutionIntent`. Conversely, an ExecutionIntent
being formed is not execution authorization and is not Bind authorization. A
valid ExecutionIntent hash is not a TrustLog write. `semantic_match` is not
Authority Evidence or Human Approval. A verified ExecutionIntent is not an
adapter invocation, operation commit, or external effect.

The builder takes every actor, target, action, policy, expected-state,
approval-context, and evidence-reference value solely from the mapping in the
verified Readiness Packet. It performs no lookup and creates no authority or
approval evidence. Missing or incoherent source data fails closed in readiness
verification rather than being inferred or fabricated.

## Auditable sequence

1. Canonical Decision Artifact (CDA)
2. Trust Link
3. Replay Source and Replay Evidence
4. Replay Handoff Binding
5. `CanonicalDecisionHandoff` validation
6. Canonical Guarded Promotion Eligibility Packet v1
7. Canonical ExecutionIntent Formation Readiness Packet v1
8. Canonical ExecutionIntent Formation Packet v1
9. **STOP**

Bind preflight, TrustLog lineage/write, Bind invocation, adapter activity, and
any API or CLI wiring are intentionally deferred to future explicit PRs. The
formation module creates no `BindReceipt` and has no filesystem, network,
provider, subprocess, adapter, or external-system capability.

## Deterministic integrity

The packet format is `canonical-execution-intent-formation/v1`. Its identifier
is `eif:v1:sha256:<64 lowercase hexadecimal characters>`; its packet hash
preimage excludes only `formation_id` and `formation_hash`. The full Readiness
Packet is embedded so the verifier can rerun readiness verification rather
than trusting a compact summary.

The ExecutionIntent identifier is
`ei:v1:sha256:<64 lowercase hexadecimal characters>`. It is derived before
instantiation from the readiness identity/hash, mapping digest, complete
source mapping, and ExecutionIntent contract version. No random/default ID
factory or current clock is used. The existing `hash_execution_intent`
contract remains the sole source of `execution_intent_hash` semantics.

The independent verifier reconstructs the ExecutionIntent, verifies every
field against the source mapping and field-mapping proof, recomputes both
content-addressed identities, and requires exact preservation of source
decision identity, candidate identity, evidence lineage, required-field
presence, and replay summary.

## Replay semantics and non-claims

Both `semantic_match: true` and `semantic_match: false` remain source facts.
The formation step preserves `fields_changed` and does not transform semantic
agreement or divergence into a refusal, authority, approval, Bind permission,
or execution permission. Any operation-specific replay-equivalence policy must
be introduced at a separately reviewed boundary.

This artifact makes no production, customer, regulatory, or certification
claim. Human review remains required for future Bind/admissibility and
TrustLog behavior changes.
