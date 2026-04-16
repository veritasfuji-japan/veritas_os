# Required Evidence Taxonomy v0（金融向け）

## Current behavior

現状ランタイムでは `required_evidence` / `missing_evidence` / `satisfied_evidence` は free string ベースで扱われます。

## Legacy / alias values

- free string は当面維持。
- taxonomy v0 で canonical key と alias を追加し、正本化を開始。

## Future tightening candidates

- 取り込み時に alias から canonical key へ正規化。
- 業界テンプレート単位で必須証拠プロファイルを強制。
- 移行が安定した後に未知キー拒否を段階導入。

## 用語

- `required_evidence`: 判定に必要な証拠キー群。
- `satisfied_evidence`: すでに充足済みの証拠キー群。
- `missing_evidence`: `required_evidence - satisfied_evidence` で算出。

機械可読の正本: `veritas_os/sample_data/governance/required_evidence_taxonomy_v0.json`。

## v0 カタログ

| canonical key | 表示名 | category | aliases |
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
