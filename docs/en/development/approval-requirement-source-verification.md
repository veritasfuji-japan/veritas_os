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

Integration tests exercise the real nested metadata-linkage chain without
mocking its verifier. They do not claim cryptographic authority authentication.
Authority signature/revocation verification and human approval verification
remain separate boundaries. No execution or approval authority is created.
