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

## Mission Control walkthrough surface (operator-facing)

Mission Control now renders this demo as a dedicated 4-phase walkthrough panel
when `demo_scenario=pre_boundary_collapse` is present in the governance layer
snapshot payload.

- Normal Mission Control mode: existing live governance timeline and artifact
  cards.
- Demo mode: additive "Pre-Boundary Collapse Demo · 4 phase walkthrough"
  section that displays:
  - phase label
  - `participation_state`
  - `preservation_state`
  - `intervention_viability`
  - `bind_outcome`
  - concise rationale
  - effective optionality and exposure/asymmetry/lineage summaries

This preserves vocabulary and backend contracts while making the paradox
visible at first glance: **formally valid, structurally collapsed**.

## Trajectory Shaping Lineage v0

Lineage is not only a record of what decision was eventually bound. In this
demo, lineage also records how the reachable decision space transformed before
bind.

`trajectory_shaping_lineage` is exposed as an additive snapshot field under
`governance_layer_snapshot` for `demo_scenario=pre_boundary_collapse`.

It captures a sequence of structural markers:

- exposure asymmetry emergence
- divergence contraction
- participation shift from informative/participatory to decision-shaping
- preservation degradation and intervention threshold crossing
- final bind evaluation over an already narrowed space

This sequence makes the pattern reusable for reviewers: they can reason about
where intervention remained viable, where structural loss began, and what bind
ultimately evaluated.

Known limitation: this is a deterministic representative demo lineage and is
not production certification.


## A/B/C/D Minimal Validation Case

The Pre-Boundary Collapse demo also includes an additive
`trajectory_shaping_lineage.abcd_minimal_validation_case` fixture. The case uses
only four options (`A`, `B`, `C`, and `D`) so reviewers can inspect the smallest
representative trajectory where option exposure, preservation, intervention
viability, and bind admissibility can separate.

The minimal A/B/C/D shape is useful because it reduces overgeneralization: the
reviewer does not need to infer the pattern from a rich domain scenario or a
large option set. Instead, the demo asks whether the same governance-relevant
separations still appear under constrained conditions:

- preservation degradation begins when A/B reinforcement first becomes detectable
- divergence contraction becomes measurable while C/D still formally remain
- intervention viability is lost before bind evaluates the final trajectory
- formal bind admissibility can still be valid over an already narrowed space

This helps VERITAS track what remained realistically preservable and enactable
before bind, while keeping the bind layer focused on the space it actually
evaluates. The result is a deterministic representative governance pattern, not
certification or a production governability claim.


## Dynamic Conditions Validation v0

Dynamic Conditions Validation v0 is the next deterministic step after the
A/B/C/D Minimal Validation Case. The minimal case shows that preservation
degradation, intervention viability loss, and formal bind admissibility can be
observed as separate structural states under constrained A/B/C/D conditions.
The dynamic case asks whether that same separation remains visible when several
trajectory-shaping pressures interact before bind.

The additive fixture is exposed as
`trajectory_shaping_lineage.dynamic_conditions_validation_case` and keeps the
same base option set (`A`, `B`, `C`, and `D`). It introduces four interacting
factors:

- reinforcement
- exposure asymmetry
- time pressure
- adaptive system behavior

The five phases keep the pattern compact: balanced option space, reinforcement
and exposure asymmetry, time-pressure compression of the intervention window,
adaptive stabilization of a narrowed trajectory, and formal bind evaluation over
the dynamically narrowed space. This makes the progressive degradation sequence
visible: governability is not a binary condition; it can degrade over time while
formal bind admissibility remains intact.

The validation compares preservation degradation, intervention viability loss,
and formal bind admissibility under dynamic pressure. It is a deterministic
representative validation pattern for review and regression testing. It is not
certification, a general dynamic trajectory engine, or a production
governability claim.


## Run and verification entrypoint

Run the representative demo from Mission Control with:

- `/?demo_scenario=pre_boundary_collapse`

Routing path under review:

- `page.tsx` reads `demo_scenario` and forwards it via `loadMissionControlIngressPayload`
- ingress calls `/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse`
- response carries `governance_layer_snapshot.demo_scenario = pre_boundary_collapse`
- Mission Control renders the demo walkthrough panel

## UI verification checklist

Confirm all of the following in the browser UI:

- `Pre-Boundary Collapse Demo · 4 phase walkthrough` is visible
- `formally valid, structurally collapsed` is visible
- `Phase 1 — Participation / open framing`
- `Phase 2 — Iterative shaping`
- `Phase 3 — Pre-boundary collapse`
- `Phase 4 — Bind`
- Phase 3 shows `participation_state: decision_shaping`
- Phase 3 shows `preservation_state: degrading` or `preservation_state: collapsed`
- Phase 4 shows `bind_outcome: FORMALLY_VALID_STRUCTURALLY_COLLAPSED`
- `lineage evidence summary` is present
- default `governance layer timeline` remains visible

## Reviewer framing

This walkthrough is a controlled representative demo for reviewer understanding.

- It is **not** a production certification claim
- It is **not** a replacement for bind-time governance enforcement
- It demonstrates the VERITAS pre-bind governance stack concretely
- It complements, rather than replaces, bind-time governance

## Known limitations

- Deterministic fixture-backed scenario
- Not an exhaustive production trace
- Does not imply legal or regulatory approval
