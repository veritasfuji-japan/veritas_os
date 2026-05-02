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
