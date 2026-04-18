# AML/KYC Pilot Evidence Map (Synthetic Pilot Scope)

**Scope boundary:** This map is for synthetic-data pilot validation and handoff preparation. It is not a claim of production AML legal determination.

## 1) Pilot package components

| Component | Purpose | Source |
|---|---|---|
| Quickstart | One-day executable PoC flow | `docs/en/guides/poc-pack-financial-quickstart.md` |
| Operator checklist | Run/handoff/security gate | `docs/en/guides/aml-kyc-pilot-checklist.md` |
| Governance templates | Contract and expected gate behavior | `docs/en/guides/financial-governance-templates.md` |
| Customer handoff path | Pilot-to-customer transition framing | `docs/en/guides/aml-kyc-customer-handoff-path.md` |
| Evidence taxonomy | Required/missing/satisfied evidence semantics | `docs/en/governance/required-evidence-taxonomy.md` |
| Fixture cases | Synthetic pilot cases | `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json` |
| Expected evidence examples | Bundle expectation examples | `veritas_os/sample_data/governance/aml_kyc_expected_evidence_bundle_examples.json` |

## 2) Validation checkpoints (minimum external-review set)

1. Confirm synthetic-only scope.
2. Confirm strict required-evidence mode in pilot runs.
3. Confirm representative outcome families are non-permissive for missing critical evidence.
4. Produce and retain runner JSON outputs.
5. Generate evidence bundle and verify acceptance checklist + verifier output.

References:
- [AML/KYC Pilot Checklist](../guides/aml-kyc-pilot-checklist.md)
- [External Audit Readiness](external-audit-readiness.md)

## 3) Reviewer-ready artifact bundle (recommended)

- Pilot run report JSON
- Selected decision/incident evidence bundle
- `verification_report.json`
- `acceptance_checklist.json`
- Minimal traceability note (which case IDs were used)

## 4) Not-yet-guaranteed (explicit)

- No claim of regulator-approved AML/KYC engine certification.
- No claim that synthetic pilot outcomes equal production legal outcomes.
- No claim that customer-specific sanctions/provider integrations are already certified.

