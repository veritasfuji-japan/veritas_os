# Governance Drift Design Note

## Purpose and scope

This design note formalizes three future-facing governance concepts for
VERITAS as a decision governance and bind-boundary control plane:

1. Governed Decision Contract
2. Governance-Relevant State Change
3. Governance Drift

The note is implementation-neutral. It does not introduce runtime monitoring,
change enforcement semantics, or claim continuous runtime governance support in
the current implementation. VERITAS v1 remains boundary-first and fail-closed:
bind boundaries are the primary governance evaluation points.

## Governed Decision Contract

A governed decision contract is the reference artifact that binds a decision
object to the governance state under which it was considered admissible.

Conceptually, the contract captures:

- decision reference
- authority model
- admissibility conditions
- constraints
- evidence requirements
- risk assumptions
- accountability structure
- revalidation triggers

The contract is not merely a copy of the decision payload. It records the
context that made the decision governable at the time of evaluation. This
context may include the policy snapshot, authority evidence, required approvals,
constraint set, risk classification, evidence freshness expectations, and the
actors or systems accountable for the decision path.

Admissibility is relational, not intrinsic. A decision is not admissible by
itself. It is admissible only in relation to the governed context that justified
it. If the relevant authority, scope, constraints, evidence, risk assumptions,
or accountability structure changes, the prior admissibility conclusion may no
longer be sufficient for a later execution state.

## Governance-Relevant State Change

A governance-relevant state change is a runtime or execution-path change that
may materially alter the authority, scope, constraints, risk, evidence context,
accountability structure, delegation chain, or external impact under which the
decision was originally admitted.

Examples include:

- authority changes
- execution scope expands
- risk level increases
- evidence becomes missing, invalid, or expired
- delegated agent changes
- human approval scope is exceeded
- external impact is introduced or increased
- accountability becomes ambiguous

Not every runtime change requires revalidation. Implementation details, timing,
transport retries, local formatting, or equivalent non-governance changes may
not affect the admissibility basis. Only governance-relevant changes should be
candidates for revalidation, escalation, or blocking.

A future runtime mechanism should therefore distinguish ordinary execution
variance from changes that alter the governed relationship between the decision
object and its admitted context.

## Governance Drift

Governance drift is the growing divergence between the current execution state
and the governed context captured by the governed decision contract.

Governance drift is not necessarily an immediate admissibility failure. Instead,
it is an early signal that admissibility continuity may be degrading. A drift
signal indicates that the execution path may still be valid, but the distance
between the current state and the admitted governance context is increasing.

Drift dimensions include:

- authority drift: the actor, role, authority evidence, or validity window no
  longer matches the admitted authority context.
- scope drift: the execution path expands beyond the originally admitted action,
  target, tenant, data class, or operational boundary.
- risk drift: the risk profile increases or new risk factors become material.
- evidence drift: required evidence becomes stale, missing, invalid,
  contradicted, or insufficient for the current execution state.
- accountability drift: ownership, reviewer responsibility, approver scope, or
  escalation responsibility becomes unclear.
- delegation drift: the agent, tool, service, or delegated execution chain
  changes in a way that affects authority or control.
- external impact drift: the path gains, increases, or changes external effects
  that were not part of the admitted context.

This concept moves VERITAS from merely detecting governance failure toward
future detection of governance degradation before commitment. The purpose is to
preserve admissibility continuity where possible and to identify when an
execution path should be revalidated before crossing or continuing past a
meaningful boundary.

## Lifecycle relationship

The intended conceptual lifecycle is:

```text
Decision Object
→ Governed Decision Contract
→ Bind Boundary Evaluation
→ Execution Path
→ Governance-Relevant State Change Detection
→ Runtime Revalidation / Escalation / Block
→ Outcome Receipt
→ Evidence Chain Verification
```

In the current v1 model, bind boundaries remain the primary governance
evaluation points. Existing fail-closed bind semantics are not changed by this
note. Runtime revalidation, escalation, or blocking based on governance drift is
a future extension.

A future implementation may use the governed decision contract as the reference
artifact for deciding whether a detected state change is governance-relevant and
whether the execution path must be revalidated. Such an implementation should
preserve the v1 boundary-first model: commitment should remain governed by
explicit bind evaluation, and indeterminate governance state should fail closed
rather than silently proceed.

## Non-goals

This note does not:

- implement runtime monitoring or drift detection.
- modify policy admissibility behavior.
- modify bind-boundary behavior.
- modify TrustLog persistence or evidence-chain verification.
- define a wire schema for governed decision contracts.
- define thresholds for runtime revalidation.
- claim that VERITAS currently provides continuous runtime governance.

## Reviewer interpretation

Reviewers should treat governance drift as a design concept for future
admissibility continuity support. It is compatible with the current VERITAS
model because it keeps bind boundaries as the authoritative enforcement points
while naming the state that future runtime revalidation would need to compare
against.
