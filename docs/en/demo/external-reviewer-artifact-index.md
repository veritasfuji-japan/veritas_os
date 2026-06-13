# External Reviewer Artifact Index v1

Key local/offline reviewer-facing artifacts:

- `docs/en/demos/pre_boundary_collapse_demo.md#procedural-admissibility-vs-maneuverability-observables-v0`
  - Procedural Admissibility vs. Maneuverability Observables v0: a reviewer-facing note clarifying that a process can remain admissible, documented, inspectable, and procedurally coherent while practical maneuverability contracts upstream. The note frames visibility of that contraction as a governance function, without adding production claims or runtime behavior.
- `docs/en/demos/pre_boundary_collapse_demo.md#governance-recognizability-conditions-v0`
  - Governance Recognizability Conditions v0: A reviewer-facing note clarifying the visibility conditions under which governance remains recognizable to later reviewers. It explains that preserving evidence of maneuverability contraction may become as important as preserving evidence of procedural admissibility, without adding runtime behavior, production claims, or certification language.
- `docs/en/demos/pre_boundary_collapse_demo.md#reviewer-facing-visibility-roadmap-v0`
  - Reviewer-Facing Visibility Roadmap v0: A docs-only roadmap note describing how reviewer-facing visibility may evolve before any future Governance Evidence Packet v1 expansion. It distinguishes procedural admissibility evidence, maneuverability contraction evidence, and recognizability evidence without changing runtime behavior, schemas, fixtures, or packet contracts.
- `scripts/demo/saas_permission_change_governed_demo.py`
  - deterministic local/offline SaaS permission-change governed execution demo
- `scripts/demo/export_reviewer_evidence_packet.py`
  - exports the Reviewer Evidence Packet JSON
- `scripts/demo/validate_reviewer_evidence_packet.py`
  - builds pass/fail validation report
- `scripts/demo/build_reviewer_evidence_bundle.py`
  - builds the complete local Reviewer Evidence Bundle
- `scripts/demo/verify_reviewer_evidence_artifact_manifest.py`
  - verifies reviewer-evidence-artifact-manifest.json against actual artifact files, hashes, and sizes
- `docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json`
  - checked-in golden fixture
- `docs/en/demo/fixtures/reviewer-evidence-packet-decision-candidate-refusal-v1.json`
  - local/offline fixture-backed reviewer evidence showing a `DecisionCandidateRefusalArtifact` as pre-`ExecutionIntent` evidence for LLM/agent proposals that fail closed or require human review
  - useful for reviewing why a `DecisionCandidate` was refused before promotion; it is not a `BindReceipt`, does not imply execution was attempted, and does not imply legal advice, regulatory approval, or third-party certification
  - does not wire into `/v1/decide`, perform bind adjudication, write to TrustLog, call adapters, perform live LLM extraction, perform live authority-source validation, or claim live IAM/IdP/SaaS/bank/sanctions/customer-system integration
- `docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`
  - JSON Schema contract
- `docs/en/demo/schemas/intervention-actionability-map-v0.schema.json`
  - JSON Schema contract for Intervention Actionability Map v0
- `docs/en/demo/fixtures/intervention-actionability-map-v0.json`
  - golden fixture for Intervention Actionability Map v0
- `docs/en/demo/schemas/governance-evidence-packet-v0.schema.json`
  - JSON Schema contract for Governance Evidence Packet v0
- `docs/en/demo/fixtures/governance-evidence-packet-v0.json`
  - golden fixture for Governance Evidence Packet v0
- `frontend/app/api/veritas/v1/report/governance/governance-evidence-packet-contract.test.ts`
  - contract test that validates the API packet against the schema, fixture, required sections, reviewer questions, preserved evidence refs, and non-claims
- `docs/en/demo/reviewer-evidence-packet.md`
  - Reviewer Evidence Packet documentation
- `docs/en/demo/reviewer-evidence-packet-validation-report.md`
  - validation report documentation
- `docs/en/demo/reviewer-evidence-bundle.md`
  - documentation for local Reviewer Evidence Bundle generation
- `.github/workflows/reviewer-evidence-packet-validation.yml`
  - CI gate for Reviewer Evidence Packet validation report
- `reviewer-evidence-packet-validation-artifacts`
  - GitHub Actions artifact containing validation report, generated packet, golden fixture, schema, and manifest
- `reviewer-evidence-artifact-manifest.json`
  - deterministic manifest of uploaded reviewer evidence artifact files, hashes, roles, and sizes
- `reviewer-evidence-artifact-manifest-verification-report.json`
  - CI-produced report verifying the artifact manifest against uploaded files
- `reviewer-evidence-step-summary.md`
  - Markdown step summary for reviewer evidence validation status
- `docs/en/demo/saas-permission-change-governed-demo.md`
  - SaaS permission-change demo documentation
- `docs/en/architecture/outcome-receipt.md`
  - OutcomeReceipt documentation
- `docs/en/architecture/evidence-chain-manifest.md`
  - EvidenceChainManifest documentation
- `docs/en/architecture/evidence-chain-verifier.md`
  - EvidenceChainVerifier documentation
- `docs/en/architecture/bind-coverage-registry.md`
  - Bind Coverage Registry documentation

## Evaluation Governance reviewer artifacts

Evaluation Governance artifacts may be referenced as optional reviewer evidence attachments in Reviewer Evidence Packet v1. These references are non-enforcing in v1 and support external review without changing runtime admissibility.

- Root Authority Manifest — asserted authority/trust anchor
- Evaluation Function Manifest — governed evaluator definition
- Manifest Change Receipt — governance manifest change record
- Evaluation Receipt — specific evaluation instance record
- Outcome Delta Attribution — outcome change explanation
- Evaluation Drift Detection — evaluator drift signal
- Trajectory-Level Admissibility Monitor — admissibility trajectory movement
- Legitimacy Impact Review — reviewable legitimacy-impacting change
- Adversarial Architecture Test Matrix — failure class map
- Adversarial Scenario Fixtures — concrete reviewer scenarios
