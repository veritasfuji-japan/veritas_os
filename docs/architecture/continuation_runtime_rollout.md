# Continuation Runtime — Rollout Plan

**Status**: Proposed (Phase-1 design boundary)
**Date**: 2026-03-28

---

## Overview

The Continuation Runtime is introduced in three strictly separated phases. Each
phase has explicit entry criteria, exit criteria, and a verification protocol.
No phase advances without architectural review.

The guiding principle is **incremental confidence**: each phase must demonstrate
that the runtime produces correct, explainable results before the next phase
adds any coupling to the execution path.

---

## Phase-1: Observe / Shadow

### Goal

Demonstrate that the Continuation Runtime can run revalidation beside the
existing pipeline, produce consistent snapshots and receipts, and generate
meaningful divergence data — without affecting any existing behavior.

### Mode

- Feature flag: `VERITAS_CAP_CONTINUATION_RUNTIME` (default: `false`)
- When `false`: zero code paths executed, zero allocations, zero log entries,
  zero response changes. The system behaves exactly as it does today.
- When `true`: revalidation runs as a sidecar between stage 5b (Critique) and
  stage 6a (FUJI Pre-check). Results are written to internal shadow artifacts
  only.

### Scope

- `ContinuationClaimLineage` creation and lifecycle management.
- `ClaimStateSnapshot` production via revalidation.
- `ContinuationReceipt` emission and storage.
- `ContinuationLawPack` loading and version tracking.
- Shadow recommendation generation (continue / narrow / escalate / suspend /
  revoke) — logged but not acted upon.
- Divergence detection: comparison between shadow recommendations and actual
  pipeline outcomes.

### What Phase-1 does NOT do

- Modify `PipelineContext` fields consumed by FUJI or the gate.
- Change `gate.decision_status` values or semantics.
- Add new API routes or response fields visible to clients.
- Add new UI components or dashboard pages.
- Enforce any continuation-based blocking or modification.
- Alter self-healing loop behavior.

### Entry Criteria

- ADR, glossary, and overview documents are reviewed and accepted.
- Responsibility boundaries between FUJI and Continuation Runtime are
  documented and understood by the team.
- Feature flag mechanism is confirmed to provide complete isolation.

### Exit Criteria (Phase-1 Success)

Phase-1 is considered successful when all of the following are demonstrated:

1. **Shadow consistency**: Revalidation produces deterministic snapshots given
   the same inputs and law pack version (verified via replay).
2. **Receipt completeness**: Every revalidation produces a receipt with
   sufficient detail for audit reconstruction.
3. **Divergence observability**: Cases where shadow recommendations differ from
   actual pipeline outcomes are detectable and explainable.
4. **Zero interference**: With flag on, all existing tests pass without
   modification. With flag off, the system is bytewise identical in behavior.
5. **Latency budget**: Shadow revalidation adds less than 5ms p99 to pipeline
   latency (configurable threshold).
6. **Snapshot/receipt separation holds**: No instance where runtime logic reads
   receipts for state, or snapshots carry audit-level detail.

### Verification Protocol

- Run full existing test suite with flag off → all pass, no new output.
- Run full existing test suite with flag on → all pass, original outputs
  identical, shadow artifacts produced as side-effects.
- Replay selected decisions with flag on → shadow artifacts are reproducible.
- Review shadow divergence log for false positives and unexplained assessments.

---

## Phase-2: Advise (Future)

### Goal

Make continuation assessments visible to operators without affecting execution.

### Mode

- Feature flag: `VERITAS_CAP_CONTINUATION_ADVISE` (default: `false`,
  requires `VERITAS_CAP_CONTINUATION_RUNTIME` = `true`)
- Continuation assessments appear in response extras, audit logs, and
  potentially operator-facing UI elements (read-only indicators).

### Scope

- Advisory signals in response extras (e.g., `continuation.shadow_recommendation`).
- Operator-visible warnings when continuation standing is narrowed or at risk.
- Audit log entries that link continuation receipts to TrustLog events.
- No blocking, no modification of `decision_status`, no pipeline flow changes.

### Entry Criteria

- Phase-1 exit criteria fully met.
- Divergence data reviewed and deemed consistent.
- Architectural review approves advise-mode coupling points.

### Exit Criteria

- Operators can interpret continuation signals correctly (validated via review).
- Advisory signals do not cause confusion with existing gate signals.
- No operator workflow depends on advise signals for correctness (they are
  informational only).

---

## Phase-3: Enforce (Future)

### Goal

Integrate continuation standing into the pipeline's execution path so that
suspension or revocation of continuation can prevent step execution.

### Mode

- Feature flag: `VERITAS_CAP_CONTINUATION_ENFORCE` (default: `false`,
  requires both prior flags = `true`)
- Continuation standing affects pipeline flow: suspended or revoked claims
  prevent step execution before FUJI evaluation.

### Scope

- Pre-merit blocking: if continuation standing is `suspended` or `revoked`,
  the step is not submitted to FUJI or the kernel.
- Integration with self-healing loop: continuation-based rejections may trigger
  healing or human review.
- New `decision_status` considerations (if any) to be designed in phase-3
  planning — not pre-committed here.

### Entry Criteria

- Phase-2 exit criteria fully met.
- Sufficient advise-mode data demonstrates enforcement would be safe and
  predictable.
- Explicit architectural review and stakeholder approval.

### Exit Criteria

- Enforcement produces outcomes consistent with advise-mode predictions.
- No regression in safety or correctness compared to pre-continuation baseline.
- Rollback to advise or observe mode is instantaneous via flag toggle.

---

## Rollback Strategy

At any phase, setting the feature flag to `false` immediately disables all
Continuation Runtime behavior. The system reverts to pre-continuation behavior
with no residual effects. This is the primary safety mechanism.

Shadow artifacts (snapshots, receipts) produced during observe/advise phases
persist in storage but are not consumed by any pipeline logic when flags are off.

---

## Phase Boundary Rules

1. **No forward references in implementation**: Phase-1 code must not contain
   hooks, stubs, or abstractions designed for phase-2 or phase-3 unless they
   are strictly necessary for phase-1 functionality.
2. **No phase mixing**: A single deployment runs exactly one phase. There is no
   "partial enforce" or "advise for some chains, enforce for others" within a
   single deployment.
3. **Each phase is independently revertible**: Advancing to phase-2 does not
   make phase-1-only operation impossible.
