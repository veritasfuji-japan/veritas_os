# WAT Lane Architecture and Operations

## Purpose

The WAT lane is a **shadow/observer lane** for Witness Attestation Token (WAT)
telemetry. It records issuance, validation, replay-suspected, and revocation
transitions as auditable events, without becoming an execution-authorization
path. It is exposed through `/v1/wat/*` API routes and is also used by the
`/v1/decide` observer hook when WAT shadow mode is enabled. 

This document is implementation-factual for the current v1 code path.

## Scope and location in the system

Primary implementation surfaces:

- HTTP routes: `veritas_os/api/routes_wat.py`
- Decide observer hook integration: `veritas_os/api/routes_decide.py`
- Event persistence and revocation-state derivation: `veritas_os/audit/wat_events.py`
- Router registration: `veritas_os/api/server.py`
- Bind coverage classification: `veritas_os/policy/bind_coverage.py`
- API behavior tests: `tests/test_wat_api.py`

See also:

- [Core Responsibility Boundaries](./core_responsibility_boundaries.md)
- [DecideResponse v2 Plan](./decide-response-v2-plan.md)
- [TrustLog Storage Consolidation](./trustlog_storage_consolidation.md)

## High-level request/response flow

### A) Direct WAT API lane (`/v1/wat/*`)

1. Caller hits WAT route with RBAC-authenticated key.
2. Route enforces permission class:
   - mutate endpoints (`issue-shadow`, `validate-shadow`, `revocation/*`) require `Permission.decide`;
   - read endpoints (`events`, `{wat_id}`) require `Permission.trust_log_read`.
3. Route persists WAT event(s) via `veritas_os.audit.wat_events` helpers.
4. Route returns event payload (or read timeline) to caller.

### B) Decide observer hook (`/v1/decide`)

1. `/v1/decide` runs normal pipeline/gating flow.
2. WAT shadow observer helper attempts to run if policy allows `wat.enabled=true`
   and `wat.issuance_mode == "shadow_only"`.
3. Hook emits `wat_issued`, signs/validates WAT locally, then emits either
   validation or replay-suspected event.
4. Hook publishes observer summary event (`wat.shadow.validation`) and attaches
   observer metadata (`meta["wat_shadow"]`) when available.
5. Any hook failure is intentionally contained (`debug` path) and does not
   raise into the main `/v1/decide` production flow.

## Relationships to Kernel, Pipeline, FUJI, TrustLog, and DecideResponse

- **Kernel / Pipeline**: WAT lane is not the decision engine; it is an additive
  observer path attached from decide routing logic. It does not replace planner,
  kernel orchestration, or pipeline stages.
- **FUJI**: WAT shadow mode is observer-only and does not override FUJI
  allow/block/defer decisions.
- **TrustLog**: WAT event records include a `trustlog_anchor_ref` and attempt
  TrustLog anchor append through audit helpers; this is an audit linkage, not a
  decision-authorization mechanism.
- **DecideResponse**: WAT observer output is attached as metadata (`wat_shadow`)
  when available; it is not the primary decision payload.

## What WAT is allowed to bypass or simplify

Current implementation allows WAT to be handled as:

- **audited exemption / observer lane** for bind-governed execution controls on
  `/v1/wat/issue-shadow`, `/v1/wat/validate-shadow`, and `/v1/wat/revocation/{wat_id}`;
- simplified shadow telemetry semantics (event write/read focused);
- policy flag `revocation.auto_escalate_confirmed_revocations` is schema-visible
  but runtime no-op in v1 (explicit confirmation still required).

## What WAT must never bypass

From current code and tests, WAT lane must not bypass:

- **RBAC** controls (auditor can read but cannot mutate WAT lane state);
- **explicit confirmation** for confirmed revocation transitions
  (`CONFIRM_REVOKED_CONFIRMED`);
- **governance/audit traceability** expectations (events persisted with lane,
  actor, timestamp, and anchor reference);
- **core decision enforcement ownership** (WAT does not become execution
  privilege, and does not replace FUJI or bind-governed policy execution paths).

## Failure and degraded behavior

Current degraded/failure characteristics:

- WAT observer hook is fail-soft toward `/v1/decide`: policy-load or internal
  observer failures return `None` and do not raise into main response path.
- Unsupported direct validation `outcome_event` returns HTTP `422`.
- `GET /v1/wat/{wat_id}` for unknown id returns HTTP `404` with
  `error=wat_not_found`.
- Warning-class outcomes are represented by warning event status/context in
  event details.

**TBD / requires implementation confirmation**:

- Formal SLO/error-budget targets for WAT event write/read availability.
- Required operator runbook behavior if TrustLog anchor append repeatedly fails
  (currently warning log path exists in helper code).

## Testing expectations

Minimum lane checks should include:

- issuance success and event-type correctness;
- validation success and event-type correctness;
- read-by-id and listing behavior;
- revocation pending + confirmed path;
- explicit confirmation requirement for confirmed revocation;
- RBAC read-vs-mutate separation;
- canonical `event_ts` emission.

Existing implementation coverage: `tests/test_wat_api.py`.

## Operator notes

- WAT lane event storage defaults to JSONL under the log directory and supports
  environment override via `VERITAS_WAT_EVENTS_PATH`.
- Event browsing APIs:
  - `GET /v1/wat/events`
  - `GET /v1/wat/{wat_id}`
- Revocation API:
  - `POST /v1/wat/revocation/{wat_id}` always emits pending revocation;
    confirmed event is emitted only with explicit confirmation phrase.
- In v1, `auto_escalate_confirmed_revocations` should be treated as
  non-runtime/non-activating.

## Non-goals

This WAT lane (current v1 implementation) is not intended to:

- grant execution authorization independent of existing policy/FUJI controls;
- replace bind-governed governance policy mutations;
- replace TrustLog as system-of-record for broader decision audit trails;
- define a public, final DecideResponse schema contract (see decide-response-v2
  plan for schema evolution intent).
