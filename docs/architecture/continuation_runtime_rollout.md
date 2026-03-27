# Continuation Runtime — Rollout Plan

**Status**: Proposed
**Date**: 2026-03-27
**Scope**: Phased rollout strategy for the continuation runtime.

---

## Current Model: Step-Level Decision Infrastructure

VERITAS OS currently operates a **step-level decision infrastructure**:

1. Each `/v1/decide` call is an independent decision unit.
2. The pipeline evaluates inputs, retrieves evidence, computes a decision,
   passes it through FUJI Gate, and produces an auditable record.
3. Safety and policy evaluation are per-step. FUJI Gate renders
   `decision_status` for each step independently.
4. There is no cross-step state tracking for continuation rights.

This model is correct, well-tested (87% coverage, 244+ test files), and
production-grade for single-step governance. It is not being replaced.

## New Model: Decision Infrastructure + Governed Continuation Substrate

The continuation runtime adds a **governed continuation substrate** that
operates alongside the existing step-level infrastructure:

```
Existing:   [ Step N ] → FUJI Gate → decision_status
                                      (per-step safety/policy)

Added:      [ Chain ] → Continuation Runtime → ContinuationReceipt
                                                (chain-level observation)
```

Both operate on the same pipeline execution. They do not interfere with
each other. The step-level infrastructure continues to be the authority
on per-step safety. The continuation substrate observes whether the
chain's continuation rights remain supported.

---

## Entry vs. Continuation

**Entry** is the first step of a chain — the point at which a continuation
claim is established. The claim's scope, law pack, and initial support
basis are set at entry.

**Continuation** is every subsequent step in the chain — points at which
the existing claim is revalidated against the current state of the chain
and the governing law pack.

The distinction matters because:

- Entry establishes the claim's scope and basis. It is a creative act.
- Continuation revalidates the existing claim. It is an assessment act.
- A per-step permit model (re-issuing permission at each step) would
  collapse this distinction and lose the ability to track drift across
  the chain.

---

## Why Per-Step Permits Do Not Work

A per-step permit model would:

1. **Lose chain-level drift detection.** Each step would be evaluated
   independently, and gradual drift from the chain's original basis
   would be invisible — exactly the current situation.

2. **Collapse entry and continuation into a single concept.** Without a
   persistent claim, there is no distinction between "this step is
   individually permitted" and "this chain still has the right to continue."

3. **Make burden tracking impossible.** Burden accumulates across steps.
   A per-step model has no cross-step state to accumulate against.

4. **Require FUJI to own continuation logic.** Per-step permits would
   naturally be issued by the per-step gate (FUJI), violating the
   independence constraint and overloading FUJI's responsibility.

The continuation claim model preserves chain-level state as a first-class
object, enabling drift detection, burden tracking, and independent
adjudication.

---

## Why Pre-Merit Revalidation Is Necessary

Revalidation must run **before** the kernel evaluates the step's merit
(before `stage_core_execute`). This is because:

1. **Continuation rights are independent of step merit.** Whether the
   chain has the right to continue is a question about the chain's
   basis, not about whether this particular step is good. Evaluating
   merit first would conflate the two.

2. **Refusal-before-effect.** If continuation rights are absent, the
   correct architectural position for intervention is before the step
   produces effects. Even in observe mode (where no intervention occurs),
   placing revalidation pre-merit ensures the structure is correct for
   future enforcement.

3. **No reverse inference.** If revalidation ran post-merit, there would
   be a temptation to infer continuation lawfulness from step success.
   Pre-merit placement makes this structurally impossible.

---

## Why Phase-1 Is Shadow-Only

Phase-1 must be shadow-only (observe, no enforce) because:

1. **Calibration.** The continuation law pack and burden model are new.
   Their thresholds and behaviors need observation against real traffic
   before enforcement is safe.

2. **False positive risk.** An incorrectly calibrated continuation model
   that enforces prematurely could block legitimate chains, degrading
   VERITAS's value rather than enhancing it.

3. **Existing safety is intact.** FUJI Gate continues to enforce per-step
   safety. The continuation runtime adds observation, not a replacement
   for existing protection.

4. **Auditability.** Shadow mode produces receipts and logs that can be
   reviewed to validate the model's behavior before trusting it with
   enforcement authority.

5. **Reversibility.** With the feature flag off, the continuation runtime
   is completely inert. This ensures zero risk to existing behavior during
   the observation period.

---

## Phase Definitions

### Phase-1: Observe / Shadow

**Feature flag**: `enable_continuation_runtime` (default: `false`)

**Behavior when flag is off**: Absolutely nothing changes. No code paths
execute. No log entries are emitted. No response fields are added.
No latency is introduced.

**Behavior when flag is on**:
- Continuation revalidation runs at the pre-merit insertion point
- `ContinuationReceipt` is emitted to structured logs
- `ClaimStateSnapshot` is appended to the claim lineage
- Divergence is logged when detected
- Pipeline behavior is unchanged — `decision_status`, response shape,
  timing, and all observable outputs remain identical

**Success criteria for phase-1**:
- Receipts are emitted correctly for all chain executions
- Divergence detection produces meaningful signals (not all-clear,
  not all-divergent)
- Zero impact on pipeline latency (within measurement noise)
- Zero behavioral change when flag is on (response payloads are
  byte-identical except for timing jitter)
- Receipts are sufficient for audit replay
- No increase in test failures

**Duration**: Until success criteria are met and reviewed.

### Phase-2: Advise (Future)

**Not part of this ADR. Direction only.**

- Continuation state surfaces in structured logs at higher visibility
- Optional Mission Control dashboard annotations showing chain
  continuation health
- Optional `extras.continuation` field in response (behind a separate
  flag)
- Still no enforcement

**Transition criteria**: Phase-1 success criteria met. Divergence
signals validated against manual review of at least N chains.

### Phase-3: Selective Enforcement (Future)

**Not part of this ADR. Requires separate ADR.**

- Continuation revocation can trigger a hold signal
- Hold signal is surfaced to the operator, not silently applied
- Enforcement is selective (per law pack configuration, not global)
- Requires integration testing with FUJI to ensure no semantic conflict

**Transition criteria**: Phase-2 advise signals validated. Enforcement
policy reviewed and approved. Separate ADR accepted.

---

## Rollback

At any phase, the feature flag can be set to `false` to fully disable
the continuation runtime. This is the primary rollback mechanism.

Phase-2 and phase-3 may introduce additional rollback mechanisms
(e.g., per-chain disable, law pack version pinning), but these are
out of scope for phase-1.

---

## Monitoring

Phase-1 monitoring focuses on:

- **Receipt emission rate**: Are receipts being produced for chains?
- **Divergence rate**: What fraction of revalidations detect divergence?
- **Latency impact**: Is the revalidation step measurably affecting
  pipeline latency?
- **Error rate**: Does the continuation runtime produce errors that
  affect pipeline stability?

All monitoring is through existing logging and observability
infrastructure. No new monitoring endpoints are added in phase-1.
