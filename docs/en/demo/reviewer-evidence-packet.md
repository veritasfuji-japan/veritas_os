# Reviewer Evidence Packet v1

Reviewer Evidence Packet v1 is a deterministic local/offline JSON-friendly export for the SaaS permission-change governed execution demo.

It packages the existing demo output into one reviewer-facing artifact so external reviewers, investors, and enterprise stakeholders can inspect the main governance evidence without opening every internal artifact separately.

## What it includes

The packet is built from `run_saas_permission_change_governed_demo()` and includes:

- case outcomes for the SaaS permission-change governed execution demo
- compact AuthorityEvidence and HumanApproval summaries
- OutcomeReceipt summaries for each case
- EvidenceChainManifest summaries for each case
- EvidenceChainVerification summaries for each case
- aggregate counts for blocked, committed, and verified cases
- deterministic reviewer notes
- a deterministic packet hash that excludes `packet_hash` itself from the hash payload

## Evaluation Governance Artifact Attachments

Reviewer Evidence Packet v1 may include optional reviewer evidence attachments for Evaluation Governance artifacts. These references are intended to help external reviewers inspect the authority basis, evaluator definition, evaluation receipt, drift signals, trajectory movement, and legitimacy-impacting changes that may be relevant to an architecture-hardening review.

Optional Evaluation Governance artifact references may include:

- Root Authority Manifest
- Evaluation Function Manifest
- Manifest Change Receipt
- Evaluation Receipt
- Outcome Delta Attribution
- Evaluation Drift Detection
- Trajectory-Level Admissibility Monitor
- Legitimacy Impact Review
- Adversarial Architecture Test Matrix
- Adversarial Scenario Fixtures

These attachments are optional reviewer evidence attachments in v1. Reviewer packets do not require them, and schema validation only checks the attachment reference shape, hash format, and declared schema reference; it does not dereference files or validate the target artifact itself.

A non-enforcing example packet with optional Evaluation Governance attachment references is checked in at `docs/en/demo/examples/reviewer-evidence-packet-with-evaluation-governance-v1.json`. A synthetic end-to-end Evaluation Governance sample bundle is also available at `docs/en/demo/examples/evaluation-governance-sample-bundle-v1/`.

Evaluation Governance artifacts are non-enforcing in v1 unless future runtime integration is added. Their presence supports external review, but does not automatically establish legitimacy, does not change runtime admissibility, does not introduce fail-closed behavior, and does not require live receipt generation.

## Local/offline boundary

Reviewer Evidence Packet v1 is a local/offline fixture export only.

It does not connect to live SaaS, IAM, IdP, SSO, customer directories, banks, sanctions systems, production approval workflows, or live audit stores.

It demonstrates bind-time governance and evidence-chain verification using deterministic artifacts. It is not legal advice, regulatory approval, third-party certification, production audit certification, or proof of live deployment.

## Usage

Run the export locally:

```bash
python3 scripts/demo/export_reviewer_evidence_packet.py
```

The command prints deterministic JSON to stdout with sorted keys and indentation. It performs no network calls and requires no credentials.

## Golden fixture

A deterministic golden fixture is checked in at:
`docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json`

This fixture is generated from the local/offline Reviewer Evidence Packet exporter and is tested against the current generated packet. It allows reviewers to inspect the packet without running the code first. The fixture is not proof of live production deployment, live SaaS execution, or audit certification.

If the generated packet changes intentionally in the future, update the golden fixture in the same PR as the behavior change.

## Schema

Reviewer Evidence Packet v1 has a checked-in schema at:
`docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`

The schema documents the required packet fields, case summaries, nested evidence summaries, aggregate summary, reviewer notes, packet hash format, and optional `evaluation_governance_artifacts` reference shape. The golden fixture and generated packet are tested against this schema. Future intentional packet-shape changes should update the schema, exporter, tests, and golden fixture in the same PR.

This schema is for a local/offline reviewer packet. It is not a production audit certification, regulatory approval, or proof of live deployment.

