# Continuation Runtime — Conceptual Overview

**Status**: Proposed (Phase-1 design boundary)
**Date**: 2026-03-28

---

## From Step-Level Decisions to Governed Continuation

### The Old Model: Step-Level Decision Infrastructure

VERITAS OS today provides a **step-level decision infrastructure**. Each call to
the decision pipeline is evaluated independently:

1. Input is normalized.
2. Evidence is retrieved.
3. The kernel produces a decision.
4. FUJI evaluates safety and policy.
5. The gate emits `decision_status` (allow / modify / rejected).
6. The result is persisted to the TrustLog.

This model is sound for individual steps. FUJI's fail-closed gate, the
hash-chained TrustLog, and the replay engine provide strong guarantees that each
step is evaluated, recorded, and reproducible.

But the model has no concept of **chains** — sequences of steps that together
pursue a goal. When an agent executes step 1, then step 2, then step 3, each
step passes through the pipeline independently. There is no mechanism to ask:
"Given everything this chain has done so far, does it retain the right to
continue?"

### The New Model: Decision Infrastructure + Governed Continuation Substrate

The Continuation Runtime adds a **chain-level continuation observation and
adjudication layer** that runs beside the existing step-level infrastructure.
The existing infrastructure is not replaced or modified — it gains a companion.

```
Step-Level (existing, unchanged):
  Input → Kernel → FUJI → Gate → TrustLog
  Each step independently evaluated.

Chain-Level (new, additive):
  ClaimLineage → Revalidation → Snapshot + Receipt
  Each step's continuation standing evaluated before merit.
```

The two layers are complementary:

- **Step-level** answers: "Is this specific action safe and policy-compliant?"
- **Chain-level** answers: "Does this chain retain the standing to continue?"

Both must be satisfied. A chain with active continuation standing still requires
each step to independently pass FUJI. A step that passes FUJI does not
automatically sustain the chain's continuation standing.

---

## Entry vs Continuation

**Entry** is the initiation of a new chain. It establishes:

- A fresh `ContinuationClaimLineage`.
- An initial scope (what the chain is authorized to do).
- An initial burden (what the chain must sustain to keep its standing).
- A law pack version (which rules govern revalidation).

**Continuation** is the ongoing exercise of an existing claim. At each
subsequent step, the claim is **revalidated** — not re-authorized. The
distinction matters:

- Re-authorization would mean each step is treated as a new entry, discarding
  chain history. This is the per-step permit model, and it is insufficient (see
  below).
- Revalidation means the existing claim is examined in light of accumulated
  evidence, updated burden, and scope compliance. History is preserved and
  matters.

---

## Why Per-Step Permits Are Insufficient

A per-step permit model would evaluate each step's continuation right in
isolation, based only on that step's properties. This fails because:

1. **Accumulated risk is invisible**: A chain that gradually escalates across
   steps would have each step independently permitted, even though the aggregate
   trajectory is problematic.

2. **Scope drift is undetectable**: If a chain's actions gradually shift away
   from its original authorization, per-step permits cannot detect this because
   they have no concept of original scope.

3. **Burden cannot be tracked**: A per-step model has no memory of what evidence
   was required and whether it was provided. Each step starts fresh.

4. **Revocation has no meaning**: You cannot revoke a permit that is issued anew
   each time. Per-step permits make chain-level governance impossible.

5. **Audit trails are disconnected**: Without a lineage connecting steps, audit
   must reconstruct chain relationships post-hoc rather than having them as
   first-class structures.

The continuation claim model addresses all of these by maintaining a live
lineage across steps with explicit scope, burden, and revalidation.

---

## Snapshot: Light. Receipt: Thick.

### Why the Snapshot Must Be Light

The `ClaimStateSnapshot` is the input to the next revalidation. It is read on
every step in the chain's critical path. It must contain exactly the facts
needed to make the next revalidation decision — no more.

If the snapshot grows to include audit detail, historical evidence, or
explanatory text, it becomes:

- Expensive to read and write on every step.
- Tempting to use as a state store for audit queries (violating separation).
- Difficult to version and migrate (because it mixes concerns).

Snapshot fields: `standing`, `scope`, `burden_state`, `headroom`,
`law_version`. Each is a direct input to revalidation logic.

### Why the Receipt Must Be Thick

The `ContinuationReceipt` is the audit artifact. It is written once per
revalidation and read later — by auditors, replay engines, compliance reviewers,
and divergence analyzers. It must contain enough detail to answer:

- What was checked during revalidation?
- What evidence was examined?
- What divergences were observed?
- What was the relationship to the preceding step's decision?
- What would the runtime have recommended (in shadow mode)?

Receipts are append-only. Their cost is amortized over time and they are not on
the critical path of revalidation logic.

### The Separation Rule

Runtime logic (revalidation, shadow recommendations) reads **snapshots**.
Audit logic (replay, compliance, divergence analysis) reads **receipts**.

If runtime logic needs something from a receipt, that data should be promoted
to the snapshot schema (with care, since it increases snapshot weight). If audit
logic only needs current state, it reads the latest receipt's snapshot reference.
The two never collapse into one structure.

---

## Why Pre-Merit Revalidation

Revalidation runs **before** FUJI pre-check — before the step's content is
evaluated for safety or policy compliance. This ordering is not arbitrary:

