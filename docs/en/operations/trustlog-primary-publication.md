# TrustLog Primary Publication — PostgreSQL Operations

## Scope

This note applies only to the explicit v1 primary-publication API backed by PostgreSQL. Existing `PostgresTrustLogStore.append()` callers are unchanged.

## Required migration

The feature requires Alembic revision `0009_trustlog_primary_publication_identity.py`.

Before enabling a caller that uses `PostgresTrustLogPrimaryPublisher`, apply:

```bash
alembic upgrade head
```

Verify the current revision with:

```bash
alembic current
```

The migration adds nullable columns and unique indexes to `trustlog_entries`; it does not rewrite existing TrustLog rows.

## Operational invariant

For publication-aware rows:

```text
logical_identity_key = one immutable logical entry identity
publication_key      = that identity + exact canonical redacted payload hash
```

A retry with the same identity and same payload returns the already committed row. A retry that reuses the same logical identity with different payload fails closed.

Operators must not delete or rewrite a committed publication-aware row to make a retry succeed.

## Incident handling

If a caller loses the response after a publish attempt, retry the exact same `entry_type`, stable `entry_id`, schema version, and payload. The service resolves from PostgreSQL durable state; do not mint a replacement `entry_id` merely because the first response was ambiguous.

A `TRUSTLOG_PRIMARY_PUBLICATION_COLLISION` is a governance/evidence integrity event, not a transient retry condition. Investigate why one logical identity was presented with changed content.

## Monitoring

Useful checks include:

```sql
SELECT logical_identity_key, count(*)
FROM trustlog_entries
WHERE logical_identity_key IS NOT NULL
GROUP BY logical_identity_key
HAVING count(*) > 1;
```

The expected result is zero rows.

To inspect one publication:

```sql
SELECT id,
       request_id,
       logical_identity_key,
       publication_key,
       canonical_payload_hash,
       publication_schema_version,
       publication_entry_type,
       publication_entry_id,
       created_at
FROM trustlog_entries
WHERE logical_identity_key = '<key>';
```

Do not place credentials, secrets, or private customer data into operational queries, tickets, or review artifacts.

## Non-claims

This feature does not provide cross-system transactions or exactly-once delivery to mirrors/transparency anchors. Secondary publication remains a separate destination-specific problem, including ambiguous `ATTEMPTED_UNKNOWN` outcomes where applicable.
