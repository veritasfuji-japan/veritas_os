# Evidence Chain Manifest v1 (local/offline)

Evidence Chain Manifest v1 is a deterministic local/offline governance artifact for one governed execution attempt.

It links the execution governance chain in one inspectable object:

- AuthorityEvidence
- HumanApprovalReceipt
- BindReceipt / bind-time decision evidence
- OutcomeReceipt
- BindCoverageEntry-style operation coverage metadata

The manifest helps reviewers inspect the full governance chain from pre-execution authority and human approval through bind-time decisioning to post-execution outcome evidence.

## Chain states

A manifest can represent these deterministic states:

- `complete`
- `blocked`
- `incomplete`
- `indeterminate`

## Boundary in this PR

In this PR, Evidence Chain Manifest v1 remains local/offline only.

It is **not**:

- proof of live production execution
- connected to live SaaS, IdP, IAM, SSO, bank, sanctions, customer, or production approval systems
- legal advice
- regulatory approval
- third-party certification
- production access-control validation
