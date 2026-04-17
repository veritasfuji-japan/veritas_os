# Required Evidence Taxonomy v0 (Financial)

## Current behavior

`required_evidence`, `missing_evidence`, and `satisfied_evidence` are carried in runtime context.
For the financial industry pack, canonical taxonomy keys are the primary contract.

## Legacy / alias values

- Canonical keys should be emitted first.
- Free-string evidence values are treated as alias inputs only.
- Taxonomy v0 introduces canonical keys and aliases for normalization.

## Future tightening candidates

- Canonicalize at ingestion (alias -> canonical key).
- Enforce per-domain required evidence profiles.
- Reject unknown keys only after migration telemetry is stable.

## Definitions

- `required_evidence`: evidence keys required for governance-safe decisioning.
- `satisfied_evidence`: subset already available.
- `missing_evidence`: computed as `required_evidence - satisfied_evidence`.

Machine-readable source: `veritas_os/sample_data/governance/required_evidence_taxonomy_v0.json`.

## v0 catalog

| canonical key | display label | category | aliases |
|---|---|---|---|
| `credit_bureau_report` | Credit Bureau Report | credit_underwriting | `bureau_report`, `credit_report`, `credit_file` |
| `kyc_profile` | KYC Profile | identity_and_aml | `know_your_customer_profile`, `customer_identity_profile` |
| `pep_screening_result` | PEP Screening Result | identity_and_aml | `pep_check`, `politically_exposed_person_screen` |
| `sanctions_screening_trace` | Sanctions Screening Trace | sanctions | `sanctions_trace`, `ofac_screening_trace` |
| `source_of_funds_record` | Source of Funds Record | aml_enhanced_due_diligence | `source_of_funds_document`, `sof_record` |
| `approval_matrix` | Approval Matrix | governance_control | `approval_boundary_matrix`, `authority_matrix` |
| `transaction_monitoring_trace` | Transaction Monitoring Trace | transaction_monitoring | `transaction_monitoring_log`, `tml_trace` |
| `audit_trail_export` | Audit Trail Export | audit_and_attestation | `audit_log_export`, `audit_evidence_export` |
| `secure_controls_attestation` | Secure Controls Attestation | security_controls | `security_controls_attestation`, `secure_controls_ready_attestation` |
| `rollback_plan` | Rollback Plan | operational_resilience | `rollback_strategy`, `rollback_support_plan` |
| `policy_definition_record` | Policy Definition Record | policy_governance | `policy_owner_confirmation`, `policy_definition_required_record` |
