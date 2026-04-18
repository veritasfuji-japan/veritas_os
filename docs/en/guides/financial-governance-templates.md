# Financial / Regulated Governance Templates

## Purpose

This template pack defines **governance expectations**, not legal conclusions, for
regulated decision domains where VERITAS output is consumed by financial and
compliance workflows.

This is the contract layer that the AML/KYC 1-day PoC quickstart executes
against. It is designed so customer, operator, and investor discussions share
the same factual semantics baseline.

The templates are intentionally designed to verify fail-closed behavior around:

- stop / hold / block actions under uncertainty,
- evidence-first progression,
- explicit human review boundaries, and
- separation between `gate_decision` and `business_decision`.

## Canonical Industry Pack Location

- Canonical fixture: `veritas_os/sample_data/governance/financial_regulatory_templates.json`

The fixture is a **pack object** with metadata and a `templates` array.

Pack-level fields include:

- `pack_id` / `pack_type` / `industry` / `version`
- `taxonomy_policy` (canonical taxonomy key policy and alias handling)
- `beachhead` (starter domain and representative template)

Each template entry includes:

- `question`
- `context`
- `expected_semantics.gate_decision`
- `expected_semantics.business_decision`
- `expected_semantics.next_action`
- `expected_semantics.required_evidence` / `missing_evidence`
- `expected_semantics.human_review_required`
- `expected_semantics.rationale_summary` / `rationale_expectations`

## Beachhead

Current beachhead is `aml_kyc` with template
`aml_kyc_high_risk_country_wire_manual_review`.
This domain is used as the first expansion anchor because it combines:

- high regulatory sensitivity,
- evidence-first progression requirements, and
- explicit human review boundaries.

AML/KYC beachhead evidence profile (canonical keys):

- `kyc_profile`
- `sanctions_screening_trace`
- `pep_screening_result`
- `source_of_funds_record`
- `approval_matrix`
- `audit_trail_export`
- `secure_controls_attestation`
- `policy_definition_record`

Runtime now treats this as a machine-readable profile (`aml_kyc_beachhead_v1`)
with `required`, `optional`, and `escalation_sensitive` key classes for
regression and response shaping. Runtime hardening now also emits unknown-key
warnings + telemetry counters instead of immediate hard-fail, so PoC and
template suites can quantify migration readiness before strict reject mode.
`strict` mode can now be enabled for AML/KYC beachhead experiments via runtime
context (`required_evidence_mode=strict`) to route unknown/profile misses into
stronger hold/review behavior while keeping full reject rollout deferred.

Canonical AML/KYC profile key list (`canonical_key_list`) is fixed as:

- `kyc_profile`
- `sanctions_screening_trace`
- `pep_screening_result`
- `source_of_funds_record`
- `approval_matrix`
- `audit_trail_export`
- `secure_controls_attestation`
- `policy_definition_record`
- `transaction_monitoring_trace`
- `rollback_plan`

Alias normalization is applied before profile matching so templates can still
provide legacy aliases (for example `sanctions_trace` or `pep_check`) while
runtime emits canonical keys for deterministic downstream processing.

## Role Split: Regulatory Templates vs PoC Questions

- **Regulatory templates** (`financial_regulatory_templates.json`)
  - Canonical, context-rich fixtures for regression and contract validation.
  - Carry full `context` and complete expected semantics for deterministic tests.
- **PoC questions** (`financial_poc_questions.json`)
  - Lightweight scenario prompts for demo and rapid PoC runs.
  - May reference `template_id` directly to avoid reverse lookup from
    `fixture_contexts`/category heuristics.

## What This Verifies

1. **Output contract compatibility**
   - Expected values are mappable into the existing public decision schema
     (`gate_decision`, `business_decision`, `required_evidence`,
     `human_review_required`).
2. **Governance posture under ambiguity**
   - Missing evidence, sanctions partial matches, high-risk-country transfer
     context, and undefined approval boundaries trend toward hold/review/block.
   - Sanctions partial matches and source-of-funds gaps are explicitly covered in
     AML/KYC regressions to reduce false-pass behavior.
3. **Operationally safe behavior**
   - Templates avoid investment advice and legal determinations, and instead
     require auditable escalation and evidence collection.

## Audience lens (same artifact, different question)

- **Customer asks**: "Can this prevent unsafe auto-proceed in AML/KYC ambiguity?"
  - Check `gate_decision` + `human_review_required` expectations.
- **Operator asks**: "Where do we fail and what evidence keys are missing?"
  - Check required/missing evidence keys and mismatch summaries from PoC runner.
- **Investor asks**: "Is this only narrative, or measurable?"
  - Check quantified pass/fail/warning output from the quickstart runner.

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


## AML/KYC pilot-ready packaging notes

For customer pilot enablement, pair this template contract with:

- [AML/KYC Pilot Checklist](aml-kyc-pilot-checklist.md)
- [AML/KYC Operator Runbook](aml-kyc-operator-runbook.md)
- [AML/KYC Customer Handoff Path](aml-kyc-customer-handoff-path.md)
- `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`
- `veritas_os/sample_data/governance/aml_kyc_failure_scenarios.json`
- `veritas_os/sample_data/governance/aml_kyc_expected_evidence_bundle_examples.json`

These artifacts stay bounded to implemented AML/KYC semantics and synthetic
inputs; they do not claim production-data readiness or legal determination.

## PoC Reproducibility Runner

To execute the lightweight PoC fixture set and compare expected semantics against
runtime output, use:

- `scripts/run_financial_poc.py`
- `veritas_os/scripts/financial_poc_runner.py`

Runbook:

- [Financial PoC Pack (1-day quickstart, EN)](poc-pack-financial-quickstart.md)
