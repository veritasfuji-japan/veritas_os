# Pre-bind formation invariants

This document introduces the v1 additive **lineage promotability** contract.

Detection tells us what state formed.
Preservation tells us whether intervention remains possible.
Lineage promotability defines whether the formed artifact can ever become bind-eligible.
Bind governance only commits already-eligible artifacts.

A bind-eligible artifact cannot emerge from a non-promotable lineage.

## Positioning

Non-promotability is **not** a third downstream check alongside detection and preservation.
It is a formation-space invariant that applies across artifact lineage.

- Detection/preservation remain observational and evidential surfaces.
- Lineage promotability defines whether that formation history can ever be eligible for bind commitment.
- Bind does not generate legitimacy; it commits artifacts that are already eligible in lineage terms.

## v1 canonical hard rule

In v1, only one canonical combination is hard-coded as non-promotable:

- `participation_state=decision_shaping`
- `preservation_state=collapsed`

For that pair, lineage promotability returns:

- `promotability_status=non_promotable`
- `reason_code=NON_PROMOTABLE_LINEAGE`
- `invariant_id=BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE`
- `transformation_stable=true`

All other combinations (including missing/unknown summaries) are backward-compatible as `promotable` in v1.

## Transformation stability expectation

The invariant should be preserved across persistence, aggregation, replay, export, summarization, reinterpretation, and repackaging surfaces.

This PR does **not** fully prove every transformation-stability path. It introduces a covered transition-path enforcement that refuses non-promotable lineage before execution-intent construction.

## Covered transition-path enforcement

On the covered `/v1/decide` transition path, the pipeline now evaluates
execution-intent transition eligibility from `lineage_promotability` and applies
structural refusal before any execution-intent lineage fields are formed in the
public response shape.

ExecutionIntent cannot be constructed from a non-promotable pre-bind formation lineage.

This is a formation transition refusal, not a bind-time rejection.

For `promotability_status=non_promotable`, the response emits an additive
`transition_refusal` object and keeps `execution_intent_id` / `bind_receipt_id`
unset (`null`) on that covered path. BindReceipt is not created on this
transition path and the case is not treated as `bind_outcome=BLOCKED`.

This enforces the invariant implementation stance that an invalid candidate
cannot be formed in a promotable shape, and bind does not manufacture
legitimacy.

## Actionability consistency under structural transition refusal

When `transition_refusal.transition_status=structurally_refused`, actionability
must be normalized to the same semantic meaning. In this state, the response
must not remain `actionable_after_bind`, and it must not imply that bind retry
can recover the refused artifact.

Formation transition refusal is not a bind retry condition.

A structurally refused formation must not be presented as actionable_after_bind.

This is **formation-reconstruction-required**, not bind-required. The operator
must reconstruct the decision from an eligible formation lineage, not retry
bind on the refused artifact.

In this state, `requires_bind_before_execution=false` does **not** mean the
artifact is executable; it means the artifact was refused before bind and
cannot progress to bind.

`transition_refusal` and actionability fields must remain semantically aligned.

The canonical recovery action is RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE.

Formation transition refusal must not select an execution action.

For structurally refused transition states, operator-facing semantics must stay
aligned across actionability and business/action guidance: `business_decision`
must be `HOLD`, `next_action` must be
`RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE`, and
`human_review_required` must be `true` on the covered `/v1/decide` path.

## Completed covered `/v1/decide` operator flow

On the covered `/v1/decide` path, `lineage_promotability` determines whether a
formation lineage can become bind-eligible.

When lineage is non-promotable, `transition_refusal` prevents ExecutionIntent
construction before bind and the response does not create ExecutionIntent or
BindReceipt fields on that covered path.

Actionability is normalized to `formation_transition_refused`, and operator
guidance is normalized to `HOLD` +
`RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE`.

The Console / Mission Control surface displays this as Formation Transition
Refused (pre-bind formation refusal), not bind failure.

This state is not `bind_outcome=BLOCKED`, and it is not bind-retryable.

A structurally refused formation is not bind-retryable.

The canonical recovery action is RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE.

The Console displays this as pre-bind formation refusal, not bind failure.
