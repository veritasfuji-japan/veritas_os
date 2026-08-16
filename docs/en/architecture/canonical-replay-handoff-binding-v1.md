# Canonical Replay Handoff Binding v1

## Boundary

This local, deterministic adapter converts a verified Canonical Replay
Source/Evidence v1 pair into an exact `replay_lineage` value and a
`TrustedValueAssertion`. It calls `verify_canonical_replay_evidence` first. It
performs no I/O and does not form a candidate, promote a handoff, create an
`ExecutionIntent`, invoke Bind, or authorize an external effect.

The identities remain separate. Handoff `source_decision` is the original CDA;
`replay_lineage.request_id` is the original request ID required by the Handoff
lineage invariant, while `replay_request_id` is the distinct replay request.
Likewise, `original_decision_id` identifies the original CDA and
`replay_decision_id` identifies the distinct replay CDA. Both pairs must differ.

## Exact evidence representation

`replay_lineage.verified=true` means only that Replay Evidence and Replay Source
linkage passed the v1 integrity verifier. It does not mean `semantic_match` is
true. Authentic divergence remains visible as `semantic_match=false` with its
exact changed fields, severity, and divergence level.

The assertion binds exact lineage JSON using the Handoff assertion-value digest.
Its artifact reference/hash are Replay Evidence `evidence_id`/`evidence_hash`,
and its mechanism is `verify_canonical_replay_evidence/v1`. Replay Source,
Replay Evidence, original/replay CDA, TrustLog, candidate, and assertion-value
hashes remain separate cryptographic domains.

## Security non-claims

Original CDA is not Replay CDA. Evidence verification is not semantic match.
Semantic match is not Authority Evidence or Human Approval. Replay lineage is
not TrustLog lineage, and a replay CDA Trust receipt is not source-decision
TrustLog proof. `READY_FOR_GUARDED_PROMOTION` is neither an `ExecutionIntent`
nor Bind authorization or execution authority.

Replay evidence never fabricates actor, target, action, authority, approval,
policy lineage, or expected state. An untrusted lineage declaring
`verified=true` cannot become ready without its independent exact-value
assertion.
