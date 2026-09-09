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

## 18. Opt-in HTTPS transport (synthetic stream validation)

`SandboxHTTPSTransport` can now be explicitly supplied to `execute_sandbox_bind`.
No default transport, endpoint, provider, listener or deployment is installed.
The executor independently configures the exact HTTPS event endpoint and reviewed
CA roots (system roots by default). A fresh verified TLS connection uses that DNS
name as the peer identity, with TLS 1.2 or later and HTTP/1.1. This is CA/hostname
verification, not certificate fingerprint pinning or DNS/IP attestation.

The transport checks canonical payload/digest and the original key, completes TLS,
then invokes the owning one-use material callback immediately before its single
write, without an intervening await. Connection delay therefore cannot bypass the
existing final send window. There are no proxies, redirects or retries. The total
request limit is five seconds. Responses require bounded headers (8 KiB) and a
Content-Length body (4 KiB); chunking, encoding and duplicate headers fail closed.
This is a deliberately restricted protocol, not a general HTTP adapter.

Matching 201/200 JSON acknowledgements require the original key, event ID and digest
plus a valid operation UUID. The returned observation records a fixed classification
only; raw bodies, headers, remote operation IDs and errors are not retained. 409 and
503 are distinct observations, never evidence of absence or confirmed success.
All durable states remain EFFECT_UNKNOWN, including matching acknowledgements.
Existing transports returning None retain their earlier observation behavior.

Tests use synthetic provider material, real native verifiers and simulated streams;
they do not establish a real TLS handshake, real HTTPS delivery or receiver commit.
Real TLS/host-clock and combined PostgreSQL/receiver fault tests are still required
before enabling external effects. Section 9 prerequisites remain mandatory.
Reconciliation must use the original key, not infer success from these observations.

## 19. Owning read-only sandbox reconciliation

`reconcile_sandbox_effect` receives the original authorization/payload and independent
archived source/governance/trust inputs. It re-verifies native issuance and rebuilds
the exact action and complete consumption row. Only the matching revision-2 sandbox
dispatch-intent EFFECT_UNKNOWN record is eligible. Missing, substituted, terminal or
non-sandbox records fail closed. No execution attempt or consumption is created.

Current operator configuration supplies a separate reader credential reference,
version, provider, environment and CA roots. Its fixed scope is
`sandbox.operation.lookup.v1`; the writer reference is rejected. The exact reader,
CA and original deployment/action configuration must be approved through an independent
`ReconciliationVerifierPolicy`. Provider metadata is revalidated before and after
resolution and after TLS, including audience, scope, version, non-revocation,
expiry and trusted clock health. Separate references do not themselves prove separate
principals: the configured provider/service must enforce this deployment property.

The only network operation is GET at the original origin's `/v1/operations`, using
the original key as its single query parameter. There is no POST, redirect, proxy,
retry or response-selected destination. Provider plus lookup work has a five-second
budget. The existing bounded HTTP framing parser is reused, but interpretation and
binding are independently performed here. A matching 200 PERSISTED operation must
contain the original key, event ID and payload digest and a valid remote operation UUID.
The UUID is learned from the independent lookup, never from the dispatch response.
All five operation fields, including explicit PERSISTED state, are mandatory;
neither dispatch nor lookup may infer that state from a model default.

The canonical retrieved operation digest, all observation lineage/time fields,
approved policy hash, original record hash and reader metadata digest form the
returned verified evidence. Only then does an existing effect-store CAS advance to
CONFIRMED_EFFECT, with commit readback required before returning confirmation.
404/401/503/redirects and other non-200 statuses preserve the original UNKNOWN row;
malformed replies, mismatches, timeouts and persistence uncertainty raise sanitized
errors without returning success. A lost CAS acknowledgement can leave a committed
terminal record; callers must inspect trusted storage, never reset or resend.

Archived issuance verification and current reader authorization are distinct: the
original grant can expire without preventing investigation of its earlier effect.
No current execution authority is restored. Terminal calls are rejected rather than
rewritten. Independent means independent of dispatch, not of the sandbox operator.

The effect store retains the verified-evidence digest; full returned evidence still
needs durable archival in the later Receipt/Outcome pipeline. Crash-safe atomic
evidence/receipt publication, replacement-authorization blocking and automatic
terminal recovery remain separate work. This is not the complete E2E proof.
Tests use real native verifiers with synthetic provider/streams and in-memory stores
under explicit test opt-in. Real TLS and PostgreSQL composition and all section 9
deployment prerequisites remain required. No live credentials or external requests
are authorized by these tests.

