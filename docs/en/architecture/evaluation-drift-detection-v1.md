# Evaluation Drift Detection v1

## 1. Purpose

Evaluation Drift Detection v1 records whether a comparison between Evaluation
Receipts suggests evaluator drift or unexplained evaluation behavior. It is a
schema-only artifact that references an Outcome Delta Attribution and records
whether the attributed or unattributed delta indicates possible evaluator drift,
unauthorized determiner influence, unexplained evaluation behavior, or
non-deterministically governed evaluation.

The artifact is intended to make drift signals reviewable without deciding that
a changed evaluation was automatically illegitimate.

## 2. Relationship to Outcome Delta Attribution

Outcome Delta Attribution records why an outcome changed between a prior
Evaluation Receipt and a current Evaluation Receipt. It captures the observed
outcome delta, candidate causes, confidence, unresolved delta state, supporting
evidence references, and recommended governance action.

Evaluation Drift Detection records whether the attributed or unattributed delta
indicates evaluation drift. It consumes the comparison established by Outcome
Delta Attribution and classifies the evaluation as stable, suspicious, drifted,
unexplained, or non-deterministically governed for future review.

In short:

- **Outcome Delta Attribution** records why an outcome changed.
- **Evaluation Drift Detection** records whether that attributed or unattributed
  delta indicates evaluation drift.

## 3. What counts as evaluation drift

Evaluation drift may be indicated when a changed outcome cannot be cleanly
explained by governed, authorized, and comparable evaluation state. Possible
causes include:

- unexplained outcome change
- unauthorized determiner influence
- evaluator version change without clear authority
- rule-set or threshold change affecting outcome
- policy identity ambiguity
- qualifier ambiguity
- material context ambiguity
- attribution inconclusive

A drift cause is not itself a runtime enforcement decision in v1. It records a
review signal and the evidence references that support that signal.

## 4. Evaluation consistency

Evaluation consistency requires VERITAS to distinguish between different kinds
of evaluation change before treating a result as stable. In particular, review
needs to distinguish:

- legitimate governed-state evolution
- evaluator change
- unauthorized determiner influence
- unexplained evaluation drift

This distinction helps reviewers separate expected governance evolution from
unexpected behavior. A consistent evaluator can produce a different result when
governed state legitimately changes; an inconsistent evaluator may require
requalification, qualifier reconciliation, escalation, refusal, or drift marking
in a future runtime integration.

## 5. Non-deterministically governed state

When the system cannot attribute the delta, v1 can mark the evaluation as
non-deterministically governed for future review. This status means the available
receipts and attribution are insufficient to explain why the outcome changed in
a governed and deterministic way.

The v1 marker is non-enforcing. It does not reject requests, alter admissibility,
change policy identity, mutate governance configuration, or trigger fail-closed
behavior.

## 6. v1 scope

Evaluation Drift Detection v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no fail-closed integration yet

This v1 foundation does not modify bind/admissibility logic, production
governance configuration, policy loading, TrustLog persistence, FUJI Gate
behavior, or any runtime resolver.

## 7. Future work

Future work can build on Evaluation Drift Detection v1 with:

- automated drift detection from Outcome Delta Attribution
- runtime fail-closed integration
- evaluator requalification workflow
- Trajectory-Level Admissibility Monitor v1 for sequence-level admissibility scope review
- Legitimacy Impact Review
- reviewer evidence packet integration
