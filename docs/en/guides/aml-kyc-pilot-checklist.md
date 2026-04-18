# AML/KYC Pilot Checklist (customer-ready)

## Purpose

Use this checklist to move the AML/KYC package from internal PoC execution to
customer pilot execution. It is scoped to implemented behavior only.

## Audience and use

- **Internal sponsor**: confirm pilot scope and decision gates before approval.
- **Operator**: execute runbook and collect machine-verifiable artifacts.
- **Evaluator / risk reviewer**: validate bounded behavior and failure handling.

## Pre-pilot readiness gate (before customer kickoff)

- [ ] Run dry-run once with current fixture.
- [ ] Run live runner against non-production environment.
- [ ] Confirm synthetic-only payload policy is active.
- [ ] Confirm no production API keys are embedded in scripts or docs.
- [ ] Confirm evidence bundle generation path is understood by operator.
- [ ] Confirm security/privacy boundaries are reviewed with sponsor.

Reference:
- [AML/KYC Operator Runbook](aml-kyc-operator-runbook.md)
- [External Audit Readiness Pack](../validation/external-audit-readiness.md)

## Pilot execution gate (during pilot)

- [ ] Use `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`.
- [ ] Enforce required-evidence mode `strict`.
- [ ] Confirm representative contracts:
  - sanctions partial match is not `proceed`
  - source-of-funds missing is not `APPROVE`
  - policy definition missing maps to policy-definition-required family
  - sufficient evidence low-risk path maps to proceed/APPROVE family
  - secure controls missing in secure posture maps to fail-closed `block`
- [ ] Record runner JSON report and keep immutable copy in pilot evidence folder.
- [ ] Log all warning/failure cases with explicit triage owner.

## Handoff gate (after pilot run)

- [ ] Provide acceptance criteria summary for sponsor sign-off.
- [ ] Provide evidence bundle example mapping (what was generated and why).
- [ ] Provide red-team/failure scenario outcomes, including unresolved risks.
- [ ] Provide customer handoff path and next decision checkpoint.

References:
- [Financial PoC Success Criteria](financial-poc-success-criteria.md)
- [Customer Handoff Path](aml-kyc-customer-handoff-path.md)

## Security and privacy boundaries (must-not-cross)

- Synthetic cases only. Do not use customer PII, account IDs, or sanctions list
  extracts in pilot package artifacts.
- Localhost HTTP is acceptable for local pilot rehearsal only. Any non-local
  environment must use HTTPS.
- Treat warnings about unknown required-evidence keys as review blockers until
  accepted explicitly by evaluator/sponsor.
- This package does not perform legal determination. It provides governance
  routing/evidence posture output only.
