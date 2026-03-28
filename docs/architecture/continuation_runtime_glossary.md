# Continuation Runtime — Glossary

**Status**: Proposed (Phase-1 design boundary)
**Date**: 2026-03-28

This glossary defines terms used across the Continuation Runtime design
documents. Definitions are intentionally precise to prevent semantic drift
between phases.

---

## Core Structures

### ContinuationClaimLineage

A **live object** representing a chain's continuation standing across its
lifetime. It is created when a chain is initiated (entry) and updated at each
step via revalidation. It is not a token or permit — it is the structured record
of an ongoing claim that must be continuously justified.

A lineage tracks: who claimed, under what law, with what scope, and what the
current burden state is. It is the identity of the continuation across steps.

### ClaimStateSnapshot

The **minimal governable state** of a `ContinuationClaimLineage` at a specific
point in time — specifically, after a revalidation pass. A snapshot contains only
the facts needed for the next revalidation and for shadow-mode recommendations:

- `standing`: Current continuation standing (e.g., active, narrowed, suspended,
  revoked).
- `scope`: Explicit boundary of what the chain is permitted to continue doing.
- `burden_state`: Current state of the evidentiary burden the chain must sustain.
- `headroom`: Remaining capacity before automatic escalation or suspension
  triggers.
- `law_version`: Version identifier of the `ContinuationLawPack` under which
  this snapshot was produced.

A snapshot is **replaced** at each revalidation. Only the current snapshot is
authoritative for runtime logic. Prior snapshots are accessible only through
receipts.

### ContinuationReceipt

An **evidence artifact** produced by each revalidation pass, recording how the
claim's standing was examined and what was found. Receipts are **append-only** —
they accumulate across steps to form a chain-level audit trail.

A receipt records:

- `revalidation_status`: What happened during revalidation (passed, narrowed,
  escalated, suspended, revoked) — this is a description of the revalidation
  event, not the resulting standing.
- `basis_examined`: Which elements of the support basis were checked.
- `divergences_observed`: Any differences between expected and observed
  continuation conditions.
- `preceding_decision_continuity`: How this step's context relates to the prior
  step's decision — this is evidence about continuity, belonging to the audit
  trail.
- `shadow_recommendation`: What the runtime would have recommended if enforcement
  were active (phase-1 only).
- `timestamps`: When revalidation started and completed.
- `law_version`: The law pack version used for this revalidation.

A receipt is **not** a state store. Runtime logic reads the snapshot for current
state; it reads receipts only for audit, replay, and divergence analysis.

### ContinuationLawPack

A **versioned, immutable set of rules** that govern continuation revalidation.
Each law pack has a version identifier. When a snapshot is produced, it records
which law pack version was applied.

Law packs define:

- Conditions under which standing is maintained, narrowed, or lost.
- Burden requirements and escalation thresholds.
- Headroom calculation rules.
- Scope validation criteria.

Law packs are not policies in the FUJI sense (they do not evaluate content
safety). They govern the structural validity of continuation itself.

---

## Support Basis and Burden

### Support Basis

The **set of justifications** that sustain a continuation claim's standing. A
support basis is not a single score — it is a structured collection of grounds
(e.g., original authorization, accumulated compliance record, scope consistency,
burden satisfaction).

Burden is a **component within** the support basis, not a separate metric.

### Burden State

The **current evidentiary obligation** that a continuation claim must satisfy to
maintain its standing. Burden state tracks:

- What evidence is required.
- Whether that evidence has been provided.
- How close the burden is to being unsatisfied (which would trigger narrowing or
  escalation).

Burden state is carried in the `ClaimStateSnapshot` because it is essential for
the next revalidation decision.

### Headroom

The **remaining capacity** before a continuation claim triggers automatic
escalation, narrowing, or suspension. Headroom is a derived quantity computed
during revalidation based on burden state, scope usage, and law pack thresholds.

Headroom is carried in the snapshot because it is needed for shadow-mode
recommendations and future revalidation logic.

---

## Revalidation Lifecycle

### Revalidation

The process of **re-examining** a continuation claim's standing before a new step
is evaluated on its merits. Revalidation:

1. Reads the current `ClaimStateSnapshot`.
2. Evaluates the claim against the current `ContinuationLawPack`.
3. Produces a new `ClaimStateSnapshot` (replacing the old one).
4. Emits a `ContinuationReceipt` (appended to the audit trail).

