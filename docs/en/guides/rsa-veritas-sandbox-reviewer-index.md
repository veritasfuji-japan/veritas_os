# RSA ↔ VERITAS Sandbox Reviewer Index

## 1. Purpose

This page is the reviewer entrypoint for the RSA-compatible V.I.K.I. ↔ VERITAS sandbox documentation set.

It consolidates the scenario map, demo plan, validation snapshots, and static fixture matrix into one navigable index so reviewers can inspect the sandbox flow without connecting live V.I.K.I. middleware.

## 2. Current taxonomy

- RSA remains the theoretical framework and underlying rule set.
- V.I.K.I. is the operational middleware that emits RSA-compatible upstream payloads.
- VERITAS is the downstream commit governance boundary.
- VERITAS consumes only the emitted payload.
- VERITAS does not consume V.I.K.I. internal reasoning.
- Existing compatibility names such as `rsa_status`, `RSASandboxPayload`, and `upstream_signal_source = "RSA"` remain unchanged for v1 sandbox compatibility.

## 3. Recommended reading order

1. [AML/KYC scenario map](./rsa-veritas-aml-kyc-scenario-map.md)
2. [E2E sandbox demo plan](./rsa-veritas-e2e-sandbox-demo-plan.md)
3. [E2E sandbox validation snapshot](./rsa-veritas-e2e-sandbox-validation-snapshot.md)
4. [Static fixture matrix](./rsa-veritas-static-fixture-matrix.md)
5. [SAFE_PROCEED validation snapshot](./rsa-veritas-safe-proceed-validation-snapshot.md)
6. [DENSITY_THROTTLED validation snapshot](./rsa-veritas-density-throttled-validation-snapshot.md)
7. [ALGORITHMIC_HUMILITY_ENGAGED validation snapshot](./rsa-veritas-algorithmic-humility-engaged-validation-snapshot.md)
8. [DEFERRAL_ENGAGED validation snapshot](./rsa-veritas-deferral-engaged-validation-snapshot.md)
9. [Local V.I.K.I. mock ingestion receiver design (Phase 2 local mock artifact, documentation-only)](./rsa-veritas-local-viki-mock-ingestion-receiver-design.md)
10. [Live V.I.K.I. integration design note (future design artifact, documentation-only)](./rsa-veritas-live-viki-integration-design-note.md)
11. [Live V.I.K.I. integration reviewer checklist (review-gate artifact, documentation-only)](./rsa-veritas-live-viki-integration-reviewer-checklist.md)
12. [Local V.I.K.I. mock receiver test fixture plan (Phase 2 local mock artifact, documentation-only)](./rsa-veritas-local-viki-mock-receiver-test-fixture-plan.md)
13. [Local V.I.K.I. mock receiver validation snapshot (Phase 2 local mock implementation validation record, documentation-only)](./rsa-veritas-local-viki-mock-receiver-validation-snapshot.md)

All four static fixture variants now have dedicated per-variant validation snapshots.

## 4. Artifact map

| Artifact | Purpose | Primary reviewer question answered |
| --- | --- | --- |
| AML/KYC scenario map | Shows the node-by-node upstream/downstream boundary. | Where does V.I.K.I. stop and where does VERITAS begin? |
| E2E sandbox demo plan | Describes the static sandbox demonstration flow. | What is the intended demo path? |
| E2E sandbox validation snapshot | Records the current static E2E output shape. | What does the current harness output look like? |
| Static fixture matrix | Compares all supported static fixture statuses. | How does VERITAS map each upstream status? |
| SAFE_PROCEED validation snapshot | Documents normal continuation. | What happens when the upstream signal says proceed? |
| DENSITY_THROTTLED validation snapshot | Documents soft upstream intervention. | What happens when the upstream output was modified but not hard-blocked? |
| ALGORITHMIC_HUMILITY_ENGAGED validation snapshot | Documents pause / human-review gating for incomplete context or insufficient authority evidence. | What happens when required KYC context is incomplete? |
| DEFERRAL_ENGAGED validation snapshot | Documents hard final-commit block. | What happens when a critical upstream deferral signal is emitted? |
| Local V.I.K.I. mock ingestion receiver design | Defines VERITAS-side local mock receiver behavior and fail-closed rules before implementation. | How should VERITAS receive and validate synthetic local mock payloads without runtime integration? |
| Local V.I.K.I. mock receiver test fixture plan | Defines positive/negative/timeout/audit fixture coverage before any receiver or test implementation. | What fixture set should future receiver tests implement to prove fail-closed behavior? |

## 5. Static fixture ladder

Current static fixture ladder:

- `SAFE_PROCEED`
  - → `CONTINUE_TO_BIND_BOUNDARY`
  - → normal continuation
- `DENSITY_THROTTLED`
  - → `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED`
  - → soft intervention logged
- `ALGORITHMIC_HUMILITY_ENGAGED`
  - → `PAUSE_FOR_HUMAN_REVIEW`
  - → pause / human review
- `DEFERRAL_ENGAGED`
  - → `BLOCK_FINAL_COMMIT`
  - → hard final-commit block

Clarifications:

- `SAFE_PROCEED`, `DENSITY_THROTTLED`, `ALGORITHMIC_HUMILITY_ENGAGED`, and `DEFERRAL_ENGAGED` all have dedicated per-variant snapshot pages.
- The E2E sandbox validation snapshot remains a separate general E2E artifact.

## 6. What this documentation set validates

- The sandbox has a documented RSA / V.I.K.I. / VERITAS terminology boundary.
- The sandbox has a documented AML/KYC scenario map.
- The sandbox has a documented E2E demo plan.
- The sandbox has a documented validation snapshot for the current static E2E path.
- The sandbox has a static fixture matrix covering `SAFE_PROCEED`, `DENSITY_THROTTLED`, `ALGORITHMIC_HUMILITY_ENGAGED`, and `DEFERRAL_ENGAGED`.
- The sandbox demonstrates deterministic mapping from RSA-compatible upstream statuses to VERITAS continuation decisions.
- The sandbox shows how audit entries redact raw upstream intent/action fields by default.
- The sandbox remains reviewable without connecting live V.I.K.I. logic.

## 7. What this documentation set does not validate

- It does not connect live V.I.K.I. middleware.
- It does not validate V.I.K.I. internal reasoning.
- It does not prove that a real transaction or workflow is safe.
- It does not determine real-world compliance status.
- It does not implement production AML/KYC compliance.
- It does not provide regulatory approval.
- It does not provide third-party certification.
- It does not provide legal advice.
- It does not use real customer, financial, medical, KYC, or regulated data.
- It does not change production runtime governance.

## 8. Next safe sandbox steps

1. Keep the static fixture matrix and reviewer index synchronized as the canonical navigation hubs for the general E2E artifact and four per-variant snapshots.
2. Add a small generated sample output file from `examples/sandbox/rsa_veritas_e2e_harness.py` if maintainers want a committed output artifact.
3. Use the live integration reviewer checklist as a required review-gate artifact for future live adapter proposals.
4. Only after the static documentation set is reviewed, consider a separate design or contract artifact for live V.I.K.I. integration.

No live V.I.K.I. connection should be added in this PR.

Live integration should be a later design phase, not part of the static sandbox documentation pass.

The live V.I.K.I. integration page in this set is a future-design artifact only and does not introduce runtime integration.
