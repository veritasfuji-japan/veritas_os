# Bind EFFECT_UNKNOWN Reconciliation v1

## Purpose

This boundary prevents ambiguous external execution from being mislabeled as `NOT_EXECUTED`.

The state flow is:

`Authorization consumed → IN_FLIGHT → {CONFIRMED_NO_EFFECT | EFFECT_UNKNOWN}`

and, when effect state is unknown:

`EFFECT_UNKNOWN → verified reconciliation → {CONFIRMED_EFFECT | CONFIRMED_NO_EFFECT | EFFECT_UNKNOWN}`

## Rules

1. Successful authorization consumption creates `IN_FLIGHT` before credential access or adapter construction.
2. If Bind completes without reaching adapter `apply`, the state may become `CONFIRMED_NO_EFFECT`.
3. If adapter `apply` was attempted and there is no independently verified external acknowledgement, the state is `EFFECT_UNKNOWN` even if Bind itself returns a committed receipt.
4. Unknown or unexpected interruption after consumption is never converted to `NOT_EXECUTED`.
5. Reconciliation input is not trusted merely because a caller declares a result. A `ReconciliationEvidenceVerifier` must return sealed verified evidence.
6. Reconciliation evidence must bind the exact operation ID, authorization ID, and consumption ID.
7. Terminal `CONFIRMED_EFFECT` and `CONFIRMED_NO_EFFECT` states are immutable.
8. The same Real Bind Authorization remains consumed throughout reconciliation and cannot be replayed.

## Persistence

`bind_effect_states` stores one current state per operation with optimistic compare-and-set semantics (`state` + `revision`). The production implementation uses PostgreSQL and the reference implementation includes a process-local in-memory store for deterministic tests.

The PostgreSQL CI races 32 concurrent state transitions from the same `IN_FLIGHT` revision and requires exactly one winner.

## Non-claims

This boundary does not claim exactly-once delivery from an external provider. It provides exactly-once authorization consumption plus conservative effect-state accounting and verified reconciliation.

A generic `adapter.apply()` call is never by itself proof that the external system committed an effect.
