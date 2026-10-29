# Bind-Boundary Governance Artifacts

## Implemented scope

VERITAS includes two **native governance artifacts** as first-class contracts:

1. `ExecutionIntent`
2. `BindReceipt`

`FinalOutcome` models bind-time terminal status.
Bind-boundary artifacts append to the existing TrustLog path so auditors can
traverse native lineage:

`decision artifact -> execution intent -> bind receipt`

## Why these artifacts exist

VERITAS already treats the decision artifact as the primary governance record.
This extension keeps that architecture intact and adds bind-boundary lineage:

- `ExecutionIntent` links an execution attempt directly to a `decision_id` and
  governance lineage (`policy_snapshot_id`, `actor_identity`, `decision_hash`).
- `BindReceipt` records bind-time checks (authority/constraint/drift/risk/
  admissibility), links back to both decision and execution intent, and carries
  TrustLog chain linkage (`trustlog_hash`, `prev_bind_hash`).
- `BindReceipt` also stores minimal replay/revalidation metadata:
  `bind_receipt_hash`, `execution_intent_hash`, copied governance identity,
  and a compact `revalidation_context` used for admissibility replay.

This provides explicit governance-native artifacts at the decision → bind
boundary without creating a parallel subsystem.

## Current boundary and caveats

Implemented in this repository:

- bind-time admissibility adjudication inputs on bind receipts
- bind terminal outcomes (`COMMITTED`, `BLOCKED`, `ESCALATED`, `ROLLED_BACK`)
- TrustLog lineage pointers and bind receipt list/export/detail endpoints
- shared compact `bind_summary` vocabulary across bind-governed mutation/export responses
- Mission Control bind-phase rendering on decision results

Not guaranteed by this document alone:

- tenant-specific external side-effect adapter coverage
- environment-specific production hardening and operational controls
- universal production-readiness claims across every deployment context

## Authenticated actor for governance mutations

`PUT /v1/governance/policy`, `POST /v1/governance/policy-bundles/promote`,
`PUT /v1/compliance/config`, `POST /v1/system/halt` and `POST /v1/system/resume`
use the API-authenticated principal from request state for `actor_identity` in
ExecutionIntent and BindReceipt. Caller-supplied `updated_by` and `X-Role`
labels do not establish that identity. Missing authenticated principal context
returns HTTP 403 before mutation. Existing role/tenant and approval checks still
apply, and the policy's `updated_by` remains caller-supplied display metadata.

The shared `require_authenticated_principal()` reader enforces this boundary.
For HTTP halt/resume requests, the authenticated principal also supplies the
effective operator in the action hash, controller call, status and history.
The request's `operator` field remains accepted for payload compatibility but
cannot establish who performed the action. Internal controller/helper callers
retain their existing explicit operator arguments.

This identifies an API credential, not an independently authenticated human.
It does not cryptographically authenticate the two approval records or establish
enterprise IAM integration. Other API routes are outside this actor boundary.

## Decision admission during emergency halt

After a committed `POST /v1/system/halt`, authenticated `POST /v1/decide`
requests in the same process return HTTP 503 with `status: HALTED` and
`decision_status: rejected` before the decision pipeline is loaded or invoked.
This check applies whether runtime EU AI Act compliance mode is enabled or
disabled. A committed resume allows subsequent requests to enter the pipeline
again, subject to its usual checks. API authentication and permissions still
run before the halt response.

This is an admission check against the controller's process-local state. It
does not cancel requests already admitted, stop other execution endpoints,
persist a halt across restarts, or synchronize a halt across workers or hosts.
Those guarantees require separate execution and deployment controls.

### Strict startup requires explicit resume

Each production/strict API lifespan starts with the decision controller halted,
after startup validation and before background schedulers or request admission.
`GET /v1/system/halt-status` reports the stop. An authorized operator must use
`POST /v1/system/resume`; normal API authentication, `config_write` permission
and current Bind adjudication still apply. A blocked resume keeps the stop.
The health endpoint being available does not mean decisions are admitted.

This deliberately requires resume after every strict startup, including a clean
restart of a previously running instance. It prevents a restart from silently
reopening decision admission without adding a new storage backend. The startup
actor is `system:startup`. An existing in-process stop retains its reason and
actor; a fresh process does not recover the previous actor, timestamp or reason.
This is fail-closed initialization, not durable halt history or cross-host stop
coordination. Non-strict startup keeps the existing state and defaults.

