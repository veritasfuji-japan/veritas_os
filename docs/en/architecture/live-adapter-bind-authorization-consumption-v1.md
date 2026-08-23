# Live Adapter Bind Authorization Consumption / Bind Invocation Gate v1

## Purpose

This boundary consumes the signed Real Bind Authorization produced by the
preceding authorization layer and is the first layer permitted to access
credential material or invoke Bind.

The required ordering is:

1. re-verify the complete Real Bind Authorization and its current validity;
2. reconstruct and hash-check the exact ExecutionIntent;
3. atomically consume the authorization exactly once;
4. resolve only the credential reference bound by that authorization;
5. construct the Authorization header in ephemeral memory;
6. construct an adapter bound to the exact adapter, endpoint and credential
   digests carried by the authorization;
7. invoke the existing Bind adjudication core.

No credential access, header construction, adapter construction or Bind call is
allowed before atomic consumption succeeds.

## Single-use semantics

The authorization and its idempotency key are unique consumption keys.
PostgreSQL enforces both using UNIQUE constraints and `INSERT ... ON CONFLICT
DO NOTHING`, so concurrent processes cannot both consume the same grant.

The in-memory store exists only for deterministic tests and reference use. It
is process-local and explicitly marks itself `production_safe = False`.

A downstream failure does **not** release an authorization. If credential
resolution, header construction, adapter construction or Bind fails after the
atomic consume step, that authorization remains consumed. A new authorization
must be issued for a new attempt.

## Secret boundary

`AuthorizationConsumptionRecord` contains only non-secret lineage digests and
identifiers. Resolved credential bytes and the constructed Authorization header
are held only in ephemeral runtime objects whose repr is redacted. Neither is
written into the consumption record or returned in the result.

## Exact binding

Before Bind invocation the gate checks the adapter factory output against the
signed authorization for:

- adapter contract ID and hash;
- endpoint identity binding digest;
- credential reference digest;
- credential scope binding digest.

The ExecutionIntent ID and canonical hash are also rechecked directly from the
signed authorization.

## Failure semantics

These conditions fail closed before credential access:

- invalid or tampered authorization;
- expired/not-yet-valid authorization;
- invalid ExecutionIntent binding;
- already-consumed authorization;
- consumption-store failure.

These conditions fail closed after consumption and do not release it:

- credential resolution failure or binding mismatch;
- Authorization-header construction failure or invalid header value;
- adapter construction failure or binding mismatch.

## Relationship to Bind

Real Bind Authorization is permission to attempt one exact future Bind.
Atomic consumption converts that one-time permission into a single Bind
attempt. It does not guarantee that Bind commits. The existing Bind core still
performs live snapshot, authority, constraints, drift, risk, freshness,
commit-boundary, postcondition and rollback/compensation checks and may return a
blocked, escalated, failed, rolled-back or committed BindReceipt.

Therefore:

**Authorization != Consumption**

**Consumption != Bind success**

**Bind invocation != External effect success**

**BindReceipt records the attempted bind outcome; it does not retroactively
create authorization.**

## Non-claims

This work does not claim customer deployment, regulatory certification, or
that every credential provider/authorization scheme has a production adapter.
Credential resolution, header construction and adapter construction are
injected contracts. PostgreSQL is the durable cross-process single-use backend
provided by this version.
