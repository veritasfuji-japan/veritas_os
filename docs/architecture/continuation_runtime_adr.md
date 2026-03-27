# ADR: Continuation Runtime (Phase-1 — Shadow-Only)

## Status

Accepted (Phase-1)

## Context

VERITAS OS currently processes each `/v1/decide` request as a single-shot
evaluation:

```
ValueCore → Gate Decision → Persist → Replay / TrustLog
```

This is sufficient for isolated decisions but does not account for
**chain-level adjudication** — the ability to evaluate whether a prior
decision's supporting context has changed and whether continued reliance on
that decision remains justified.

### Problem

When an agent executes a multi-step plan, intermediate decisions may depend on
evidence or risk conditions that shift between steps.  Without chain-level
reassessment, the system cannot flag that a previously allowed action's
support has degraded or expired.

## Decision

Introduce a **Continuation Runtime** as a new, independent responsibility
alongside FUJI.

### Responsibility Boundary

| Module | Responsibility |
|---|---|
| **FUJI** | Final safety / policy gate (single-shot). Unchanged. |
| **Continuation Runtime** | Chain-level adjudication: evaluates whether a prior claim's support still holds across steps. |

The Continuation Runtime is **not** a replacement for FUJI.  It operates on a
different axis (temporal / chain-level) and produces an independent assessment.

### Pipeline Insertion Point

```
ValueCore → Gate Decision → Continuation Runtime (shadow) → Persist → Replay / TrustLog
```

The Continuation Runtime runs **after** the gate decision.  In phase-1 it
operates in **shadow-only** mode: it computes and logs its assessment but does
not alter the gate decision, the response payload (when the feature flag is
off), or any downstream behavior.

### gate.decision_status — Why It Does Not Change

`gate.decision_status` represents FUJI's single-shot safety verdict.  Its
semantics (`allow | modify | rejected | block | abstain`) are consumed by
every frontend panel, audit trail, and compliance report.  Changing its
meaning would:

- break backward compatibility for API consumers,
- blur the boundary between single-shot safety and chain-level adjudication,
- require a coordinated migration across frontend, audit, and compliance
  modules.

The Continuation Runtime expresses its assessment through a separate,
optional `continuation` field on the response.  This keeps the two axes
of evaluation cleanly separated.

### Phase-1 Scope (Shadow-Only)

- The `continuation` field is present **only** when the feature flag is
  enabled.
- When the feature flag is **off**, computation, response, logs, and UI
  behave identically to the pre-continuation codebase.
- `shadow_refusal` is computed but **never enforced** in phase-1.
- `refusal_boundary` is limited to `none` or `pre_tool_execution`.
- Frontend changes are limited to an optional card on existing pages — no
  new routes or product areas.

### Core Types

| Type | Purpose |
|---|---|
| `ContinuationClaim` | A claim that a prior decision's support still holds. |
| `SupportSnapshot` | A point-in-time snapshot of the evidence basis for a claim. |
| `ContinuationAssessment` | The runtime's evaluation of a claim (returned in the response). |

### Minimal Shape (`ContinuationAssessment`)

```
claim_id           : string
status             : "active" | "narrowed" | "revoked" | "expired"
support_status     : "valid" | "degraded" | "lost"
support_basis      : string[]
allowed_action_classes : string[]
revocation_reason_code : string | null
shadow_refusal     : boolean
refusal_boundary   : "none" | "pre_tool_execution"
```

## Non-Goals

- **Enforcement**: Phase-1 does not block, modify, or redirect any request
  based on continuation assessment.
- **UI product areas**: No new routes or dedicated pages.  Display is limited
  to a card on existing console pages.
- **Replacing FUJI**: Continuation Runtime is complementary, not a
  replacement.
- **Retroactive reassessment**: Phase-1 does not re-evaluate historical
  decisions; it only assesses forward from the current request.
- **Cross-session chains**: Phase-1 is scoped to a single session.

## Rollout Strategy

| Phase | Scope | Enforcement |
|---|---|---|
| **Phase-1** (current) | Shadow-only. Schema, types, and logging. Feature-flagged. | None |
| **Phase-2** | Metrics collection, dashboard visibility, alerting. | None (observe) |
| **Phase-3** | Soft enforcement: advisory warnings surfaced to operators. | Advisory |
| **Phase-4** | Hard enforcement: continuation assessment can block execution. | Active |

## Consequences

- New shared types added to `packages/types` and `veritas_os/api/schemas.py`.
- New JSON schema at `spec/continuation.schema.json`.
- `DecideResponse` gains an **optional** `continuation` field (null by
  default).
- Existing tests remain green; no behavioral change when feature flag is off.
- Future phases will add runtime logic, metrics, and enforcement incrementally.
