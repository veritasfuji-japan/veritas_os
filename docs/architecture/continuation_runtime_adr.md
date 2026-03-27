# ADR: Continuation Runtime — Architectural Boundary Definition

**Status**: Proposed
**Date**: 2026-03-27
**Scope**: Responsibility boundary and insertion-point design for chain-level
continuation observation. No logic implementation.

---

## Context

VERITAS OS currently operates on a **step-level decision infrastructure**.
Each call to `/v1/decide` is evaluated as an independent unit: the pipeline
normalizes inputs, retrieves evidence, runs kernel computation, passes through
FUJI Gate, and produces a decision record. This model is correct and well-tested
for single-step governance.

However, when an agent executes a **chain of steps** (a multi-step plan), the
current infrastructure has no mechanism to observe whether the chain as a whole
remains within its continuation rights. Each step is evaluated in isolation.
A chain that drifts outside its original lawful basis — even if each individual
step passes FUJI Gate — has no surface for detection.

This ADR defines the boundary for a **Continuation Runtime**: a new,
independent responsibility that observes chain-level continuation state
alongside the existing step-level decision infrastructure.

---

## Decision

### 1. Continuation Runtime is an independent responsibility beside FUJI

The Continuation Runtime is **not inside FUJI**. FUJI remains the final
safety/policy gate for each step. The Continuation Runtime occupies a
separate responsibility:

- **FUJI**: Per-step safety and policy evaluation. Owns `decision_status`.
- **Continuation Runtime**: Chain-level continuation observation and
  adjudication. Owns `ContinuationReceipt`.

FUJI does not consult the Continuation Runtime for its gate decision.
The Continuation Runtime does not override FUJI's `decision_status`.
They operate on different axes of the same pipeline execution.

**Rationale for independence**: FUJI's responsibility boundary is explicitly
defined in `docs/architecture/core_responsibility_boundaries.md`. Adding
chain-level state tracking to FUJI would violate that boundary and create
a dual-mandate module that is harder to audit, test, and reason about.

### 2. FUJI remains the final safety/policy gate

FUJI's public contract (`evaluate()`, `validate_action()`, `reload_policy()`)
is unchanged. FUJI error codes (F-1xxx through F-4xxx), risk thresholds,
`FujiInternalStatus`, and the mapping to `DecisionStatus` are all preserved
exactly as they are.

### 3. Continuation Runtime owns chain-level continuation observation

The Continuation Runtime is responsible for:

- Maintaining a `ContinuationClaimLineage` as a live object across a chain
- Performing **revalidation** of the claim at each step, producing a
  `ClaimStateSnapshot`
- Tracking `burden_state` and `headroom` as part of the claim's support basis
- Emitting a `ContinuationReceipt` per step that records the revalidation
  outcome
- Detecting **continuation divergence**: situations where chain-level
  continuation rights are no longer supported even though individual steps
  may pass FUJI Gate

### 4. gate.decision_status is not changed

`decision_status` (`allow | modify | block | abstain | rejected`) retains
its current semantics exactly. The Continuation Runtime does not write to,
modify, or depend on `decision_status`. It produces its own orthogonal
output (`ContinuationReceipt`).

**Why**: `decision_status` is a per-step concept that reflects FUJI's
safety/policy judgment. Continuation state is a chain-level concept that
reflects whether the chain's original basis for proceeding still holds.
Mixing them would create semantic overloading and break existing consumers.

### 5. Phase-1 is observe/shadow-only

In phase-1, the Continuation Runtime:

- **Observes**: Runs revalidation and emits receipts
- **Shadows**: Records divergence without affecting pipeline behavior
- **Does not enforce**: Never blocks, modifies, or alters the decision

When the feature flag is off, the Continuation Runtime does not execute.
No additional fields appear in the response. No log entries are emitted.
No latency is added.

### 6. Existing execution behavior is unchanged

The 20+ stage pipeline (`run_decide_pipeline`) continues to execute in
the same order with the same semantics. The Continuation Runtime, when
enabled, is an additional observation step that runs **before** step
evaluation (pre-merit revalidation) and emits its output as a sidecar
to the existing pipeline context.

---

## Pipeline Insertion Point

### Design candidates

The Continuation Runtime revalidation must run **before** the kernel
evaluates the step's merit. This ensures that continuation state is
assessed independently of the step's outcome.