## 20. Atomic reconciliation evidence archival

This section supersedes section 19's digest-only storage limitation. After migration
0006, the sandbox reconciliation owner commits the CONFIRMED_EFFECT record and a
full `SandboxReconciliationArchive` in one SQL UPDATE on `bind_effect_states`.
The compare-and-set checks the exact original JSON record, hash, state and revision,
and requires an empty archive column. A failed CAS writes neither value. Existing
transition methods cannot rewrite a row once its archive has been committed.

The archive contains the verified evidence, original UNKNOWN record, five-field
retrieved operation and reader metadata digest. These are sufficient to recompute
its observation, acknowledgement, original-record and verification-proof hashes.
It contains no token, Authorization header, raw response or event message.
`get_reconciliation` reads the state/archive pair together and validates schemas,
hashes, times and lineage. Only a successful commit and validated readback allow
`reconcile_sandbox_effect` to return confirmation. Missing or inconsistent evidence
fails closed; legacy terminal rows are never backfilled with invented proof.

A lost commit acknowledgement can still raise after both values were committed.
An operator can subsequently read the archived evidence without a new lookup,
POST, authorization or state transition. This is integrity-checked retrieval,
not automatic recovery, renewed HTTPS verification or a Receipt/Outcome. Hashes
are not signatures and do not protect against a database operator rewriting all
bound data. The trusted sandbox/provider and database remain trust assumptions.

Deploy migration 0006 before this code, including use of legacy transition methods.
The nullable column preserves old records and hashes. A downgrade drops archived
evidence; operators must preserve it under the applicable retention policy first.
Real PostgreSQL tests in the effect-state CI workflow exercise rollback, lost
commit acknowledgement, contention, fresh-store readback and missing evidence.
They establish storage behavior, not the combined real-TLS/receiver E2E proof.
Receipt/Outcome publication and replacement-authorization blocking are now implemented;
automatic recovery is composed in section 23. Real TLS/provider/host-clock
composition remains outstanding. Section
9 deployment prerequisites continue to apply; no live external access is enabled.

## 21. Retrospective BindReceipt / Outcome publication

`publish_sandbox_receipts` re-verifies the original native authorization and exact
sandbox action against independent historical source/governance/trust inputs. It
rebuilds the complete consumption row and confirmed effect record, validates the
stored archive, matches its event ID/payload digest/origin to the authorized action,
and requires approval of the exact archived reconciliation policy configuration.
Neither caller-supplied receipts nor dispatch acknowledgements are accepted.

The publisher reuses the existing BindReceipt and OutcomeReceipt schemas. The
BindReceipt is explicitly retrospective: `bind_ts` is the stored dispatch-intent
time, not an invented timestamp of a live check. Missing live constraint, drift
and risk results are marked `LIVE_RESULTS_NOT_ARCHIVED`; no new admissibility or
execution permission is asserted. COMMITTED and the passed outcome postcondition
mean only the independently reconciled persistence of the bound sandbox event.
No before/after system-state fingerprints are invented. Historical human-approval
status and proof digest are linked without creating another approval receipt.

Both receipts bind authorization, consumption, intent/decision, exact payload,
external operation, confirmed record and archived evidence hashes. Outcome links
the BindReceipt hash. IDs and times are deterministic from original records; a
bundle hash covers the complete pair. The returned dictionaries are detached from
stored values. Event messages, credentials and raw HTTP data are not copied.

Migration 0007 adds a nullable `sandbox_receipt_bundle` to the same effect row.
One conditional UPDATE stores the pair only once against the exact confirmed
record and archive. Identical repeat publishers return the same pair; differing
stored contents, missing evidence and readback failures raise sanitized errors.
A commit acknowledgement can be lost after publication. Repeating the publisher
with the same independently verified inputs recovers the pair without another
POST, lookup, consumption or effect-state transition. Publication does not change
the effect record or reconciliation archive. Apply migration 0007 before using this
publisher; retain receipt data before any downgrade that removes the column.

This closes the database-backed artifact connection for confirmed sandbox effects.
It does not publish TrustLog entries: `trustlog_hash` remains empty and metadata
explicitly records `NOT_PUBLISHED`. The publisher alone does not claim crash-safe exactly-once TrustLog delivery or
complete recovery composition; section 23 now composes the recovery path. It still
does not establish real Decision-to-Effect E2E completion. Those and section 9 deployment prerequisites
remain separate work. No live credentials or external effects are authorized by
this implementation or its synthetic tests.

## 22. Replacement business-event execution blocking

