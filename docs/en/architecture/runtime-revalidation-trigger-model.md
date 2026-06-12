# Runtime Revalidation Trigger Model (Future Design Note)

This note extends the [Governance Drift design note](governance-drift.md)
by defining a future conceptual trigger model for classifying
Governance-Relevant State Changes into revalidation outcomes.

The model is implementation-neutral. It does not introduce runtime monitoring,
runtime revalidation, drift scoring, or enforcement changes. It does not claim
that VERITAS v1 provides continuous runtime governance. VERITAS v1 remains
boundary-first and fail-closed: bind boundaries remain the primary governance
evaluation points.

## Purpose

Governance drift describes divergence between the current execution state and
the governed context captured by a Governed Decision Contract. A future runtime
revalidation model would need to decide whether a detected state change can
continue under the admitted context, requires fresh evaluation, requires
reviewer escalation, or must be blocked.

This document names that future decision surface without changing current v1
behavior.

## Trigger source layers

Governance relevance can originate from two layers: explicit decision-layer
triggers and runtime material divergence detection. Future implementations
should treat explicit triggers as the primary source of governance criteria and
runtime inference as a secondary escalation mechanism.

### Decision-layer explicit triggers

Decision-layer explicit triggers are defined in the Governed Decision Contract
before execution. They describe the conditions under which the original
admissibility conclusion is no longer sufficient without fresh evaluation or
review.

Examples include:

- authority changes.
- execution scope expands.
- risk level increases.
- evidence expires.
- human approval scope is exceeded.
- delegated agent changes.
- external impact is introduced.
- accountability becomes ambiguous.

These triggers are reviewer-facing criteria. They should be explicit enough for
a reviewer to understand what was admitted, what would exceed the admitted
context, and what evidence would be needed to preserve admissibility continuity.

### Runtime material divergence detection

Runtime material divergence detection is a secondary future mechanism for
identifying unexpected divergence that was not explicitly defined in the
original governed context.

This layer may be useful when execution-path facts reveal a new or changed
condition that appears governance-relevant even though the Governed Decision
Contract did not name it directly. Examples may include an unexpected tool
handoff, a newly introduced external effect, a changed data sensitivity class,
or an authority ambiguity discovered during execution.

Runtime inference should not replace explicit governance criteria. It should not
silently expand the admitted context, infer new approvals, or treat absence of a
trigger as proof that a path remains admissible. Runtime inference should only
act as an escalation mechanism that brings uncertain or unexpected divergence to
fresh evaluation.

Where regulated, high-impact, security-sensitive, legal, compliance, or
approval-scoped actions are involved, an indeterminate governance state should
fail closed rather than continue by default.

## Revalidation outcome classes

A future trigger model may classify a Governance-Relevant State Change into one
of four conceptual outcomes.

### Continue

The state change is not governance-relevant, or it remains within the admitted
governed context captured by the Governed Decision Contract.

A Continue outcome means the prior admissibility basis is still sufficient for
the current execution state. It does not mean the system has performed a new
admissibility evaluation.

### Revalidate

The state change may affect admissibility and requires fresh evaluation against
the Governed Decision Contract.

A Revalidate outcome is appropriate when authority, scope, risk, evidence,
accountability, delegation, external impact, or policy conditions may have
changed enough that the previous bind-time conclusion may no longer be adequate.

### Escalate

The system cannot determine whether admissibility continuity remains valid, or
the change requires human, legal, compliance, security, or other designated
review.

An Escalate outcome is appropriate when the state is ambiguous, the consequence
is high-impact, the required reviewer authority is outside the automated path,
or the Governed Decision Contract requires non-automated review for that change
class.

### Block

The state change clearly violates admitted authority, constraints, policy
conditions, approval scope, evidence requirements, or risk limits.

A Block outcome is appropriate when the execution path no longer satisfies the
conditions under which it was admitted and no valid revalidation or escalation
path authorizes continuation.

## Drift severity bands

A future implementation may use drift severity bands to help route state
changes to conceptual outcomes. These bands are intentionally descriptive, not
numeric thresholds.

| Band | Conceptual meaning | Typical routing |
|---|---|---|
| none | No governance-relevant divergence from the admitted context is detected. | Continue. |
| low | Divergence is visible but does not materially affect admissibility continuity. | Log or attach to evidence without revalidation. |
| material | Divergence may affect authority, scope, risk, evidence, accountability, delegation, or external impact. | Revalidate. |
| critical | Divergence appears to exceed authority, constraints, approval scope, evidence requirements, policy conditions, or risk limits. | Escalate or Block. |
| indeterminate | The system cannot determine whether admissibility continuity remains valid. | Escalate; fail closed for regulated or high-impact actions. |

Low drift may be logged without revalidation when it remains within the
admitted governed context. Material drift should trigger revalidation. Critical
drift should escalate or block depending on whether an authorized review path
exists. Indeterminate drift should fail closed where regulated, high-impact,
security-sensitive, legal, compliance, or approval-scoped actions are involved.

## Relationship to VERITAS v1

This note preserves the current VERITAS v1 model:

- VERITAS v1 remains boundary-first and fail-closed.
- Bind boundaries remain the primary governance evaluation points.
- This note does not claim that current VERITAS provides continuous runtime
  governance.
- Runtime revalidation is a future extension.
- No enforcement semantics are changed by this PR.

The future trigger model described here should be read as a design vocabulary
for reviewer discussion and later specification work. It does not define a wire
schema, runtime service, scoring algorithm, policy engine behavior, or TrustLog
persistence requirement.

## Conceptual lifecycle

The intended future lifecycle is:

```text
Governed Decision Contract
→ Bind Boundary Evaluation
→ Execution Path
→ Governance-Relevant State Change
→ Drift Severity Classification
→ Continue / Revalidate / Escalate / Block
→ Outcome Receipt
→ Evidence Chain Verification
```

In VERITAS v1, the lifecycle remains anchored at bind boundaries. Future runtime
revalidation should preserve the boundary-first model by using the Governed
Decision Contract as the reference artifact for determining whether execution
state remains inside the admitted governed context.

## Non-goals

This note does not:

- implement runtime monitoring.
- implement runtime revalidation.
- implement drift scoring or severity thresholds.
- modify policy admissibility behavior.
- modify bind-boundary behavior.
- modify TrustLog persistence or evidence-chain verification.
- define a schema for trigger declarations or outcome receipts.
- claim that VERITAS currently provides continuous runtime governance.

## Reviewer interpretation

Reviewers should treat this trigger model as a future design note for
admissibility continuity. It clarifies how future VERITAS versions may classify
governance-relevant state changes while preserving current v1 boundary-first and
fail-closed semantics.