**Candidate A — Between Stage 1 (Input Normalization) and Stage 2 (Memory Retrieval)**:

```
Stage 1:  normalize_pipeline_inputs
Stage 1c: continuation_revalidation    ← insertion point
Stage 2:  stage_memory_retrieval
```

Pros: Earliest possible point; continuation state is available to all
subsequent stages for observability. No dependency on memory or evidence.

Cons: No evidence context available yet.

**Candidate B — Between Stage 3 (Options Normalization) and Stage 4 (Core Execute)**:

```
Stage 3:  stage_normalize_options
Stage 3c: continuation_revalidation    ← insertion point
Stage 4:  stage_core_execute
```

Pros: Memory and web evidence are available for richer revalidation.
Still before kernel evaluation.

Cons: Later insertion means continuation observation is not available
during memory retrieval.

**Selected: Candidate A for phase-1.**

Rationale: In observe/shadow mode, the revalidation does not need evidence
context — it evaluates the claim's own support basis and law pack against
the chain's current position. Placing it earliest ensures no coupling with
downstream stages and maximizes the separation between continuation
observation and step evaluation.

Phase-2 may introduce a secondary observation point post-evidence for
richer divergence analysis, but this is explicitly out of scope for phase-1.

---

## Non-Goals

1. **FUJI is not a continuation engine.** The Continuation Runtime does not
   delegate to FUJI for continuation adjudication, and FUJI does not consume
   continuation state for its gate decision.

2. **Continuation claims are not per-step permits.** A continuation claim is
   a chain-level live object that persists across steps. It is not
   re-issued per step; it is revalidated per step.

3. **Local step success does not prove continuation lawfulness.** A step
   passing FUJI Gate does not mean the chain has continuation rights. These
   are orthogonal assessments.

4. **Burden is not a separate metric.** Burden is a component of the
   claim's support basis, not an independent score or KPI.

5. **Phase-1 does not enforce.** No refusal, no blocking, no modification
   based on continuation state.

6. **No new routes or product areas.** The Continuation Runtime is observed
   through existing logging and audit infrastructure, not through new API
   endpoints.

7. **No large-scale refactoring.** The Continuation Runtime is implemented
   as a sidecar to the existing pipeline, not as a restructuring of it.

---

## Stop Conditions

Implementation must halt and report (rather than proceed) if any of:

- Existing responsibility boundaries (Planner / Kernel / FUJI / MemoryOS)
  cannot be preserved
- FUJI changes are required for continuation observation
- `gate.decision_status` semantics must change
- The pre-merit insertion point cannot be confirmed in the pipeline
- Feature flag off → behavior change is unavoidable
- Continuation claims must function as per-step permits to work
- Existing tests break broadly

---

## Rollout Strategy

See `continuation_runtime_rollout.md` for phased rollout details.

- **Phase-1**: Observe / shadow. Feature flag gated. Zero behavioral change.
- **Phase-2**: Advise mode. Continuation divergence surfaced in logs and
  optional UI annotations. Still no enforcement.
- **Phase-3**: Selective enforcement. Continuation revocation can trigger
  a hold/review signal. Requires separate ADR.

Phase-2 and phase-3 directions are documented in the rollout plan but
are explicitly not part of this ADR's scope. Each phase transition
requires its own review.

---

## Relationship to Existing Architecture

| Component | Change | Rationale |
|---|---|---|
| `pipeline.py` | None in phase-1 ADR | Insertion point identified but not implemented |
| `fuji.py` | None | FUJI remains independent |
| `decision_status.py` | None | Enum unchanged |
| `pipeline_types.py` | None in phase-1 ADR | Context extension deferred to implementation |
| `config.py` | None in phase-1 ADR | Feature flag addition deferred to implementation |
| `core_responsibility_boundaries.md` | Future update | Will add Continuation Runtime section when implementation lands |

---

## References

- `docs/architecture/core_responsibility_boundaries.md` — existing boundary doc
- `veritas_os/core/pipeline.py` — pipeline orchestrator
- `veritas_os/core/fuji.py` — FUJI Gate v2
- `veritas_os/core/decision_status.py` — DecisionStatus enum
- `veritas_os/core/pipeline_types.py` — PipelineContext
