# Outcome Receipt v1 (local/offline)

Outcome Receipt v1 is a deterministic local/offline artifact that records post-execution outcome evidence for governed execution attempts.

It complements:

- Authority Evidence Ingestion v1
- Human Approval Receipt v1
- SaaS Permission-Change Governed Demo
- Bind Coverage Registry v1

It can represent:

- what execution was attempted
- final outcome (`commit`, `block`, `escalate`, etc.)
- commit/block/escalation/rollback status
- postcondition status (`passed`, `failed`, `skipped`, `indeterminate`)
- optional pre/post state fingerprints
- observed effects captured as local/offline fixtures
- deterministic `outcome_hash` for review and replay stability

Boundary in this PR:

- Local/offline deterministic artifact only
- No live SaaS/IdP/IAM/SSO/bank/sanctions/customer-system integrations
- Not proof of live production execution
- Not legal advice, regulatory approval, third-party certification, or production access-control validation

## Verified human approval proof binding

When an action requires human approval and bind-time validation uses a sealed `VerifiedHumanApprovalReceipt`, the resulting `OutcomeReceipt` carries the exact approval proof in metadata:

- `verified_human_approval_proof_hash`
- `verified_human_approval_receipt_id`
- `human_approval_verification_source`

These metadata fields are included in the deterministic outcome hash payload. Reviewers can therefore check that the committed outcome references the same verified approval proof that passed bind-time validation, rather than a later substituted approval artifact. No-approval-required paths remain valid without these metadata fields.
