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

This PR does **not** fully prove every transformation-stability path. It introduces the minimal additive contract needed as a foundation for future enforcement and transition-refusal behavior.

## Roadmap note

A centralized execution-intent refusal guard for non-promotable lineage is intentionally deferred to a follow-up PR to keep this change small and reviewable.
