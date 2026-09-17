# WAT Operations Contract

## Purpose

This document defines the operator-facing service targets and degraded-operation procedure for the current v1 WAT shadow lane.

It is an operational contract for the existing implementation. It does **not** make WAT an execution-authority path, does not change authorization/admissibility/Human Approval/Bind semantics, and does not create a production SLA claim.

Related tracking:

- Issue #2246 — WAT event write/read SLO and error budget
- Issue #2247 — repeated TrustLog anchor-append failure runbook

## Boundary

The WAT lane is observer/audit telemetry. A WAT event write can persist a local JSONL record and separately attempt TrustLog linkage. Those are distinct outcomes:

1. **WAT local event persistence** — the WAT JSONL record is appended and flushed/fsynced.
2. **TrustLog anchor linkage** — `append_signed_decision(...)` is attempted and its compact result is stored in `trustlog_anchor_ref`.

A TrustLog anchor failure currently records `{"error": "anchor_append_failed"}` in `trustlog_anchor_ref`; it does not convert WAT into execution authority and does not authorize any real-world action.

## WAT v1 service objectives

These are **provisional operator targets**, not externally validated production SLAs. They become measured claims only when the deployment exports the corresponding request/write/read telemetry and a 30-day observation window exists.

### Measurement population

Count only syntactically valid, authenticated WAT requests presented to the WAT lane.

Exclude:

- caller validation errors (`4xx` caused by invalid input or insufficient permission);
- planned maintenance explicitly excluded from the measurement window;
- requests intentionally rejected by documented policy semantics.

Do not exclude server-side storage, signing, TrustLog, filesystem, or internal application failures.

### Write SLO

**Target:** at least **99.9% successful local WAT event persistence over a rolling 30-day window**.

A write is successful only when the WAT event has been appended to the configured WAT event store and the local write path has completed its flush/fsync boundary.

A TrustLog anchor failure is tracked separately and does not redefine a successful local WAT write as a successful anchor.

**Latency target:** p95 WAT event mutation request latency <= **1,000 ms** over the same observation window, measured at the HTTP boundary when route-level latency telemetry is available.

### Read SLO

**Target:** at least **99.9% successful WAT read operations over a rolling 30-day window** for valid authenticated reads whose target exists.

Expected `404 wat_not_found` responses are semantic misses and are not counted as availability failures.

**Latency target:** p95 valid WAT read latency <= **500 ms** over the same observation window, measured at the HTTP boundary when route-level latency telemetry is available.

### Error budget

For each 30-day measurement window:

- local write error budget: **0.1%** of eligible WAT write attempts;
- read error budget: **0.1%** of eligible existing-target WAT reads.

The error budget is request-count based, not a promise of downtime minutes. A deployment may additionally derive time-based availability, but that must not replace the request-based calculation above.

If either budget is exhausted:

1. stop treating WAT lane availability as healthy;
2. open an operator incident;
3. preserve relevant logs, WAT records, request identifiers, and TrustLog references;
4. prioritize correctness/integrity recovery over feature work;
5. do not weaken RBAC, revocation confirmation, retention, or TrustLog integrity checks to restore the target.

### Operator-visible failure classes

Use these stable operator classifications in incident notes and reviewer packets. They are operational labels, not new runtime reason codes.

| Classification | Meaning | Required posture |
|---|---|---|
| `WAT_LOCAL_WRITE_FAILED` | Local WAT event was not durably persisted | Treat as WAT lane availability failure; investigate storage/I/O before normal operation |
| `WAT_READ_FAILED` | Valid read could not complete because of server/storage failure | Treat as WAT lane availability failure |
| `WAT_ANCHOR_APPEND_FAILED` | WAT local record exists but TrustLog linkage attempt reported failure | Preserve local evidence; follow anchor runbook below |
| `WAT_ANCHOR_APPEND_REPEATED` | More than one anchor-append failure is observed within 10 minutes or two consecutive WAT events contain `anchor_append_failed` | Escalate to operator incident; stop blind recovery attempts |
| `WAT_INTEGRITY_UNCERTAIN` | Operator cannot determine whether an anchor append committed before the caller observed failure | Read-only verification/reconciliation only; no blind resend |

## Retry posture

### WAT local persistence

The current v1 code path does not define a cross-process idempotency contract for replaying a failed WAT mutation. Operators must not create an automated infinite retry loop.

