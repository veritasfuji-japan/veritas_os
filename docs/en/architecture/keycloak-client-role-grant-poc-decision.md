# Keycloak client role grant PoC decision

Status: **PROPOSED — maintainer architecture review required**

The PoC covers assigning one preconfigured Keycloak client role directly to one
test user in a dedicated realm. Configure the Keycloak origin, realm name and
internal ID, target user ID, client UUID, role name and UUID, and credential
references before deploying the PoC. Register the action and its exact dispatch
boundary as a separate Bind target. Keep the existing controlled Sandbox proof
and the Keycloak rehearsal as the baseline for comparison.

The [Keycloak rehearsal](../demo/saas-permission-change-governed-demo.md#self-hosted-keycloak-role-grant-rehearsal)
establishes the provider behavior in a disposable realm. The
[architecture freeze](controlled-execution-proof-architecture-freeze-v1.md#6-changes-that-reopen-architecture)
requires an architecture decision before extending credential or network
authority. Approval of this proposal is the prerequisite for adding a deployable
write path.

## Execution and recovery

1. Assign an opaque UUID for the attempt when forming the execution intent,
   before building and hashing the outbound body and before approval or
   authorization issuance. Include it in the body and bind the exact origin,
   realm, user, client, role, intended POST, canonical body digest, deployment
   policy, and business-event identity to the execution intent. Keep the UUID
   fixed for that intent through approval, dispatch, and recovery. The executor
   derives the route and body from the verified intent and pinned deployment
   configuration. Issuance and dispatch use existing governance and current
   authorization checks. Require authoritative reconciliation capability for
   this deployment under the
   [policy-gated execution profile](reconciliation-capable-execution-profile-v1.md).
2. Consume the authorization once and reserve the business event in PostgreSQL.
   Before making the request, commit a dispatch-intent transition to
   `EFFECT_UNKNOWN` with the authorization ID, original attempt UUID,
   business-event key, exact outbound body digest and target, and policy
   references. Store no credential material. Persist enough lineage to
   reconstruct the exact approved request and reconcile it after process loss.
   Serialize dispatch commitment with cancellation if the PoC exposes
   cancellation, using a shared database boundary with an explicit ordering
   result. Reuse the existing consumption and effect-state contracts where
   their scope permits, and keep provider-specific data typed and versioned.
3. Allow only the worker that successfully committed the current dispatch
   transition to send the POST, with bounded HTTPS timeouts, validated server
   identity, an origin fixed by deployment, and redirects and transport retries
   disabled. An uncertain database commit authorizes zero sends. A crash
   after the intent commits may leave the outcome unknown even if the request
   never left the worker.
4. After restart, load the original attempt and its bound reconciliation
   policy from the same PostgreSQL database. Recovery of an uncertain attempt
   uses only read operations. Reject reuse of the same authorization and a
   replacement authorization for the same unresolved or confirmed business
   event. Clear business-event ownership only through existing reviewed
   terminal-state rules where their prerequisites apply. PostgreSQL backup
   restore and cross-site failover require independent validation before the
   PoC can make recovery claims for those scenarios.

## Business-event identity

Define the business-event key as SHA-256 of canonical JSON with these fields:

| Field | Value |
| --- | --- |
| `namespace` | `veritas.keycloak-client-role-grant.business-event/v1` |
| `event_id` | Immutable upstream business-event ID from the verified and approved intent |
| `origin` | Canonical, deployment-pinned Keycloak origin |
| `realm_id`, `user_id`, `client_id`, `role_id` | Canonical UUIDs of the approved target |

Preserve the upstream event ID across replacement authorizations. The key
depends only on the fields above. This keeps the reservation stable when the
authorization ID, attempt UUID, body digest, or credential and policy versions
change. PostgreSQL enforces uniqueness on the business-event key. A worker that
fails to reserve it cannot dispatch. A replacement authorization for the same
event and target remains subject to the stored reservation.

## Credentials and evidence

Use distinct credentials for the grant, admin-event queries, and role
mapping queries. Prefer service identities with provider-side scope for the one
configured target. If the provider cannot enforce that scope for the selected
configuration, keep the environment disposable and isolated. The grant identity
does not provision clients, configure audit, or delete events. Audit settings
and approved trust anchors belong to the operator. Verify the read identities
can perform their own queries and that Keycloak rejects their write requests.

The approved request body carries the attempt UUID as the marker in the role
representation's `description` field, as exercised in the rehearsal. Verify
that the pinned Keycloak version preserves the marker in the audit record
before enabling the PoC. Bind the marker and
payload to the stored attempt, and use a bounded authenticated event query.
Require exactly one successful event matching the marker, writer service-user
and client IDs, realm, operation type, exact resource path, and normalized role
payload. Missing, malformed, ambiguous, or incomplete evidence keeps the attempt
in `EFFECT_UNKNOWN`. Read the direct role mapping after establishing the event
match, verify the actual user, client, and role, and persist the evidence and
state transition atomically through the authorized reconciliation path.

Record the event UUID, matched attempt identity and digests, verifier policy,
and role observation time as reviewable evidence. A successful grant event
records that Keycloak accepted the request, including when the mapping already
existed. The separate role observation shows the mapping was present at the
read. It does not assert that the request created a new mapping or that the
mapping will remain present afterward.

## Rehearsal confirmation

The confirmation service reloads the persisted reservation and observation,
then uses a trusted read-only source to recheck the uniquely matching audit
event and the direct role mapping. The approved deployment policy digest must
bind the expected writer identities and the verifier profile. The final
PostgreSQL update compares the original pending reservation and archived
observation and records the confirmation digest. An absent or changed mapping,
missing or ambiguous audit evidence, or an older unbound verifier profile
leaves the operation unresolved. Confirmation observes the mapping at the
fresh read and grants no authority to send again.

The audit reader reconstructs the confirmation digest from the stored effect
record, approved intent, and archived observation in PostgreSQL. It checks the
stored authorization and consumption lineage and rejects missing or mismatching
evidence for a confirmed operation. This read path does not contact Keycloak.
The result describes the historical confirmation and its observed role mapping.

## Implementation acceptance

Exercise the adapter as a separate process against isolated Keycloak and real
PostgreSQL. Kill and restart that process with the original database, and use
observed provider writes rather than in-process counters as evidence. Report
the tested commit and a sanitized attempt/evidence summary.

Run **Keycloak Bind Role Rehearsal** from GitHub Actions to repeat the
disposable Keycloak/PostgreSQL test. A successful run publishes
`keycloak-rehearsal-evidence-<tested-sha>` with the actual checkout SHA,
Keycloak image reference and ID, PostgreSQL server version, and pytest command.
Use the Keycloak and PostgreSQL repository digests to pull the recorded images
instead of resolving the version tags again.
The two crash cases report provider grant events, recovery POST counts,
reservation rejections, final states, and the confirmation and receipt hashes
when published. The report omits provider credentials, request bodies, external
identifiers, and full receipt contents.

| Scenario | Required result |
| --- | --- |
| Target, request, verifier, or deployment binding is different, including a marker changed after approval | Zero Keycloak grant POSTs. |
| Two workers contend for the same authorization | At most one Keycloak grant POST. |
| Distinct authorization IDs and attempt markers name the same business event and target | At most one Keycloak grant POST across both authorizations, including after restart. |
| Dispatch-intent commitment is ambiguous | Zero Keycloak grant POSTs from that worker. |
| Worker exits after intent commit and before the POST | Zero grant POSTs, including after restart. Keep `EFFECT_UNKNOWN` while evidence is unavailable. |
| Keycloak accepts the grant, the response is lost, and the worker exits | Exactly one grant POST across both processes. Recovery first leaves the attempt unresolved when audit evidence is unavailable, then confirms it when the unique match and direct mapping are available. |
| Evidence is missing, ambiguous, incomplete, revoked, or the direct mapping is absent | Keep `EFFECT_UNKNOWN` and create no confirmed evidence. Recovery sends no grant POST. |
| Read identities attempt grant or audit mutation | Keycloak rejects the writes. |

A maintainer-approved boundary registration, a pinned PoC configuration, and
passing crash/recovery evidence are required before offering the adapter as a
deployable PoC.

## Isolated PoC implementation review

**Implementation approved for the disposable lab.** This decision covers
implementation and testing for the isolated configuration below. Credentials
and deployment outside that lab require separate approval.

### Boundary to approve

- Allow one preconfigured client role assignment to one synthetic user in one
  dedicated Keycloak realm. Bind the HTTPS origin, realm name and ID, user ID,
  client UUID, role name and UUID, POST route and canonical body to the approved
  execution intent. Reject substitutions before transport.
- Use distinct credentials for the single grant POST, admin-event reads, and
  direct-mapping reads. Keep bootstrap administration with the lab operator.
  If provider policy cannot enforce the configured target scope, confine the
  credentials and all writes to the disposable realm.
- Require current governance checks, durable single-use consumption and a
  committed PostgreSQL reservation before HTTPS dispatch. Pin the approved
  endpoint and trust anchors. Allow one POST with bounded timeouts, redirects
  disabled, and transport retries disabled.
- Recover using read-only reconciliation and the stored attempt identity.
  Persist the confirmed outcome and audit receipts only after the bound event
  and direct mapping are verified.

### Evidence and remaining acceptance work

The [PR #2556 rehearsal artifact](https://github.com/veritasfuji-japan/veritas_os/actions/runs/45731492668/artifacts/15077790117)
records CI checkout `20162ee89d99e7dda937dad6a6915f6a54c3a48f` and both
container repository digests. The [merge into main](https://github.com/veritasfuji-japan/veritas_os/commit/bdb8db78b838f9ec0f8f5e047f0ec9ad174f6f8f)
has SHA `bdb8db78b838f9ec0f8f5e047f0ec9ad174f6f8f`. A separate
[`main` workflow run](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/keycloak-bind-role-rehearsal.yml)
and its artifact are pending. Record the run ID, exact tested SHA and artifact
link here before treating the result as evidence from `main`.

| Acceptance area | Evidence available for review | Required before offering the adapter |
| --- | --- | --- |
| Request binding and contention | The rehearsal composes signed requests with PostgreSQL and denies a replacement reservation for the same business event. | Exercise the actual registered HTTPS boundary with changed binding inputs and two separate sender workers. |
| Crash before POST or after accepted POST with a lost response | The artifact records 0 and 1 provider grant events, respectively, with 0 recovery POSTs in both cases. The positive case includes verified receipt hashes. | Repeat against the approved adapter entry point and pinned lab configuration. |
| Ambiguous PostgreSQL commit | The [PostgreSQL regression](../../../veritas_os/tests/test_pg_bind_effect_state_contention.py#L754) injects a lost acknowledgement and proves that a committed reservation survives and cannot be claimed again. | Inject acknowledgement loss at the adapter boundary and measure 0 outgoing grant POSTs from the affected worker. |
| Reader credentials | The [Keycloak rehearsal](../../../veritas_os/tests/test_keycloak_bind_role_rehearsal.py#L390) checks a denied grant route for the mapping reader, and [checks the same for the audit reader](../../../veritas_os/tests/test_keycloak_bind_role_rehearsal.py#L501). | Check denial of both grant and audit mutations for each provisioned reader using the approved provider policy. |
| Unresolved evidence | The rehearsal exercises missing mappings, role revocation and retry refusal in its isolated fixtures. | Exercise missing, ambiguous and stale observations through the registered adapter recovery path, and verify that they stay unresolved with 0 grant POSTs. |

The dedicated executable boundary uses the separate
`KEYCLOAK_DISPOSABLE_LOOPBACK_LAB_V1` registry scope. The executor only connects
to a fixed loopback TLS peer, authenticates its signed lab hostname using
configured lab roots, and exposes no application route. Its transport records a
bounded HTTP observation. Separate read credentials and recorded Keycloak
events plus direct mappings establish confirmed effect.

The single-use consumer and an independent current-input recheck must verify
the signed human approval and exact request. The durable dispatch commitment
must return successfully before the executor opens the transport. The owning
task rechecks governance after TLS and spends its internal permit immediately
before the sole write. The local acknowledgement, a restored reservation, and
an unresolved effect cannot create another send authority.

### Staging worker lifecycle rehearsal

The internal `keycloak_staging_rehearsal_worker` context shares the normal API
lifespan in a dedicated rehearsal process. A trusted local harness provisions
a synthetic user and role in the disposable loopback realm, constructs the
existing lab deployment and signed authorization inputs, and enters the
context. No HTTP route is registered.

This entry point requires staging posture, explicit
`VERITAS_ENABLE_KEYCLOAK_STAGING_REHEARSAL=1`, and the reviewed deployment digest
in `VERITAS_KEYCLOAK_STAGING_DEPLOYMENT_SHA256`. It accepts a numeric loopback
PostgreSQL host and a dedicated `veritas_rehearsal_*` database. The shared
PostgreSQL halt backend uses a dedicated `veritas-rehearsal-*` deployment ID.
Normal startup arms the halt. The operator uses the existing authenticated
resume flow before the harness calls the yielded dispatch function once in
the same task. The entry point cannot resume the deployment.

The worker checks the database recovery state before startup and again before
handing the request to the existing executor. Run the restore and dispatch
phases in sequence. For the staging acceptance test, record zero grants while
recovery is pending, zero additional grants for an already consumed
authorization, and one grant for a newly approved authorization. Record
both write requests and independent Keycloak admin events. Concurrent restore
and live worker execution require separate verification.

### Database ordering prerequisite

Migration `0019` records Keycloak reservations, cancellations and dispatch
commitments in the same PostgreSQL ordering table as Sandbox, with distinct
Keycloak values. The trusted Keycloak control-plane function verifies the signed
authorization and exact Keycloak binding even before consumption or reservation.
Before a trusted operator can cancel an unreserved Sandbox authorization,
the control plane must call `register_sandbox_revocation_scope` with the
signed native artifact and its exact Sandbox binding. A verified Sandbox
attempt already provides durable scope. Both Sandbox cancellation interfaces
require that scope and reject existing Keycloak intents, including reservations
created before migration `0019`. Operator grants remain independently required.
An existing Sandbox ordering row blocks a Keycloak commitment for the same ID.

A reservation commits its ordering row, effect row and recovery intent
together. Only the call that receives a fresh reservation can attempt the
subsequent commitment. A committed cancellation prevents the commitment.
A lost acknowledgement or a restore fence blocks the caller from proceeding.
The commitment records database ordering only. A future executor still needs
current governance, the authorized credentials and the registered transport
boundary. There is no Keycloak operator SQL entry point in this change.

Apply the migration with workers drained and use the same PostgreSQL primary.
Existing Keycloak reservations remain readable for reconciliation and cannot
be resumed through the new commitment path. Use the matching restore reconciler
before clearing the restore fence. It can replay an authoritative Keycloak
revocation over a restored reservation when the durable consumption and
business event claims match. Other decision conflicts keep the fence set.
The migration refuses downgrade while Keycloak ordering history exists.
