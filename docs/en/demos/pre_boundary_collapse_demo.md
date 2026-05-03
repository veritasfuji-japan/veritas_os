# Pre-Boundary Collapse Demo Walkthrough

## Why this scenario matters

This demo fixes a representative pre-bind governance risk: options can remain
formally visible (A/B/C/D) while iterative framing converges the practical
decision path before bind. The result is a structural gap where bind can look
formally valid even though upstream optionality has already collapsed.

## Mapping to Andrzej's minimal scenario

Andrzej's minimal scenario is:

- "A/B/C/D choices formally remain"
- "Iterative framing reinforces a narrow subset"
- "Effective optionality collapses before bind"

The fixture set in this PR encodes that exact sequence as four deterministic
phases with explicit expected participation and preservation states.

## VERITAS five-layer mapping

1. **Participation signal**
   - Each phase includes `participation_signal` with shared fields:
     `interpretation_space_narrowing`, `counterfactual_availability`,
     `intervention_headroom`, and `structural_openness`.
2. **Pre-bind structural detection**
   - `expected_participation_state` is fixed per phase to make structural drift
     reviewable before UI implementation.
3. **Preservation / intervention viability**
   - `expected_preservation_state` and `intervention_viability` define whether
     practical intervention capacity remains open, degrading, or collapsed.
4. **Bind-time admissibility**
   - `expected_bind_outcome` highlights that bind-time formality can remain
     valid while upstream decision space is structurally narrowed.
5. **Post-bind replay and lineage**
   - `lineage_evidence` pins minimum evidence categories required for replay,
     external review, and phase-by-phase provenance reconstruction.

## Phase semantics

- **Phase 1 — Participation / open framing**
  - A/B/C/D all exposed; optionality is full.
  - Participation is informational (`informative`), preservation is `open`.
- **Phase 2 — Iterative shaping**
  - A/B gain reinforcement; C/D exposure drops.
  - Formal optionality remains, but divergence shrinks.
  - Participation becomes `participatory`; preservation enters `degrading`.
- **Phase 3 — Pre-boundary collapse**
  - A/B converge to one trajectory; C/D lose viability.
  - Effective optionality is near zero.
  - Participation is `decision_shaping`; preservation is `collapsed`.
- **Phase 4 — Bind**
  - Bind can remain formally admissible.
  - Upstream decision space is already collapsed.
  - This phase encodes the governance-relevant gap explicitly.

## Meaning of "formally valid, structurally collapsed"

The phrase means syntax-level or contract-level validity at bind time does not
prove that pre-bind decision formation preserved meaningful optionality.
Accordingly, this demo treats pre-bind structure as a first-class review target,
not a post-hoc UI concern.

## Required lineage evidence

Each phase requires the following evidence keys:

- `framing_iteration_log`
- `option_exposure_trace`
- `counterfactual_probes`
- `intervention_record`
- `bind_context_snapshot`

This minimum set supports replayability, reviewer traceability, and consistent
cross-phase comparison.

## Scope guardrails for this PR

This PR intentionally does **not** implement UI, governance feed route changes,
OpenAPI changes, or bind-contract changes. It only fixes scenario fixtures,
walkthrough semantics, and validation tests so the demo is reviewable before
surface implementation.
