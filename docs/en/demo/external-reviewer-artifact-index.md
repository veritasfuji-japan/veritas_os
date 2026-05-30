# External Reviewer Artifact Index v1

Key local/offline reviewer-facing artifacts:

- `scripts/demo/saas_permission_change_governed_demo.py`
  - deterministic local/offline SaaS permission-change governed execution demo
- `scripts/demo/export_reviewer_evidence_packet.py`
  - exports the Reviewer Evidence Packet JSON
- `scripts/demo/validate_reviewer_evidence_packet.py`
  - builds pass/fail validation report
- `scripts/demo/verify_reviewer_evidence_artifact_manifest.py`
  - verifies reviewer-evidence-artifact-manifest.json against actual artifact files, hashes, and sizes
- `docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json`
  - checked-in golden fixture
- `docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`
  - JSON Schema contract
- `docs/en/demo/reviewer-evidence-packet.md`
  - Reviewer Evidence Packet documentation
- `docs/en/demo/reviewer-evidence-packet-validation-report.md`
  - validation report documentation
- `.github/workflows/reviewer-evidence-packet-validation.yml`
  - CI gate for Reviewer Evidence Packet validation report
- `reviewer-evidence-packet-validation-artifacts`
  - GitHub Actions artifact containing validation report, generated packet, golden fixture, schema, and manifest
- `reviewer-evidence-artifact-manifest.json`
  - deterministic manifest of uploaded reviewer evidence artifact files, hashes, roles, and sizes
- `reviewer-evidence-artifact-manifest-verification-report.json`
  - CI-produced report verifying the artifact manifest against uploaded files
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
