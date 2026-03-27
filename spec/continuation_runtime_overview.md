# Continuation Runtime — Overview

**Status**: Proposed
**Date**: 2026-03-27
**Scope**: Conceptual overview of the continuation runtime and its
relationship to the existing VERITAS decision infrastructure.

This document is a companion to the ADR (`docs/architecture/continuation_runtime_adr.md`).
The ADR defines boundaries and decisions. This document explains the
reasoning and model.

---

## The Problem

VERITAS OS evaluates each decision step independently. FUJI Gate determines
whether a step is safe and policy-compliant. This per-step model is correct
for individual actions but has a structural gap: it cannot observe whether
a **chain of steps** — taken as a whole — remains within its continuation
rights.

Consider a chain of 10 steps. Each step individually passes FUJI Gate.
But by step 7, the chain has drifted far from its original purpose. The
accumulated effect of steps 1–7 has created a situation that was not
anticipated or authorized at chain start. No individual step is "bad,"
but the chain as a whole has exceeded its basis for continuing.

The current infrastructure has no surface to detect this. The continuation
runtime provides that surface.

---

## What the Continuation Runtime Is

The continuation runtime is a **chain-level observation and adjudication
substrate** that runs alongside the existing step-level decision
infrastructure.

It is **not**:
- A replacement for FUJI Gate
- A better version of FUJI Gate
- A per-step permit system
- A general-purpose chain orchestrator
- A solved problem (it is new and requires calibration)

It **is**:
- An independent responsibility with its own lifecycle
- A chain-level state tracker that maintains continuation claims
- An observation system that detects continuation divergence
- A foundation for future selective enforcement (not in phase-1)

---

## Two Axes of Assessment

After the continuation runtime is active, each step in a chain is
assessed on two independent axes:

| Axis | Owner | Question | Output |
|---|---|---|---|
| Step validity | FUJI Gate | Is this individual step safe and policy-compliant? | `decision_status` |
| Continuation rights | Continuation Runtime | Does this chain still have the right to continue? | `ContinuationReceipt` |

These axes are orthogonal:

- A step can be **valid + supported**: normal operation
- A step can be **valid + unsupported**: the step itself is fine, but
  the chain has drifted beyond its basis (divergence detected)
- A step can be **invalid + supported**: FUJI blocks the step, but the
  chain's continuation rights are intact (the chain can try a different step)
- A step can be **invalid + unsupported**: both assessments indicate problems

In phase-1, only the first axis (FUJI) has behavioral consequences.
The second axis (continuation) is observed and logged only.

---

## The Continuation Claim Model

### Claim lifecycle

```
Chain start
  │
  ├─ ContinuationClaimLineage created
  │   - scope set (what the claim covers)
  │   - law_pack referenced (rules governing the claim)
  │   - initial support_basis established
  │   - initial burden_state = minimal
  │   - initial headroom = maximum
  │
  ├─ Step 1: revalidation → ClaimStateSnapshot (supported)
  │   └─ ContinuationReceipt emitted
  │
  ├─ Step 2: revalidation → ClaimStateSnapshot (supported, headroom reduced)
  │   └─ ContinuationReceipt emitted
  │
  ├─ Step N: revalidation → ClaimStateSnapshot (weakened)
  │   └─ ContinuationReceipt emitted (divergence_detected: true)
  │
  ├─ Step N+1: revalidation → ClaimStateSnapshot (unsupported)
  │   └─ ContinuationReceipt emitted (divergence_detected: true)
  │
  └─ [Phase-3 only] revocation → chain hold
```

### Why not per-step permits?

A per-step permit model would issue a fresh "you may proceed" token at
each step. This is structurally equivalent to the current model (FUJI
independently evaluates each step) and provides no new information about
chain-level drift.

The continuation claim model maintains a **persistent, evolving object**
across the chain. This enables:

- **Drift detection**: The claim's support basis erodes over time if the
  chain deviates. Per-step permits have no memory of prior steps.
- **Burden accumulation**: Burden state tracks cumulative effects that
  no single step reveals. Per-step permits reset at each step.
- **Headroom tracking**: The claim knows how close it is to losing
  support. Per-step permits have no concept of proximity to failure.
- **Audit continuity**: The claim lineage provides a single audit trail
  for the entire chain. Per-step permits produce disconnected records.

### Why pre-merit revalidation?

Revalidation runs before the kernel evaluates the step (`stage_core_execute`).
This placement ensures:

1. **Independence**: Continuation assessment is not influenced by step
   outcome. There is no temptation to infer continuation rights from
   step success.
2. **Structural correctness**: When enforcement is later enabled, the
   intervention point is already in the correct position (before effects).
3. **Clean separation**: Step merit and continuation rights are evaluated
   in separate temporal windows within the pipeline.

---

## Relationship to Existing Design Assets

The continuation runtime builds on — and does not replace — VERITAS's
existing strengths:

| Existing Asset | Continuation Runtime Relationship |
|---|---|
| FUJI Gate | Independent. FUJI is unmodified. Continuation does not override FUJI. |
| DecisionStatus enum | Unchanged. No new values. No semantic changes. |
| Pipeline orchestration | Insertion point added (phase-1: pre-merit). Pipeline structure preserved. |
| Self-healing loop | Independent. Self-healing operates within a single step. Continuation operates across steps. |
| TrustLog | Continuation receipts are designed for compatibility with TrustLog's audit model, but do not modify TrustLog's existing entries. |
| Replay engine | Continuation receipts are replay-friendly (deterministic inputs → deterministic outputs). |
| Feature flags | Uses existing `CapabilityConfig` pattern for `enable_continuation_runtime`. |

---

## What Phase-1 Success Looks Like

Phase-1 is successful when:

1. **Receipts are meaningful.** Revalidation produces receipts that
   distinguish between supported and unsupported continuation states
   in a way that correlates with actual chain behavior.

2. **Divergence is observable.** When a chain drifts beyond its basis,
   the receipts detect it. When a chain stays within its basis, the
   receipts confirm it. The signal is not trivial (all-clear) or
   useless (all-divergent).

3. **Zero behavioral impact.** With the flag on, every observable
   output of the pipeline (response payloads, decision_status, FUJI
   results, TrustLog entries, UI behavior) is identical to flag-off
   behavior. The only difference is additional structured log entries.

4. **Zero stability impact.** The continuation runtime does not
   introduce errors, crashes, or latency degradation.

5. **Audit replay works.** Given a set of continuation receipts, a
   reviewer can reconstruct the chain's continuation state history
   without access to the runtime.

---

## When to Consider Selective Enforcement

Selective enforcement (phase-3) should be considered only after:

1. Phase-1 observation data has been collected for a sufficient period
2. Phase-2 advise-mode annotations have been validated by operators
3. Divergence detection accuracy has been measured against manual review
4. False positive rate is acceptably low (threshold TBD based on data)
5. A separate ADR has been written and reviewed for enforcement semantics
6. Integration testing confirms no semantic conflict between continuation
   enforcement and FUJI Gate decisions

Enforcement is never automatic. It is a deliberate transition that
requires evidence and review.
