# Bind Coverage Registry v1 (local/offline)

## Purpose

Bind Coverage Registry v1 is a deterministic local/offline coverage artifact that records which effect-bearing operations are expected to be governed by bind-time controls.

It helps reviewers answer a practical question:

- Are high-impact execution paths governed by bind-time controls, or only isolated demos?

## What this registry is

- A deterministic list of effect-bearing operations in current scope.
- A reviewer-facing mapping between operations and governance expectations.
- A fail-closed expectation record for authority and human-approval prerequisites.

## What this registry is not

- Not a live route scanner.
- Not proof of production deployment.
- Not live integration with SaaS, IdP, IAM, banks, sanctions providers, or customer systems.
- Not runtime enforcement changes by itself.

## How it complements existing governance artifacts

Bind Coverage Registry v1 complements:

- Authority Evidence Ingestion v1 (`docs/en/architecture/authority-evidence-ingestion.md`)
- Human Approval Receipt v1 (`docs/en/architecture/human-approval-receipt.md`)
- SaaS Permission-Change Governed Execution Demo (`docs/en/demo/saas-permission-change-governed-demo.md`)

Together, these artifacts make local/offline governance expectations more reviewable for external diligence.

## Validation expectations

Registry validation checks include:

- `operation_id` is non-empty and unique.
- `effect_level` is one of `low|medium|high|critical`.
- `high|critical` entries require bind-time governance and fail-closed defaults.
- authority-required entries must block without authority.
- human-approval-required entries must block without human approval.
- implementation refs are non-empty.
- docs refs are non-empty for reviewer-facing entries.
- entries do not claim live integration unless explicitly implemented elsewhere.
