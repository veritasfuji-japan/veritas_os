# Canonical ExecutionIntent Pre-Bind Validation v1

## Purpose and boundary

Canonical ExecutionIntent Pre-Bind Validation v1 is a deterministic, local,
side-effect-free library boundary between a verified Canonical ExecutionIntent
Formation Packet and any future Bind boundary. It makes one narrow claim:
**this exact ExecutionIntent, from this exact independently verified Formation
Packet, satisfies deterministic local structural and lineage checks**.

An ExecutionIntent being formed is not execution authorization. Pre-bind
validation is neither Bind authorization nor Bind invocation. Verifying the
ExecutionIntent hash is not a TrustLog write. Replay `semantic_match` is not
Authority Evidence or Human Approval. A verified pre-bind packet is not an
external effect, operation commit, live-state check, or runtime-risk acceptance.

The validator reconstructs the existing ExecutionIntent without assigning a
new ID, recomputes its existing canonical hash, and requires exact equality of
the source mapping, field-mapping proof, required-field presence, source and
candidate identities, evidence lineage, and replay summary. It performs no
policy, authority, approval, expected-state, or live-state lookup and fabricates
none of those facts.

## Auditable sequence

1. Canonical Decision Artifact (CDA)
2. Trust Link
3. Replay Source and Replay Evidence
4. Replay Handoff Binding
5. `CanonicalDecisionHandoff` validation
6. Canonical Guarded Promotion Eligibility Packet v1
7. Canonical ExecutionIntent Formation Readiness Packet v1
8. Canonical ExecutionIntent Formation Packet v1
9. Canonical ExecutionIntent Pre-Bind Validation Packet v1
10. **STOP**

Bind preflight, Bind adjudication, TrustLog write, `BindReceipt` creation,
adapter invocation, and API/CLI auto-wiring are intentionally deferred to
future explicit PRs.

## Deterministic integrity

The packet format is
`canonical-execution-intent-pre-bind-validation/v1`. Its content-addressed ID
is `eipbv:v1:sha256:<64 lowercase hexadecimal characters>`. The packet-hash
preimage excludes only `pre_bind_validation_id` and
`pre_bind_validation_hash`, under the
`veritas.execution-intent-pre-bind-validation.packet/v1` domain. Local checks
use the separate
`veritas.execution-intent-pre-bind-validation.local-checks/v1` domain.

The complete verified Formation Packet is embedded, not replaced by its compact
summary. Both builder and verifier run the Formation Packet verifier. The
verifier then reconstructs the ExecutionIntent, requires its `to_dict()` to be
exact, and recomputes `hash_execution_intent` without changing existing
ExecutionIntent hash semantics.

## Replay semantics and non-claims

Both `semantic_match: true` and `semantic_match: false`, including the exact
`fields_changed`, are preserved. Semantic agreement or divergence is not
converted into authorization, approval, authority, refusal, Bind permission,
or execution permission. Any operation-specific replay-equivalence gate needs
a separately reviewed future boundary.

This artifact makes no production, customer, regulatory, or certification
claim. Human approval remains required for future Bind/admissibility,
TrustLog, and public-claim changes.
