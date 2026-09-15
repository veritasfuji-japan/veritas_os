# TrustLog Primary Publication PostgreSQL Proof

## Purpose

This proof implements the first scoped property from `TrustLog Publication Boundary v1`:

```text
one immutable logical TrustLog identity
-> at most one durable PostgreSQL TrustLog row
```

It does **not** extend that statement to mirrors, transparency anchors, external delivery, execution authority, or real-world effect confirmation.

## Storage change

Alembic revision `0009` adds nullable publication identity columns to `trustlog_entries`:

- `logical_identity_key`
- `publication_key`
- `canonical_payload_hash`
- `publication_schema_version`
- `publication_entry_type`
- `publication_entry_id`

Existing TrustLog rows remain valid because the columns are nullable. The new explicit primary-publication API is the only path that populates them.

Two unique PostgreSQL indexes provide durable arbitration for publication-enabled rows:

- one on `logical_identity_key`;
- one on `publication_key`.

## Identity model

The implementation deliberately separates logical identity from exact content identity.

`logical_identity_key` is derived from:

- `entry_type`;
- stable `entry_id`;
- publication schema version.

`publication_key` additionally binds the canonical redacted payload hash.

This split is required to detect the case where the same logical entry identity is reused with changed content. If payload hash were part of the only unique identity, changed content would silently become a different key instead of a collision.

Payload hashing follows the TrustLog safety rule: redaction happens before canonical hashing.

## Primary publication behavior

`PostgresTrustLogPrimaryPublisher.publish(...)` uses the same PostgreSQL advisory-lock identity as the existing TrustLog append path so publication-enabled entries remain serialized with the existing hash chain.

Within one transaction it:

1. acquires the TrustLog chain advisory lock;
2. looks up durable state by `logical_identity_key`;
3. returns the already committed row when identity and payload match;
4. fails closed when the same logical identity is bound to different content;
5. otherwise prepares the redacted/hash-chained TrustLog entry;
6. inserts one `trustlog_entries` row with the publication identity fields;
7. advances `trustlog_chain_state`;
8. returns a reviewer-safe publication result and deterministic receipt hash.

No process-local success flag is authoritative.

## Real PostgreSQL proof cases

The dedicated workflow `.github/workflows/trustlog-primary-publication-postgresql.yml` runs Alembic to head against PostgreSQL 16 and proves:

1. 32 concurrent same-identity/same-payload calls resolve to one durable row;
2. exactly one caller reports `created=true` and the others report `observed_existing`;
3. same logical identity with changed payload fails closed;
4. retry after a hypothetical lost success response resolves the original durable row;
5. closing and recreating the process-local connection pool does not permit duplicate insertion;
6. deterministic identity unit tests remain stable under JSON key reordering and TrustLog redaction.

## Receipt semantics

The primary publication result records whether the current caller:

- created the durable row; or
- observed an already committed equivalent publication.

The receipt also fixes explicit negative claims:

- no mirror delivery claim;
- no transparency-anchor delivery claim;
- no execution authority creation;
- no external-effect proof.

## Relationship to existing TrustLog append

The existing `PostgresTrustLogStore.append()` behavior is intentionally unchanged. This proof introduces a separate explicit publication API rather than retroactively changing duplicate semantics for every existing TrustLog caller.

Pre-existing rows therefore continue to use the established request-id/hash-chain contract. Publication-aware callers opt into the stronger logical-identity contract.

## Migration operations

Apply:

```bash
alembic upgrade head
```

Revision `0009` follows `0008` and adds only nullable columns plus unique indexes. Downgrade removes those indexes and columns; production operations should continue to prefer forward migrations over destructive downgrade.

## Claim boundary

When the dedicated real-PostgreSQL proof is green, the valid statement is limited to:

```text
primary PostgreSQL logical uniqueness is proven for the explicit v1 publication API.
```

It is **not** valid to infer:

- cross-system distributed exactly-once;
- exactly-once mirror delivery;
- exactly-once transparency-anchor delivery;
- independently operated external TrustLog infrastructure;
- production readiness;
- external effect authenticity;
- regulatory approval or certification.