Revalidation runs **before** FUJI pre-check — before the step's content is
evaluated for safety. This ordering is deliberate: continuation standing is a
precondition, not a consequence.

### Revocation

The **terminal loss** of continuation standing. Once revoked, a claim cannot be
reinstated within the same lineage. A new chain would require a new entry with
its own claim.

Revocation is recorded in both the final snapshot (`standing: revoked`) and the
corresponding receipt (with the reason and evidence).

### Refusal-Before-Effect

The principle that a chain should be stopped **before** it produces effects that
would need to be undone, rather than after. In the continuation model, this means
revalidation (which can lead to suspension or revocation) happens before step
execution, not after.

In phase-1 (observe/shadow), refusal-before-effect is not enforced — it is only
observed and logged as a shadow recommendation.

---

## Step vs Chain Concepts

### Local Step Validity

Whether an individual step passes FUJI's safety and policy evaluation. This is
the existing VERITAS responsibility — `gate.decision_status` reflects this.
Local step validity says nothing about whether the chain as a whole should
continue.

### Chain-Level Continuation Rights

Whether a chain retains the standing to continue executing additional steps.
This is the Continuation Runtime's responsibility. Chain-level rights depend on
the claim lineage, law pack, burden state, and scope — not on any single step's
local validity.

A step can be locally valid but the chain's continuation standing can be
narrowed, suspended, or revoked. Conversely, a chain with active continuation
standing still requires each step to pass FUJI independently.

---

## Operating Modes

### Observe Mode (Phase-1)

The Continuation Runtime runs revalidation, produces snapshots and receipts, and
records shadow recommendations — but does **not** affect pipeline execution. No
blocking, no modification, no signaling to FUJI or the gate. The runtime is
invisible to the pipeline's decision path.

### Advise Mode (Phase-2, future)

The Continuation Runtime produces advisory signals that are visible in logs,
audit artifacts, and potentially response extras — but does **not** block or
modify execution. Operators can see what the runtime recommends.

### Enforce Mode (Phase-3, future)

The Continuation Runtime's assessments are integrated into the pipeline's
execution path. Suspension or revocation of continuation standing can prevent
step execution. This mode requires extensive validation from observe and advise
phases.

---

## Architectural Boundaries

### State vs Receipt Boundary

**State** (snapshot) is the minimal, current, actionable representation of the
claim. **Receipt** is the historical, evidential record of how state was derived.

The boundary rule: runtime logic that decides what to do next reads the
**snapshot**. Logic that explains what happened and why reads **receipts**.

Violations of this boundary (e.g., the runtime reading receipts to determine
current standing, or snapshots accumulating audit-level detail) are architectural
defects.

### Revalidation Status

Revalidation status (what happened during a revalidation pass) belongs to the
**receipt** side, not the snapshot side. The snapshot records the *result*
(updated standing, burden, headroom). The receipt records the *process*
(what was checked, what was found, what diverged).

### Preceding Decision Continuity

The relationship between consecutive steps' decisions (e.g., "step N's decision
was consistent with step N-1's") is **evidence about continuity**. It belongs to
the receipt / audit trail, not to the snapshot. The snapshot does not need to
carry the history of prior decisions — only the current standing that results
from considering that history.

---

## Replay and Audit

### Lawful Replay

A replay is **lawful** if it can reproduce the continuation revalidation
sequence using the same law pack versions and input conditions, and arrive at the
same snapshot states and receipt contents. Lawful replay requires that:

- Law pack versions are immutable and retrievable.
- Snapshots are deterministically derived from inputs + law pack.
- Receipts record sufficient detail to verify the revalidation process.

This aligns with VERITAS's existing replay infrastructure
(`docs/replay_audit.md`), extending it to cover chain-level continuation
artifacts.

### Continuity Grounding

The property that a continuation claim's standing is **traceable** back to its
original entry authorization through an unbroken chain of revalidation receipts.
If any receipt in the chain is missing or inconsistent, continuity grounding is
lost, which is an audit finding.

---

## Entry vs Continuation

### Entry

The initiation of a new chain. Entry requires establishing a fresh
`ContinuationClaimLineage` with an initial scope, burden, and law pack version.
Entry is a distinct event from continuation — it is not "the first continuation."

### Continuation

The ongoing exercise of an existing claim across subsequent steps. Each
continuation requires successful revalidation. Continuation is not automatic —
it must be actively sustained through burden satisfaction and scope compliance.
