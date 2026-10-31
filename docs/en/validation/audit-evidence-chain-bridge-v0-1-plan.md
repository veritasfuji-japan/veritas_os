# Audit Evidence Profile ↔ Evidence Chain Verifier bridge v0.1

Status: **implementation in Draft review**. The bridge module and offline test workflow are committed. This is not runtime proof, independent attestation, or certification.

## Existing interfaces (confirmed on main)

- `veritas_os/governance/evidence_chain_verifier.py` exposes `verify_evidence_chain_manifest(..., verified_at, ...)` returning `EvidenceChainVerificationResult` with `verification_status` in `verified | failed | incomplete | indeterminate`, link sets, failure reasons and recomputed manifest hash.
- `scripts/validation/validate_audit_evidence_profile.py` exposes `verify(obj, profile_path)` returning structural/local errors. It currently **rejects** self-asserted `authenticity_status=VERIFIED`, `independent_trust_status=VERIFIED`, `handoff_status=REVIEWABLE` and `reviewer_verdict=ACCEPT`.
- `scripts/demo/verify_reviewer_evidence_artifact_manifest.py` checks a different local artifact manifest and emits `status=pass|fail`. It is not an authority-chain verifier.

## Proposed narrow contract

1. Implement an **additive, offline, read-only bridge** consuming a precomputed `EvidenceChainVerificationResult` or invoking the existing chain verifier with explicit, supplied artifacts. Never mutate source evidence or rewrite the v0.1 profile in place.
2. Match a profile case to a chain using explicit identity fields, at minimum `decision_id` and `intent_id` ↔ `execution_intent_id`; mismatched or absent identity must never produce a positive link verdict. Decide whether operation and manifest IDs require a v0.2 schema extension before implementation.
3. Emit a separate, versioned **bridge report** with profile packet/case ID, chain manifest ID, source verifier identity, manifest digest, explicitly referenced manifest evidence ID and canonical file SHA-256, identity-match results, source verification status, normalized status, reasons and limits. Do not add undocumented properties to the strict v0.1 schema.
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

## Implemented in this PR

- `scripts/validation/audit_evidence_chain_bridge.py`: `verify_audit_evidence_chain_bridge(...)` and deterministic `serialize_bridge_report(...)`.
- Explicit `manifest_evidence_id` is required and must be listed in the target case's `evidence_ids`. Its profile SHA-256 must equal SHA-256 of **canonical JSON bytes** of `EvidenceChainManifest.to_dict()`. The pre-existing profile validator also verifies those bytes against the local regular file under the profile directory. The canonical format is UTF-8 JSON, sorted keys, compact separators `(',', ':')`, and `ensure_ascii=False`.
- Required ID binding is decision + intent; supplied optional authority, human approval, bind and effect receipt IDs are also compared. Named IDs without their corresponding manifest hash evidence do not produce `LINK_VERIFIED`.
- A shared decision/intent pair in two distinct profile cases is rejected as ambiguous. `LINK_VERIFIED` additionally requires a complete chain with no missing links, a case with local evidence, and an execution-performed scope with a declared observed outcome. **Those declarations are not independently authenticated by the bridge.**
- The bridge itself calls `verify_evidence_chain_manifest` and preserves the verifier's failed/incomplete/indeterminate outcomes; it refuses to promote incomplete manifest states even if the source verifier reports its present hash links as `verified`.
- `tests/validation/test_audit_evidence_chain_bridge.py` covers positive synthetic linking, signature-free claim boundaries, byte/ID substitution, incomplete and indeterminate chains, forged results, duplicate cross-case identities, logical contradictions and deterministic JSON.
- `.github/workflows/audit-evidence-chain-bridge-v0-1.yml` executes bridge tests and existing Audit Evidence Profile negative regressions.

## Remaining limitations and review decisions

- A synthetic `LINK_VERIFIED` shows the local **hash and identity link** only. It is **not** proof of authentic source, valid authority or human approval, actual effects, third-party review, provider execution or compliance.
- Profile v0.1 has no operation ID or native manifest ID reference, so it cannot ensure full operation-level binding without a versioned schema change. Its explicit `manifest_evidence_id` sidecar binding is scoped to this function call.
- The existing Evidence Chain Verifier accepts supplied local artifact hash surfaces; it is not a signature/trust-root verifier. The bridge cannot upgrade that trust boundary.
- The profile validator's local evidence reader and file metadata checks do not ensure an atomic snapshot under all concurrent in-place writes; validate stable isolated evidence directories.
- The implementation does not create a service endpoint or accept serialized status JSON as proof. Integration into runtime authorization must be a separate reviewed change.
- **Do not merge until final-head CI is green and these boundaries are reviewed.**
