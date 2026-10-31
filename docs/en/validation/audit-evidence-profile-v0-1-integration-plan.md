# Audit Evidence Profile v0.1 — implementation integration plan

Status: draft implementation staging. This document is not an implementation-complete or certification claim.

## Source of truth
- `docs/en/validation/audit-evidence-profile-v0-1-draft.md` defines the claim boundaries.
- Existing `veritas_os/governance/evidence_chain_verifier.py` verifies evidence-chain links.
- Existing `scripts/demo/verify_reviewer_evidence_artifact_manifest.py` verifies local artifact hashes and sizes.
- Existing Reviewer Evidence Packet schema, validator and CI remain authoritative for their own format.

## Proposed increment
1. Introduce a separate versioned Audit Evidence Profile schema, without changing existing packet formats.
2. Add a read-only offline validator for referenced artifacts, scope and claim provenance.
3. Treat absent evidence as missing; never infer successful effects from hashes or self-reported statuses.
4. Preserve failed, incomplete and indeterminate results without promoting them to verified.
5. Add synthetic fixtures and negative tests (missing evidence, digest mismatch, unsupported claims, scope mismatch, symlink/path escape).
6. Add isolated CI that requires no credentials, network calls, or production side effects.

## Explicit exclusions
No modifications to authority issuance, Bind, Custody, trust roots, runtime execution, or benchmark scoring. No claims of independent execution replication, production readiness, universal bypass resistance, or ISO certification.

## Review gate
Do not merge until the separately prepared local design package is reconciled with existing validators, code is committed, tests execute in CI, and reviewer-facing claims are checked for provenance inflation.

## Compatibility boundary
The Audit Evidence Profile validator checks local schema, references and file hashes only. It does not call the Evidence Chain Verifier or the Reviewer Evidence Artifact Manifest Verifier. Their outputs and statuses are not interchangeable. The earlier case-level proposal includes fields not implemented in this v0.1 schema. Any integration or provenance mapping needs a separate change and dedicated tests.

## Merge criteria
The final head must pass dedicated CI; the path and file-reading threat model must be reviewed; schema omissions must be disclosed; and no external attestation, effect verification, or certification may be claimed from local structural validation.