1. **Continuation standing is a precondition, not a consequence**: A chain's
   right to continue is determined by its accumulated history, scope compliance,
   and burden satisfaction — not by whether the next step happens to be safe.
   Evaluating merit first and then checking continuation would reverse the
   logical dependency.

2. **Prevents retroactive justification**: If revalidation ran after merit
   evaluation, a passing step could be used to argue that the chain should
   continue — even if the chain's accumulated trajectory warrants suspension.
   Pre-merit ordering prevents local step success from being used to justify
   chain-level continuation.

3. **Refusal-before-effect**: If a chain's continuation standing is lost, the
   chain should be stopped before the next step produces effects, not after.
   Pre-merit revalidation is the structural enabler of this principle (enforced
   in phase-3, observed in phase-1).

4. **Clean separation of concerns**: FUJI evaluates "is this step safe?" The
   Continuation Runtime evaluates "should this chain still be running?" Running
   continuation first keeps FUJI's input unchanged — FUJI never needs to know
   about continuation standing, and continuation never needs to know about step
   content.

---

## Why Phase-1 Is Shadow-Only

Phase-1 operates in observe/shadow mode for three reasons:

1. **Calibration before consequence**: The Continuation Runtime is a new
   assessment layer. Its judgments need to be validated against real production
   traffic before they carry enforcement weight. Shadow mode produces the data
   needed to evaluate whether the runtime's assessments are consistent,
   explainable, and aligned with human judgment.

2. **Protecting existing value**: VERITAS OS has a working, audited,
   fail-closed step-level infrastructure. Introducing enforcement from a new,
   unvalidated layer risks degrading the system's reliability. Shadow mode
   guarantees that existing behavior is preserved while the new layer proves
   itself.

3. **Divergence as the primary signal**: The most valuable output of phase-1 is
   **divergence data** — cases where the Continuation Runtime's shadow
   recommendation differs from the actual pipeline outcome. These cases reveal
   whether continuation-level observation adds genuine insight or merely
   replicates what step-level gating already catches. Without shadow mode,
   there is no way to measure this before enforcement changes behavior.

---

## Phase-1 Success Criteria

Phase-1 is considered successful when:

1. **Deterministic shadows**: Given the same inputs and law pack, revalidation
   produces the same snapshots and receipts. Verified via the existing replay
   infrastructure.

2. **Receipt sufficiency**: An auditor can reconstruct the full revalidation
   history of a chain from its receipts alone, without access to runtime state.

3. **Divergence observability**: Cases where shadow recommendations differ from
   actual outcomes are automatically detected, logged, and available for review.

4. **Zero interference**: All existing tests pass with the feature flag both on
   and off. Response payloads, log formats, UI behavior, and execution
   semantics are identical to the pre-continuation baseline when the flag is on.

5. **Latency within budget**: Shadow revalidation does not materially increase
   pipeline latency (target: < 5ms p99 overhead).

6. **Architectural boundaries hold**: Snapshot/receipt separation is maintained.
   FUJI is unmodified. No new routes or product areas are introduced.

Phase-1 success does **not** require:

- Proof that continuation-level observation catches problems step-level gating
  misses (that is what the divergence data is for — phase-1 collects it,
  phase-2 planning interprets it).
- A complete law pack covering all possible continuation scenarios (phase-1 law
  packs may be minimal and evolve).
- UI integration of any kind.

---

## What This Is Not

The Continuation Runtime is **not**:

- **A better FUJI**: It does not replace, improve, or compete with FUJI. FUJI
  evaluates steps; the Continuation Runtime evaluates chains. Different axis,
  different responsibility.
- **A solved problem**: Phase-1 is explicitly exploratory. The runtime's value
  proposition is hypothesized, not proven. Shadow data will determine whether
  chain-level observation adds genuine governance capability.
- **A rejection of the current design**: The existing step-level infrastructure
  is the foundation. The Continuation Runtime extends it — it does not critique
  or replace it.
- **An abstraction layer**: It is a concrete runtime with specific data
  structures (lineage, snapshot, receipt, law pack) and a specific insertion
  point (pre-merit, between critique and FUJI pre-check). It is not a framework
  or plugin system.

---

## Seam Between Step-Level and Chain-Level

The seam between the two layers is narrow and well-defined:

| Aspect | Step-Level (existing) | Chain-Level (new) |
|---|---|---|
| Unit of evaluation | Single pipeline invocation | Chain of invocations |
| Primary gate | FUJI (`decision_status`) | Continuation Runtime (`standing`) |
| State carrier | `PipelineContext` | `ContinuationClaimLineage` |
| Point-in-time record | Gate decision in TrustLog | `ClaimStateSnapshot` |
| Audit trail | TrustLog entries | `ContinuationReceipt` chain |
| Evaluation timing | During pipeline execution | Before pipeline merit evaluation |
| Phase-1 effect on pipeline | Defines pipeline outcome | None (shadow only) |

The seam is **read-only from chain to step**: the Continuation Runtime may read
pipeline context (e.g., chain identifier, step sequence number) but does not
write to any `PipelineContext` field that step-level logic consumes. In phase-1,
this is absolute. In future phases, any coupling across this seam requires
explicit architectural review.
