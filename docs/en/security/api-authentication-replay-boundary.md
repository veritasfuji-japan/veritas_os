# API authentication and HMAC replay boundary

Source baseline: `3fc36cfb7e240424871f280c93bef9f1f127b8a1` (after #2397).
This is a scoped source/ASGI authentication review, not production validation or
a complete vulnerability assessment.

## Mounted application boundaries

`server.py` mounts the following routers. Permissions are enforced by individual
route dependencies; successful API-key validation alone does not confer every
permission. Read the current route modules for exact paths.

| Router / path family | Router authentication | Route authorization / replay protection |
| --- | --- | --- |
| Public system: root, health, status aliases | Public | No HMAC |
| Decide: `/v1/decide`, `/v1/fuji/validate` | API key + rate limit | `decide`; no HMAC dependency |
| `/v1/replay/{decision_id}` | API key + rate limit | Handler manually invokes HMAC verification and forces strict replay; no separate RBAC permission dependency |
| `/v1/decision/replay/{decision_id}` | API key + rate limit | `trust_log_read`; forces mocked external APIs; no HMAC dependency |
| Memory: put / erase | API key + rate limit | `memory_write`; tenant identity derived from API key; no HMAC |
| Memory: get / search | API key + rate limit | `memory_read`; tenant identity derived from API key; no HMAC |
| Trust read / verification / export | API key + rate limit | `trust_log_read`; no HMAC |
| Trust feedback | API key + rate limit | `trust_feedback_write`; no HMAC |
| WAT shadow issue / validation / revocation | API key + rate limit | `decide`; no HMAC |
| WAT event / timeline reads | API key + rate limit | `trust_log_read`; no HMAC |
| Governance reads / writes | API key + governance access check | `governance_read` / `governance_write`; no HMAC |
| System metrics / compliance reads | API key | `compliance_read`; no HMAC |
| System reports | API key | `governance_read`; no HMAC |
| System configuration / halt controls | API key | `config_write`; no HMAC |
| Observability | API key | `governance_read`; no HMAC |
| SSE `/v1/events` | Header-first API key; query credential opt-in only | Current per-event read permissions; governance events also use the governance access guard; no HMAC |
| WebSocket `/v1/ws/trustlog` | Explicit WebSocket API-key authentication in handler | Current per-event read permissions within the existing four-type filter; no HMAC |

HMAC is not a global middleware. An imported `verify_signature` symbol alone
would not establish enforcement; the legacy replay handler explicitly calls it.
Absence of HMAC on other routes is not itself evidence of an authentication
bypass. Bind single-use execution authorization remains a separate boundary.

The two replay handlers use different engines and contracts. The legacy public
handler explicitly requests `strict=True`, which makes its replay engine mock
external APIs and disable the replay memory store, regardless of the deployment
default or signed request body. Other callers of the engine can still choose
non-strict behavior; this route check does not establish global outbound-network
isolation or permission parity with the other replay handler. Replay execution
safety and stream authorization remain separate review surfaces.

## Event-stream read authorization

Previously, SSE delivered every event in its shared history/queue to any valid
API key. This exposed compliance configuration and governance notifications to
an `operator` key even though that role cannot read those resources through the
ordinary APIs. WebSocket's type filter also admitted `compliance.pending_review`
without checking `compliance_read`.

Both streams now check the current configured API-key role before sending each
event, including history prefilled at subscription and events already queued
when the role changes. The header remains authoritative over a query key;
`X-Role` cannot grant the API-key role's read permissions. Removed keys retain
the existing stream termination behavior.

| Event types | Required permission |
| --- | --- |
| `trustlog.appended`, `trustlog.debate`, `trustlog.critique`, `decide.completed`, `fuji.rejected`, `wat.shadow.validation` | `trust_log_read` |
| `compliance.config.updated`, `compliance.pending_review` | `compliance_read` |
| `governance.updated`, `governance.alert` | `governance_read`, plus the existing governance role/tenant/bypass guard |
| Unclassified event types | Suppressed for every role until explicitly classified |

WebSocket retains its narrower existing set: the three `trustlog.*` types and
`compliance.pending_review`. SSE filters the classified inventory. Suppression
does not close an otherwise valid connection; allowed events can still arrive.
Sequence IDs may consequently have gaps. Synthetic SSE lifecycle tests use a
classified event so send-failure and disconnect checks still exercise delivery.

`test_stream_authorization.py` verifies the mounted application with synthetic
keys/readiness: all three API roles, both transports, header and opted-in local
query credentials, history/live delivery, queued events after role downgrade,
and governance access constraints. These are process-local role checks, not
customer/tenant isolation, object-level authorization, external IdP revocation,
cross-process secret distribution, or production validation. Governance events
also use the authenticated-scope guard below, including current key tenant
membership. Stream role tests explicitly grant auditors governance access in
their fixture; the default governance allowlist does not grant that access.

## Authenticated governance scope

The additional governance access guard previously trusted the caller's
`X-Role` and checked only whether `X-Tenant-Id` matched a deployment-wide string.
An auditor could claim an allowed role to read governance resources, and a key
could claim the configured tenant without evidence of membership. Ordinary
write permissions still prevented auditors from acquiring `governance_write`;
that existing protection must not be confused with enforcement of the
additional governance role/tenant constraints.

The guard now requires the principal established by API authentication and
verifies that the request's key matches that context. It resolves the current
key role from server configuration and applies the governance allowlist to that
role as well as the existing header assertion. A configured tenant additionally
requires a matching server-side `tenant_id` in the key's `VERITAS_API_KEYS`
entry. Missing, invalid or mismatched membership fails closed. The tenant header
remains an additional scope assertion; it cannot create membership. This same
guard runs before governance SSE delivery, so queued events respect current
role and tenant changes.

`tenant_id` is an optional nonempty string. Existing unbound multi-key entries
and legacy single keys still work when tenant scope is unset, but cannot access
tenant-scoped governance APIs until a multi-key entry explicitly binds them.
See the environment reference and `.env.example` for migration. The existing
explicitly acknowledged RBAC bypass still disables these additional role/tenant
constraints; authenticated principal context and ordinary route permissions
remain required.

Mounted read/write regressions require rejection before handler callbacks;
authorized read controls, parser roundtrip/invalid-value cases, and existing
real Bind write tests cover compatibility. No external provider is called.
This is a configured governance-scope boundary, not per-tenant policy storage,
object-level authorization, organizational identity federation, or full
multi-tenant isolation. A BFF using a shared backend key still presents that
key's backend identity; end-user identity propagation is a separate boundary.

## Nonce expiry defect and correction

The verifier accepts `abs(int(now) - signed_timestamp) <= 300`. Previously it
retained an admitted nonce for only 300 seconds from admission. A timestamp
accepted up to 300 seconds ahead therefore outlived the nonce record. Even a
current timestamp had a fractional-second gap at the inclusive final second.
The same signed HTTP request could reach the replay callback twice.

The verifier now retains a nonce for at least 300 seconds and until
`signed_timestamp + 300 + 1`, whichever is later. The extra second covers integer
timestamp truncation. Redis nonce TTL conversion rounds up to milliseconds.
Future-dated requests can occupy nonce capacity for about 601 seconds. Capacity
exhaustion continues to refuse new admissions; unexpired records are not evicted.
The signed payload format and accepted timestamp skew remain unchanged.
Existing nonce records are not extended retroactively. Mixed-version workers
still admit requests through the old behavior; deploy consistently and allow
the previous signature acceptance horizon to pass before relying on the fix.

## Bounded verification

`test_replay_http_nonce_window.py` sends in-process ASGI HTTP requests to the
mounted production application. API-key validation, rate limiting, HMAC and the
in-memory nonce implementation run normally; only the replay business callback
is stubbed. A controlled clock covers current/future timestamps, immediate and
end-of-window replays, fresh requests, invalid keys/signatures/timestamps and
synthetic store failures. The regression failed before the correction.

The dedicated real Redis workflow also exercises that mounted HTTP route with
actual Redis storage. It verifies current/future timestamp retention using PTTL
and rejects immediate replay. This measures TTL rather than waiting ten minutes.
It uses a stubbed replay callback and proves no external business effect.

These tests do not prove production transport security, clock rollback
resistance, deployment configuration, authorization for every business object,
or Redis rollback resistance. Existing process/restart tests and the
[Redis restart boundary](auth-redis-restart-boundary.md) retain their own scope.
