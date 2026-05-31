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

## Irreversibility Horizon v0

Irreversibility Horizon v0 is the next compact marker layer after Dynamic
Conditions Validation v0. Dynamic Conditions Validation v0 shows that
preservation degradation, intervention viability loss, and formal bind
admissibility can remain separate while reinforcement, exposure asymmetry, time
pressure, and adaptive system behavior interact. Irreversibility Horizon v0 asks
how early structurally meaningful degradation becomes visible before operational
irreversibility stabilizes.

This is not a production irreversibility detection engine, a scoring model, or
a new enforcement gate. It is an additive deterministic representative
validation pattern under
`trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon`.
It marks representative temporal points in the existing dynamic sequence:

- **first structural degradation signal** — Phase 2, where reinforcement and
  exposure asymmetry first make dynamic asymmetry detectable while intervention
  remains realistic.
- **early warning** — Phase 3, where time pressure begins compressing the
  intervention window while meaningful intervention is still possible.
- **last meaningful intervention** — Phase 3, the last representative phase
  before adaptive stabilization where intervention remains meaningfully
  available.
- **irreversibility horizon** — Phase 4, where adaptive behavior stabilizes the
  narrowed trajectory and recovery becomes operationally hard.
- **bind after horizon** — Phase 5, where bind evaluates a formally admissible
  trajectory after the representative horizon has already been crossed.

The marker keeps the existing OpenAPI, bind contract, state family, and pre-bind
vocabulary unchanged. It does not make a production governability claim. Its
purpose is to make the temporal relationship visible: a trajectory can remain
formally admissible and inspectable at bind while meaningful intervention
capacity has already become operationally hard to recover upstream.

## Actor Recognition Gap v0

Actor Recognition Gap v0 is the next compact marker layer after
Irreversibility Horizon v0. Irreversibility Horizon v0 marks when structural
intervention capacity becomes operationally hard to recover; Actor Recognition
Gap v0 asks when the visibility of remaining intervention capacity begins
degrading before actors fully recognize the loss.

This layer does not infer actor psychology, predict actor beliefs, score actor
awareness, or introduce automatic enforcement. It is an additive deterministic
representative validation pattern under
`trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon.actor_recognition_gap`.
It marks a representative visibility gap between structural degradation and
actor recognition of reduced intervention capacity, without changing OpenAPI,
bind admissibility, state family, or pre-bind vocabulary.

The marker distinguishes these representative points:

- **actual degradation visible** — Phase 2, where reinforcement and exposure
  asymmetry first make structural degradation visible.
- **actor still perceives governable** — Phase 2, where the system may still
  appear formally open and procedurally coherent to the actor.
- **visibility degradation** — Phase 3, where time pressure compresses the
  intervention window and the visibility of remaining intervention capacity
  begins degrading.
- **recognition gap** — Phase 3, where a representative lag emerges between
  structural degradation and actor recognition of reduced intervention capacity.
- **recognition alignment** — Phase 4, where actors may begin recognizing the
  narrowed trajectory after adaptive behavior has made meaningful divergence
  operationally hard to recover.
- **bind after recognition gap** — Phase 5, where bind evaluates a formally
  admissible trajectory after the representative recognition gap has already
  occurred upstream.

The purpose is visibility, not formal assurance, prediction, or a production
governability claim. A system may remain formally open, procedurally admissible,
and apparently governable while meaningful divergence capacity has already
become progressively nonviable upstream.

## Governance Attack Surface Registry v0

Governance Attack Surface Registry v0 is the next compact visibility layer after
Actor Recognition Gap v0. Actor Recognition Gap v0 shows that actors may still
perceive a trajectory as governable after intervention capacity visibility has
started to degrade. The registry asks the meta-governance question that follows:
what structural safeguards prevent the governance process itself from becoming
the attack surface?

This layer does not claim complete security, certification, formal verification,
production threat coverage, automatic attack detection, or automatic
enforcement. It is an additive deterministic representative visibility registry
under `governance_layer_snapshot.governance_attack_surface_registry`. It keeps
the existing OpenAPI, bind contract, state family, pre-bind vocabulary,
Trajectory Shaping Lineage v0, Irreversibility Horizon v0, and Actor Recognition
Gap v0 behavior unchanged.

The registry focuses on representative governance-process failure classes where
governance evidence, approval, policy, escalation, or replay traces could be
manipulated, spoofed, bypassed, or made self-authorizing. Its first critical
emphasis is governance self-authorization / evidence-chain manipulation: the
risk is not only that a risky decision occurs, but that the evidence or approval
path can be shaped to make the decision look safe, admissible, or reviewed after
the fact.

Governance Attack Surface Registry v0 includes these representative failure
classes:

- **self_authorization** — governance or a governed component appears to
authorize its own action without independent governance authority.
- **evidence_chain_manipulation** — evidence used to justify a decision is
altered, reordered, omitted, or replaced after the fact.
- **approval_receipt_spoofing** — a human approval receipt or authorization proof
appears valid without reliable provenance.
- **policy_snapshot_drift** — bind-time policy cannot be reproduced because later
policy state differs from the decision-time snapshot.
- **escalation_suppression** — warning, pause, review, or escalation conditions
are not preserved in the governance trace.
- **replay_trace_tampering** — replayable audit traces are missing, reordered,
overwritten, or no longer reproduce the observed governance sequence.
- **recognition_gap_masking** — Actor Recognition Gap v0 / intervention capacity
visibility markers are not preserved as governance evidence.

