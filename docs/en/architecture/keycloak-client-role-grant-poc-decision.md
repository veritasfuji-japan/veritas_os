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

## Implementation acceptance

Exercise the adapter as a separate process against isolated Keycloak and real
PostgreSQL. Kill and restart that process with the original database, and use
observed provider writes rather than in-process counters as evidence. Report
the tested commit and a sanitized attempt/evidence summary.

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
