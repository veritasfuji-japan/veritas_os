# Reviewer Evidence Packet Validation Report v1

Reviewer Evidence Packet Validation Report v1 is a deterministic local/offline pass/fail report for the existing Reviewer Evidence Packet v1 fixture.

It is intended to help external reviewers, investors, and enterprise stakeholders verify the checked-in demo packet with one local command.

## What it verifies

The validation report checks that:

- the generated Reviewer Evidence Packet matches the checked-in golden fixture
- the `packet_hash` field is present and recomputes correctly from the generated packet
- the packet validates against the Reviewer Evidence Packet JSON Schema v1 when `jsonschema` is available locally
- deterministic fallback structural validation runs when `jsonschema` is unavailable
- the expected demo case outcomes still hold
- blocked demo cases include refusal bases and outcome failure reasons
- evidence-chain verification summaries are present for every case
- the valid authority-and-approval case has a verified evidence chain
- no demo case reports mismatched evidence-chain links
- the local/offline boundary remains explicit

## Usage

Run the validator locally:

```bash
python3 scripts/demo/validate_reviewer_evidence_packet.py
```

The command prints deterministic JSON to stdout with sorted keys and indentation. It exits with status code `0` when the report status is `pass` and a non-zero status when the report status is `fail`.

## Inputs

The report uses only local deterministic artifacts:

- generated packet from `build_reviewer_evidence_packet()`
- golden fixture at `docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json`
- schema at `docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`

It does not require credentials and performs no live network calls.

## Schema and fallback validation

When `jsonschema` is available in the local environment, the validator checks both the generated packet and the golden fixture against Reviewer Evidence Packet JSON Schema v1.

When `jsonschema` is unavailable, the validator does not add or require a dependency. Instead, it runs deterministic fallback structural checks for required top-level fields, `packet_id`, `packet_version`, `local_offline_only`, packet hash format, non-empty cases, aggregate summary, and nested case evidence summaries.

## CI gate

Reviewer Evidence Packet Validation is also enforced by a dedicated GitHub Actions workflow at:
`.github/workflows/reviewer-evidence-packet-validation.yml`

The workflow runs:

```bash
python3 scripts/demo/validate_reviewer_evidence_packet.py
```

This verifies that the generated packet matches the golden fixture, `packet_hash` recomputes correctly, schema or fallback validation passes, deterministic case expectations hold, and evidence-chain verification summaries remain valid.

The workflow also verifies `reviewer-evidence-artifact-manifest.json` before uploading artifacts. The manifest verifier at `scripts/demo/verify_reviewer_evidence_artifact_manifest.py` recomputes the manifest hash, each listed file hash, and each listed file size to confirm that the manifest matches the actual artifact directory.

This CI gate is local/offline only and does not connect to live SaaS, IAM, IdP, SSO, customer systems, banks, sanctions systems, production approval workflows, or live audit stores.

## CI artifacts

The Reviewer Evidence Packet Validation workflow uploads CI artifacts under the artifact name:
`reviewer-evidence-packet-validation-artifacts`

The uploaded artifact includes:

- `reviewer-evidence-packet-validation-report.json`
- `reviewer-evidence-packet-generated.json`
- `reviewer-evidence-packet-golden-fixture.json`
- `reviewer-evidence-packet-schema.json`
- `reviewer-evidence-artifact-manifest.json`
- `reviewer-evidence-artifact-manifest-verification-report.json`
- `reviewer-evidence-step-summary.md`

These files allow reviewers to inspect the exact validation report, generated packet, checked-in fixture, and schema used by CI. The uploaded artifact also includes `reviewer-evidence-artifact-manifest.json`, a deterministic manifest that lists the uploaded reviewer evidence files, their roles, whether they are generated or checked-in, their sha256 hashes, and their byte sizes. The CI-produced `reviewer-evidence-artifact-manifest-verification-report.json` records the local/offline manifest verification result. The CI-produced `reviewer-evidence-step-summary.md` provides a Markdown summary of the same reviewer evidence status.

This artifact is local/offline only and does not represent live SaaS execution, production deployment, audit certification, regulatory approval, or third-party certification.

## Boundary

This report validates a local/offline Reviewer Evidence Packet fixture only.

It does not connect to live SaaS, IAM, IdP, SSO, customer directories, banks, sanctions systems, production approval workflows, or live audit stores.

It is not legal advice, regulatory approval, third-party certification, production audit certification, or proof of live deployment.
