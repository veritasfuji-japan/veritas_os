# Audit Replay Registry PostgreSQL v0.1 — Local Observation Archive

**Status:** opt-in PostgreSQL archive of locally verified Audit Evidence Profile v0.2 observations. This is **not** a runtime security gate, authenticated provenance system, proof of external effects, or a guarantee that historical packet coverage is complete.

## Purpose

PR #2446 checks replay in an explicitly submitted set of local packets; PR #2447 introduced the observation schema and read-only validator. This PR adds a separate database inventory so that a later invocation can detect ID and Manifest byte reuse against **previously archived packets**, even after the process restarts.

The existing production-capable Bind Authorization consumption database and single-use semantics remain completely separate. Audit retention does not authorize any action, consume an execution permit, or validate third-party origin.

## Changes

- Migration `0012`, after `0011`, creates `audit_packet_inventory` (one packet row) and `audit_case_observations` (one row per case). It adds PostgreSQL-enforced unique indexes for `packet_id`, `(packet_id,case_id)`, `(repository_key,operation_id)`, `(repository_key,manifest_id)`, and global `manifest_sha256`.
- `PostgresAuditReplayRegistry.ingest(packet_root, profile_paths)` independently re-runs the bounded scanner from #2446; **no API accepting a caller-supplied `PASS` report or arbitrary record payload exists**. Every bound case is converted into a strictly checked #2447 observation record. A non-`PASS` local scan, unsupported claimed repository namespace or malformed field fails without storage.
- The shared PostgreSQL pool performs the entire requested packet set in **one transaction**. Every case and envelope is inserted with SQL `ON CONFLICT DO NOTHING RETURNING`; a conflict is a **transaction-rollback** event, not a partially accepted batch. Parallel invocations rely on DB uniqueness, not process-local locks or a check-then-insert.
- Exact, **unchanged** retries of the same packet set are reported as `ALREADY_PRESENT` after header and all case records match. Mixed existing/new packets are rejected as `REPLAY_DETECTED` and rolled back, requiring a fresh non-overlapping input batch.
- `readback(packet_id)` fetches retained case records, rechecks local record format/digests and joins to the packet header, and reports `FOUND_UNAUTHENTICATED`, `NOT_FOUND`, `INCOMPLETE`, or `REGISTRY_UNAVAILABLE`. A missing packet is not evidence that the entire history is complete.

## Example (opt-in; requires migration)

```python
from pathlib import Path
from scripts.validation.audit_replay_registry_postgresql_v0_1 import (
    PostgresAuditReplayRegistry,
)

registry = PostgresAuditReplayRegistry()
result = await registry.ingest(
    packet_root=Path("/trusted-isolated-packets"),
    profile_paths=["packet-a/profile.json"],
)
assert result.status in {
    "NEW_OBSERVATION", "ALREADY_PRESENT", "REPLAY_DETECTED",
    "INPUT_INVALID", "REGISTRY_UNAVAILABLE",
}
```

Set `VERITAS_DATABASE_URL` using the project’s existing PostgreSQL connection settings and run `alembic upgrade head`. No runtime request handler, agent tool, Bind policy, or production ingestion job calls this API automatically.

## Explicit outcome meanings

| Status | Meaning |
| --- | --- |
| `NEW_OBSERVATION` | The whole locally consistent input batch committed new packet/case observations in this database |
| `ALREADY_PRESENT` | An exact retry of the same archived packet/case records; **not** a fresh independent observation |
| `REPLAY_DETECTED` | The proposed batch collided with recorded identity/bytes, or attempted a mixed old/new archive; **no new batch was committed** |
| `INPUT_INVALID` | The caller's file set failed local scanner or observation-contract validation |
| `REGISTRY_UNAVAILABLE` | Storage, transaction, permission, or commit acknowledgement failed; record existence is **unknown** until read-back |

Read-back statuses deliberately do not offer an `AUTHENTICATED` or global `PASS` value.

## Invariants and limitations

1. **Atomic within one request:** a failure at any case insert rolls back its entire packet set. This is database transaction atomicity, not a globally synchronized snapshot of files in an untrusted input directory.
2. **Concurrent replay:** unique indexes serialize conflicting inserts across processes. Exactly one new batch can win a same-key race; identical retries may become `ALREADY_PRESENT`.
3. **Database restarts:** archived rows remain on the PostgreSQL server across application pool lifecycle changes; the automated CI reopens the pool and reads them back. This does not claim a simulated physical DB crash/recovery, point-in-time restoration or backup integrity.
4. **Locally observed ≠ authenticated:** all IDs, repositories, source commits, metadata and JSON digests are self-declared. Hashes are unsigned and do not establish identity, trusted timestamps, retention, legal custody, issuer authenticity or actual effects.
5. **Claimed namespaces:** `repository_key` lowercases an unverified ASCII `owner/repo`. This avoids trivial casing changes inside this inventory; **it is not a tenant isolation boundary**.
6. **Coverage:** only explicitly scanned and successfully archived packets can be compared. Omitted packets, deleted records, database restore/rollback, privileged changes and other stores are not visible. No independent completeness watermark or external append-only checkpoint is created here.
7. **Unstable inputs:** the scanner uses bounded, descriptor-relative local file reads but does not guarantee a perfect atomic filesystem snapshot under concurrent mutation. Use an isolated, stable input directory and independent immutable acquisition for stronger evidence.
8. **Outages:** `REGISTRY_UNAVAILABLE` means indeterminate storage state, never a clean history or guaranteed rollback if acknowledgement was lost. Retry only after readback and reconciliation.
9. **No runtime gate changes:** failure of this archival service does not change the separate Bind Authorization consumption gate or automatically fail closed a live provider action; integration of any future effect boundary requires a distinct design and review.
10. **Administrative rights:** PostgreSQL UNIQUE constraints do not prevent privileged deletion, updates, restore from old backup or malicious tampering. Append-only privilege restrictions, recovery verification and independently anchored commits are later work.

## Required CI and human review

- PostgreSQL 16 service with `alembic upgrade head` and strict new offline contract tests.
- Real database tests for fresh archive, identical retries, cross-invocation replay, namespace scoping, same-packet concurrent races, full-batch rollback on a later conflicting case, restart-equivalent pool close/reopen readback, invalid scanner inputs.
- Existing #2446 and #2447 regressions remain green; broad security/CI checks pass on the final head.
- Review that no runtime credential/Bind code changed, database privileges/migrations are appropriate, and only local claimed provenance is represented.

**Do not merge the Draft PR until these checks are green.** Do not deploy the migration without a migration/backup plan. Downgrading populated archive tables destroys the retained audit history.
