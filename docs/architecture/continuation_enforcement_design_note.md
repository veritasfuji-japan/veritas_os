# Continuation Runtime — Limited Enforcement Design Note

**Date:** 2026-04-10
**Author:** VERITAS OS Team
**Status:** Implemented (Beta)

---

## Summary

This document explains the design rationale for adding a limited
enforcement mode to the Continuation Runtime, evolving it from
Phase-1 (observe/shadow) into a narrowly scoped, explainable
enforcement model for high-confidence governance failures.

---

## Why These Conditions

We selected four enforcement conditions based on two criteria:
**high confidence** (the condition is unambiguously detectable) and
**governance criticality** (the condition represents a clear violation
of chain-level governance principles).

### 1. Repeated High-Risk Continuation Degradation

**Why:** A single degraded receipt may be transient. But 3+ consecutive
degraded/escalated/halted receipts indicate a pattern of systematic
governance weakening that individual step-level gates cannot catch.

**Confidence model:** Confidence starts at 0.80 at threshold and scales
with excess count (+0.05 per additional occurrence). This ensures
marginal cases are filtered by the min_confidence gate (default 0.80).

### 2. Approval-Required Transition Without Approval

**Why:** When the continuation scope explicitly requires escalation
(approval) and none has been provided, this is a deterministic
governance failure — not a judgment call.

**Confidence model:** Always 1.0 (deterministic binary condition).

### 3. Replay Divergence Above Threshold

**Why:** When continuation decisions diverge significantly from replay
expectations, this indicates environmental drift, configuration
change, or potential manipulation of the decision path.

**Confidence model:** Scales linearly from 0.80 at threshold to 1.0
at full divergence.

### 4. Policy Boundary Violation in Continuation State

**Why:** When the continuation state violates a declared policy
boundary (e.g., an action class that is not allowed by current scope),
this is a deterministic governance failure.

**Confidence model:** Always 1.0 (deterministic condition).

---

## Why These Actions

### `require_human_review`

Used for: Accumulated degradation patterns.

**Rationale:** Degradation is a trend, not a single event. The
appropriate response is to pause and have an operator review the
chain's governance health before allowing continuation. This is
the least disruptive enforcement action.

### `halt_chain`

Used for: Missing approval, policy boundary violations.

**Rationale:** These are deterministic governance failures where
continuing the chain would violate declared governance rules.
Halting is the only safe response.

### `escalate_alert`

Used for: Replay divergence.

**Rationale:** Divergence may have legitimate causes (environment
change, model update). The appropriate response is to alert
operators and governance reviewers, not to halt the chain.

---

## Why This Is Still Safe for a Beta Governance Platform

### 1. Feature-flagged with conservative defaults

- Default mode is `observe` — zero enforcement, zero behavioral change.
- Even in `advisory` mode, events are informational only.
- `enforce` mode is opt-in and requires explicit configuration.

### 2. Posture-aware

- dev/staging: `observe` (no enforcement)
- secure/prod: `advisory` (emit events, no blocking)
- Operators must explicitly set `VERITAS_CONTINUATION_ENFORCEMENT_MODE=enforce`.

### 3. Only high-confidence conditions

- Every enforcement condition requires ≥0.80 confidence (configurable).
- Two of four conditions are deterministic (confidence=1.0).
- The remaining two have graduated confidence scaling.

### 4. Conceptually separate from FUJI

- Continuation enforcement operates on chain-level state, not step-level decisions.
- FUJI remains the final safety/policy gate for each step.
- No new `gate.decision_status` values are introduced.
- No FUJI logic is modified.

### 5. Every enforcement event is auditable

- Logged via Python logging
- Carries full linkage: `claim_lineage_id`, `snapshot_id`, `receipt_id`
- Replay-visible: `law_version`, conditions, reasoning
- Operator-visible: `action`, `severity`, `reasoning`

### 6. Fail-closed for enforcement, not for observation

- In `enforce` mode, enforcement actions are applied.
- In `observe`/`advisory` mode, the system continues as before.
- If the enforcement evaluator itself fails, the pipeline continues
  (best-effort, same as Phase-1 continuation revalidation).

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `0` | Enable Continuation Runtime |
| `VERITAS_CONTINUATION_ENFORCEMENT_MODE` | `observe` | `observe` / `advisory` / `enforce` |

### Enforcement Config Defaults

| Parameter | Default | Description |
|---|---|---|
| `degradation_repeat_threshold` | 3 | Consecutive degraded receipts before trigger |
| `min_confidence` | 0.80 | Minimum confidence for any condition |
| `replay_divergence_threshold` | 0.30 | Max divergence ratio before trigger |

### Action Map (Default)

| Condition | Action |
|---|---|
| `repeated_degradation` | `require_human_review` |
| `approval_required_without_approval` | `halt_chain` |
| `replay_divergence_exceeded` | `escalate_alert` |
| `policy_boundary_violation` | `halt_chain` |

---

## File-by-File Summary

| File | Change |
|---|---|
| `veritas_os/core/continuation_runtime/enforcement.py` | **New.** Enforcement engine: EnforcementMode, EnforcementAction, EnforcementCondition, EnforcementEvent, EnforcementConfig, ContinuationEnforcementEvaluator |
| `veritas_os/core/continuation_runtime/__init__.py` | Updated exports for enforcement types |
| `veritas_os/core/config.py` | Added `continuation_enforcement_mode` to CapabilityConfig |
| `veritas_os/core/posture.py` | Added `continuation_enforcement_mode` to PostureDefaults with posture-aware defaults |
| `veritas_os/core/pipeline/__init__.py` | Added Stage 5.9b enforcement evaluation in pipeline |
| `veritas_os/core/pipeline/pipeline_types.py` | Added `continuation_enforcement_events`, `continuation_enforcement_halt` to PipelineContext |
| `veritas_os/core/pipeline/pipeline_response.py` | Include enforcement data in response |
| `veritas_os/core/pipeline/pipeline_persist.py` | Include enforcement audit fields in trustlog |
| `tests/test_continuation_enforcement.py` | 64 unit tests for enforcement logic |
| `tests/test_continuation_enforcement_integration.py` | 15 integration tests for mode switching and pipeline |
| `tests/test_continuation_enforcement_audit.py` | 11 audit/replay/operator-visibility tests |
| `README.md` | Updated continuation section with enforcement modes |
| `docs/architecture/continuation_enforcement_design_note.md` | This design note |

---

## Verification Commands

```bash
# Run enforcement tests
python -m pytest tests/test_continuation_enforcement.py tests/test_continuation_enforcement_integration.py tests/test_continuation_enforcement_audit.py -q --tb=short

# Run all continuation tests (existing + new)
python -m pytest tests/test_continuation_enforcement.py tests/test_continuation_enforcement_integration.py tests/test_continuation_enforcement_audit.py tests/test_continuation_revalidator.py tests/test_continuation_receipt_first.py tests/test_continuation_receipt_enrichment.py tests/test_continuation_golden.py tests/test_continuation_integration.py tests/test_continuation_replay.py tests/test_continuation_eval_harness.py -q --tb=short

# Run full test suite
python -m pytest veritas_os/tests/ tests/ -q --tb=short

# Lint changed files
ruff check veritas_os/core/continuation_runtime/enforcement.py veritas_os/core/continuation_runtime/__init__.py veritas_os/core/config.py veritas_os/core/posture.py veritas_os/core/pipeline/__init__.py veritas_os/core/pipeline/pipeline_types.py veritas_os/core/pipeline/pipeline_response.py veritas_os/core/pipeline/pipeline_persist.py
```
