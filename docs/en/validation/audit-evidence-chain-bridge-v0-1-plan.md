# Audit Evidence Profile ↔ Evidence Chain Verifier bridge v0.1

Status: **design staging only**. This document is not an implemented bridge, runtime proof, independent attestation or certification.

## Existing interfaces (confirmed on main)

- `veritas_os/governance/evidence_chain_verifier.py` exposes `verify_evidence_chain_manifest(..., verified_at, ...)` returning `EvidenceChainVerificationResult` with `verification_status` in `verified | failed | incomplete | indeterminate`, link sets, failure reasons and recomputed manifest hash.
- `scripts/validation/validate_audit_evidence_profile.py` exposes `verify(obj, profile_path)` returning structural/local errors. It currently **rejects** self-asserted `authenticity_status=VERIFIED`, `independent_trust_status=VERIFIED`, `handoff_status=REVIEWABLE` and `reviewer_verdict=ACCEPT`.
- `scripts/demo/verify_reviewer_evidence_artifact_manifest.py` checks a different local artifact manifest and emits `status=pass|fail`. It is not an authority-chain verifier.

## Proposed narrow contract

1. Implement an **additive, offline, read-only bridge** consuming a precomputed `EvidenceChainVerificationResult` or invoking the existing chain verifier with explicit, supplied artifacts. Never mutate source evidence or rewrite the v0.1 profile in place.
2. Match a profile case to a chain using explicit identity fields, at minimum `decision_id` and `intent_id` ↔ `execution_intent_id`; mismatched or absent identity must never produce a positive link verdict. Decide whether operation and manifest IDs require a v0.2 schema extension before implementation.
3. Emit a separate, versioned **bridge report** with profile packet/case ID, chain manifest ID, source verifier ID/version, source digest, identity-match results, source verification status, normalized status, reasons and limits. Do not add undocumented properties to the strict v0.1 schema.
4. Preserve status semantics without elevation:

| Chain verifier status | Bridge status | Permitted claim |
| --- | --- | --- |
| verified | LINK_VERIFIED | Supplied local chain links verified only; **not** actual effect, authority validity, signature or independent trust |
| failed | FAILED | Link verification failed |
| incomplete | INCOMPLETE | Required link evidence missing |
| indeterminate | INDETERMINATE | Insufficient basis to decide |
| missing/malformed/unbound | INDETERMINATE or FAILED | Fail closed, never claim LINK_VERIFIED |

5. Keep `reviewer_verdict=ACCEPT`, `handoff_status=REVIEWABLE`, external authenticity/trust and case `observed=PASS` **outside bridge promotion**. A local chain hash match does not establish these claims.
6. Do not interpret the separate reviewer artifact manifest's `pass` as chain `verified`; if added later, use an explicitly separate namespace and claim type.

## Required negative tests

- Wrong decision/intent/operation IDs; missing manifest; mismatched manifest hash.
- Missing link, mismatched receipt hash, indeterminate artifact hash.
- Conflicting source status and `is_valid`; malformed/unknown status; absent verifier identity.
- Self-asserted `verified` JSON report without a trusted local invocation or bound evidence; forged source digest.
- Synthetic profile requesting reviewer ACCEPT, REVIEWABLE or authenticity VERIFIED; should remain rejected.
- Repeated case IDs and one chain attached to the wrong case; no cross-case status leakage.
- Deterministic report bytes under reordered input dictionaries; no credentials, network, writes or runtime side effects.

## Acceptance gates

- Choose the trusted invocation boundary: **prefer calling the existing verifier in-process with supplied local artifacts**, rather than treating arbitrary serialized `verified` reports as authentic.
- Explicit mapping documented and independently tested with positive and negative fixtures.
- Dedicated CI on final HEAD, and existing Audit Evidence Profile CI remains green.
- No changes to authority issuance, Bind, Custody, trust roots, effect execution, benchmark scoring, or existing verifier verdict semantics.
- Retain Draft until implementation, threat-model review and final CI pass.
