# Canonical Decision Trust Link v1

The dedicated `canonical_decision_link` event means only that an exact,
internally verified CDA identity survived post-decision persistence without
canonical-source drift. It is appended after the drift guard and contains a
compact reference—not the complete CDA or its rationale, evidence, query,
chosen value, user data, or policy text.

## Evidence layers

Verification deliberately keeps separate domains:

1. CDA verification proves the artifact's internal structure, `decision_hash`,
   and content-addressed `decision_id` coherence.
2. The canonical reference exactly copies CDA version, profile, request ID,
   decision ID, decision hash, and decision timestamp.
3. The encrypted full-ledger row commits to that reference with its own
   `sha256` and `sha256_prev` chain domain.
4. The existing compact signed witness commits to the exact full row through
   `full_payload_hash` and an `artifact_ref` locator of
   `sha256:<full-ledger-sha256>`.
5. Existing witness signature and chain verification are separate checks.
6. WORM or transparency evidence, when configured, is another independent
   layer.

The response receipt is only a locator confirming successful local append and
exact validation of the returned full-ledger entry. By itself it does not prove
the full ledger or witness chain is intact, the signature key or CDA producer
is trusted, or WORM/transparency storage is valid. It grants no handoff
readiness, execution intent, Bind permission, external effect, or regulatory
certification.

## Replay boundary

Replay linkage remains future work. The replay snapshot is generated late in
Stage 8 while decision disk persistence occurs earlier, and each replay run
forms a distinct live CDA timestamp and identity. A future contract must
separate original decision identity, replay source reference, replay execution
identity, and semantic replay equivalence.