Migration 0008 adds a nullable unique `business_event_key` column to
`bind_effect_states`. The key is execution ownership metadata and is deliberately
kept outside the hashed `EffectStateRecord` JSON so existing evidence hashes do
not change. New sandbox attempts derive the key from a domain separator, the
sandbox action, exact HTTPS endpoint and event UUID. Message text, target-system
label, authorization ID and idempotency key are excluded. A newly issued authorization
therefore cannot escape an existing same-event claim merely by changing those
values.

`prepare_sandbox_attempt` supplies the key to the same atomic INSERT that claims
the effect-state row. PostgreSQL uniqueness is the cross-process race arbiter; the
in-memory store mirrors this only for explicit tests. No preflight "absence"
observation is accepted as permission. A failed or ambiguous claim fails closed.
A replay of the same consumed authorization remains `SPE_ATTEMPT_ALREADY_EXISTS`;
a different operation colliding on the same business event is rejected as
`SPE_BUSINESS_EVENT_ALREADY_CLAIMED` before current-governance rechecks,
credential resolution or transport.

`IN_FLIGHT` and `EFFECT_UNKNOWN` retain the business-event claim.
`CONFIRMED_EFFECT` also retains it permanently, preventing a second effect for
the same sandbox business event. A transition to independently established
`CONFIRMED_NO_EFFECT` releases the unique key in the same state UPDATE, allowing
a later authorization to make a fresh claim. Storage ambiguity never implies
no-effect and therefore never authorizes a replacement.

This guard is intentionally at the execution-claim boundary. Native authorization
artifacts may still be issued or exist for the same event; they do not become
execution permission while a conflicting durable claim remains. Blocking issuance
itself would be a separate policy surface and is not required for the safety
property that no replacement reaches credential or network execution.

Migration 0008 does not invent business-event identities for legacy rows. Apply it
before enabling this sandbox execution path and confirm that any pre-migration
sandbox attempts have been handled under deployment procedures. Section 23 now composes the automatic recovery coordinator. The repository still
does not claim real TLS/provider/host-clock/PostgreSQL deployment composition,
TrustLog exactly-once publication, or a passing real Decision-to-Effect E2E proof.


## 23. Automatic crash recovery coordinator

`recover_sandbox_attempt` is the owning recovery composition for the native v2
sandbox path. It is deliberately not a scheduler and never creates a new execution
attempt. Every invocation re-verifies the original native authorization/action and
durable consumption lineage, then reads the stored effect state before selecting a
recovery action. The coordinator has no POST/re-dispatch path and never re-consumes
the authorization.

An exact revision-1 `IN_FLIGHT` row with reason
`SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED` may be closed as
`CONFIRMED_NO_EFFECT`. This is safe because `execute_sandbox_bind` cannot enter
transport until that same row has durably advanced to revision-2
`EFFECT_UNKNOWN` and a matching readback has succeeded. A durable revision-1
read therefore proves that this attempt did not cross the transport-entry gate.
The no-effect transition uses compare-and-set, requires committed readback, and
releases the business-event claim in the existing atomic state update. A lost
transition acknowledgement is recovered from a fresh durable read rather than
from the return value.

`EFFECT_UNKNOWN` never becomes no-effect from absence. The coordinator delegates
one read-only GET attempt to `reconcile_sandbox_effect`. Matching persisted
evidence advances to `CONFIRMED_EFFECT`; 404, lookup outage and other non-confirming
results remain `EFFECT_UNKNOWN`. No blind resend, replacement authorization,
writer credential or dispatch transport is used.

A durable `CONFIRMED_EFFECT` row is handed to `publish_sandbox_receipts`, which
revalidates the archived reconciliation lineage and returns/persists the same
deterministic BindReceipt/Outcome pair. Repeating recovery after a lost receipt
publication acknowledgement does not perform another lookup or external effect.
`CONFIRMED_NO_EFFECT` created by the exact pre-dispatch recovery rule is returned
idempotently. Unexpected terminal provenance, substituted lineage, storage
ambiguity or cancellation fails closed and never sets
`external_effect_retry_permitted`.

Synthetic composition tests cover pre-dispatch crash, lost transition
acknowledgement, non-confirming lookup, unknown-to-confirmed recovery, terminal
restart and receipt reuse without POST. A real PostgreSQL test covers the
pre-dispatch terminal transition, fresh-store readback and business-event claim
release. These tests close the repository's automatic recovery coordinator for the
sandbox path; they do not establish real TLS/provider/host-clock deployment
composition, TrustLog exactly-once publication, or a passing real
Decision-to-Effect E2E proof. Section 9 deployment prerequisites remain required
before any live external effect.
