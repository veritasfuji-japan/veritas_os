# VERITAS Audit Evidence Profile v0.2 — operation-level binding

**Status:** proposed local/offline schema and verifier extension; PR #2445. Not an external audit, runtime authorization control, effect attestation, independently trusted proof, or ISO certification.

## Scope

v0.1 lacked first-class `operation_id`, `manifest_id` and `manifest_evidence_id` fields. Profile v0.2 introduces these on every case and requires each **observed** case to provide nonempty values. An unobserved case may declare all three IDs as `null`; a partial triple is rejected. This models **one distinct operation and manifest per case**; reuse of a non-null operation ID, manifest ID, or manifest evidence ID across cases is rejected.

The v0.2 schema is **separate** from the existing strict v0.1 schema. The validator dispatches strictly on the exact `profile_version` field; unknown versions fail closed. v0.1 data and Bridge calls remain accepted without changing their historical verdict semantics.

## Contract

| v0.2 case field | Chain / local target | Enforcement |
| --- | --- | --- |
| `decision_id` | `EvidenceChainManifest.decision_id` | Same as v0.1; required for positive Bridge |
| `intent_id` | `EvidenceChainManifest.execution_intent_id` | Same as v0.1; required for positive Bridge |
| `operation_id` | `EvidenceChainManifest.operation_id` | **Required and exact-match** for v0.2 positive Bridge |
| `manifest_id` | `EvidenceChainManifest.manifest_id` | **Required and exact-match** for v0.2 positive Bridge |
| `manifest_evidence_id` | profile evidence item's `id` and Bridge's `manifest_evidence_id` | **Required and exact-match**; evidence ID must exist in inventory and target case's `evidence_ids` |

Existing v0.1 link checks remain: the bound file's SHA-256 must match the canonical JSON serialization of the supplied manifest, and the local Profile object must equal the bounded on-disk JSON file. Existing source `EvidenceChainVerificationResult` statuses and completeness checks are preserved without promotion.

v0.2 emits `bridge_version=veritas.audit-evidence-chain-bridge/0.2` with explicit case-level IDs and `identity_matches`. v0.1 still emits `veritas.audit-evidence-chain-bridge/0.1`. `LINK_VERIFIED` signifies local, internal hash-and-ID continuity **only**; a matching claimant-provided operation ID does not independently prove that the stated operation executed.

## Safety and compatibility limits

- Profiles v0.1 and v0.2 are versioned separately; v0.1 cannot silently carry the new fields because `additionalProperties=false`.
- No migration is performed in place; no hardcoded ID inference from filenames or user-supplied status JSON.
- Multiple cases for one operation are intentionally not supported in v0.2. A future schema could represent multiple observations under one explicitly scoped operation, but must be separately reviewed and versioned.
- Local file hashes, manifest content and identifier matches are **not signatures, chain-of-custody attestations, issuance-validity checks, independent reviewer verdicts, or observed real-world effect verification**.
- The preexisting local file validators have bounded file reads and symlink protections but are not a transactional snapshot under arbitrary concurrent mutation.
- No change to authority issuance, revocation, Bind, Custody, action execution, external trust roots, scoring, benchmark metrics, or production services.

## Tests and merge gates

- v0.1 and v0.2 valid synthetic fixtures both pass local schema/reference/hash validation.
- Missing required v0.2 fields, partial triples, duplicate IDs, unreferenced/unlisted manifest evidence, unsupported versions, and self-asserted review claims are rejected.
- A synthetic fully bound v0.2 Bridge case succeeds locally; mismatched operation/manifest/evidence IDs, alternate manifests with equal decision+intent but different operations, and case-reuse substitutions are rejected.
- Unexecuted and unbound cases cannot become `LINK_VERIFIED`.
- Previous v0.1 Bridge and profile negative suites continue to pass.
- All GitHub Actions CI on the final commit must pass before moving out of Draft; reviewers must validate the stated **limited claim** and the one-operation-per-case modeling decision.
