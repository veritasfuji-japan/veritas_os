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
- Existing bind family contracts (`ExecutionIntent`, `BindReceipt`,
  `BindSummary`, flat bind compatibility fields) remain backward-compatible.
- Runtime behavior is unchanged unless producers explicitly attach a
  `participation_signal` payload.

## Why this shape

The schema is intentionally minimal but first-class so future PRs can add:

- pre-bind detection scoring
- preservation safeguards
- operator-facing detection timelines

without redefining public vocabulary or breaking existing bind contracts.
