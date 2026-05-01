# Observe Mode Semantics Foundation

## Purpose

Observe Mode is a **development-time governance mode semantics** that records what the bind boundary would have done, without weakening production fail-closed enforcement.

This document defines semantics, safety constraints, and schema foundations for future implementation work.

## Core policy modes

- `enforce`
  - Production default.
  - Existing fail-closed behavior applies.
  - Blocking checks stop execution.
- `observe`
  - Development / test / sandbox contexts only.
  - Governance checks still run.
  - Violations are recorded as `would_have_blocked`.
  - Execution may continue only in explicitly configured non-production contexts.
  - Audit records preserve the original blocking reason.
- `off`
  - Not recommended.
  - Must never be default.
  - If used, must be explicit and auditable.

## Required observation fields

- `policy_mode`
- `environment`
- `would_have_blocked`
- `would_have_blocked_reason`
- `effective_outcome`
- `observed_outcome`
- `operator_warning`
- `audit_required`

## Safety constraints

- Observe mode must never be the implicit production default.
- Production must remain fail-closed.
- Observe mode must not erase violation evidence.
- Observe mode must not rewrite blocked outcomes as clean success.
- Observe mode must be visible to operators.
- Observe mode is **default off**.
- Observe mode is not an “allow everything” switch.

## Scope in this PR

### Implemented in this PR

- Semantics definition for observe/enforce/off.
- Explicit production safety constraints.
- Additive schema/type foundation for governance observation fields.
- Fixture tests for `enforce` and `observe` modes and invalid mode rejection.
- README and README_JP short references.

### Not implemented in this PR

- Runtime enforcement switch.
- Production bypass behavior.
- UI toggle.
- API mutation endpoint changes.
- Policy engine behavior changes.
- Automatic evidence generation.
- Governance palette implementation.

## Security note

Observe mode misuse can become a security and compliance risk if enabled in production or if audit evidence is suppressed. Any future runtime rollout must include explicit environment guards and operator-visible warnings.


## Dev-only sample live snapshot

- `fixtures/governance_observation_live_snapshot.json` is a development/test/documentation-only sample payload for reproducing Mission Control display with `governance_observation`.
- This fixture does **not** enable Observe Mode runtime behavior and is not loaded by production runtime paths.
- Production fail-closed behavior remains unchanged (`enforce` stays the production default semantics).
- When `governance_observation` is present in payload, Mission Control renders it as read-only operator context.
- `would_have_blocked: true` indicates a violation that should block under production enforcement semantics.
- `effective_outcome: "proceed"` demonstrates a non-production observe-context continuation example.
- `observed_outcome: "block"` preserves the would-be blocking governance outcome for audit visibility.
- `bash scripts/validate_governance_observation_fixture.sh` validates that this sample fixture is preserved by the Mission Control adapter and verified by Mission Control read-only rendering tests.

Short excerpt:

```json
{
  "governance_layer_snapshot": {
    "decision_id": "dec_observe_demo_001",
    "governance_observation": {
      "policy_mode": "observe",
      "environment": "development",
      "would_have_blocked": true,
      "effective_outcome": "proceed",
      "observed_outcome": "block"
    }
  }
}
```
