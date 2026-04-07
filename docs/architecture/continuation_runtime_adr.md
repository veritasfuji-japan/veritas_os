# ADR: Continuation Runtime — Architecture Decision Record

**Status**: Proposed (Phase-1 design boundary)
**Date**: 2026-03-28
**Author**: Principal Engineer (automated)
**Scope**: Chain-level continuation observation substrate for VERITAS OS

---

## Context

VERITAS OS currently operates with a **step-level decision infrastructure**: each
call to `/v1/decide` is independently evaluated by the pipeline, gated by FUJI,
and persisted to the TrustLog. There is no first-class concept of whether a
chain of decisions — a sequence of steps toward a goal — retains the right to
continue executing.

This gap means that:

- A chain can accumulate risk across steps without any mechanism noticing the
  aggregate trajectory.
- There is no place to record *why* a chain is still permitted to continue,
  separate from *why* a single step passed the gate.
- Revocation of continuation rights requires ad-hoc intervention rather than
  structured adjudication.

The Continuation Runtime addresses this by introducing a **chain-level
continuation observation and adjudication layer** that runs alongside — not
inside — the existing step-level infrastructure.

---

## Decision

### 1. Continuation Runtime is an independent responsibility beside FUJI

The Continuation Runtime is **not** part of FUJI. It does not modify, wrap, or
extend FUJI's evaluation logic. FUJI remains the final safety and policy gate
for each individual step. The Continuation Runtime operates on a different axis:
whether the *chain as a whole* retains continuation standing.

**Rationale**: FUJI's responsibility boundary is well-defined (safety and policy
evaluation for actions and content — see `core_responsibility_boundaries.md`).
Embedding chain-level continuation logic inside FUJI would blur this boundary,
complicate FUJI's fail-closed guarantees, and make it harder to review safety
behavior in isolation.

### 2. FUJI remains the final safety/policy gate — unchanged

FUJI's public contract (`evaluate()`, `validate_action()`, `reload_policy()`)
and its internal status semantics (`allow`, `allow_with_warning`,
`needs_human_review`, `deny`) are not modified. The Continuation Runtime does
not override, veto, or reinterpret FUJI decisions.

### 3. Continuation Runtime owns chain-level continuation observation and adjudication

The Continuation Runtime is responsible for:

- Maintaining a `ContinuationClaimLineage` — a live object representing a
  chain's continuation standing across steps.
- Running **revalidation** before each step's merit evaluation, producing a
  `ClaimStateSnapshot`.
- Emitting a `ContinuationReceipt` after revalidation that records how the
  standing was examined, maintained, narrowed, escalated, suspended, or lost.
- Evaluating continuation against a `ContinuationLawPack` (versioned law set).

It is **not** responsible for:

- Deciding whether an individual step's content is safe (FUJI's job).
- Generating per-step permits (see Non-Goals).
- Enforcing refusal (phase-1 is observe/shadow only).

### 4. Phase-1 is observe/shadow only

In phase-1, the Continuation Runtime:

- **Observes**: Runs revalidation logic and produces snapshots and receipts.
- **Shadows**: Records what it *would* recommend (continue / narrow / escalate /
  suspend / revoke) without affecting execution.
- **Does not enforce**: The pipeline proceeds exactly as it does today regardless
  of the Continuation Runtime's assessment.

This means that with the continuation runtime feature flag off, there is **zero
change** to response payloads, log output, UI behavior, or execution semantics.

### 5. `gate.decision_status` is not modified

`gate.decision_status` (the `DecisionStatus` enum: `allow`, `modify`, `block`,
`abstain`, `rejected`) represents the outcome of FUJI's step-level safety gate.
The Continuation Runtime does not add new values, reinterpret existing values, or
condition its behavior on `decision_status` in ways that would change its
meaning.

**Rationale**: `decision_status` is consumed by the API layer, frontend, replay
engine, and audit tooling. Changing its semantics would cascade across the entire
system. The Continuation Runtime introduces its own state vocabulary
(`ClaimStateSnapshot`) that is orthogonal to `decision_status`.

### 6. Snapshot and Receipt have separated responsibilities

| Concern | Snapshot (`ClaimStateSnapshot`) | Receipt (`ContinuationReceipt`) |
|---|---|---|
| Purpose | Minimal governable state of the claim at a point in time | Evidence of how revalidation was conducted and what was found |
| Content | standing, scope, burden_state, headroom, law_version | revalidation_status, basis_examined, divergences, preceding_decision_continuity, timestamps, auditor-facing detail |
| Lifecycle | Replaced each revalidation; only current snapshot is authoritative | Appended; forms an audit trail across steps |
| Size | Small and fixed-schema | Grows with evidence complexity |
| Consumed by | Runtime logic (next revalidation, shadow recommendations) | Audit, replay, compliance review |

