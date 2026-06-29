# Reviewer Evidence Assurance Overview

This document is the reviewer-facing map of the local/offline evidence assurance model implemented across the Reviewer Evidence Packet, Evidence Chain verification, verifier continuity checks, verifier lifecycle checks, and failure reason catalog artifacts.

It explains how the existing demo/reviewer artifacts fit together. It does not introduce runtime behavior, schema changes, or new failure reasons.

## Assurance boundary

The reviewer evidence assurance layer is a deterministic demo/reviewer documentation and validation layer. It helps reviewers inspect whether the local/offline artifacts are internally consistent, whether hashes and continuity fields agree across artifacts, and whether failure explanations come from the generated catalog.

It is intentionally not a production trust infrastructure. This layer does **not** implement:

- live KMS;
- HSM-backed signing or key custody;
- certificate authorities;
- production PKI;
- external revocation services;
- runtime authorization changes;
- runtime admissibility changes;
- FUJI fail-closed behavior changes;
- TrustLog persistence or encryption changes.

## Layered architecture

The assurance model is layered so reviewers can trace a governed decision from human approval evidence, through verifier continuity, into packet-level validation and catalog-backed explanation.

```text
Layer 1  Human Approval Evidence
  ↓
Layer 2  Verifier Identity / Key / Policy / Proof
  ↓
Layer 3  Verifier Lifecycle
  ↓
Layer 4  Lifecycle Snapshot Hash
  ↓
Layer 5  Evidence Chain Verification
  ↓
Layer 6  Reviewer Packet Validation
  ↓
Layer 7  Failure Reason Taxonomy
  ↓
Layer 8  Failure Reason Metadata
  ↓
Layer 9  Failure Reason Catalog
  ↓
Layer 10 Catalog Schema & Validator
  ↓
Layer 11 Catalog Provenance
```

| Layer | Reviewer question | Assurance role | Primary outputs |
|---|---|---|---|
| 1. Human Approval Evidence | Was a human approval required and represented for the governed outcome? | Captures reviewer-visible approval summaries and proof references for approval-required committed outcomes. | `human_approval_summary`, approval proof hashes, approver/verifier fields. |
| 2. Verifier Identity / Key / Policy / Proof | Is the same verifier, key, policy hash, timestamp, and proof represented across the packet, manifest, and outcome metadata? | Prevents substituted verifier identity, verifier key, policy hash, `verified_at`, or approval proof fields from appearing valid in reviewer-facing artifacts. | Verifier continuity fields and proof hash continuity fields. |
| 3. Verifier Lifecycle | Was verifier lifecycle state included where needed? | Adds lifecycle evidence for the verifier and checks policy/lifecycle continuity in reviewer summaries. | `verifier_lifecycle_summary` and lifecycle validation results. |
| 4. Lifecycle Snapshot Hash | Do lifecycle snapshot hashes agree everywhere they are expected? | Binds verifier lifecycle state to the manifest and outcome metadata using deterministic hash continuity. | `verifier_lifecycle_snapshot_hash`, `human_approval_verifier_lifecycle_snapshot_hash`, outcome metadata snapshot hash. |
| 5. Evidence Chain Verification | Does the evidence chain verify the artifact links it claims to verify? | Checks evidence-chain artifact integrity and verified links before packet validation relies on them. | Evidence chain manifest and `evidence_chain_verification_summary`. |
| 6. Reviewer Packet Validation | Does the reviewer-facing packet consistently summarize the underlying evidence? | Validates the packet schema and cross-artifact continuity expectations for reviewer consumption. | `reviewer-evidence-packet.generated.example.json`, validation reports. |
| 7. Failure Reason Taxonomy | Are failure reasons stable and known? | Allowlists deterministic machine-readable reason strings used by packet cases, chain summaries, lifecycle summaries, tamper fixtures, and reports. | Stable failure reason codes. |
| 8. Failure Reason Metadata | Can reviewers understand a reason without changing its code? | Maps each reason to category, severity, label, explanation, remediation hint, and affected artifacts. | Python metadata source of truth. |
| 9. Failure Reason Catalog | Is there a generated reviewer explanation artifact? | Generates JSON and Markdown catalogs for reviewers and automation. | Generated catalog JSON/MD. |
| 10. Catalog Schema & Validator | Is the generated catalog valid and fresh? | Validates schema shape, deterministic freshness, coverage, uniqueness, sorting, and metadata fidelity. | Catalog schema and validator result. |
| 11. Catalog Provenance | Which catalog and schema explained this validation report? | Records local digests, version, paths, reason count, categories, and severities used by validation reports. | `failure_reason_catalog_provenance`. |

