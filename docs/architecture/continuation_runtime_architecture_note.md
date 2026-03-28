# Architecture Note: Continuation Runtime (Phase-1)

**Status**: Phase-1 (observe/shadow only)
**Date**: 2026-03-28

---

## One-Page Summary

### Before: Decision-Centric Model

VERITAS OS evaluates each `/v1/decide` call as an independent step.
FUJI gates each step on content safety and policy. Once a step passes,
there is no mechanism to track whether the *chain* of steps retains the
right to continue.

```
Step N  →  FUJI gate  →  allow/deny  →  done
Step N+1 →  FUJI gate  →  allow/deny  →  done    (no chain awareness)
```

**Gap**: A chain can accumulate risk, lose its justification, or exceed
its scope across steps — and no layer notices.

### After: Decision + Governed Continuation Substrate

The Continuation Runtime adds a **chain-level observation layer** that
runs beside (not inside) the existing step-level infrastructure.

```
Step N  →  [Continuation Revalidation]  →  FUJI gate  →  allow/deny
           ↓ snapshot (state)
           ↓ receipt (audit witness)
```

FUJI is unchanged. `gate.decision_status` is unchanged. The Continuation
Runtime observes and records whether the chain's continuation standing
is maintained, narrowed, escalated, halted, or revoked.

---

## Why Lineage

A `ContinuationClaimLineage` is a **live object** created at chain entry
and updated at each step. It is not a permit — it is the structured
record of an ongoing claim that must be continuously justified.

Without lineage, there is no persistent identity for a chain's
continuation standing. Each step would need to re-derive context from
scratch, losing the ability to detect progressive weakening.

## Why Snapshot

A `ClaimStateSnapshot` captures the **minimal governable facts** at a
point in time: support basis, scope, burden, headroom, law version, and
revocation conditions.

Snapshots are replaced at each revalidation. Only the current snapshot
is authoritative for runtime logic. This prevents stale state from
accumulating and keeps the snapshot schema small and fixed.

**Separation rule**: Snapshots do not carry revalidation_status,
divergence_flag, or preceding_decision_continuity. Those belong to
receipts.

## Why Receipt

A `ContinuationReceipt` is the **audit witness** emitted per
revalidation pass. It records how the claim was examined, what was found,
and what the runtime would have recommended.

Receipts are append-only and form a chain-level audit trail. They carry
digests, reason codes, divergence flags, and linkage to parent receipts.

**Separation rule**: Receipts do not carry support_basis, burden_state,
or headroom_state. Those belong to snapshots. Receipts are for audit,
replay, and divergence analysis — not for runtime state.

## Why Pre-Merit Revalidation

Continuation revalidation runs **before** FUJI's step-level evaluation
(between pipeline stages 5b and 6a). This preserves the principle that
continuation standing is checked before new work is assessed — not
derived from the result of that work.

If revalidation ran after FUJI, local step success could mask chain-level
problems. Pre-merit placement ensures the runtime can detect "locally
correct but chain-level problematic" situations.

## Why Burden / Headroom

**Burden** tracks evidentiary obligations the chain must sustain across
steps. It is part of the support basis — not a separate metric bolted on.

**Headroom** is the runtime interpretation of burden: how much margin
remains before thresholds are breached. When headroom collapses (reaches
threshold_suspension), the claim is halted.

Without burden/headroom, there is no way to detect gradual evidentiary
erosion across steps — only sudden, total support loss.

## Why Refusal-Before-Effect is Deferred

Phase-1 is observe/shadow only. The `should_refuse_before_effect` field
is advisory: it records what the runtime *would* recommend, but does not
block execution.

Enforcement is deferred to later phases because:

1. Shadow data must first demonstrate consistent, explainable assessments
   under production traffic.
2. Snapshot/receipt separation must hold under real-world conditions.
3. Divergence patterns must be understood before acting on them.
4. Explicit architectural review is required before advancing.

---

## What is NOT Solved

- Enforcement (refusal gating) — deferred to phase-3
- Advisory mode (logged recommendations) — deferred to phase-2
- Integration with external authority/policy stores — phase-1 uses heuristics
- Cross-chain continuation awareness — out of scope
- Production-grade burden accumulation logic — phase-1 is conservative

## Key Invariants

| Invariant | Guarantee |
|---|---|
| FUJI unchanged | No modification to FUJI's public contract or internal logic |
| gate.decision_status unchanged | No new values, no reinterpretation |
| Feature flag off = zero change | No response mutation, no computation, no log output |
| Snapshot ≠ Receipt | Separate schemas, separate responsibilities |
| Revocation is terminal | Once revoked, always revoked |
| Pre-merit placement | Revalidation runs before FUJI evaluation |
| Law version recorded | Every snapshot and receipt records applicable law_version |

---

## References

- `continuation_runtime_adr.md` — Architecture decision record (detailed)
- `continuation_runtime_glossary.md` — Term definitions
- `continuation_runtime_rollout.md` — Phased rollout plan
- `spec/continuation_runtime_overview.md` — Conceptual overview
- `core_responsibility_boundaries.md` — Module boundaries