Controlled secure proof fixtures perform the resume through the real HTTP/Bind
management route using a separate synthetic admin credential. The decision
credential retains its operator role. This fixture step is not evidence of an
independently authenticated human approval.

### Authenticated HTTP admission requires startup completion

In production/strict profiles, valid HTTP credentials alone do not permit API
operations. The API lifespan clears an app-local completion marker on entry,
sets it to the literal boolean `True` with the current process ID only after
validation, backend setup, halt initialization and scheduler startup succeed,
and clears both values on shutdown. A marker inherited from another process
does not establish startup completion for the current process.
API-key, permission and SSE authentication dependencies return HTTP 503 after
credential validation when the marker is absent or incomplete. Invalid
credentials retain their authentication refusal; public health routes remain
available and are not proof of protected API readiness.

This closes protected HTTP admission when startup is skipped, including
Uvicorn `--lifespan off`, and when initialization fails or the API shuts down.
It does not make a server with disabled lifespan exit automatically, terminate
already admitted work, or attest a different process or host. Direct trusted
helper calls without an HTTP Request retain their compatibility behavior; normal
FastAPI dependencies receive the actual Request. Non-strict profiles retain their existing behavior.

The mounted TrustLog WebSocket uses its own header-first API-key check; the
HTTP-only SSE authentication dependency is attached only to the SSE route.
Invalid WebSocket credentials close with code 1008. In strict profiles, valid
credentials with incomplete startup or a mismatched PID close with code 1013
and reason `security_startup_incomplete`, before acceptance or event-hub
registration. Production query-string credentials remain refused. This is an
admission check; it does not terminate already accepted WebSocket streams.

The TrustLog stream concurrently watches ASGI disconnect messages and sends
queued events. Disconnect, handler cancellation, or send failure cancels and
awaits both connection tasks and unregisters the subscriber. Event reads are
nonblocking, with a 100 ms idle poll and the existing 15 second heartbeat; no
blocking queue reader is left in the thread pool. This covers observable ASGI
disconnects, not independent detection of a silent network partition.

For ASGI 2.4+, the SSE response explicitly watches disconnect notifications
alongside streaming, rather than relying solely on a later failed send through
HTTP intermediaries. Either completion cancels and awaits both tasks before
closing the generator and releasing its subscription. Older ASGI versions retain
Starlette's existing disconnect watcher.

SSE event reads also use nonblocking queue polling (100 ms while idle), so
cancelling a stream does not leave a thread-pool reader waiting for the
configured heartbeat timeout. The existing disconnect check and subscription
cleanup remain in place; event frames, response headers and the configurable
heartbeat interval are preserved. Idle event delivery may incur the poll delay.

The SSE response owns and closes its event generator in a `finally` block,
including when response headers or a body frame cannot be sent. The response
reserves its subscription before sending headers, and cleanup uses the same
captured event hub even if the generator has not started. This releases subscribers synchronously at response exit
instead of relying on later generator finalization. Transport errors retain
Starlette's existing exception behavior; this does not retry failed sends or
prove delivery of a frame that encountered an error.

### Current stream credential checks

SSE and TrustLog WebSocket delivery revalidate their header-first credentials
against the process's current API-key configuration on each delivery loop,
including idle polling. If the key is no longer accepted, SSE ends the response
and unregisters its subscriber; WebSocket closes with code 1008 and reason
`api_key_no_longer_valid`, then releases its tasks and subscription. Query-key
streams must also retain the existing transport-specific dual opt-in; production
query-key refusal is unchanged.

This uses the existing multi-key and legacy fallback matching rules. Removing a
key from one source does not revoke it if another accepted source still matches.
API keys do not gain a TTL or external revocation feed. Configuration changes
must reach the running process: changing a parent shell environment or an
external secret does not itself update that process. Other processes and hosts
are not synchronized by this check. Idle detection normally follows the 100 ms
poll, but is not a wall-clock deadline and cannot cancel a send already in
progress. Already sent data cannot be recalled. This does not recheck role
permissions or startup readiness throughout an accepted stream.

### Stream resource limits

The API event hub admits at most 128 subscribers by default, shared by SSE and
TrustLog WebSocket within that process. Admission is checked under the hub lock;
existing subscribers are not evicted. Authenticated excess SSE requests receive
HTTP 503 before event-stream headers; excess WebSocket requests close with code
1013 and reason `stream_capacity_reached` before acceptance. Releasing a
subscription makes its slot reusable. With the tested Uvicorn backend, a
pre-accept WebSocket refusal is HTTP 403 on the wire, rather than a WebSocket
close frame; the close code/reason above describe the ASGI refusal. The hub constructor accepts a positive
`max_subscribers` for embedded callers; the API uses the default.

