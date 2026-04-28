# Pre-Bind Participation Signals (First-Class Schema)

This document defines the additive **participation admissibility** schema layer
introduced upstream of the existing bind boundary.

## Positioning

VERITAS currently governs commitment at bind time via:

`decision -> execution_intent -> bind_receipt`

This remains unchanged.

The participation layer is an upstream signal family:

`participation_signal -> decision -> execution_intent -> bind_receipt`

It does **not** replace bind governance and does not grant execution permission.

## Admissibility distinction

- **Admissibility of participation:** whether decision formation remains
  governable before commitment (pre-bind).
- **Admissibility of commitment:** whether an execution intent may cross the
  bind boundary and commit real-world effect.

These are intentionally separate contracts.

## Schema vocabulary (frozen for this layer)

`ParticipationSignal` carries:

- `interpretation_space_narrowing`: `open|narrowing|constrained|closed`
- `counterfactual_availability`: `high|medium|low|none`
- `intervention_headroom`: `high|medium|low|none`
- `structural_openness`: `open|partially_open|fragile|closed`
- `participation_admissibility`: `admissible|review_required|inadmissible|unknown`

The signal family name is fixed as `participation_signal`.

## Current integration scope

- `DecideResponse.participation_signal` is optional and additive.
- `DecideResponse.pre_bind_detection_summary` and
  `DecideResponse.pre_bind_detection_detail` are optional additive operator
  surfaces derived from structural participation signals.
- `DecideResponse.pre_bind_preservation_summary` and
  `DecideResponse.pre_bind_preservation_detail` are optional additive operator
  surfaces describing whether meaningful intervention is still realistic.
- Existing bind family contracts (`ExecutionIntent`, `BindReceipt`,
  `BindSummary`, flat bind compatibility fields) remain backward-compatible.
- Runtime behavior is unchanged unless producers explicitly attach a
  `participation_signal` payload.

## Pre-bind structural detection semantics (v1)

The repository now fixes a minimal structural classifier upstream of bind:

- `informative`: system behavior remains primarily informational and does not
  materially narrow interpretation or option space.
- `participatory`: structural participation impact is emerging through framing,
  reinforcement, or alignment while alternatives remain open.
- `decision_shaping`: structural signals indicate interpretation/option space is
  materially narrowed and counterfactual availability is reduced.

Detection is based on the participation signal family only (not interaction
frequency/length). The v1 evaluator consumes:

- `interpretation_space_narrowing`
- `counterfactual_availability`
- `intervention_headroom`
- `structural_openness`

This layer reports threshold crossing only. It does **not** trigger a
preservation policy action in this PR.

## Pre-bind preservation semantics (v1, additive)

Preservation is a separate layer from detection:

- detection: **was** a structural threshold crossed?
- preservation: **when observed now**, is meaningful intervention still viable?

The preservation state family is:

- `open`: intervention/correction/counterfactual recovery remain viable.
- `degrading`: intervention remains possible but structural openness is eroding.
- `collapsed`: meaningful intervention is no longer realistically available
  even if bind has not happened yet.

The minimal preservation evaluator uses structural openness plus intervention
viability and counterfactual recovery possibility. It does not replace
bind-time commitment admissibility and does not auto-enforce heavy policy
actions in this PR.

## Why this shape

The schema is intentionally minimal but first-class so future PRs can add:

- pre-bind detection scoring
- preservation safeguards (without collapsing into detection semantics)
- operator-facing detection timelines

without redefining public vocabulary or breaking existing bind contracts.

## Internal composition boundaries (non-breaking refactor)

To keep future governance layers reviewable without changing public contracts,
`/v1/decide` now follows a contract-centered split:

- **Route orchestration:** `veritas_os.api.routes_decide`
  - receives request, delegates orchestration, returns response.
- **Operator/public assembly:** `veritas_os.api.decide_operator_assembly`
  - assembles bind/WAT operator summary/detail and canonical drift vocabulary.
- **Pre-bind evaluators:**
  - detection: `veritas_os.core.participation_detection`
  - preservation: `veritas_os.core.preservation_evaluator`
- **Evaluation-to-assembly adapter:** `veritas_os.core.pipeline.governance_layers`
  - computes typed governance snapshot and maps it into additive
    `DecideResponse` fields.

This split keeps `decision`, `execution_intent`, `bind_receipt`, and
`bind_summary` contracts stable while making additional governance layers easier
to add without route bloat.
