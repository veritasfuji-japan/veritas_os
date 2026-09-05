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
This composition itself remains non-effecting. The separate approval and
authorization issuers accept v0.3 with the independent inputs described below.
No trusted policy registry, credential access, or execution capability is added.

## Explicit v0.3 issuance inputs

`issue_gate_bound_human_approval_artifact` accepts `expected_source` separately
from the gate and uses its existing `action_contract` argument as trusted policy.
An explicit approval event, matching approval reference and deployment signer
remain mandatory. NOT_REQUIRED does not generate or infer a Human Approval Receipt.

For Bind authorization, set `RealBindAuthorizationGovernanceInputs.expected_source`
to the independently acquired authority linkage source and `action_contract` to
the trusted contract. The decision-to-authorization entry point, authorization
builder, verifier and governance context derivation propagate those same inputs.
Do not populate either from embedded snapshots in an untrusted gate or artifact.
Legacy v1 inputs remain compatible; missing anchors fail closed for v0.3.

These are prerequisites, not a replacement for signed authority verification,
revocation/freshness checks, required signed Human Approval, explicit authorizer
GO, approved issuer identity or signature checks. Local tests use ephemeral keys
and real Ed25519 verification. Issuance produces an unconsumed authorization;
it does not invoke Bind, resolve credentials, dispatch requests or create effects.

Requirement-resolution integration tests exercise the nested metadata chain without
mocking its verifier. They do not claim cryptographic authority authentication.
Authority signature/revocation verification and human approval verification
remain separate boundaries. The requirement-resolution layer creates no authority.
