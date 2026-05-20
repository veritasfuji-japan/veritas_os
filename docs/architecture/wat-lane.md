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

## WAT token structure

The current v1 implementation persists **WAT lane event records** (audit entries),
not a standalone signed bearer token object. The structure below is sourced from
`veritas_os/audit/wat_events.py` and route request/response models in
`veritas_os/api/routes_wat.py`.

| Field | Type | Description |
|---|---|---|
| `event_id` | `string` (UUID) | Unique event record identifier generated at write time. |
| `ts` | `string` | Write timestamp in canonical UTC format (`YYYY-MM-DDTHH:MM:SSZ`). |
| `event_ts` | `string` | Canonical event timestamp; same normalization rule as `ts` in v1. |
| `lane` | `string` | Fixed event lane label: `wat_shadow`. |
| `wat_id` | `string` | Stable WAT identifier used to correlate lane events. |
| `event_type` | `string` | One of supported WAT event types (issued/validated/replay/revocation/etc.). |
| `actor` | `string` | Initiator identity (for API routes typically `api:<rbac_role>`). |
| `status` | `string` | Event outcome label (`ok` / `warning`, depending on path). |
| `details.metadata` | `object` | Retained event metadata (includes fields such as `psid`, `ttl_seconds`, `mode`, `reason`, warning and validation context when present). |
| `details.event_pointers` | `object` | Pointer-style references; includes `observable_digest_ref` when provided/valid. |
| `details.observable_digest_ref` | `string` | Canonical separate-store digest locator/reference (locator-form expected). |
| `details.observable_digest_access_class` | `string` | Access-class label for observable digest linkage (`restricted` or `privileged`). |
| `details.wat_metadata_retention_ttl_seconds` | `integer` | Metadata retention TTL applied to this event record. |
| `details.wat_event_pointer_retention_ttl_seconds` | `integer` | Event-pointer retention TTL applied to this event record. |
| `details.observable_digest_retention_ttl_seconds` | `integer` | Observable-digest reference retention TTL applied to this event record. |
| `details.retention_policy_version` | `string` | Retention-policy version label persisted with the record. |
| `details.retention_enforced_at_write` | `boolean` | Whether retention policy enforcement was active at write time. |
| `details.retention_boundary_assertion` | `object` | Assertion result for retention-boundary checks (`outcome`, `failed_reasons`). |
| `trustlog_anchor_ref` | `object` | TrustLog append result reference (`trustlog_decision_id`, `payload_hash`, `anchor_backend`, `anchor_status`) or error payload on append failure. |

**Signing mechanism (v1):**
- WAT lane records themselves are not assigned a dedicated per-token `hmac` or
  per-token `Ed25519` signature field in the WAT event schema.
- Integrity linkage is provided by `trustlog_anchor_ref`, produced via TrustLog
  signed append helpers (`append_signed_decision`) that use the project
  signing stack (Ed25519 key material in TrustLog signing utilities).

**Expiry semantics (v1):**
- No standalone WAT token expiry claim (for example `exp`) is persisted as a
  first-class top-level token field in the WAT event record schema.
- `ttl_seconds` may appear in event metadata for issuance telemetry input, but
  this is metadata attached to lane events, not a separately validated token
  lifetime contract.

**Canonical `event_ts` format:** `YYYY-MM-DDTHH:MM:SSZ` (UTC, seconds precision).

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
- ⚠️ **v1 no-op flag**: `revocation.auto_escalate_confirmed_revocations` is
  present in the policy schema but has **no runtime effect** in v1.
  Operators must not rely on automatic escalation; explicit confirmation
  (`CONFIRM_REVOKED_CONFIRMED`) is always required.
  Activating this flag requires a future implementation — see issue tracker.

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

📌 **Tracking**: These items are unresolved operational gaps. Create a
GitHub issue for each and link here (replace `#TBD` below):
- SLO/error-budget for WAT event write/read: issue #TBD
- Operator runbook for repeated TrustLog anchor-append failure: issue #TBD

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
- ⚠️ **v1 no-op flag**: `revocation.auto_escalate_confirmed_revocations` is
  present in the policy schema but has **no runtime effect** in v1.
  Operators must not rely on automatic escalation; explicit confirmation
  (`CONFIRM_REVOKED_CONFIRMED`) is always required.
  Activating this flag requires a future implementation — see issue tracker.

## Non-goals

This WAT lane (current v1 implementation) is not intended to:

- grant execution authorization independent of existing policy/FUJI controls;
- replace bind-governed governance policy mutations;
- replace TrustLog as system-of-record for broader decision audit trails;
- define a public, final DecideResponse schema contract (see decide-response-v2
  plan for schema evolution intent).