At most one caller-level retry may be attempted **only when** the caller has a stable operation/request identity and can establish that the original WAT event was not persisted. If that fact cannot be established, classify the state as uncertain and do not resend blindly.

### TrustLog anchor append

Do **not** blindly call the TrustLog append path again for the same historical WAT event after an exception.

Reason: a caller-visible append error does not, by itself, prove that no durable TrustLog effect occurred. Blind redispatch can create duplicate or conflicting audit evidence.

The operator procedure is verification-first and read-only until the state is known.

## Runbook: repeated TrustLog anchor-append failure

### 1. Detect and classify

Treat either of the following as an anchor failure signal:

- WAT record contains `trustlog_anchor_ref.error == "anchor_append_failed"`;
- TrustLog observability reports an anchor/append failure associated with the same time window.

Escalate to `WAT_ANCHOR_APPEND_REPEATED` when:

- more than one anchor-append failure occurs within 10 minutes; or
- two consecutive persisted WAT events contain `anchor_append_failed`.

If logs indicate a timeout, connection loss, process interruption, or any condition where commit status cannot be proven, additionally classify `WAT_INTEGRITY_UNCERTAIN`.

### 2. Preserve evidence before intervention

Preserve, without rewriting:

- affected WAT JSONL records;
- `event_id`, `wat_id`, `event_ts`, `event_type`, and actor;
- full `trustlog_anchor_ref` contents;
- application logs covering the failure window;
- TrustLog append/sign/anchor metrics and relevant backend logs;
- current TrustLog ledger/witness verification output;
- deployment/version/configuration identifiers needed to reproduce the state.

Do not edit the affected WAT event to make the anchor appear successful.

### 3. Stop unsafe retries

When the repeated-failure threshold is met:

- stop automated/manual blind anchor redispatch for the affected historical event;
- do not downgrade signer, mirror, retention, or integrity requirements merely to force success;
- do not synthesize a successful `trustlog_anchor_ref`;
- do not interpret WAT telemetry as execution permission.

The existing WAT shadow lane may remain observationally available if local event persistence is healthy, but the anchor-linkage degradation must remain visible to operators/reviewers.

### 4. Diagnose the dependency

Check, in this order:

1. TrustLog signing/key availability;
2. TrustLog primary append health;
3. configured anchor backend health and credentials;
4. mirror/object-lock dependencies when enabled;
5. storage/network/process errors in the failure window;
6. ledger verification results for possible partial/uncertain commit.

Use existing TrustLog observability guidance in `docs/en/operations/trustlog_observability.md`.

### 5. Reconcile read-only

Before any repair action, determine whether a TrustLog entry corresponding to the affected WAT event already exists.

Use read-only ledger/witness inspection and verification. Match on the strongest available evidence, such as event identifiers, request references, payload hashes, timestamps, and signed evidence.

Outcomes:

- **confirmed present and valid** — do not append again; record the incident as caller-observed failure with durable evidence present;
- **confirmed absent** — historical repair requires an explicitly designed/idempotent repair path; current v1 does not claim one;
- **indeterminate** — retain `WAT_INTEGRITY_UNCERTAIN`; do not resend.

### 6. Restore normal service

After the underlying TrustLog/anchor dependency is healthy:

1. verify a new, non-replayed WAT event can persist locally;
2. verify its `trustlog_anchor_ref` is successful and structurally valid;
3. run the relevant TrustLog verification checks;
4. confirm failure counters/alerts have stopped increasing;
5. attach preserved evidence and recovery results to the incident/reviewer record.

Do not rewrite prior failed WAT records. Recovery evidence is additive.

## Fail-closed / non-bypass rules

Operational recovery must never:

- grant or widen execution authority;
- bypass RBAC;
- bypass explicit confirmed-revocation confirmation;
- mutate Human Approval or BindAuthorization semantics;
- treat an observer-lane record as permission to act;
- silently discard failed anchor evidence;
- claim external mirror/transparency exactly-once delivery.

## Non-claims

This contract does not prove:

- production availability at the stated targets;
- customer deployment reliability;
- external TrustLog mirror/transparency exactly-once semantics;
- independent infrastructure durability;
- production HA/DR or SLA readiness.

The numeric objectives above are operational targets that require measured deployment telemetry before they can be reported as achieved.