The snapshot is not a receipt. The receipt is not a state store. Revalidation
status belongs to the receipt side (it describes what happened during
revalidation, not the resulting standing). Preceding decision continuity belongs
to the receipt/audit side (it describes the relationship between consecutive
steps, which is evidence, not current state).

### 7. Pipeline insertion point design

The Continuation Runtime revalidation runs **before** FUJI's step-level
evaluation. In the current 8-stage pipeline:

```
... Stage 5b (Critique) →
  [Continuation Revalidation]  ← new, pre-merit
  Stage 6a (FUJI Pre-check) →
  Stage 6b (ValueCore) →
  Stage 6c (Gate Decision) →
...
```

**Candidate insertion**: Between stage 5b and stage 6a, as a sidecar operation
that reads pipeline context but writes only to its own state (snapshot + receipt).
It does not modify `PipelineContext` fields that FUJI or the gate consume.

In phase-1 (observe/shadow), this insertion is a no-op for pipeline flow: it
produces artifacts but does not alter `ctx.fuji_dict`, `ctx.decision_status`, or
any other pipeline state.

**Alternative considered**: Post-gate insertion (after stage 6c). Rejected
because revalidation must happen *before* merit evaluation to preserve the
principle that continuation standing is checked before new work is assessed — not
derived from the result of that work.

---

## Non-Goals

1. **FUJI as continuation engine**: FUJI evaluates steps; the Continuation
   Runtime evaluates chains. These are distinct responsibilities.
2. **Per-step permits**: Continuation claims are not permits. A claim represents
   ongoing standing that is revalidated, not a fresh authorization issued per
   step.
3. **Reverse-engineering continuation from step results**: Local step success
   does not prove continuation lawfulness. Continuation standing must be
   evaluated on its own terms (law pack, burden, scope) before step merit is
   known.
4. **Burden as a separate metric**: Burden is part of the support basis within
   the continuation claim, not an independent metric bolted onto the pipeline.
5. **Phase-1 enforcement**: No refusal, blocking, or behavioral modification in
   phase-1. The runtime observes and records only.
6. **New routes or product areas**: No new API endpoints, no new UI pages. Shadow
   data is internal or exposed via existing extension points (e.g., response
   extras, audit artifacts).
7. **Large-scale refactoring**: The runtime is added as a sidecar. Existing
   modules are not restructured.

---

## Stop Conditions

Implementation must halt and report (without code changes) if any of:

- Existing responsibility boundaries (Planner / Kernel / FUJI / MemoryOS) cannot
  be read clearly enough to guarantee non-interference.
- Implementation requires modifying FUJI's public contract or internal logic.
- `gate.decision_status` semantics must change.
- No viable pre-merit insertion point exists in the pipeline without modifying
  existing stage signatures.
- Feature-flag-off invariance cannot be guaranteed.
- The continuation claim must degenerate into a per-step permit to function.
- Existing tests break in ways that require widespread modification.

---

## Rollout Strategy

See `continuation_runtime_rollout.md` for detailed phasing. Summary:

| Phase | Mode | Enforcement | Scope |
|---|---|---|---|
| 1 | observe / shadow | None | Internal artifacts only |
| 2 | advise | Logged recommendations; no blocking | Shadow + advisory signals |
| 3 | enforce | Continuation-based gating | Full integration |

Phase boundaries are gated by:

- Divergence data from shadow mode demonstrating the runtime produces
  consistent, explainable assessments.
- Confirmation that snapshot/receipt separation holds under production traffic
  patterns.
- Explicit architectural review before advancing.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Continuation logic leaks into FUJI | Strict module boundary; continuation runtime is a separate package/module; CI boundary check |
| Shadow mode adds latency | Revalidation is designed to be lightweight; phase-1 monitors latency overhead |
| Snapshot schema grows unbounded | Fixed-schema constraint; additional data goes to receipt |
| Receipt replaces snapshot as de facto state | Architectural rule enforced in review: runtime logic reads snapshot, not receipt |
| Feature flag off still costs something | Flag check is the first operation; short-circuit before any allocation |

---

## References

- `docs/architecture/core_responsibility_boundaries.md` — Module boundaries
- `docs/self_healing_loop.md` — Existing retry/continuation pattern (step-scoped)
- `docs/ja/audits/replay_audit_ja.md` — Replay and divergence detection infrastructure
- `docs/architecture/continuation_runtime_glossary.md` — Term definitions
- `docs/architecture/continuation_runtime_rollout.md` — Phased rollout plan
- `spec/continuation_runtime_overview.md` — Conceptual overview
