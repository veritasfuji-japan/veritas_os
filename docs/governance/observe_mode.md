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