Each SSE ASGI send has a 15 second deadline, including the actual transport send
outside the HTTP response intermediaries. Other JSON endpoints are not subject to this
stream deadline (the new stream-capacity refusal itself is bounded). WebSocket acceptance, event/heartbeat sends and post-admission
close attempts also have a 15 second deadline. A timed-out WebSocket attempts a
bounded close with code 1013 and reason `stream_send_timeout`, then releases its
connection tasks and subscriber even if the close cannot be delivered. SSE
response ownership also releases its subscription after send timeout. Deadlines
rely on cooperative async cancellation and do not cancel bytes already sent.

These are per-process subscriber and send-wait bounds, not a deployment-wide
connection quota or a byte-size limit. Each subscriber queue remains bounded at
64 entries by default; its existing drop-on-full behavior is unchanged, so these
live streams remain best-effort notifications rather than durable delivery
proofs. A silent network stall is noticed only when a transport send blocks or a
disconnect is reported; this does not establish production load capacity.

The `stream-real-uvicorn` CI job runs twenty loopback TCP tests against the
actual API application: eight with a server thread, the same eight with a
separate Python interpreter, and four subprocess replacement cases. It rejects skipped, failed, or missing cases and
checks the child source SHA plus distinct client/server PIDs from each child
case's JUnit properties. These check delivery/disconnect cleanup, server-process
key rotation, a shared two-slot fixture limit and reuse, invalid credentials,
and incomplete-readiness refusal. Child configuration and event fixtures are
controlled only through a test-only stdin pipe; no control endpoint is added to
the API. Child key rotation must leave the parent environment unchanged, and
teardown checks empty subscriptions and reaps the server process.

Both fixtures disable lifespan and supply an explicitly synthetic process-bound
startup completion marker in the server process. They validate post-startup
transport, not real security initialization. The job records the checkout SHA
and transport versions. Ordinary lanes may skip this optional transport module
when `websockets` is absent; the dedicated Linux job installs the pinned test
dependency and requires every case. These are processes on the same host, not
independently administered hosts or OS-user isolation. This does not validate
TLS, durable runtime-state recovery, slow real networks, production load, or
external secret/revocation distribution. No external provider or business API is called.

The four replacement cases cover graceful termination and forced process kill,
for both SSE and WebSocket. They require the old socket to terminate, reap the
old process, then bind a new interpreter to the same loopback port. The new
process starts with an explicitly supplied replacement synthetic key: the old
key must be refused and the replacement key must receive a newly published
event. Both process PIDs and source SHAs are recorded and checked in CI. This
is transport replacement after process exit, not automatic key-rotation
persistence, durable subscription/event history, database recovery, replay
resistance across a rollback, or restoration of authorization/Bind state.

Startup rejects declared multi-worker API deployments in production/strict
profiles while this controller remains process-local. Either `WEB_CONCURRENCY`
or `UVICORN_WORKERS` greater than one triggers refusal, including when Redis
authentication is configured. Explicit `--workers N` and `--workers=N`
arguments from the standard `uvicorn` executable or `python -m uvicorn` are
also inspected, including inside spawned workers. An environment count of one
cannot hide an explicit CLI count greater than one. Non-strict deployments emit
a warning. Set both declared counts to one and run a single API process for this bounded halt
behavior; Redis shares authentication state, not halt/resume state.

The guard also refuses strict startup in Python multiprocessing child processes
and runtimes marked by the standard Gunicorn `SERVER_SOFTWARE=gunicorn/...`
environment value. Programmatic `uvicorn.run(workers=2)` uses multiprocessing
children even without a CLI declaration; standard Gunicorn workers carry the
marker even when the worker count comes from a configuration file. Non-strict
profiles warn. These signals do not prove a worker count, so strict startup
refuses even one managed child or one Gunicorn-marked worker. Run the API as
one standalone process; no bypass flag is provided.

The checks do not establish shared halt state. Custom launchers that do not
expose these signals, independent replicas, and additional hosts remain outside
detection, and restart recovery is not durable. Gunicorn detection depends on
its standard environment marker being preserved; it is not an independent
operating-system process inventory.
Operators must keep the actual process topology consistent with the declared
single-process configuration.

## Compliance configuration policy source

