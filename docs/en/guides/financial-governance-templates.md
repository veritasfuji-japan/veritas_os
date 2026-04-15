# Financial / Regulated Governance Templates

## Purpose

This template pack defines **governance expectations**, not legal conclusions, for
regulated decision domains where VERITAS output is consumed by financial and
compliance workflows.

The templates are intentionally designed to verify fail-closed behavior around:

- stop / hold / block actions under uncertainty,
- evidence-first progression,
- explicit human review boundaries, and
- separation between `gate_decision` and `business_decision`.

## Fixture Location

- Canonical fixture: `veritas_os/sample_data/governance/financial_regulatory_templates.json`

Each template entry includes:

- `question`
- `expected_governance_behavior.gate_decision`
- `expected_governance_behavior.business_decision`
- `expected_governance_behavior.required_evidence`
- `expected_governance_behavior.human_review_required`
- `expected_governance_behavior.rationale_expectations`

## What This Verifies

1. **Output contract compatibility**
   - Expected values are mappable into the existing public decision schema
     (`gate_decision`, `business_decision`, `required_evidence`,
     `human_review_required`).
2. **Governance posture under ambiguity**
   - Missing evidence, sanctions partial matches, high-risk-country transfer
     context, and undefined approval boundaries trend toward hold/review/block.
3. **Operationally safe behavior**
   - Templates avoid investment advice and legal determinations, and instead
     require auditable escalation and evidence collection.

## Domain Coverage

- Credit underwriting
- Fraud detection
- AML / KYC
- Sanctions screening
- Client suitability checks
- High-risk transaction hold/release control
- Approval boundary undefined stop condition

## Security Note

Template fixtures should remain synthetic and free of PII, account numbers,
production sanctions watchlists, and customer-identifiable traces.
