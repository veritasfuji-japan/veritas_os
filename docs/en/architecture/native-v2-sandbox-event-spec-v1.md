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