It maps those failure classes to structural safeguards such as separation of
decision and governance authority, immutable evidence chains, policy snapshot
hashing, approval receipt provenance, replayable escalation traces, append-only
governance logs, and recognition gap visibility markers. This preserves
methodological restraint: the registry makes governance-process attack surfaces
visible as representative classes and safeguard mappings; it does not turn those
mappings into a scoring model, detection engine, blocking behavior, security
guarantee, or certification claim.

## Governance Safeguard Coverage Matrix v0

Governance Safeguard Coverage Matrix v0 is the compact follow-on layer after
Governance Attack Surface Registry v0. The registry identifies representative
failure classes where the governance process itself can become an attack surface
and lists structural safeguards that make those surfaces inspectable. The
coverage matrix makes that relationship easier to review by mapping each
failure class to a primary safeguard, supporting safeguards, and the visibility
evidence required to inspect the coverage.

The matrix asks: **Which structural safeguard covers which governance attack
surface, and what evidence makes that coverage visible?** It is exposed
additively under
`governance_layer_snapshot.governance_attack_surface_registry.safeguard_coverage_matrix`
so existing Trajectory Shaping Lineage v0, Dynamic Conditions Validation v0,
Irreversibility Horizon v0, Actor Recognition Gap v0, and Governance Attack
Surface Registry v0 consumers can continue to read their existing fields.

The v0 matrix uses a deterministic representative visibility model. Each row
keeps the relationship explicit:

- `failure_class_id` — the representative governance attack surface from the
  registry.
- `primary_safeguard_id` — the main structural safeguard that makes the surface
  visible.
- `supporting_safeguard_ids` — additional safeguards that support review.
- `evidence_requirement` — the evidence marker reviewers need in order to
  inspect the coverage.
- `visibility_question` — the review question the row is designed to answer.
- `coverage_state` — `representative_visibility_only` for v0 rows.
- `limitation` — an explicit non-claim attached to the row.

This preserves methodological restraint. The matrix does **not** claim complete
prevention, production security, scoring, automatic attack detection,
automatic enforcement, formal verification, or certification. It makes the
registry more inspectable without turning the registry into an enforcement
engine.

## Intervention Actionability Map v0

Intervention Actionability Map v0 is the compact next step after Governance
Safeguard Coverage Matrix v0. The previous layers make trajectory degradation,
irreversibility markers, actor recognition gaps, governance attack surfaces, and
safeguard evidence visible. The actionability map keeps that visibility layer
separate from automatic action, then asks: when a governance marker becomes
visible, what representative intervention category becomes actionable?

The demo exposes this as the additive field
`governance_layer_snapshot.intervention_actionability_map`. It maps visible
markers such as `first_structural_degradation_signal`, `early_warning`,
`last_meaningful_intervention`, `irreversibility_horizon`,
`actor_recognition_gap`, `bind_after_recognition_gap`, `self_authorization`,
`evidence_chain_manipulation`, `approval_receipt_spoofing`, and
`escalation_suppression` to representative categories such as `annotate`,
`warn`, `preserve_evidence`, `reframe`, `pause`, `escalate`,
`require_explicit_approval`, `freeze_bind_path`, and `post_horizon_review`.
Each mapping also names the evidence that should remain inspectable for later
review.

This layer preserves methodological restraint. It does not claim automatic
enforcement, automatic blocking, automatic escalation, scoring, certification,
production decisioning, formal verification, or production security coverage.
It shows representative intervention guidance only: visibility is connected to a
human-reviewable action category, while automatic action remains out of scope.
## Intervention Actionability Map contract v0

Intervention Actionability Map v0 has a checked-in schema and golden fixture:

- `docs/en/demo/schemas/intervention-actionability-map-v0.schema.json`
- `docs/en/demo/fixtures/intervention-actionability-map-v0.json`

The contract keeps the layer deterministic and reviewable. It verifies that
visible governance markers map only to known representative intervention
categories, that evidence-to-preserve guidance remains present, and that the
layer remains non-enforcement and non-certification.

This contract does not make the map an automatic enforcement engine, blocking
engine, escalation system, scoring model, production decisioning layer,
certification, or production security guarantee.


## Governance Evidence Packet v0

Governance Evidence Packet v0 is the compact reviewer packet added after
Intervention Actionability Map v0. The previous layers emit markers, registries,
matrices, and representative actionability guidance; the packet groups those
existing layers into one reviewer-ready summary of what evidence should be
inspected.

The packet is exposed additively at
`governance_layer_snapshot.governance_evidence_packet` for the
`pre_boundary_collapse` demo. It does not change runtime bind behavior, OpenAPI,
state family, pre-bind vocabulary, Trajectory Shaping Lineage v0, Governance
Attack Surface Registry v0, Governance Safeguard Coverage Matrix v0, or
Intervention Actionability Map v0.

The v0 packet summarizes:

- decision context and bind outcome
- trajectory shaping lineage
- dynamic degradation signals
- irreversibility horizon markers
- actor recognition gap markers
- governance attack surface registry references
- safeguard coverage matrix references
- intervention actionability map references
- preserved evidence refs that reviewers should inspect
- reviewer questions and explicit limitations

This is a deterministic representative reviewer packet. It improves reviewer
readability by showing how decision-space narrowing, governability degradation,
safeguard visibility, and representative intervention categories connect across
existing evidence layers.

The packet preserves methodological restraint. It does not claim certification,
automatic enforcement, automatic attack detection, automatic blocking, a scoring
model, a legal conclusion, formal verification, complete prevention, production
security, or production security coverage. Its purpose is to help reviewers see
what to inspect, not to have VERITAS automatically decide correctness.