## Component mapping

| Component | Purpose | Output | Validation |
|---|---|---|---|
| Reviewer Evidence Packet | Reviewer-facing evidence bundle for governed demo cases. | [`reviewer-evidence-packet.generated.example.json`](examples/evaluation-governance-chain-reviewer-packet-v1/reviewer-evidence-packet.generated.example.json) and fixtures. | [`reviewer-evidence-packet-v1.schema.json`](schemas/reviewer-evidence-packet-v1.schema.json) plus local packet validator. |
| Human Approval Evidence | Shows approval-required outcomes, approver context, verifier context, proof hash, and policy fields. | Packet `human_approval_summary` fields and proof-hash metadata. | Reviewer packet validation and evidence-chain proof continuity checks. |
| Verifier Continuity | Ensures verifier id, verifier key id, policy id/hash, proof hash, and `verified_at` agree across summaries. | Continuity fields in human approval summaries, evidence-chain manifests, verification summaries, and outcome metadata. | Reviewer packet validation failure reasons such as verifier id/key/policy/proof/timestamp mismatches. |
| Verifier Lifecycle | Represents verifier lifecycle state and lifecycle policy continuity. | `verifier_lifecycle_summary`. | Lifecycle summary checks and reviewer packet lifecycle failure reasons. |
| Lifecycle Snapshot Hash | Binds lifecycle state into manifest and outcome metadata. | Lifecycle snapshot hash fields in lifecycle summary, evidence-chain manifest, and outcome receipt metadata. | Evidence-chain and reviewer-packet lifecycle snapshot continuity checks. |
| Evidence Chain | Artifact integrity layer for chain manifests and verified links. | Evidence chain manifest and `evidence_chain_verification_summary`. | Evidence Chain Verification. |
| Reviewer Packet Validation Report | Reviewer-facing validation status and failure explanations. | [`reviewer-evidence-packet-validation-report.md`](reviewer-evidence-packet-validation-report.md) and generated validation report fields. | Packet schema, packet validator, taxonomy checks, and catalog provenance checks. |
| Failure Reason Taxonomy | Stable machine-readable failure reason allowlist. | Reason strings in packet cases, tamper fixtures, validation reports, chain summaries, and lifecycle summaries. | Local taxonomy guard. |
| Failure Reason Metadata | Reviewer explanation layer for stable reason strings. | Category, severity, label, explanation, remediation hint, and affected artifacts for every reason. | Catalog validator metadata fidelity checks. |
| Failure Reason Catalog | Generated reviewer explanation layer. | [`reviewer-failure-reason-catalog.generated.example.json`](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json) and [`reviewer-failure-reason-catalog.generated.example.md`](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md). | Catalog schema and catalog validator. |
| Catalog Schema | Machine-readable shape for generated catalog JSON. | [`reviewer-failure-reason-catalog-v1.schema.json`](schemas/reviewer-failure-reason-catalog-v1.schema.json). | JSON Schema validation. |
| Catalog Validator | Local/offline freshness, coverage, uniqueness, sorting, and fidelity check. | Validator pass/fail result. | `scripts/demo/validate_reviewer_failure_reason_catalog.py`. |
| Catalog Provenance | Records which catalog/schema explained a validation result. | `failure_reason_catalog_provenance` in validation reports. | Digest/path/version/count/category/severity comparison. |

