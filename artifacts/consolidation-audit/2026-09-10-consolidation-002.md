# Consolidation 002 — Exact Duplicate Behavior Tests

Status: **IMPLEMENTED IN PR — awaiting merge**  
Source main: `bb114ecf0172db0b03f7ff2da4d30effffae7406`  
Audit basis: PR #2218 Phase 2 overlap matrix

## Objective

Reduce maintenance duplication in the sequential plan8–plan17 coverage suites
without changing runtime behavior or removing distinct safety/failure-mode
coverage.

## Removed duplicate tests

Four duplicate tests were removed after line-by-line comparison:

1. `test_replay_decision_endpoint_query_params_error_defaults_true`
2. `test_replay_decision_endpoint_defaults_mock_true_on_query_error`
3. `test_rollout_enforcement_unknown_strategy_defaults_to_safe_full`
4. `test_schedule_nonce_cleanup_reschedules_even_after_cleanup_error`

## Canonical retained coverage

### Replay query-parameter failure

Retained:

`test_routes_replay_decision_query_param_error_defaults_to_mock_true`

This retained test proves:

- query parameter access failure is handled;
- the exact decision id is forwarded;
- `mock_external_apis=True` is forced;
- the replay response is returned unchanged.

It subsumes the two removed weaker variants.

### Unknown rollout strategy

Retained:

`test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full`

This retained test proves:

- unknown strategy does not disable enforcement;
- state is `full_unknown_strategy`; and
- a warning is emitted.

It subsumes the removed outcome-only variant.

### Nonce cleanup scheduler failure while active

Retained and strengthened:

`test_rate_nonce_scheduler_logs_when_cleanup_raises`

It now proves:

- cleanup failure emits a warning;
- exactly one replacement timer is created;
- the replacement interval remains 60 seconds; and
- the replacement timer starts.

This subsumes the removed weaker active-scheduler variant.

## Explicitly preserved as distinct

The following were reviewed and **not** consolidated.

### Pipeline unavailable / lazy-state reset

Both remain because they exercise different surrounding conditions:

- `test_decide_pipeline_unavailable_resets_lazy_state`
- `test_decide_pipeline_unavailable_resets_lazy_state_when_mutated`

The variants differ in response handling and event-publication behavior, so they
are not safe duplicates.

### Nonce cleanup scheduler stopped state

Retained:

`test_schedule_nonce_cleanup_logs_and_stops_when_timer_cleared`

This covers cleanup failure when the scheduler has been stopped and therefore
must not reschedule. It is semantically distinct from the active-scheduler case.

### Effective nonce max branches

All remain:

- import-error fallback
- non-integer override fallback
- valid integer override

They target different branches and are not duplicate coverage.

## Audit tooling update

The Phase 2 matrix now marks:

- replay query-failure group → `CONSOLIDATED`
- unknown rollout strategy group → `CONSOLIDATED`
- pipeline unavailable group → `PRESERVE_DISTINCT_VARIANTS`
- nonce scheduler failure group → `PARTIALLY_CONSOLIDATED_PRESERVE_DISTINCT_STATES`
- effective nonce max group → `PRESERVE_DISTINCT_BRANCHES`

A regression guard verifies that the four removed test names are absent and all
required retained cases remain present.

## Runtime impact

**None.**

No production/runtime Python module is changed.

No authorization, policy decision, Bind, effect, reconciliation, receipt,
outcome, credential, migration, TrustLog runtime, or network behavior changes.

## Proof boundary

The frozen controlled Decision-to-Effect architecture remains unchanged.

Full CI and the frozen reproducible Decision-to-Effect proof must pass before
merge.
