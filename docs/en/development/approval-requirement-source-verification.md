# Approval requirement source verification

`verify_human_approval_requirement_resolution_packet(packet, source, contract)`
requires the full Authority Evidence Linkage source and the expected Action
Class Contract. The one-argument, hash-only interface is no longer supported.
The verifier revalidates the source and reconstructs every field from it and
the contract. Rehashing a forged NOT_REQUIRED result cannot bypass this check.
Both the builder and verifier of requirement satisfaction use this interface.

The caller must obtain the expected contract from trusted policy configuration;
an attacker-controlled replacement contract is not a trust anchor. A satisfaction
packet's embedded contract snapshot is integrity evidence, not proof of trusted
policy selection. Its caller must still bind that snapshot to trusted policy.
Resolution time is a recorded timestamp, not a live freshness attestation.

Integration tests exercise the real nested metadata-linkage chain without
mocking its verifier. They do not claim cryptographic authority authentication.
Authority signature/revocation verification and human approval verification
remain separate boundaries. No execution or approval authority is created.
