# External Reviewer Quickstart v1

## Purpose

This quickstart helps reviewers inspect VERITAS local/offline reviewer artifacts without needing live SaaS, IAM, IdP, SSO, customer systems, banks, sanctions systems, credentials, or production approval workflows.

It is intended for:

- external reviewers
- investors
- enterprise stakeholders
- governance, compliance, and platform engineering evaluators

## What this quickstart verifies

The current review path demonstrates:

- an AI agent attempting a SaaS admin permission change
- bind-time governance before commit
- AuthorityEvidence and HumanApproval checks
- block behavior for missing, expired, or scope-mismatched evidence
- commit-eligible behavior for valid authority and approval
- OutcomeReceipt post-execution evidence
- EvidenceChainManifest linking artifacts
- EvidenceChainVerifier checking manifest/artifact consistency
- Reviewer Evidence Packet packaging the result
- golden fixture, schema, and validation report checks

## Fast path

Use this 10–15 minute path for a reviewer-facing inspection:

1. Read the golden fixture:
   `docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json`
2. Run the validation report:
   `python3 scripts/demo/validate_reviewer_evidence_packet.py`
3. Confirm expected report fields:
   - `status == "pass"`
   - `generated_packet_matches_golden_fixture == true`
   - `packet_hash_recomputes == true`
   - `schema_validation_status == "pass"` or `"skipped"` with fallback mode
   - `case_expectations_passed == true`
   - `blocked_cases_have_refusal_basis == true`
   - `valid_case_chain_verified == true`
   - `no_mismatched_links_in_demo == true`
4. Inspect the schema:
   `docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`
5. Inspect the exporter:
   `scripts/demo/export_reviewer_evidence_packet.py`
6. Inspect the original demo:
   `scripts/demo/saas_permission_change_governed_demo.py`
7. Optionally review Evaluation Governance artifacts, if present. These attachments are optional in v1, non-enforcing, and useful for architecture-hardening review without changing runtime admissibility.
   A synthetic example packet is available at `docs/en/demo/examples/reviewer-evidence-packet-with-evaluation-governance-v1.json`; schema validation does not require the referenced artifact files to exist.

## Local bundle generation

Reviewers can reproduce the GitHub Actions reviewer evidence artifact locally by running:

```text
python3 scripts/demo/build_reviewer_evidence_bundle.py
```

This creates `artifacts/reviewer-evidence-packet/` with the validation report, generated packet, golden fixture copy, schema copy, artifact manifest, manifest verification report, and step summary. The bundle also includes copies of this quickstart and the external reviewer artifact index.

## One-command validation

```text
python3 scripts/demo/validate_reviewer_evidence_packet.py
```

This command:

- prints deterministic JSON
- exits `0` on pass
- exits non-zero on fail
- uses only local files
- requires no credentials
- makes no network calls

The same validation path is enforced in CI by the Reviewer Evidence Packet Validation workflow, so reviewers can see that the packet, fixture, schema/fallback validation, case expectations, and evidence-chain verification summaries are continuously checked.

On GitHub Actions, the Reviewer Evidence Packet Validation workflow also uploads `reviewer-evidence-packet-validation-artifacts`, which contains the generated validation report, generated packet, checked-in golden fixture, and schema for inspection. The uploaded artifact includes `reviewer-evidence-artifact-manifest.json`, and the CI workflow verifies this manifest against the actual artifact files before upload. The uploaded artifact also includes `reviewer-evidence-artifact-manifest-verification-report.json`, a deterministic local/offline report from `scripts/demo/verify_reviewer_evidence_artifact_manifest.py`.

## Expected current results

The current deterministic summary is expected to show:

- `total_cases: 5`
- `blocked_cases: 4`
- `committed_cases: 1`
- `verified_chains: 5`
- `failed_chains: 0`
- `local_offline_only: true`

Expected case outcomes:

- `missing_authority` -> block
- `missing_human_approval` -> block
- `expired_human_approval` -> block
- `scope_mismatch` -> block
- `valid_authority_and_approval` -> commit or commit_eligible

## How to interpret the artifacts

### Reviewer Evidence Packet

One JSON-friendly packet containing case outcomes, authority/human approval summaries, OutcomeReceipt summaries, EvidenceChainManifest summaries, EvidenceChainVerification summaries, aggregate counts, reviewer notes, and `packet_hash`.

### Golden fixture

A checked-in deterministic JSON output. Reviewers can inspect it without running code.

### JSON Schema

Defines the packet contract and helps detect unintended shape changes.

### Validation Report

A pass/fail report that verifies generated packet equality with the fixture, packet hash recomputation, schema/fallback validation, case expectations, and evidence-chain verification summaries.

### Evidence Chain

Authority, approval, bind-time decision, outcome, and verification are linked into a traceable local/offline evidence chain.

### Evaluation Governance artifacts

If present, Evaluation Governance artifact references are optional reviewer evidence attachments for architecture-hardening review. They may help reviewers inspect authority anchors, evaluator definitions, evaluation receipts, drift signals, trajectory-level admissibility movement, legitimacy-impacting changes, and adversarial scenarios. They are non-enforcing in v1 and do not automatically establish legitimacy or change runtime admissibility.

## Boundary and non-claims

This quickstart is:

- local/offline only
- no live SaaS
- no live IAM, IdP, or SSO
- no live customer directory
- no bank or sanctions system
- no production approval workflow
- no credentials
- no live audit store
- not legal advice
- not regulatory approval
- not third-party certification
- not production audit certification
- not proof of live deployment

## Suggested reviewer questions

- Does the packet clearly show what the AI attempted?
- Are blocked cases explained with `refusal_basis` and `failure_reasons`?
- Does the valid case have a verified evidence chain?
- Does the packet hash recompute?
- Does the generated packet match the golden fixture?
- Does the schema describe the packet shape?
- Are local/offline boundaries clearly stated?
