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

## Verified human approval proof continuity

When human approval is required, the manifest summary includes `verified_human_approval_proof_hash` and records whether human approval was required for the chain. This lets reviewers verify continuity across:

- the decision artifact,
- the bind receipt or bind-time decision evidence,
- the human approval receipt and sealed verified proof,
- the outcome receipt, and
- the evidence-chain manifest.

The manifest-level proof hash must match the proof hash embedded in the `OutcomeReceipt` metadata and the actual `VerifiedHumanApprovalReceipt.verification_proof_hash`. If policy explicitly allows no human approval, the manifest may set human approval as not required and omit the proof hash while preserving valid no-approval flows.