## Tamper coverage

The local/offline reviewer assurance checks include the following tamper detections and drift guards.

| Detection | Covered artifact relationship | Reviewer-facing outcome |
|---|---|---|
| ✓ verifier id mismatch | Human approval summary vs. manifest/outcome/verification summaries. | Packet validation fails with verifier continuity reason. |
| ✓ verifier key mismatch | Human approval verifier key id vs. manifest/outcome metadata. | Packet validation fails with verifier key continuity reason. |
| ✓ policy hash mismatch | Human approval policy hash vs. manifest/outcome/lifecycle policy hash. | Packet validation fails with policy continuity or lifecycle policy reason. |
| ✓ verification proof mismatch | Approval proof hash vs. manifest/outcome/verified links. | Evidence-chain or packet validation fails with proof continuity reason. |
| ✓ `verified_at` mismatch | Human approval timestamp vs. lifecycle and evidence-chain verification summaries. | Packet validation fails with timestamp continuity reason. |
| ✓ lifecycle snapshot mismatch | Lifecycle summary snapshot hash vs. manifest/outcome metadata. | Evidence-chain or packet validation fails with lifecycle snapshot mismatch reason. |
| ✓ manifest missing snapshot hash | Lifecycle summary exists but manifest omits the expected lifecycle snapshot hash. | Evidence-chain or packet validation fails with manifest snapshot missing reason. |
| ✓ outcome missing snapshot hash | Lifecycle summary/manifest includes snapshot hash but outcome metadata omits it. | Evidence-chain or packet validation fails with outcome snapshot missing reason. |
| ✓ unknown failure reason | Report, fixture, chain summary, lifecycle summary, or packet case uses a reason outside the taxonomy. | Taxonomy/catalog validation fails. |
| ✓ stale catalog | Generated JSON/MD catalog no longer matches the Python metadata source of truth. | Catalog validator fails freshness/fidelity checks. |

## How reviewers should read the artifacts

1. Start with the packet overview in [`reviewer-evidence-packet.md`](reviewer-evidence-packet.md) to understand the packet scope, local/offline boundary, schema, and golden fixtures.
2. Inspect a generated packet such as [`examples/evaluation-governance-chain-reviewer-packet-v1/reviewer-evidence-packet.generated.example.json`](examples/evaluation-governance-chain-reviewer-packet-v1/reviewer-evidence-packet.generated.example.json) or [`examples/evaluation-governance-reviewer-demo-v1/generated/reviewer-evidence-packet.generated.example.json`](examples/evaluation-governance-reviewer-demo-v1/generated/reviewer-evidence-packet.generated.example.json).
3. Check the packet schema at [`schemas/reviewer-evidence-packet-v1.schema.json`](schemas/reviewer-evidence-packet-v1.schema.json) for required fields and nested summary shapes.
4. Use the generated failure reason catalog Markdown for reviewer-friendly explanations: [`examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md`](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md).
5. Use the generated failure reason catalog JSON for automation: [`examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json`](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json).
6. Check the catalog schema at [`schemas/reviewer-failure-reason-catalog-v1.schema.json`](schemas/reviewer-failure-reason-catalog-v1.schema.json).
7. Review validation report provenance in [`reviewer-evidence-packet-validation-report.md`](reviewer-evidence-packet-validation-report.md) to identify which catalog version, schema, local digests, categories, and severities explained validation failures.

## Non-goals for this PR

This overview intentionally does not:

- change runtime code;
- change schemas;
- add or rename failure reasons;
- regenerate artifacts;
- alter governance policy behavior;
- alter bind/admissibility logic;
- alter FUJI behavior;
- alter TrustLog persistence or encryption behavior.