`PUT /v1/compliance/config` reads the current governance policy through
`get_policy()` before Bind adjudication. Its `bind_adjudication` controls and
`updated_at` / `version` identity accompany the execution intent. The separate
runtime compliance configuration remains the state captured by the adapter for
drift checks and mutation; it is not the source of governance policy controls.

When policy requires TTL or approval freshness, missing evidence blocks or
escalates the update according to `missing_signal_default`, with HTTP 403 and no
configuration mutation. The current configuration request does not carry those
expiry signals, so enabling either requirement prevents updates through this
route until an appropriate evidence path is provided. Default policies without
these requirements retain the existing successful update behavior.

The focused HTTP tests use real route authentication, adapter and Bind
adjudication with isolated configuration and audit storage. They establish this
management-route policy boundary, not external-operation or customer-deployment
coverage.

## Policy promotion approval metadata

`POST /v1/governance/policy-bundles/promote` rejects the reserved
`bind_adjudication` key in client-supplied `approval_context` with HTTP 400
(`approval_context_policy_override_forbidden`) before invoking promotion.
Bind policy controls come from the current server governance policy.

The internal Bind engine accepts policy overrides from trusted callers. Passing
HTTP approval metadata directly to that mechanism previously let a promotion
request disable TTL or approval-freshness requirements. The regression tests
exercise the real HTTP route, helper, adapter and Bind evaluation using temporary
bundle files and an active pointer, with audit storage isolated. A control
request remains BLOCKED/ESCALATED under the configured missing-evidence policy;
an override request is rejected without changing the pointer. These fixtures do
not establish cryptographic bundle authenticity or production deployment safety.

## Governance update lineage boundary

`PUT /v1/governance/policy` rejects HTTP `policy_lineage` containing the reserved
`bind_adjudication` key with HTTP 400, before approval processing or mutation.
The current server-side governance policy supplies Bind controls; request
lineage cannot disable its TTL or approval-freshness requirements. Ordinary
lineage metadata and trusted internal helper overrides remain compatible.

Regression tests exercise the real HTTP, approval, adapter and persistence path
with a temporary governance policy. Control requests with missing required
signals remain BLOCKED/ESCALATED, and override requests produce no policy update
calls or file changes. This is a bounded API regression, not proof of all
execution paths or production IAM enforcement.

## Policy bundle verification before promotion

Signature-required promotion reuses `load_runtime_bundle()` during Bind
constraint validation, immediately before writing the active pointer, and in
postcondition verification. Invalid bundles are refused before the pointer is
written; a later verification failure retains the existing rollback path.

Verification requires manifest integrity and exact manifest-declared content
bindings, including canonical-IR digest, semantic hash, policy id and version.
Secure/prod posture or `VERITAS_POLICY_REQUIRE_ED25519=true` requires an Ed25519
signature with the trusted public key configured by `VERITAS_POLICY_VERIFY_KEY`.
Non-strict legacy SHA-256 mode verifies integrity only; it does not establish
signer authenticity. Bundles without content declarations must be rebuilt before
signature-required promotion. The trusted internal `require_signature=False`
compatibility option is not exposed by the public promotion request.

HTTP tests use generated Ed25519 keys, compiler-produced temporary bundles and
the real promotion/Bind path. Invalid signatures, modified manifests/bodies,
wrong/missing keys and missing signatures cause zero pointer writes. Controlled
changes after validation or after writing exercise revalidation and rollback.
This does not make the bundle directory immutable against concurrent filesystem
modification; filesystem ownership and subsequent runtime verification remain
separate boundaries.

## TrustLog and lineage integration

- `ExecutionIntent` appends as `kind=governance.execution_intent` via the
  existing `append_trust_log` implementation (same hash-chain/signing path).
- `BindReceipt` appends as `kind=governance.bind_receipt` via the same TrustLog
  append pipeline and receives the TrustLog chain hash in `trustlog_hash`.
- `prev_bind_hash` chaining is derived from prior bind receipts already stored
  in TrustLog (`bind_receipt_hash`), not from a new logging plane.
- Retrieval helpers resolve bind receipts by `bind_receipt_id`,
  `execution_intent_id`, or `decision_id` directly from TrustLog entries.
- Internal helper `veritas_os.policy.bind_revalidation.revalidate_bind_receipt`
  can re-run admissibility from receipt-contained context and verify lineage/hash
  linkage against an optional execution intent payload.

