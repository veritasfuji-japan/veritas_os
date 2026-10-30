# VERITAS Audit Evidence Profile v0.1 (draft)

Status: proposal only; non-enforcing, non-certifying. This document is not an ISO/IEC 42001 conformity assessment.

## Purpose
Provide an independently reviewable evidence projection showing not just that controls are configured, but whether bounded tests demonstrate their effectiveness against unauthorized agent execution.

## Evidence record
Each case SHOULD contain:
- `profile_version`, `case_id`, `scenario_id`, `source_commit`, `environment`
- `actor`, `action`, `target`, `request_digest`, `policy_digest`
- `authority_issuer`, `authority_scope`, `authority_validity`, `single_use_state`
- `expected_decision`, `observed_decision`, `effect_state`, `outcome_evidence_ref`
- `artifact_sha256`, `verification_method`, `verifier_identity`, `verification_result`
- `test_provenance`, `trust_assumptions`, `limitations`

All references MUST resolve to pinned artifacts; an absent link must be marked missing rather than inferred. Evidence hashes prove byte integrity only when independently verified against trusted source material; they do not by themselves prove that an effect occurred.

## Claim gates
1. Distinguish control existence, configured enforcement, observed effect, and independently reproduced results.
2. Preserve negative tests: expired authority, replay, changed request/target, altered signature, stale policy, lost response, restart, and bypass probes.
3. Report authorized-task utility separately from unauthorized-task success. Include denominator, scorer provenance, corpus, run identity, and confidence limitations.
4. Treat unknown outcomes as UNKNOWN, never as success or failure by assumption.
5. Report provenance tiers: synthetic fixture, same-host operator observation, independent artifact recomputation, independent execution, held-out independent execution.
6. No universal bypass-resistance, production readiness, or ISO certification claims from bounded results.

## Existing evidence boundaries
- Reviewer Evidence Packet v1 is a deterministic local/offline demo export, not proof of production enforcement.
- The RCC/REVAS AgentDojo V13 frozen 128-case evidence reports Arm A utility 93/128, injection success 20/128; Arm B utility 64/128, injection success 0/128. This is a bounded corpus result, not a universal guarantee.
- The signed-ledger Linux exercise is same-host operator-provided evidence, with no live provider or banking effect and no independent host attestation.
- External replication handoff is ready, but independent execution replication is not established by the handoff alone.

## Proposed acceptance criteria for a later implementation PR
- Versioned JSON Schema with no unknown keys and explicit status vocabulary.
- Deterministic offline verifier checks hashes, referential integrity, status consistency, and claim provenance.
- Synthetic passing fixture and negative tests for missing evidence, tampering, fabricated outcome, and scope mismatch.
- CI runs without credentials, network calls, provider access, or mutations.
- No changes to authority issuance, Bind, Custody, trust roots, runtime execution, or benchmark scoring.

## References
- docs/en/demo/reviewer-evidence-packet.md
- https://github.com/veritasfuji-japan/rcc-revas-veritas-benchmark/blob/main/docs/AGENTDOJO_FINAL_128_INDEPENDENT_EXTERNAL_REPLICATION_HANDOFF_V1.md
- https://github.com/veritasfuji-japan/rcc-revas-veritas-benchmark/blob/main/docs/TASK4_SIGNED_LEDGER_OPERATOR_OBSERVATIONS_335A3C9_V1.md
