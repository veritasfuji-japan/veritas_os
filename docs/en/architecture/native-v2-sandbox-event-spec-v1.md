# Native v2 sandbox event integration specification v1

Status: implementation proposal for human review; no runtime implementation or deployment authorization.
Baseline: `33460417782b3659a32a1ecfbc20714edc5943bc` (#2197 merged).
Japanese companion: [日本語版](../../ja/architecture/native-v2-sandbox-event-spec-v1.md).

## 1. Purpose and boundary

Demonstrate one native v2 execution path that durably registers one synthetic event
in a dedicated sandbox. The effect is insertion of a sandbox event row, not receipt
creation or an HTTP acknowledgement. No production API, payment, customer data or
general adapter framework is included. This document specifies future behavior;
it does not claim that credential resolution, native v2 Bind or reconciliation works today.

Existing code anchors:

- `veritas_os/policy/native_bind_authorization.py`: issuance and verification.
- `veritas_os/policy/native_bind_authorization_consumption.py`: current rechecks and
  durable single-use consumption; its result is audit lineage, not an execution capability.
- `veritas_os/policy/webhook_bind_adapter.py`: reference HTTP adapter. Its HMAC and
  derived idempotency-key protocol is not automatically the native v2 protocol below.
  Reuse needs explicit compatibility review; do not silently substitute either key.

## 2. One operation and its identity

| Item | Fixed proposal |
| --- | --- |
| Action | `sandbox.event.register.v1` |
| Effect request | `POST /v1/events` at one deployment-pinned HTTPS origin |
| Body | Exactly `event_id` (UUID string) and `message` (synthetic UTF-8 string, 1–256 bytes); reject extra fields |
| Request limit | 4 KiB; reject duplicate JSON keys and non-JSON values |
| Lookup | `GET /v1/operations/{operation_id}`; lookup by the original idempotency key when the response was lost |
| Transport | TLS identity verification; no redirects or automatic POST retries |
| Timeout | 5 seconds total per request; expiration does not imply no effect |

Before issuance, bind the method, exact origin/path, canonical payload digest,
event ID, ActionClassContract digest, credential reference/version/scope, endpoint
identity and authorization idempotency key to the exact action. Use the repository's
canonical JSON/hash contracts; choose no alternate serialization at dispatch.
Implement missing payload binding before resolving credentials. Do not regenerate
an idempotency key from mutable adapter configuration. Lookup uses the same pinned
origin and validated identifiers, never a response-supplied arbitrary URL.

## 3. Trust and credentials

The deployment operator supplies trusted issuer keys, the ActionClassContract,
source registry, endpoint identity and credential metadata independently of packets.
The operator controls their versioning/revocation through reviewed configuration.
Embedded snapshots cannot replace those inputs, including with unchanged IDs/versions.
Human approval, where required, must be verified from an actual authorized receipt;
never synthesize or infer it. Sandbox service administrators, the credential provider,
host clock infrastructure and registry administrators remain explicit trusted parties.
Compromise of those parties is outside this first slice's guarantee.

Use one credential model: provider-managed, versioned sandbox bearer tokens over TLS.
The executor may resolve only its authorized reference, scoped to event registration
and operation lookup at the pinned sandbox. Reconciliation uses a separate read-only
principal under the same token model. No caller-supplied secret or arbitrary reference.
Validate provider-authenticated audience, scope, version, expiry and revocation
metadata before use; missing metadata/provider errors fail closed. There is no
fallback to a broad environment token. Rotation changes the binding and requires
new authorization. Keep material in memory for the attempt and dispose of references
after use; Python memory erasure is not claimed. Logs/receipts contain references
and metadata digests only, never tokens, headers or secret-bearing exceptions.

The concrete HTTPS origin, hosting, provider, token references, principals and key
fingerprints are deployment prerequisites, not values to invent in this document.
Authenticated input proves origin/integrity, not that the external system is truthful.

## 4. Time and material change

Use executor-controlled UTC wall time and a monotonic timer; ignore request-supplied
verification time. Proposed sandbox limits: clock health sampled within 30 seconds,
reported uncertainty at most 1 second, pre-effect recheck to send at most 1 second.
Missing health, detected wall-clock rollback or exceeded limits stops dispatch.
Treat a validity window as usable only if the entire uncertainty interval is inside
it; do not add expiry grace. Monotonic time measures durations, not UTC authenticity.
These limits require deployment validation before enabling the path.

Changes to payload/event ID, destination, credential metadata, contract content,
authority, approval or revocation invalidate continuation and require reevaluation.
For this first slice, do not introduce a generic materiality threshold. A fresh risk
review may have a new timestamp/hash, but must pass the existing verifier and bind
to the same exact action; changed risk conditions cannot be ignored as harmless.

## 5. Consumption to pre-effect boundary

1. Verify issuance and current governance using existing native v2 code and external
   trust inputs. Atomically consume once in PostgreSQL.
2. Resolve the matching durable consumption row from trusted storage. Check the full
   authorization/action identity, not a caller's `authorization_consumed=true` claim.
3. Persist one exclusive execution-attempt claim per consumption identity. Competing
   workers cannot claim another attempt; do not use an expiring lease that permits
   an old worker and its replacement to send concurrently.
4. Recheck current contract, endpoint, credential metadata, authority, human approval,
   revocation and runtime risk before credential material access. Resolve only that
   reference. Repeat the freshness/governance check immediately before send if work
   intervened, and stop if any binding or validity condition changed.
5. Persist dispatch intent before the request can leave the executor. Send once under
   the claimed attempt and original idempotency key. An ambiguous database commit
   prevents dispatch until trusted storage establishes the claim state.

No returned consumption result alone authorizes Bind. Recovery after a crash uses
the durable attempt record. Uncertain ownership or possible dispatch means reconcile,
not claim and send again. Consumption is never rolled back, even if no event occurred.
Local checks do not atomically freeze remote policy/revocation; the bounded delay and
this residual race must be recorded in the E2E evidence, not described as eliminated.

## 6. Sandbox durability and duplicate semantics

In one sandbox database transaction, enforce uniqueness of the original idempotency
key and event ID, insert the event, and persist its operation record and request digest.
A response is successful only after commit. Same key/same digest returns the original
operation; same key/different digest returns conflict with no new effect. Reusing the
event ID under another key also conflicts. Concurrent requests produce one row.
Do not expire deduplication records during the PoC or restart the namespace while
outstanding/unknown operations exist. An authorized teardown must preserve evidence.

The response contains operation ID, original key, payload digest and persisted state.
`201` means a new durable registration; `200` means the same registration already
exists; `409` is conflict. The client still treats an acknowledgement as an observation
until reconciliation. Provider errors and 5xx/timeouts are not proof of no effect.

## 7. Receipt, outcome and reconciliation

| Observation/state | Meaning |
| --- | --- |
| Accepted locally | Governance/attempt accepted; no external-success claim |
| Dispatch intent persisted | A request may have been sent; crash recovery starts with lookup |
| Dispatched | Transport reports send; does not establish persistence |
| Externally acknowledged | Valid response names a matching operation |
| Confirmed success | Read-only reconciliation confirms the durable event, key, event ID and digest |
| Failed before send | Locally proven no request was issued; authorization remains consumed |
| Unknown | Request/commit/receipt state is ambiguous; no blind resend or success inference |

BindReceipt must report observed facts and link authorization, consumption, attempt,
action digest and operation identity. Outcome adds independent lookup evidence; do
not upgrade an HTTP status to confirmed success. Receipt persistence failure leaves
the attempt unresolved and triggers reconciliation, even if the event exists.
Recovery writes are idempotent and append evidence; they do not rewrite earlier facts.

Use a separate read-only process/principal to query durable sandbox operation state.
This is independent of the dispatch response, not independent of the sandbox operator.
If operation ID is unavailable, query by original key. Not-found, unavailable,
inconsistent digest or unauthenticated replies remain unknown; an in-flight request
may still commit. No automatic retransmission in v1. A replacement authorization for
the same business event is blocked while outcome is unknown. Human escalation may
investigate but cannot turn unknown into proven failure without evidence.

## 8. Acceptance and implementation sequence

| Required experiment | Passing evidence |
| --- | --- |
| Required / legitimately not-required approval | Correct independent policy evaluation; no fabricated receipt |
| Normal registration | One event, consumption, attempt, observed receipt and matching reconciliation |
| Concurrent duplicate workers/requests | One durable claim and one external event |
| Same key/different payload; same event/different key | Conflict, no second row |
| Same-ID/version contract downgrade and source substitution | Fail closed before material access/dispatch |
| Expiry, revocation, drift, clock rollback/unhealthy clock | Stop; no unauthorized dispatch |
| Provider failure or scope/audience/version mismatch | Stop without exposing secrets |
| Crash after consumption / before send | No consumption reuse; recovery consults durable state |
| Effect committed but response lost / receipt write failed | Unknown then lookup-confirmed; no resend |
| Lookup outage, lag or mismatched record | Remain unknown; no guessed outcome |

Implementation order: deployment contract and payload binding → pre-effect/attempt
boundary → credential resolver → sandbox native Bind plus observed Receipt/Outcome
→ reconciliation and crash recovery → reproducible normal/fault E2E. Freeze only after
all acceptance cases pass; preserve the commit, configuration digests and evidence.
Then consolidation audit, benchmark rebaseline and external review follow.

## 9. Required decisions before connection

Record the sandbox origin/TLS identity and owner; credential provider, references and
scopes; trust registry/key administration; clock health source and measured bounds;
database durability/retention and read-only lookup access. Confirm synthetic payloads
and failure-injection scope. These are mandatory deployment inputs. Until provided
and reviewed, implementation may use inert tests, but must not access credentials,
deploy infrastructure or send external requests.

## 10. Initial metadata binding implementation

`veritas_os/policy/sandbox_action_binding.py` supplies the opt-in local binding
boundary. `build_sandbox_action_binding` validates the two-string payload and
explicit deployment pins and returns a `sandbox-action:v1:sha256:` reference.
Include exactly one such reference in the decision candidate's `evidence_refs`
before decision capture, promotion and authorization issuance. It commits to POST,
the exact endpoint, payload digest, full contract digest and credential metadata
pins without introducing a circular dependency on a later authorization digest.

`verify_sandbox_action_binding` calls the native authorization verifier with
independent source/governance/trust inputs, then reconstructs the reference and
checks the verified intent, endpoint and credential metadata. It preserves the
authorization's original idempotency key. The returned immutable association is
not executable permission and is not accepted in place of native verification.
No existing native entry point is rerouted: a future sandbox executor must require
this boundary as well as consumption and final pre-effect checks.

The provider credential version is a deployment pin committed before issuance;
authenticating that version and its expiry/revocation remains a resolver task.
This module does not authenticate TLS, time health, provider data or payload truth,
and does not implement an execution claim, credential access or external effect.

## 11. No-effect attempt preparation

`prepare_sandbox_attempt` reads the durable consumption row and reconstructs all
lineage fields from independently verified native authorization/source inputs.
It reuses `bind_effect_states` to create one permanent `IN_FLIGHT` attempt per
consumption/authorization; uniqueness is enforced in PostgreSQL. Existing v1
execution entry points are unchanged. Process-local stores require explicit test
opt-in and cannot establish cross-process guarantees.

After the claim commits, an executor-configured callback loads independent current
source, contract, credential metadata, authority/approval and runtime-risk inputs.
Native verifiers check them against the original action. No packet snapshot becomes
a trust anchor. Clock/health callbacks are trusted deployment inputs: health age
must be at most 30 seconds, uncertainty at most one second, and both UTC and
monotonic elapsed recheck time at most one second. Rollback fails closed. Validity
is checked from the lower uncertainty bound through a conservative two-second end
horizon (one second of work plus maximum uncertainty). Short remaining validity
therefore stops preparation. Authenticity of host time/health is assumed, not proven.

Read failure, missing consumption or lineage mismatch stops before claiming.
Claim acknowledgement loss or any later verification failure never releases the
attempt or rolls back consumption. A later caller cannot reclaim even an abandoned
attempt. `IN_FLIGHT` does not assert dispatch or success; crash recovery and
independent reconciliation remain required before making any outcome claim.

The returned preparation result is audit data only. This implementation performs
no credential resolution, dispatch-intent persistence, Bind, external request,
Human Approval creation or BindReceipt/Outcome generation. A future executor must
enforce ownership and repeat current checks after credential work at the actual
send boundary. The one-second budget is enforced, not a measured performance
guarantee; deployment throughput and trusted callback configuration remain gates.

## 12. Credential continuation contract

`prepare_and_resolve_sandbox_credential` performs preparation itself. It accepts
the original authorization and independent deployment/source/governance inputs,
never a caller's prepared result or consumed flag. An existing attempt cannot be
resumed through this entry point. PostgreSQL remains the default requirement.

The trusted executor supplies one `SandboxCredentialProvider`. Its `describe`
operation returns no secret. Its `resolve` operation must authenticate the provider,
atomically check the expected metadata digest and current revocation/version, and
return material bound to that exact metadata. No `authenticated=true` packet flag
substitutes for that integration contract. The local code does not establish a
provider trust root, select a vendor, read environment tokens or contact a service.
Provider/hosting configuration and real-provider tests remain deployment gates.

The request pins the credential reference, provider, version, exact scope,
environment and HTTPS origin audience derived from the verified action binding.
Metadata must identify a bearer credential, explicitly report non-revocation and
cover the entire checked time-uncertainty interval. Missing/malformed/stale metadata,
same-reference version changes, different audience, wider scope, expiry and provider
errors stop the call. Each provider operation times out after five seconds with no
retry; descriptor age across the continuation is also bounded to five seconds.

The continuation reads the exact attempt row and repeats the #2200 current checks
after metadata inspection before secret access, and again after resolution. Failed
checks never return material or release the attempt/consumption. Current checks
reuse the existing verifier implementation; embedded snapshots remain untrusted.

Material uses a redacted `SecretBytes` wrapper. The result has no generic JSON,
dataclass or pickle serialization; explicit trusted code can access bytes through
`material.get_secret_value()`. `close()` drops the result's reference; it does not
promise Python memory erasure or control a provider's internal logs. Public failures
contain a fixed code and do not retain provider exception context. Audit data carries
only the preparation and a metadata digest, never a token or token hash.

No Authorization header, Bind, network dispatch, external effect, Human Approval,
BindReceipt or Outcome is created. A future sender must recheck ownership, expiry
and current governance at use, then persist dispatch intent. Tests use synthetic
credentials. Section 13 describes a limited host-clock measurement; real-provider
authenticity and deployment performance remain unproven.

## 13. Bounded host-clock validation

The timing checkpoint preserves the one-second recheck, two-second conservative
horizon and five-second provider/descriptor limits. Each public verifier still
requires its independent source/contract and reconstructs every field. Within that
same call, HARR returns its reconstructed source to native satisfaction, readiness
and final rechecks project children of fully rebuilt parents, and native risk
verification retains the final source it just reconstructed. There is no global or
cross-call verification cache, no caller-supplied verified flag, and no shortcut for
current policy, revocation, signatures or either temporal recheck. Exact built-in
JSON scalar leaves avoid an unnecessary Pydantic model test; boundary-specific
normalization, timestamp handling and invalid-value rejection are retained.

The opt-in timing test uses actual `datetime.now(timezone.utc)` and `time.monotonic()`
samples, real native verifiers and signed synthetic artifacts. It builds fresh risk
evidence inside each measured recheck. Run it separately from coverage/profiling:

```sh
VERITAS_RUN_SANDBOX_TIMING=1 python -m pytest veritas_os/tests/test_sandbox_real_clock.py -q -s --no-cov -o junit_family=xunit1 --junitxml=/tmp/sandbox-timing.xml
```

On the 2026-09-07 Python 3.12 development host, three successful runs measured
0.603–0.770 seconds for each of their nine rechecks and 2.592–2.749 seconds for the
whole credential continuation (excluding fixture issuance and consumption).
Descriptor age was 1.287–1.456 seconds against the unchanged five-second limit.
Injected source delay of 1.05 seconds and provider describe/resolve delays of 5.05
seconds were rejected with consumption and the attempt retained; no retry occurred.
These are observations on one host, not throughput or deployment guarantees.
The opt-in test reports each measurement and fails if the requested phase cannot
be reached or the normal continuation exceeds the unchanged limits.

Those checkpoint measurements used explicitly in-memory stores, synthetic
material/provider and declared clock health with zero uncertainty. They did not
measure a provider service, PostgreSQL latency, authenticated time or external
effect. At that checkpoint, the 50-millisecond uncertainty case failed before
provider access because fresh risk stamped at `checked.now` was later than the
lower uncertainty bound. Section 14 defines the focused temporal correction.

## 14. Causal observation time and independent validity windows

The executor samples `checked.now` and only then invokes its trusted synchronous
current-input loader, inside the permanently owning attempt. The reconstructed
risk decision's `reviewed_at` and packet's `recorded_at` must both equal that exact
sample. These are causal observation markers for this invocation, not an external
not-before grant. Risk/source reconstruction runs at `checked.now`, using all
mandatory independent source/contract inputs. No artifact is backdated, rehashed
by the verifier, or accepted through a caller-supplied verified flag.

This rule is confined to the sandbox owning call. General native/risk verifiers
retain their exact point-in-time semantics and still reject a packet recorded
after their supplied verification time. Even a fully rebuilt risk packet whose
timestamp differs from the current invocation by one microsecond is rejected;
being inside the uncertainty interval is not permission to replay it.

Authorization and signed authority/approval continue to be verified at the lower
uncertainty bound. Risk expiry, authorization and governance must also survive
the unchanged conservative horizon `checked.now + 2 seconds`. UTC and monotonic
work must each finish within one second, and the completion clock must be healthy
and inside authorization validity. Future signed grants, expired grants, rollback
and excessive delay remain fail-closed. This correction neither extends TTLs nor
relaxes the one-second uncertainty cap, 30-second health age, or five-second
credential-provider/descriptor bounds. Both credential-continuation rechecks use
the same rule and retain consumption/attempt state on failure.

The opt-in host-clock test now requires normal continuation with both 50 ms and
one second of declared uncertainty, in addition to zero uncertainty and delay
rejection cases. Deterministic tests cover reconstructed timestamp substitution,
real synthetic Ed25519 authority validity boundaries and post-resolution failure.
These tests do not authenticate a clock or provider. The executor-configured
loader must acquire genuinely current inputs; timestamp equality and signatures
alone cannot prove input truth. Actual clock/provider deployment validation,
dispatch intent, Bind, external effect and outcome reconciliation remain outside
this correction and are not authorized by a successful credential continuation.

## 15. Avoiding repeated normalization after reconstruction

Profiling identified repeated recursive JSON normalization of complete nested
packets as a significant cost inside current rechecks. Satisfaction, readiness,
gate, fresh-source and final-recheck verifiers now compare their complete Python
model dumps after input normalization, schema validation and independent full
reconstruction. Those five packet builders produce JSON-valued fields. Input
normalization, every field comparison, hashes, source reconstruction at both time
checks, signatures and revocation checks remain present. The compact runtime-risk
packet retains its existing normalization because its result contains typed
datetimes; this is not a generic model-comparison shortcut.

Regression tests cover both approval-requirement states, unchanged canonical
values/hashes, fresh returned objects, malformed nested dictionary/model inputs,
and changed approval requirements with attacker-recomputed hashes.

On the 2026-09-08 Python 3.12 development host, the final opt-in clock suite passed
all eight cases: three zero-uncertainty continuations, 50 ms and one-second
uncertainty continuations, and three injected-delay rejections. The fifteen normal
rechecks measured 0.529–0.680 seconds; continuation took 2.184–2.426 seconds and
descriptor age was 1.103–1.261 seconds. All original deadlines were enforced.
The earlier host's 1.4–1.7 second failures cannot be attributed solely to this
change: the current host also passed a pre-optimization zero-uncertainty control
(0.622–0.784 second rechecks). These observations demonstrate this host's result,
not a portable latency guarantee. Deployments still must validate their own time,
provider and database configuration under expected load.

## 16. Owning dispatch seam (inert validation only)

`execute_sandbox_bind` owns preparation and credential resolution itself; it
does not accept a returned credential or preparation object as authorization.
It repeats independent current governance and ownership checks, then uses the
existing effect-state compare-and-set to persist `EFFECT_UNKNOWN` with reason
`SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED` before entering transport.
This record links the consumed authorization and its original idempotency key;
the authorization commits to the action/payload binding. Commit acknowledgement
loss, failed CAS or mismatched readback prevents transport entry. No state,
consumption or exclusive attempt is released, reset or retried.

The final ownership read, governance reconstruction, intent persistence/readback
and transport preparation share a one-second UTC/monotonic budget. The secret
handoff callback rechecks that budget, clock health, authorization window and
the original credential descriptor validity/age. It may be called only once.
Transport entry has a five-second total timeout. Material references are closed
on return, failure or cancellation; Python memory erasure is not claimed.

`SandboxDispatchTransport` is a trusted executor-injected **interface**, not an
implemented HTTPS adapter. It must invoke the callback immediately before its
only send, preserve canonical payload and the original key, verify TLS, and
disable redirects, proxies and retries. An arbitrary/dishonest implementation
could retain material or send after its deadline: this interface cannot prove
otherwise. A reviewed concrete transport and real-clock send tests are mandatory
before enabling network effects. No default transport or API route is installed.

Transport responses are not parsed as authority or effect evidence. The returned
`SandboxDispatchObservation` always says `UNKNOWN`; durable state also remains
`EFFECT_UNKNOWN`, including on apparent transport success. This local result is
not a BindReceipt, Outcome or acknowledgement. Cancellation raises a sanitized
cancellation with the same durable uncertainty retained. A recovery process must
look up the original idempotency key and must not blindly resend.

This checkpoint tests synthetic material and an inert transport using real
native verifiers. It does not establish real HTTPS delivery, PostgreSQL timing,
sandbox durability, formal Receipt/Outcome integration or reconciliation. Those
remain required steps, not guarantees implied by these tests. The deployment
decisions in section 9 are still required before any external connection.

## 17. Independent sandbox event service

`create_sandbox_event_service` constructs a separate ASGI application; it is not
mounted into the main API and there is no default application/listener. As the
user-approved narrow exception recorded in the repository instructions, this
service uses Bearer authentication while existing VERITAS APIs retain X-API-Key.
An operator supplies two distinct, expiring tokens through trusted configuration:
writer (registration and lookup) and reader (lookup only). No token is generated,
resolved from a provider, read from an environment fallback, or recorded in an
operation. Missing/invalid configuration rejects startup; unauthorized or expired
requests stop before body processing and database access. Rotation currently
requires rebuilding the application with new configuration. Live provisioning,
revocation distribution, TLS termination and network policy remain deployment gates.

The operator must supply a dedicated psycopg async pool and install
`veritas_os/policy/sandbox_events.sql` in that sandbox database. This is deliberately
not a main-API migration. A single immutable row represents both event and operation;
primary/unique constraints cover operation ID, original key and event ID. Runtime
writer database privileges should be SELECT/INSERT only; independent reconciler
credentials should permit only read access. Lookup transactions are read-only.

`POST /v1/events` accepts the fixed JSON payload and one `Idempotency-Key` header.
Duplicate JSON keys, extra fields, invalid UUIDs, invalid UTF-8, NUL, oversized bodies
or messages are rejected before persistence. Idempotency keys use 1–256 ASCII
letters, digits, dot, underscore, colon or hyphen. Within one READ COMMITTED
transaction, registration uses INSERT ON CONFLICT DO NOTHING followed by a fresh
statement reading the original key. Same key and exact payload returns the original
operation (200); a new committed row returns 201. Same key/different payload or
same event ID/different key returns 409, with no second event. Success is returned
only after commit/context exit; synchronous_commit is enabled for registration.
Statement duration is bounded to four seconds; timeout or uncertain commit returns
503 with no automatic retry or success inference. No TTL/delete/reset API exists.

Lookup uses `GET /v1/operations/{operation_id}` or
`GET /v1/operations?idempotency_key=<original-key>`. Both require authentication
and return operation ID, original key, event ID, canonical payload digest and
`PERSISTED`, without the message or credentials. All responses use no-store.
A missing row returns 404, explicitly not proof of no effect; DB lookup failure
returns 503. A lost POST response can be investigated by the original key.
The service's PERSISTED observation is not a VERITAS confirmed Outcome/BindReceipt.
Independent reconciliation and prevention of replacement authorizations while
the earlier outcome is unknown remain sender-side work.

ASGI tests use synthetic tokens and a SQL double. Separate real PostgreSQL tests
exercise concurrent identical/conflicting requests, rollback and commit-response
loss in disposable isolated schemas and are included in the existing PostgreSQL
CI job. Local mocks are not claimed as durability proof. HTTPS transport, actual
deployment/provider configuration and native Receipt/Outcome/reconciliation are
still not connected by this service implementation.