This keeps decision artifacts primary while extending native VERITAS governance
lineage toward bind-boundary control.

## Participation vs commitment admissibility

Bind artifacts govern **admissibility of commitment** at the bind boundary.
The additive pre-bind `participation_signal` family governs
**admissibility of participation** during decision formation.

The two layers are intentionally separate and composable:

- participation layer (upstream): governability signals before commit
- bind layer (boundary): commitment adjudication before real-world effect

Current upstream participation detection now includes an additive pre-bind
structural state classifier (`informative|participatory|decision_shaping`) on
`/v1/decide` via optional `pre_bind_detection_summary/detail` fields. This
remains non-binding and does not alter bind-time fail-closed adjudication.

An adjacent additive preservation layer now exposes
`pre_bind_preservation_summary/detail` (`open|degrading|collapsed`) to indicate
whether meaningful intervention remains viable at observation time. This is not
a bind outcome and not a rename of pre-bind detection.


## Companion summary vocabulary (`bind_summary`)

`BindReceipt` remains the full bind artifact contract.

`bind_summary` is the companion compact summary family: it is intentionally
smaller than the full receipt payload and is reused across mutation/export
responses so operators can triage bind outcomes without losing a path to the
full artifact (`/v1/governance/bind-receipts*`).

This keeps full-artifact and summary-object semantics explicit rather than
merging them into a single overloaded shape.

Canonical vocabulary used across backend schema, OpenAPI, and frontend surfaces:

- `bind_summary`: compact, shared operator-facing bind envelope.
- `bind_receipt` / `bind_receipt_id`: full artifact and stable lineage pointer.
- `execution_intent_id`: lineage pointer linking decision → execution intent → bind receipt.
- target metadata fields (`target_path_type`, `target_label`, `operator_surface`, `relevant_ui_href`):
  backend-owned canonical metadata for operator rendering.
- bind outcome/reason fields (`bind_outcome`, `bind_reason_code`, `bind_failure_reason`):
  compact triage vocabulary; full diagnostics remain in `BindReceipt` check payloads.

Legacy flat bind fields remain intentionally additive for compatibility.

## Runtime behavior impact

Additive to existing decision flows. Decision-phase semantics remain primary;
bind-phase semantics add an explicit boundary between approval and commitment.

## Operator interpretation in Mission Control

Mission Control keeps the decision artifact as the primary record and now shows
bind-phase as a lower-layer execution-governance outcome:

- Decision approved + `bind_outcome=COMMITTED`: approved and applied.
- Decision approved + `bind_outcome=BLOCKED`: approved but bind checks blocked.
- Decision approved + `bind_outcome=ESCALATED`: approved but requires escalation.
- Decision approved + `bind_outcome=ROLLED_BACK`: approved, attempted, then rolled back.

This distinction prevents operators from misreading decision-phase approval as
bind-phase commitment.

Mission Control Bind Cockpit also provides an additive **pre-bind governance
surface** in the receipt drill-down when optional payload fields are present:

- `pre_bind_detection_summary.participation_state`
- `pre_bind_detection_summary.concise_rationale`
- `pre_bind_detection_summary.primary_contributing_signals`
- `pre_bind_preservation_summary.preservation_state`
- `pre_bind_preservation_summary.intervention_viability`
- `pre_bind_preservation_summary.concise_rationale`
- `pre_bind_preservation_summary.main_contributing_conditions`

The UI renders these as an ordered pre-bind flow (`participation` →
`preservation` → `bind gate`) and keeps them visually separate from
`bind_outcome`/`bind_reason_code` to avoid vocabulary mixing.

## Minimal API example

`GET /v1/governance/decisions/export?limit=1`

```json
{
  "ok": true,
  "items": [
    {
      "decision_id": "dec-9001",
      "decision_status": "allow",
      "bind_outcome": "BLOCKED",
      "bind_receipt_id": "br-9001",
      "execution_intent_id": "ei-9001",
      "bind_failure_reason": "Constraint mismatch",
      "bind_reason_code": "CONSTRAINT_MISMATCH"
    }
  ]
}
```

`GET /v1/governance/bind-receipts/br-9001` returns the linked bind receipt
artifact with authority/constraint/drift/risk check payloads.

- VERITAS now keeps a tested bind coverage registry for API effect paths. Effect-bearing routes must be classified as `bind_governed` or documented as explicit `audited_exemption` entries (reason/risk/owner/review cadence), reducing the risk of TrustLog(recorded) being misread as execution permission without bind lineage.
