# AML/KYC Runtime Revalidation Scenarios (Future Design Note)

## Scope and current behavior boundary

This note is a future-facing, documentation-only scenario note. It applies the
concepts from the [Governance Drift design note](../architecture/governance-drift.md)
and the [Runtime Revalidation Trigger Model](../architecture/runtime-revalidation-trigger-model.md)
to concrete AML/KYC regulated-action examples for reviewer discussion.

This note does not change current VERITAS behavior:

- VERITAS v1 remains boundary-first and fail-closed.
- Bind boundaries remain the primary governance evaluation points.
- Runtime revalidation is not implemented by this note.
- The scenarios below are conceptual examples for reviewer discussion.
- This note does not claim continuous runtime governance support.

For the currently implemented deterministic AML/KYC fixture path, see
[AML/KYC Regulated Action Path](aml-kyc-regulated-action-path.md).

## Why AML/KYC is a useful scenario

AML/KYC workflows are useful examples because the governed decision may remain
nominally the same while the runtime context changes. A path that was admitted
for one customer, evidence set, risk level, reviewer approval, and action scope
may become materially different before a regulated consequence is finalized.

Examples of governance-relevant context changes include:

- customer risk changes.
- sanctions or watchlist evidence appears.
- evidence expires.
- delegated agents change.
- approval scope is exceeded.
- external reporting is introduced.
- data sensitivity changes.
- transaction scope expands.

In the future model, a Governed Decision Contract would provide the reference
context for deciding whether such changes remain within the admitted basis or
require Continue, Revalidate, Escalate, or Block routing. This note names
scenario patterns only; it does not define runtime scoring, policy enforcement,
wire schemas, or monitoring behavior.

## Scenario table

| Scenario | Governance-relevant state change | Drift dimension | Suggested outcome | Rationale |
|---|---|---|---|---|
| Low-impact formatting change | Output formatting or presentation changes without changing customer, authority, risk, data scope, or external effect. | none / low | Continue | No material governance divergence from the admitted context. |
| Risk level changed | Customer risk level changes from low to medium or high during the execution path. | risk drift | Revalidate | The original admissibility basis may no longer be sufficient. |
| Sanctions or watchlist hit detected | Sanctions, PEP, adverse media, or watchlist evidence appears after the initial decision was admitted. | risk drift / evidence drift | Escalate or Block | This is a high-impact regulated path; automated continuation may no longer be admissible. |
| Human approval scope exceeded | Execution expands beyond the approval scope originally granted by the reviewer. | accountability drift / scope drift | Escalate | Continuation requires reviewer or compliance authority. |
| Evidence expired or becomes invalid | Required KYC evidence expires, becomes stale, missing, contradicted, or invalid. | evidence drift | Revalidate or Block | The governed context no longer supports the prior admissibility conclusion. |
| Delegated agent changed | The execution path changes from the originally admitted agent, tool, or service to another delegated agent. | delegation drift / authority drift | Revalidate | Delegation may alter authority, accountability, or control. |
| External reporting or third-party transmission added | The workflow adds regulator reporting, third-party transmission, or external notification not present in the admitted context. | external impact drift / scope drift | Revalidate or Escalate | External impact changes the governed consequence. |
| Transaction scope expanded | The governed action expands from one customer, account, transaction, or jurisdiction to multiple targets. | scope drift / risk drift | Revalidate | Original authority and risk assumptions may not cover the expanded scope. |
| Accountability becomes ambiguous | The system cannot identify which reviewer, authority, policy basis, or agent chain is accountable for continuation. | accountability drift / indeterminate drift | Escalate; fail closed for regulated or high-impact paths | Indeterminate governance state should not silently proceed. |

## Lifecycle example

A future AML/KYC runtime revalidation design could be described as the following
reviewer-facing lifecycle:

```text
Initial AML/KYC decision admitted
→ Governed Decision Contract captures authority, approval, evidence, risk assumptions, constraints, and triggers
→ Bind boundary evaluates commitment readiness
→ Execution path begins
→ Governance-relevant state change occurs
→ Drift severity is classified
→ Continue / Revalidate / Escalate / Block
→ Outcome receipt and evidence-chain verification preserve reviewability
```

In VERITAS v1, the bind boundary remains the operative governance evaluation
point. The lifecycle above is a vocabulary for future admissibility-continuity
design discussion, not a statement that runtime monitoring or runtime
enforcement exists today.

## Why this matters

Without this model, an AML/KYC action could appear procedurally valid because it
passed an earlier checkpoint, even though the runtime context later changed. For
example, a path may have been admitted with fresh KYC evidence and a low-risk
customer classification, but the evidence could become stale or a sanctions hit
could appear before the regulated consequence is finalized.

The Governance Drift and Runtime Revalidation Trigger Model concepts help
describe how VERITAS could preserve admissibility continuity before regulated
consequences are finalized. The goal is to make the gap between the admitted
context and the current execution context visible to reviewers without changing
current v1 bind-boundary semantics.

## Non-goals

This note does not:

- implement AML/KYC runtime revalidation.
- implement sanctions screening.
- implement risk scoring.
- implement runtime monitoring.
- modify policy admissibility behavior.
- modify bind-boundary behavior.
- modify TrustLog persistence.
- define production compliance requirements.
- claim regulatory approval or production readiness.

## Reviewer interpretation

Reviewers should treat this page as an implementation-neutral scenario map. It
is intended to clarify future design vocabulary and review questions for
AML/KYC regulated-action paths while preserving the current VERITAS v1
boundary-first, fail-closed model.
