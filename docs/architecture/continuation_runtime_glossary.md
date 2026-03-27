# Continuation Runtime — Glossary

**Status**: Proposed
**Date**: 2026-03-27
**Scope**: Term definitions for the continuation runtime design.
These terms are binding for all subsequent implementation tasks.

---

## Chain-Level Concepts

### ContinuationClaimLineage

A live object that represents a chain's asserted right to continue executing
steps. Created when a chain begins (or when continuation tracking is first
applied to an in-progress chain). The lineage is not re-created per step —
it persists across the chain and accumulates revalidation history.

Contains:
- `claim_id`: Unique identifier for this lineage
- `law_pack`: Reference to the `ContinuationLawPack` governing this claim
- `law_version`: Version of the law pack at claim creation
- `scope`: Explicit description of what the claim covers (chain identity,
  purpose bounds, temporal bounds)
- `support_basis`: The grounds on which the claim is currently supported
  (includes burden state and headroom)
- `state_history`: Ordered sequence of `ClaimStateSnapshot` entries

A claim lineage is never silently created. Its scope must be explicit.

### ClaimStateSnapshot

An immutable record of the claim's state at a specific step. Produced by
each revalidation. Contains:

- `step_index`: Which step in the chain this snapshot corresponds to
- `timestamp`: When the revalidation occurred
- `claim_state`: The assessed state of the claim after revalidation
  (e.g., `supported`, `weakened`, `unsupported`, `revoked`)
- `burden_state`: Current burden assessment
- `headroom`: Remaining margin before the claim becomes unsupported
- `law_version`: Law pack version used for this revalidation
- `divergence`: Description of any divergence detected (null if none)
- `receipt_ref`: Reference to the corresponding `ContinuationReceipt`

Snapshots are append-only within the lineage. They are never modified
after creation.

### ContinuationLawPack

A versioned bundle of rules that define what constitutes a valid
continuation. The law pack determines:

- Under what conditions a claim remains `supported`
- What burden thresholds trigger `weakened` or `unsupported` states
- What constitutes a revocation event
- How headroom is calculated

The law pack is external to the claim — a claim references a law pack
version but does not contain the rules themselves. This allows law packs
to evolve independently of active claims (with version-aware revalidation).

Every claim must reference a `law_version`. A claim without a law version
is invalid.

### ContinuationReceipt

A per-step audit record emitted by the Continuation Runtime after
revalidation. The receipt is the primary observability surface for
continuation state.

Contains:
- `receipt_id`: Unique identifier
- `claim_id`: Which claim was revalidated
- `step_index`: Which step triggered this revalidation
- `timestamp`: When the receipt was emitted
- `claim_state`: Assessed state after revalidation
- `divergence_detected`: Boolean
- `divergence_detail`: Structured description if divergence detected
- `mode`: Which runtime mode produced this receipt (`observe`, `advise`,
  `enforce`)
- `action_taken`: What the runtime did (`none` in observe mode; `log`,
  `annotate` in advise mode; `hold`, `revoke` in enforce mode)
- `law_version`: Law pack version used

Receipts are designed for audit replay. They must contain enough
information to reconstruct the revalidation decision without access
to the runtime's internal state.

---

## Support Basis Concepts

### support basis

The set of grounds that currently justify a continuation claim's
`supported` state. The support basis is not a single score — it is
a structured record that includes burden state, headroom, and
references to the evidence or conditions that sustain the claim.

A claim with an empty or insufficient support basis transitions to
`weakened` or `unsupported`.

### burden state

The current load on the claim's support basis. Burden increases when
conditions that originally justified the claim are eroded — for example,
when the chain deviates from its stated purpose, when external conditions
change, or when accumulated step effects create risk not present at
chain start.

Burden is a component of the support basis, not a standalone metric.
It is not reported as an independent KPI or score outside the
continuation context.

### headroom

The remaining margin between the current burden state and the threshold
at which the claim transitions from `supported` to `weakened` or
`unsupported`. Headroom is derived from burden state and the law pack's
threshold definitions.

When headroom reaches zero, the claim is no longer `supported`.
Headroom is directional information for observability; it is not
a guarantee of future support.

---

## Lifecycle Concepts

### revalidation

The process of re-assessing a continuation claim's state at a given step.
Revalidation runs before step evaluation (pre-merit) and produces a
`ClaimStateSnapshot` and a `ContinuationReceipt`.

Revalidation is not re-issuance. The claim is not destroyed and recreated.
The same lineage persists, and the revalidation assesses whether the
existing claim's support basis still holds under the current law pack.

### revocation

The terminal state of a continuation claim. A revoked claim cannot be
revalidated further. Revocation is a recorded event with a reason.

In phase-1 (observe mode), revocation is recorded but not enforced —
the chain continues executing, and the revocation is visible in receipts
and logs only.

In future enforce mode, revocation triggers a hold or refusal signal.

### refusal-before-effect

The principle that if continuation rights are determined to be absent,
the refusal should occur before the step produces side effects — not
after. This is why revalidation runs pre-merit (before kernel evaluation).

In phase-1, this principle is observed structurally (the insertion point
is pre-merit) but not enforced (no refusal occurs). The structural
placement ensures that when enforcement is later enabled, it is already
in the correct position.

---

## Scope Concepts

### local step validity

Whether an individual step passes FUJI Gate's safety and policy
evaluation. This is the domain of the existing step-level decision
infrastructure. FUJI owns this assessment.

Local step validity does not imply chain-level continuation rights.
A step can be locally valid (FUJI allows it) while the chain's
continuation claim is unsupported.

### chain-level continuation rights

Whether the chain as a whole retains the right to continue executing
further steps. This is the domain of the Continuation Runtime.

Chain-level continuation rights do not imply local step validity.
A chain can have valid continuation rights while an individual step
is blocked by FUJI.

These two assessments are orthogonal. Neither subsumes the other.

---

## Runtime Mode Concepts

### observe mode

Phase-1 mode. The Continuation Runtime runs revalidation, produces
receipts, and logs divergence. It does not affect pipeline behavior.
No fields are added to the API response. No enforcement occurs.

The only external surface is structured logging and audit records.

### advise mode

Phase-2 mode (future). The Continuation Runtime surfaces continuation
state in logs, optional dashboard annotations, and potentially in
response extras. Still no enforcement — the chain continues regardless
of continuation state.

### enforce mode

Phase-3 mode (future). The Continuation Runtime can trigger holds or
refusals when continuation rights are determined to be absent. Requires
a separate ADR and review before activation.

Enforcement is always selective — it does not apply uniformly to all
chains. The selection criteria are defined in the law pack and rollout
configuration.
