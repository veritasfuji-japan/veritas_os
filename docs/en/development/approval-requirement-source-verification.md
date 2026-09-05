# Approval requirement source verification

`verify_human_approval_requirement_resolution_packet(packet, source, contract)`
requires the full Authority Evidence Linkage source and the expected Action
Class Contract. The one-argument, hash-only interface is no longer supported.
The verifier revalidates the source and reconstructs every field from it and
the contract. Rehashing a forged NOT_REQUIRED result cannot bypass this check.
Both the builder and verifier of requirement satisfaction use this interface.

The caller must obtain the expected contract from trusted policy configuration;
an attacker-controlled replacement contract is not a trust anchor.
The satisfaction verifier requires keyword-only `expected_source` and
`expected_contract`, compares the complete embedded source and contract to
these independently verified inputs, and derives results only from the
reconstructed resolution. Same-ID/version contract substitutions are rejected.
Final Bind Readiness and Bind Gate Review builders and verifiers propagate
these same keywords through every self-verification call. They are optional
only for the legacy v1 linkage path; a v0.3 satisfaction path fails closed when
either is absent. No embedded snapshot fallback is permitted. Further callers
that omit these inputs cannot consume a v0.3 gate; they must explicitly pass
trusted inputs before enabling that path. Never extract expected inputs from
the packet under verification.
Resolution time is a recorded timestamp, not a live freshness attestation.

## Non-effecting fresh composition

`build_fresh_bind_source_chain(..., expected_contract=trusted_contract)` selects
v0.3 requirement satisfaction. Supply the contract from trusted configuration
outside `FreshBindSourceChainInputs`; do not select it from a candidate gate.
The authority source is freshly constructed from the checked prerequisite chain.
REQUIRED needs caller-supplied human reference metadata; NOT_REQUIRED may use
`human_approval_reference_bundle=None`. No receipt is inferred. Omitting the
contract retains legacy v1 composition.

Pass `result.authority_linkage_packet` and that same trusted contract as
`expected_source` and `expected_contract` to
`derive_verified_real_bind_context_hash(result.verified_gate_review_packet, ...)`.
The helper reverifies the whole gate before deriving its context digest.
Missing anchors or same-ID/version policy substitution fail closed for v0.3.
This connects only the non-effecting path: existing approval/authorization
issuers have not been enabled for v0.3 and still reject gates without anchors.
No trusted policy registry, credential access, or execution capability is added.

Integration tests exercise the real nested metadata-linkage chain without
mocking its verifier. They do not claim cryptographic authority authentication.
Authority signature/revocation verification and human approval verification
remain separate boundaries. No execution or approval authority is created.
