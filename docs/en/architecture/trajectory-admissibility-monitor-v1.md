# Trajectory-Level Admissibility Monitor v1

## 1. Purpose

Trajectory-Level Admissibility Monitor v1 records whether a sequence of
Evaluation Receipts, Outcome Delta Attributions, and Evaluation Drift Detections
suggests admissibility scope expansion over time. It is a schema-only artifact
for making trajectory-level admissibility movement visible to reviewers.

The monitor does not decide that any individual bind or evaluation event is
invalid. Instead, it records whether repeated locally valid events may be
widening the admissibility envelope, delegated authority, requalification
posture, refusal boundary, or escalation requirements across the trajectory.

## 2. Relationship to previous artifacts

Trajectory-Level Admissibility Monitor v1 builds on the preceding schema-only
foundations:

- **Evaluation Receipt v1** records one evaluation instance, including the
  governed evaluation inputs, outcome, determiners, and evidence references for
  that instance.
- **Outcome Delta Attribution v1** explains outcome changes between two
  Evaluation Receipts, including candidate causes, confidence, unresolved delta
  state, and recommended governance action.
- **Evaluation Drift Detection v1** records suspected evaluator drift,
  unauthorized determiner influence, unexplained evaluation behavior, or
  non-deterministically governed evaluation.
- **Trajectory-Level Admissibility Monitor v1** examines the sequence across
  repeated evaluations to determine whether the admissibility scope appears to
  be expanding over time.

## 3. Strategic Admissibility Drift

Strategic admissibility drift can occur when individual bind or evaluation
events appear locally valid while the overall admissibility envelope expands
across repeated continuity events. A single event may preserve evidence,
complete requalification, or classify a change as low risk; however, the
sequence may still produce a more permissive governance posture than the
original authority scope allowed.

This artifact is intended to make that trajectory visible. It records whether
continuity is preserving evidence or beginning to manufacture legitimacy by
accumulating small, locally acceptable changes into a broader authority scope.

## 4. What the monitor captures

The monitor captures reviewable evidence for trajectory-level admissibility
movement, including:

- evaluation receipt references
- attribution references
- drift detection references
- trajectory window
- baseline and current authority scope
- admissibility scope change
- continuity event summary
- trajectory risk signals
- trajectory status
- recommended governance action

These fields are informational in v1 and provide a foundation for later reviewer
and runtime integrations.

## 5. v1 scope

Trajectory-Level Admissibility Monitor v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no fail-closed integration yet

This v1 foundation does not modify bind/admissibility logic, production
governance configuration, policy loading, TrustLog persistence, FUJI Gate
behavior, continuity handling, or any runtime resolver.

## 6. Future work

Future work can build on Trajectory-Level Admissibility Monitor v1 with:

- automated trajectory analysis from Evaluation Receipts
- strategic admissibility drift detection
- legitimacy impact review using [Legitimacy Impact Review v1](legitimacy-impact-review-v1.md)
- governance exhaustion safeguards
- runtime fail-closed integration
- reviewer evidence packet integration
