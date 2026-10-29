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

## Memory erasure attribution

`POST /v1/memory/erase` requires `memory_write` and keeps deriving its target
user from the API key; a body `user_id` cannot select another principal. The
erasure actor now comes from the authenticated request principal, before loading
or mutating the store. Missing principal context returns HTTP 403. The body
`actor` field remains accepted for compatibility but does not select the actor
written into the backend erasure report or audit record. Previously a caller
could supply another person's label, an empty value, or the generic default.

Mounted HTTP regressions use two configured operator keys and the real JSON
MemoryStore on temporary files. Reopening the file verifies authenticated actor
attribution. Separate controls verify that a forged target cannot erase the
other principal's records, legal-hold records remain, unprotected source and
derived records are removed, and missing/invalid keys, read-only roles or
missing principal context cannot mutate the file. The pre-fix selection had
eight failures and five passing controls.

This fixes audit attribution, not an observed cross-principal deletion bypass.
The missing-principal test deliberately suppresses normal context binding; it
does not demonstrate an unauthenticated route bypass. These tests do not prove
PostgreSQL erasure, concurrency/rollback resistance, immutable audit storage,
external IdP identity, all lifecycle metadata shapes or production legal-hold
compliance. The BFF's shared backend key remains a backend identity, not a
trusted per-end-user identity. Low-level internal erasure helpers retain their
explicit actor argument for trusted callers.

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

## BFF Authorization and Cookie credential selection

The BFF proxy, browser `/api/veritas/session` and legacy `/api/auth/session`
share the same credential resolver. A
present `Authorization` header now owns credential selection: it must contain a
complete Bearer credential (case-insensitive scheme, one or more separating
spaces). Empty, unsupported or malformed values return HTTP 401 without using
a session cookie. A well-formed but unconfigured token retains HTTP 403.
Cookie authentication is considered only when Authorization is absent; missing
server token-role configuration retains HTTP 503.

Previously the resolver split on a single space and could fall back to an
ambient admin cookie for an unsupported scheme, an incomplete Bearer value or
multiple separating spaces. It could also accept a valid token prefix while
ignoring extra credential text. In particular, a multi-space viewer Bearer
credential could be replaced by the admin cookie, resulting in a different
authenticated role from the one explicitly selected by the caller.

The regression calls the actual session and privileged proxy handlers with
synthetic credentials and mocked upstream fetch. It checks refusal before
forwarding, exact viewer-role selection despite an admin cookie, unknown-token
refusal, and valid Bearer/cookie-only controls. Production session-issuance
guards and the explicit global-session escape hatch are unchanged and retain
their existing tests. This fix does not add session expiry, external IdP
revocation, trusted per-user backend identity, or browser/deployment validation.

### Browser Cookie delivery to session lookup

The middleware and development login issue `__veritas_bff` with
`Path=/api/veritas`. The governance page previously called `/api/auth/session`,
which is outside that path. A browser therefore omitted the Cookie and could
report an authenticated session as unauthenticated. Direct handler tests that
manually supplied a Cookie header did not exercise this browser path rule.

The page now calls `/api/veritas/session`, a static route that reuses the legacy
session handler. The existing Cookie scope, HttpOnly/SameSite flags and issuance
rules remain unchanged; no cookie migration or broader scope is required. The
legacy endpoint is retained for programmatic Bearer clients. Its existence does
not cause a scoped Cookie to be sent outside `/api/veritas`.

The frontend E2E gate additionally runs `playwright.cookie-session.config.ts`:
a separate loopback Next.js production server with synthetic configured roles
and explicitly enabled fixture-only global Cookie issuance. It verifies browser
delivery, governance-page role recognition, the legacy path exclusion, and the
shared resolver's malformed-header and explicit-viewer precedence rules. The
fixture disables backend configuration, so it cannot call business APIs. This
is not proof of production login/IdP integration, HTTPS deployment, strict CSP,
external revocation or backend tenant isolation. Existing production issuance
defaults are tested separately and are not relaxed by this fixture.

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
