# PostgreSQL Production Guide

> **Audience**: Operations / DevOps / SRE teams deploying VERITAS OS with PostgreSQL  
> **Last updated**: 2026-04-12

---

## 0. Docker Compose Quick Start (PostgreSQL Enabled)

Docker Compose **defaults to PostgreSQL** for both Memory and TrustLog backends.
No additional configuration is needed beyond `docker compose up --build`:

```bash
# Start with PostgreSQL backend (default)
docker compose up --build

# Verify backend selection
curl -s http://localhost:8000/health | python3 -c "
import json, sys
h = json.load(sys.stdin)
print('Storage backends:', h['storage_backends'])
# Expected: {'memory': 'postgresql', 'trustlog': 'postgresql'}
"
```

The `backend` service sets:
- `VERITAS_MEMORY_BACKEND=postgresql`
- `VERITAS_TRUSTLOG_BACKEND=postgresql`
- `VERITAS_DATABASE_URL=postgresql://veritas:veritas@postgres:5432/veritas`
- `VERITAS_DB_AUTO_MIGRATE=true`

### Lightweight local dev (file-based backends)

To run without PostgreSQL, override in your `.env`:

```bash
VERITAS_MEMORY_BACKEND=json
VERITAS_TRUSTLOG_BACKEND=jsonl
```

---

## 1. Backend Selection Policy

VERITAS OS supports two storage backend families:

| Backend | Best for | Limitations |
|---------|----------|-------------|
| **JSONL / JSON** (default) | Single-node dev/demo, rapid prototyping, air-gapped environments | No concurrent-write safety beyond file locks, no queryable audit, single-process only |
| **PostgreSQL** | Multi-worker production, durable audit, queryable TrustLog, horizontal read scaling | Requires PostgreSQL 14+ infrastructure, connection pool tuning, backup discipline |

### When to choose PostgreSQL

- You run multiple backend workers (`WEB_CONCURRENCY > 1` or multi-pod Kubernetes).
- You need queryable TrustLog or MemoryOS data (SQL access, JSONB containment queries).
- Your compliance posture requires a durable, WAL-backed, point-in-time-recoverable audit store.
- You plan to scale beyond a single application instance.

### When JSONL is still appropriate

- Single-process development or demo deployments.
- Air-gapped environments where PostgreSQL infrastructure is unavailable.
- CI test pipelines (mock pools simulate PostgreSQL behaviour without a live database).

### Environment variables for backend selection

```bash
# MemoryOS backend (default: json)
VERITAS_MEMORY_BACKEND=postgresql

# TrustLog backend (default: jsonl)
VERITAS_TRUSTLOG_BACKEND=postgresql

# PostgreSQL DSN (required when either backend = postgresql)
VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
```

---

## 2. Connection Pool Configuration

The process-wide async connection pool is managed by `psycopg_pool.AsyncConnectionPool`
in `veritas_os/storage/db.py`.

### Recommended settings by environment

| Variable | Dev | Staging | Production | Description |
|----------|-----|---------|------------|-------------|
| `VERITAS_DB_POOL_MIN_SIZE` | `1` | `2` | `5` | Minimum idle connections maintained |
| `VERITAS_DB_POOL_MAX_SIZE` | `5` | `10` | `20` | Maximum connections (match PostgreSQL `max_connections` budget) |
| `VERITAS_DB_CONNECT_TIMEOUT` | `10` | `5` | `5` | TCP connect timeout (seconds) |

### Sizing guidance

- **Production rule of thumb**: `max_size` ≤ (`max_connections` − superuser reserve) / number of backend workers.
- Default PostgreSQL `max_connections` is 100. With 4 workers and a 10-connection superuser reserve: `max_size` = (100 − 10) / 4 = 22 → use `20`.
- Use PgBouncer in `transaction` mode for high-concurrency deployments (>100 total connections).
- Monitor `pg_stat_activity` to confirm pool utilisation is not saturating.

---

## 3. SSL / TLS

### Environment variable

```bash
# libpq sslmode parameter
VERITAS_DB_SSLMODE=verify-full    # Production recommended
```

### Recommended posture by environment

| Environment | `sslmode` | Notes |
|-------------|-----------|-------|
| Dev (local Docker) | `disable` or `prefer` | No TLS overhead for local development |
| Staging | `require` | Encrypts traffic; does not verify server certificate |
| Production | `verify-full` | Full certificate chain + hostname verification |

### Server-side setup

For `verify-full`, PostgreSQL must be configured with:

```ini
# postgresql.conf
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file  = '/etc/ssl/private/server.key'
ssl_ca_file   = '/etc/ssl/certs/ca.crt'
```

The client (VERITAS backend) verifies the CA chain via the system trust store or
the `sslrootcert` parameter in the DSN:

```bash
VERITAS_DATABASE_URL=postgresql://veritas:***@db.prod:5432/veritas?sslrootcert=/etc/ssl/certs/ca.crt
```

---

## 4. Statement Timeout

```bash
# Per-statement timeout in milliseconds (default: 30000 = 30s)
VERITAS_DB_STATEMENT_TIMEOUT_MS=30000
```

This is injected via `options=-c statement_timeout=…` in the connection string
built by `veritas_os/storage/db.py:build_conninfo()`.

### Guidance

| Environment | Recommended | Rationale |
|-------------|-------------|-----------|
| Dev | `30000` (30 s) | Generous for debugging |
| Staging | `15000` (15 s) | Catch slow queries early |
| Production | `10000` (10 s) | Prevent runaway queries from holding locks |

If TrustLog chain-hash appends regularly approach the timeout, investigate:
- Lock contention on `trustlog_chain_state` (advisory lock `0x5645524954415301`).
- Index bloat on `trustlog_entries`.
- Connection pool exhaustion.

---

## 5. Transaction Timeout

PostgreSQL does not have a native `transaction_timeout` parameter (as of PostgreSQL 16).
VERITAS OS relies on the **statement timeout** (§4) combined with the
`psycopg_pool` connection reclaim timeout to bound transaction duration.

### Application-level safeguards

- All `PostgresTrustLogStore.append` calls use `conn.transaction()` context manager,
  which auto-rolls-back on exception — **fail-closed**.
- All `PostgresMemoryStore` writes use explicit `conn.transaction()`.
- The advisory lock (`pg_advisory_xact_lock`) is released on COMMIT or ROLLBACK —
  there is no risk of leaked locks from timed-out transactions.

### PostgreSQL-side recommendation

Set `idle_in_transaction_session_timeout` on the PostgreSQL server to catch
stale transactions that the application fails to close:

```sql
ALTER SYSTEM SET idle_in_transaction_session_timeout = '60s';
SELECT pg_reload_conf();
```

---

## 6. Migration Operations

VERITAS OS uses **Alembic** for PostgreSQL schema management.
See [`database-migrations.md`](database-migrations.md) for the full reference.

### Pre-deployment checklist

1. **Back up the database** before any migration (see §8).
2. Run `alembic upgrade head` against the **staging** database first.
3. Validate with `make db-current` to confirm the expected revision.
4. Apply to production: `alembic upgrade head`.
5. Verify application health after migration.

### Migration commands

```bash
# Apply all pending migrations
make db-upgrade          # → alembic upgrade head

# Show current revision
make db-current

# Roll back one revision (⚠️ destructive — dev/staging only)
make db-downgrade        # → alembic downgrade -1

# Generate SQL without executing (for DBA review)
alembic upgrade head --sql > migration.sql
```

### Auto-migration on startup

```bash
VERITAS_DB_AUTO_MIGRATE=false   # Default — migrations must be run explicitly
```

Setting `VERITAS_DB_AUTO_MIGRATE=true` is acceptable for **dev** and **staging** only.
In production, run migrations as a discrete deployment step before starting
application workers.

### Migration from legacy SQL migrator

If the database was originally created by `veritas_os/storage/migrations/`, stamp
the current state without re-running DDL:

```bash
alembic stamp head
```

---

## 7. Secret Management

### Database credentials

| Environment | Approach |
|-------------|----------|
| Dev | Plaintext in `.env` (not committed to source control) |
| Staging | Environment variable injection via CI or container orchestrator |
| Production | **External secret manager** (Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) |

**Never** embed credentials in `docker-compose.yml`, `alembic.ini`, or source code.

### VERITAS_DATABASE_URL in production

- Store the full DSN (including password) in your secret manager.
- Inject it as an environment variable at container runtime.
- If using Kubernetes, use a `Secret` resource with `envFrom`.

### Alignment with VERITAS posture

In `secure` / `prod` posture, VERITAS OS already enforces external secret management
for `VERITAS_API_SECRET`. Apply the same discipline to `VERITAS_DATABASE_URL`:

```bash
# AWS Secrets Manager example
VERITAS_DATABASE_URL=$(aws secretsmanager get-secret-value \
  --secret-id veritas/prod/database-url \
  --query SecretString --output text)
```

---

## 8. Backup and Restore

### Recommended strategy

| Method | Use case | Frequency |
|--------|----------|-----------|
| `pg_dump` (logical) | Full export, cross-version migration | Daily or pre-migration |
| Continuous WAL archiving | Point-in-time recovery (PITR) | Continuous (production) |
| Filesystem snapshot | Fast backup on managed databases (RDS, Cloud SQL) | Managed by cloud provider |

### Logical backup

```bash
# Full database dump (compressed)
pg_dump -Fc -U veritas -h db.prod veritas > veritas_$(date +%Y%m%d).dump

# Restore
pg_restore -U veritas -h db.prod -d veritas veritas_20260411.dump
```

### TrustLog backup considerations

- TrustLog entries are **append-only** and **hash-chained**. A partial restore
  will break the chain. Always restore the complete `trustlog_entries` and
  `trustlog_chain_state` tables together.
- After restore, verify chain integrity:
  ```bash
  curl -H "X-API-Key: $VERITAS_API_KEY" http://localhost:8000/v1/trustlog/verify
  ```

### Retention policy

Define retention based on your regulatory requirements:

- **TrustLog entries**: Retain for the legally required audit period (often 5–7 years
  for financial, 10 years for healthcare/EU AI Act Art. 12).
- **Memory records**: Governed by your data retention policy and GDPR/CCPA
  erasure obligations (`erase_user_data` API).

---

## 9. Replication and High Availability

### Current status

VERITAS OS does **not** manage PostgreSQL replication or failover. The application
connects to a single `VERITAS_DATABASE_URL` endpoint.

### Recommended HA topology

```
┌─────────────────┐     ┌────────────────┐
│  VERITAS Backend │────▶│   PgBouncer    │
│  (N workers)     │     │ (transaction)  │
└─────────────────┘     └───────┬────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
              ┌─────▼─────┐          ┌─────▼─────┐
              │  Primary   │──WAL──▶ │  Replica   │
              │ (read/write)│        │ (read-only)│
              └───────────┘          └───────────┘
```

### Guidance

- Use a **managed PostgreSQL** service (RDS, Cloud SQL, Azure Database for PostgreSQL)
  for automatic failover and backup management.
- If self-hosted, configure streaming replication with `pg_basebackup` and a
  failover manager (Patroni, repmgr, pg_auto_failover).
- TrustLog chain-hash integrity depends on **serialized writes**. Never point
  TrustLog writes at a read replica or a multi-primary cluster. The advisory lock
  (`pg_advisory_xact_lock`) assumes a single writable primary.

### Read replicas

- Safe for: MemoryOS search queries (`search`, `list_all`, `get`).
- **Not safe for**: TrustLog `append` (chain serialization), MemoryOS `put` (upsert).
- Application-level read/write splitting is **not yet implemented**. This is a
  future enhancement (see §13).

---

## 10. Secure / Prod Posture Recommended Settings

The following is a reference configuration for `secure` or `prod` posture
deployments with PostgreSQL:

```bash
# ── Posture ──
VERITAS_POSTURE=prod
VERITAS_ENV=production

# ── PostgreSQL backend ──
VERITAS_MEMORY_BACKEND=postgresql
VERITAS_TRUSTLOG_BACKEND=postgresql
VERITAS_DATABASE_URL=postgresql://veritas:${DB_PASSWORD}@db.prod:5432/veritas?sslrootcert=/etc/ssl/certs/ca.crt

# ── Connection pool ──
VERITAS_DB_POOL_MIN_SIZE=5
VERITAS_DB_POOL_MAX_SIZE=20
VERITAS_DB_CONNECT_TIMEOUT=5
VERITAS_DB_STATEMENT_TIMEOUT_MS=10000

# ── TLS ──
VERITAS_DB_SSLMODE=verify-full

# ── Migrations ──
VERITAS_DB_AUTO_MIGRATE=false

# ── PostgreSQL server-side (set via ALTER SYSTEM) ──
# idle_in_transaction_session_timeout = '60s'
# log_min_duration_statement = 500       -- log queries > 500ms
# shared_preload_libraries = 'pg_stat_statements'
```

### PostgreSQL server hardening checklist

| Item | Action | Priority |
|------|--------|----------|
| Use `verify-full` sslmode | Prevent MITM between app and database | **CRITICAL** |
| Set `idle_in_transaction_session_timeout` | Kill leaked transactions | HIGH |
| Set `log_min_duration_statement` | Detect slow queries | HIGH |
| Enable `pg_stat_statements` | Query performance monitoring | HIGH |
| Restrict `pg_hba.conf` to application IPs | Limit network access | **CRITICAL** |
| Use separate database roles | Least-privilege access | HIGH |
| Disable `SUPERUSER` for application role | Prevent privilege escalation | **CRITICAL** |
| Set `password_encryption = scram-sha-256` | Strong password hashing | HIGH |

---

## 11. JSONL → PostgreSQL Migration

### Migration CLI

The `veritas-migrate` CLI tool automates the file-to-PostgreSQL migration.
It is designed to be:

- **Idempotent** — re-running produces the same final state.  Entries
  already present in PostgreSQL are skipped (duplicate-safe).
- **Fail-soft** — a single malformed or failing entry is recorded in the
  report but does not abort the migration.
- **Chain-preserving** — TrustLog `sha256` / `sha256_prev` values are
  stored verbatim; the hash chain is *never* recomputed.
- **Resume-safe** — after a partial failure, simply re-run the same
  command.  Already-imported entries are counted as duplicates.
- **Observable** — every run produces a structured report (text or JSON)
  with counts for migrated, duplicates, malformed, failed, and
  (optionally) a post-import hash-chain verify result.

#### Subcommands

| Subcommand | Source format | Target table | Dedup key |
|------------|--------------|--------------|-----------|
| `memory`   | JSON (`memory.json`) | `memory_records` | `(key, user_id)` |
| `trustlog` | JSONL (`trust_log.jsonl`, plain or `ENC:` encrypted) | `trustlog_entries` | `request_id` |

#### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Migration (or dry-run) completed with zero failures |
| 1 | Migration completed but some entries failed or were malformed |
| 2 | Invalid arguments or fatal runtime error |

### Step-by-step procedure

```bash
# ── 1. Preparation ──────────────────────────────────────────────
# Back up the existing file-based data
cp -a runtime/memory/ /backup/memory_$(date +%Y%m%d)/
cp -a runtime/trustlog/ /backup/trustlog_$(date +%Y%m%d)/

# Start PostgreSQL (if not already running)
docker compose up -d postgres
# Wait for health check
docker compose exec postgres pg_isready -U veritas

# ── 2. Schema setup ─────────────────────────────────────────────
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
make db-upgrade          # alembic upgrade head

# ── 3. Dry-run (read-only validation) ──────────────────────────
# Verify source files are parseable and estimate migration scope
# without writing anything to PostgreSQL.
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --dry-run
veritas-migrate memory   --source /data/logs/memory.json      --dry-run

# For CI pipelines, use --json for machine-readable output:
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --dry-run --json

# ── 4. Import TrustLog entries ──────────────────────────────────
# Entries are inserted in original file order with sha256 / sha256_prev
# preserved verbatim (no recomputation).  Duplicate request_ids are
# skipped automatically.
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --verify

# ── 5. Import Memory records ───────────────────────────────────
# Memory records use skip-on-conflict semantics: existing (key, user_id)
# pairs are not overwritten.  Both the list format and the legacy
# {"users": {...}} dict format are supported.
veritas-migrate memory --source /data/logs/memory.json

# ── 6. Verify ───────────────────────────────────────────────────
# The --verify flag (step 4) already ran a post-import hash-chain
# integrity check.  You can also verify via the API:
VERITAS_TRUSTLOG_BACKEND=postgresql \
VERITAS_MEMORY_BACKEND=postgresql \
  python -m pytest veritas_os/tests/ -m smoke -q --tb=short

# Or via the REST endpoint:
curl -H "X-API-Key: $VERITAS_API_KEY" http://localhost:8000/v1/trustlog/verify

# ── 7. Switch backends ──────────────────────────────────────────
# Update .env
# VERITAS_MEMORY_BACKEND=postgresql
# VERITAS_TRUSTLOG_BACKEND=postgresql
# Restart the application
```

### Dry-run checklist

Before committing to a production import:

- [ ] `veritas-migrate trustlog --source … --dry-run` reports zero malformed / failed
- [ ] `veritas-migrate memory   --source … --dry-run` reports zero malformed / failed
- [ ] PostgreSQL schema applied (`make db-current` shows expected revision)
- [ ] Import completed on **staging** first
- [ ] `veritas-migrate trustlog --source … --verify` shows `Verify: PASS`
- [ ] `/v1/trustlog/verify` returns `ok` after import
- [ ] Smoke tests pass with PostgreSQL backend (`pytest -m smoke`)
- [ ] Entry count matches: JSONL file lines ≈ `SELECT count(*) FROM trustlog_entries`

### Retry / resume after partial failure

The migration CLI is **idempotent** and **resume-safe**.  If a run
fails partway through (e.g. a database connection drops), simply
re-run the same command:

```bash
# Re-run — already-imported entries are counted as duplicates, not errors.
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --verify
veritas-migrate memory   --source /data/logs/memory.json
```

There is no need to drop and re-create the schema.  The report will
show the number of duplicates (previously imported) and newly migrated
entries.

### Rollback

If you need to discard the imported data entirely and start fresh:

```bash
# Drop all managed tables and re-create a clean schema
alembic downgrade base    # ⚠️ drops all managed tables
alembic upgrade head      # re-create clean schema
# Re-run the migration from step 4
```

### Key considerations

- **TrustLog chain hashes**: The `import_entry()` method stores original
  `sha256` / `sha256_prev` values verbatim — `prepare_entry()` is
  **not** invoked.  This preserves the cryptographic chain exactly as
  it was computed by the JSONL backend.
- **Memory records**: Each record is a key/value pair with user isolation.
  Import uses `ON CONFLICT … DO NOTHING` semantics — existing records
  are never overwritten.
- **Ordering matters**: TrustLog entries are read line-by-line from the
  source JSONL file and inserted in that order, preserving `prev_hash` →
  `hash` chain linkage.
- **Encrypted sources**: Lines prefixed with `ENC:` are decrypted
  automatically when `VERITAS_ENCRYPTION_KEY` is set.
- **Test on staging first**: Verify the migrated data with `--verify`
  and `/v1/trustlog/verify` before switching production.
- **Quiesce writes**: Run the migration while TrustLog writes are paused
  (service stopped or quiesced) to avoid interleaving new entries with
  migrated ones.

### After migration

- Update `.env` to set `VERITAS_TRUSTLOG_BACKEND=postgresql` and
  `VERITAS_MEMORY_BACKEND=postgresql`.
- Remove or archive the JSONL files.
- The file-based stores are no longer read once the backend is switched.

---

## 12. Rollback / Downgrade

### Application rollback

If a VERITAS OS version upgrade introduces PostgreSQL schema changes:

1. **Do not downgrade the schema** (`alembic downgrade`) in production unless
   you have verified the downgrade path in staging.
2. **Preferred approach**: Deploy the previous application version with the
   new schema. Alembic migrations are designed to be backward-compatible
   (additive columns, not destructive changes).
3. **Emergency rollback**: Restore from backup (§8) to the pre-migration state.

### Backend rollback (PostgreSQL → JSONL)

Switching back from PostgreSQL to JSONL is possible but requires data export:

1. Export TrustLog entries from PostgreSQL to JSONL format.
2. Export Memory records from PostgreSQL to JSON format.
3. Set `VERITAS_TRUSTLOG_BACKEND=jsonl` and `VERITAS_MEMORY_BACKEND=json`.
4. Restart the application.

**Warning**: This is a downgrade path. Data written to PostgreSQL after the last
export will be lost. Use only in emergency scenarios.

### Schema downgrade

```bash
# Roll back one migration (⚠️ data loss)
alembic downgrade -1

# Roll back all migrations (⚠️ drops all managed tables)
alembic downgrade base
```

**Never run `alembic downgrade` in production without a verified backup.**

### Re-executing a failed migration

If `alembic upgrade head` fails midway (e.g. network timeout), the Alembic
version table may be in an inconsistent state:

```bash
# 1. Check the current revision
make db-current

# 2. If the revision is at the failed migration, stamp it back
alembic downgrade -1        # undo the partial migration

# 3. Re-run
make db-upgrade

# 4. If downgrade also fails, restore from backup (see Backup and Restore, §8) and re-apply
```

Alembic tracks each revision atomically — a migration either fully applies
or the version table is not updated.  However, if a migration contains
multiple DDL statements and the database does not support transactional DDL
for the operation (e.g. `CREATE INDEX CONCURRENTLY`), partial application
is possible.  In that case, manually fix the schema state and use
`alembic stamp <revision>` to align the version table.

---

## 13. Smoke Tests and Release Validation

The PostgreSQL backend is exercised across all three CI validation tiers.
Understanding how each tier relates to storage backends is essential for
confident deployments.

### Tier 1 — PR / push to `main` (`main.yml`)

| Job | Storage backend | What it validates |
|-----|-----------------|-------------------|
| `governance-smoke` | Default (JSONL/JSON) | 20+ smoke tests verify governance invariants |
| `test (py3.11/3.12)` | Default (JSONL/JSON) + mock PostgreSQL pool | 195+ parity tests via mock pool |

Smoke tests (`@pytest.mark.smoke`) run with whichever backend is active.
In the default CI matrix this is JSONL/JSON. PostgreSQL-specific behaviour
is covered by the mock-pool parity tests in `test_storage_backend_*.py`.

New in this tier:
- `TestPostgresqlBackendReadWrite` exercises Memory write/read and TrustLog
  list through the API, confirming the backend read/write paths work.
- `TestBackendMisconfigurationFailFast` verifies that startup fails fast
  on missing `VERITAS_DATABASE_URL`, unknown backends, unused DATABASE_URL,
  and mixed backend configurations.

### Tier 2 — Release gate (`release-gate.yml`)

| Job | Storage backend | What it validates |
|-----|-----------------|-------------------|
| `production-tests` | Default + `@pytest.mark.production` | Production-like validation |
| `docker-smoke` | PostgreSQL (via `docker compose`) | Full-stack health + read/write with real PostgreSQL |
| `trustlog-production-matrix` | N/A (posture profiles) | TrustLog promotion paths for dev/secure/prod |

The `docker-smoke` job starts the full Docker Compose stack, which defaults
to PostgreSQL.  This validates that:
- Schema migrations apply cleanly (`VERITAS_DB_AUTO_MIGRATE=true`)
- `/health` reports `storage_backends: {memory: postgresql, trustlog: postgresql}`
- Memory write/read operations succeed against real PostgreSQL
- TrustLog read path is exercised against real PostgreSQL
- Failure messages clearly indicate "backend not switched to PostgreSQL"

### Tier 3 — Weekly / manual (`production-validation.yml`)

| Job | Storage backend | What it validates |
|-----|-----------------|-------------------|
| `postgresql-smoke` | Real PostgreSQL (service container) | Backend parity + health endpoint verification |
| `docker-smoke` | PostgreSQL (via `docker compose`) | Full-stack health + read/write with real PostgreSQL |
| `production-tests` | Default | Long-running production-like checks |

The `postgresql-smoke` job now also verifies that `get_backend_info()` reports
`postgresql` for both backends, catching silent fallback to file stores.

### Misconfiguration fail-fast

The `validate_backend_config()` function (called during app startup) enforces
the following:

| Scenario | Behaviour |
|----------|-----------|
| `VERITAS_*_BACKEND=postgresql` without `VERITAS_DATABASE_URL` | **RuntimeError** — hard fail |
| Unknown backend name (e.g. `redis`, `sqlite`) | **ValueError** — hard fail |
| `VERITAS_DATABASE_URL` set but neither backend is `postgresql` | **Warning** — likely backend-switch oversight |
| Only one backend is `postgresql` (mixed setup) | **Warning** — usually unintentional |

### Running smoke tests locally with PostgreSQL

```bash
# Start PostgreSQL and apply schema
docker compose up -d postgres
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
make db-upgrade

# Run smoke tests against PostgreSQL
VERITAS_MEMORY_BACKEND=postgresql \
VERITAS_TRUSTLOG_BACKEND=postgresql \
  make test-smoke

# Run full production-like validation
VERITAS_MEMORY_BACKEND=postgresql \
VERITAS_TRUSTLOG_BACKEND=postgresql \
  make test-production
```

### Verifying PostgreSQL backend usage

After starting the stack with `docker compose up`, confirm PostgreSQL is
actually in use (not silently falling back to file backends):

```bash
# Quick check via /health endpoint
curl -s http://localhost:8000/health | python3 -c "
import json, sys
h = json.load(sys.stdin)
b = h.get('storage_backends', {})
print(f'memory={b.get(\"memory\")}, trustlog={b.get(\"trustlog\")}')
assert b.get('memory') == 'postgresql', 'Memory backend is NOT PostgreSQL!'
assert b.get('trustlog') == 'postgresql', 'TrustLog backend is NOT PostgreSQL!'
print('✓ Both backends confirmed as PostgreSQL')
"
```

### Validation coverage summary

| Validation area | Covered by | Backend |
|-----------------|-----------|---------|
| Schema creation / migration | `test-postgresql` CI job, `docker-smoke` | Real PostgreSQL |
| Contract parity (JSONL ↔ PG) | `test_storage_backend_contract.py` | Mock pool |
| Side-by-side parity | `test_storage_backend_parity_matrix.py` | Mock pool |
| Full-stack health check | `docker-smoke` | Real PostgreSQL (compose) |
| Memory read/write via API | `TestPostgresqlBackendReadWrite`, `docker-smoke` | Both |
| TrustLog read via API | `TestPostgresqlBackendReadWrite`, `docker-smoke` | Both |
| Chain-hash integrity | Smoke tests + `/v1/trustlog/verify` | Both |
| Advisory lock contention | `test_pg_trustlog_contention.py` (38 tests: 25 mock + **13 real-PG**) | Mock pool + **real PostgreSQL** |
| Pool/activity metrics | `test_pg_metrics.py` (28 tests) | Mock pool + TestClient |
| Backup/restore/drill scripts | `test_drill_postgres_recovery.py` (31 tests) | Shell script validation |
| Fail-fast on missing DSN | `test_storage_factory.py` | Mock |
| Fail-fast on contradiction | `test_storage_factory.py`, `TestBackendMisconfigurationFailFast` | Mock |
| Mixed backend warning | `test_storage_factory.py` | Mock |
| Connection pool lifecycle | `test_storage_db.py` | Mock |

### Contention test suite (`test_pg_trustlog_contention.py`)

This test module contains **two layers** of advisory-lock serialisation tests:

**Layer 1 — Mock-pool tests (25 tests)**  
Exercise TrustLog advisory-lock serialization under realistic
concurrent-access patterns using an enhanced mock pool that faithfully
simulates `pg_advisory_xact_lock` via `threading.Lock`.  Run on every
PR as part of Tier 1 CI.

| Scenario | Tests | What it proves |
|----------|------:|----------------|
| 2-worker simultaneous append | 2 | Chain intact after exactly 2 racing writers |
| N-worker burst (5 / 10 / 20) | 4 | Hash chain valid under burst load |
| Statement timeout → fail-closed | 3 | INSERT / lock / UPDATE timeout → `RuntimeError` |
| Connection pool starvation | 2 | Pool exhaustion → `RuntimeError` (fail-closed) |
| Rollback recovery | 2 | Chain state unchanged after partial failure |
| Advisory lock release | 3 | Lock freed on both commit and rollback |
| Full chain verification | 4 | Hash formula, get_by_id, iter_entries correct |
| Mixed success/failure | 2 | Interleaved failures leave chain valid |
| Threaded contention (OS threads) | 2 | Multi-thread chain integrity (closer to Uvicorn workers) |

**Layer 2 — Real PostgreSQL tests (13 tests, `@pytest.mark.postgresql @pytest.mark.contention`)**  
Prove that PostgreSQL's own `pg_advisory_xact_lock` mechanism actually
serialises writes on a live database.  Run in the `test-postgresql` job
(Tier 1, every PR) and the `postgresql-smoke` job (Tier 3, weekly) against
a PostgreSQL 16 service container.

| Scenario | Tests | What it proves |
|----------|------:|----------------|
| 2 concurrent writers | 2 | Real advisory lock serialises two concurrent appends |
| 5-worker burst | 1 | Chain intact after 5 workers on live PG |
| 10-worker burst | 1 | No gaps / duplicates after 10-worker burst on live PG |
| Lock timeout → fail-closed | 1 | Real PG `statement_timeout` triggers `RuntimeError` |
| Chain intact after lock-timeout + recovery | 1 | Chain not corrupted by a timed-out append |
| Pool waiting (8 workers, max_size=2) | 1 | All appends complete when pool is saturated |
| Rollback recovery | 1 | Chain state unchanged after forced rollback on real PG |
| Append after recovery | 1 | Post-failure append continues chain correctly |
| Full chain verify (20-writer burst) | 1 | `iter_entries` + sha256 chain validated on real PG |
| No duplicate request_ids | 1 | DB `UNIQUE` constraint + advisory lock prevent duplicates |
| Advisory lock released after commit | 1 | Second connection acquires lock without blocking |
| Advisory lock released after rollback | 1 | Next append succeeds without lock starvation |

**How to run locally**:

```bash
# Mock-pool tests (no database needed)
pytest veritas_os/tests/test_pg_trustlog_contention.py -m "not (postgresql and contention)"

# Real PostgreSQL contention tests (requires VERITAS_DATABASE_URL + migrations)
export VERITAS_DATABASE_URL="postgresql://user:pass@localhost:5432/veritas"
alembic upgrade head
pytest veritas_os/tests/test_pg_trustlog_contention.py \
  -m "postgresql and contention" \
  -v --tb=short
```

### Metrics test suite (`test_pg_metrics.py`)

Exercises the full observability stack for the PostgreSQL backend:

| Area | Tests | What it proves |
|------|------:|----------------|
| Metric definitions | 4 | All pool gauges, counters, histograms, activity gauges exist |
| Recording helpers | 7 | `set_db_pool_stats`, `record_db_connect_failure`, latency, conflict, etc. |
| Pool-stats collection | 3 | Mock pool → correct in_use/available/waiting |
| pg_stat_activity collection | 3 | long_running / idle_in_tx / advisory_lock_wait parsed |
| Health-check gauge | 2 | Healthy / unhealthy pool → correct gauge value |
| Backend label emission | 1 | Component/backend labels emitted |
| High-level collector | 2 | File backend stub + PG full collection |
| `/v1/metrics` integration | 3 | Endpoint includes `db_pool`, `db_health`, `db_activity` |
| DB unavailable behaviour | 1 | Broken pool → safe zero defaults |

### Recovery drill test suite (`test_drill_postgres_recovery.py`)

Validates the backup / restore / drill shell scripts without requiring a
running PostgreSQL instance:

| Area | Tests | What it proves |
|------|------:|----------------|
| Script existence & permissions | 3×3 | `backup_postgres.sh`, `restore_postgres.sh`, `drill_postgres_recovery.sh` exist, are executable, have shebang |
| Bash syntax validation | 3 | `bash -n` passes for all scripts |
| Help flag output | 3 | `--help` exits 0 and shows usage |
| Content coherence | 6 | Scripts reference expected tools (`pg_dump`, `pg_restore`) and flags (`--ci`, `--verify`) |
| Runbook coherence | 7 | `postgresql-drill-runbook.md` references all scripts, documents HA boundaries, exit codes |

See also [`postgresql-drill-runbook.md`](postgresql-drill-runbook.md)
for the complete drill procedure.

See [`production-validation.md`](../validation/production-validation.md) for the
complete tier model and [`backend-parity-coverage.md`](../validation/backend-parity-coverage.md)
for the full parity test matrix.

---

## 14. Legacy Path Cleanup

### Official vs. compatibility paths

The PostgreSQL backend is the **recommended production path**.  Several
legacy code paths remain for backward compatibility:

| Path | Status | Location | Notes |
|------|--------|----------|-------|
| File-based TrustLog helpers | **Compatibility** | `server.py` (`LEGACY COMPAT` comments) | Wraps file I/O; delegated to DI store when PostgreSQL is active |
| Backward-compat re-exports | **Compatibility** | `server.py` (route imports) | Tests monkeypatch these; removing would break test imports |
| `veritas_os/storage/migrations/` | **Superseded** | SQL file migrator | Replaced by Alembic; retained for pre-existing databases |
| `is_file_backend()` predicate | **Active** | `dependency_resolver.py` | Used by health checks and route handlers to adapt behaviour |

### Migration from legacy SQL migrator

If the database was created by `veritas_os/storage/migrations/` (the
original SQL-file migrator), stamp the Alembic version without re-running DDL:

```bash
alembic stamp head
```

After stamping, all future schema changes are managed by Alembic.

### Cleanup timeline

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | DI-based store injection (`app.state.trust_log_store`) | ✅ Done |
| Phase 2 | Consolidate legacy TrustLog helpers to DI store | ✅ Done (PR #1292) |
| Phase 3 | Remove backward-compat re-exports from `server.py` | Planned — requires test import audit |
| Phase 4 | Remove legacy SQL migrator (`storage/migrations/`) | Planned — requires migration-path documentation cutover |

See [`legacy-path-cleanup.md`](legacy-path-cleanup.md) for the full
cleanup plan and rationale.

---

## 15. PostgreSQL Metrics Reference (`/v1/metrics`)

When either `VERITAS_TRUSTLOG_BACKEND` or `VERITAS_MEMORY_BACKEND` is set to
`postgresql`, the `/v1/metrics` endpoint exposes additional fields and the
Prometheus `/metrics` endpoint emits additional gauges/counters.

### JSON response fields

| Field | Type | Description |
|-------|------|-------------|
| `db_pool` | `object \| null` | Connection pool snapshot (null when backend = file) |
| `db_pool.in_use` | `int` | Connections currently checked out |
| `db_pool.available` | `int` | Idle connections ready for use |
| `db_pool.waiting` | `int` | Requests blocked waiting for a connection |
| `db_pool.max_size` | `int` | Configured maximum pool size |
| `db_pool.min_size` | `int` | Configured minimum pool size |
| `db_health` | `bool` | `true` when `SELECT 1` succeeds |
| `db_activity` | `object \| null` | pg_stat_activity snapshot (null when file backend or DB unhealthy) |
| `db_activity.long_running` | `int` | Queries exceeding the statement timeout |
| `db_activity.idle_in_tx` | `int` | Connections idle in a transaction |
| `db_activity.advisory_lock_wait` | `int` | Sessions waiting on advisory locks |

### Prometheus metrics

#### Pool gauges (updated on every `/v1/metrics` scrape)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `db_pool_in_use` | Gauge | — | Checked-out connections |
| `db_pool_available` | Gauge | — | Idle connections |
| `db_pool_waiting` | Gauge | — | Waiting requests |
| `db_pool_max_size` | Gauge | — | Max pool size |
| `db_pool_min_size` | Gauge | — | Min pool size |

#### Health and backend

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `db_health_status` | Gauge | — | 1 = healthy, 0 = unhealthy |
| `db_backend_selected` | Gauge | `component`, `backend` | 1 for each active storage backend |

#### Failure counters

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `db_connect_failures_total` | Counter | `reason` | Connection failures |
| `db_statement_timeouts_total` | Counter | — | SQL statement timeouts |
| `trustlog_append_conflict_total` | Counter | — | Unique-constraint conflicts on append |
| `slow_append_warning_total` | Counter | — | Appends exceeding 1 s threshold |

#### Latency and activity

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `trustlog_append_latency_seconds` | Histogram | — | End-to-end TrustLog append time |
| `long_running_query_count` | Gauge | — | Queries exceeding timeout threshold |
| `idle_in_transaction_count` | Gauge | — | Idle-in-transaction connections |
| `advisory_lock_contention_count` | Gauge | — | Advisory lock waiters |

### Interpreting the metrics

* **`db_pool_in_use` ≈ `db_pool_max_size`** → Pool exhaustion risk.
  Action: increase `VERITAS_DB_POOL_MAX_SIZE` or investigate slow queries.
* **`db_pool_waiting > 0`** → Callers are blocked.
  Correlate with `trustlog_append_latency_seconds` to find the bottleneck.
* **`db_health_status = 0`** → Database is unreachable.
  Check `db_connect_failures_total` for the failure pattern.
* **`long_running_query_count > 0`** → Possible lock contention or
  missing indexes.  Cross-check with `advisory_lock_contention_count`.
* **`slow_append_warning_total` increasing** → TrustLog appends are slow.
  Investigate lock contention, WAL pressure, or connection pool saturation.

### File-backend behaviour

When both backends use file storage (`jsonl` / `json`), the `db_pool`,
`db_activity` fields are `null` and `db_health` is always `true`.
Prometheus gauges for pool/activity are set to zero.
The `db_backend_selected` gauge still reflects the active backend names.

### 日本語サマリー

PostgreSQL バックエンド使用時、`/v1/metrics` は接続プールの利用状況
(`db_pool`)、データベース健全性 (`db_health`)、アクティブセッション情報
(`db_activity`) を返します。ファイルバックエンド時はこれらは `null` / `true`
になります。Prometheus メトリクスも同様に更新されます。

| 指標 | 意味 |
|------|------|
| `db_pool_in_use ≈ max_size` | プール枯渇リスク |
| `db_pool_waiting > 0` | 接続待ちが発生中 |
| `db_health_status = 0` | データベース到達不能 |
| `long_running_query_count > 0` | 長時間クエリ検出 |
| `slow_append_warning_total` 増加 | TrustLog 書込みが遅い |

---

## 16. Known Limitations and Future Work

### Current limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Search** | Token-based `LIKE ANY` search (no vector similarity) | Lower relevance ranking vs. vector search |
| **Read replicas** | No application-level read/write splitting | All queries go to primary |
| **Data import** | `veritas-migrate` CLI requires service quiesce during TrustLog migration (§11) | Planned: online migration with write-ahead buffering |
| **Multi-database** | Single `VERITAS_DATABASE_URL` for all backends | Cannot split MemoryOS and TrustLog across databases |
| **Schema versioning in CI** | Mock pool in unit tests, real PG only in `test-postgresql` and `docker-smoke` jobs | Behavioral drift possible between mock and real |
| **Concurrent advisory lock testing** | 13 real-PG contention tests (`@pytest.mark.postgresql and contention`) run in `test-postgresql` (Tier 1) and `postgresql-smoke` (Tier 3) | Advisory lock serialisation verified on live PG 16; high-load saturation not tested |
| **Backup encryption** | `backup_postgres.sh` / `restore_postgres.sh` do not encrypt backups at rest | Use filesystem-level or object-storage encryption |
| **Cross-region restore** | Drill scripts assume same-network restore target | Manual adaptation needed for cross-region DR |
| **Recovery drill requires CREATEDB** | Test-mode drill creates a temporary database | PostgreSQL user needs `CREATEDB` privilege |

### What is guaranteed by tests

| Guarantee | Test module | Count |
|-----------|-------------|------:|
| Hash chain intact under N-way concurrent append (mock) | `test_pg_trustlog_contention.py` | 25 |
| Hash chain intact under N-way concurrent append (real PG) | `test_pg_trustlog_contention.py` | 13 |
| Pool/activity metrics emitted correctly | `test_pg_metrics.py` | 28 |
| Drill scripts syntactically valid and coherent | `test_drill_postgres_recovery.py` | 21 |
| CRUD parity (JSONL ↔ PostgreSQL) | `test_storage_backend_*.py` | 195+ |
| `/v1/metrics` includes `db_pool`, `db_health`, `db_activity` | `test_pg_metrics.py` | 3 |
| Fail-closed on pool starvation / statement timeout (mock) | `test_pg_trustlog_contention.py` | 5 |
| Fail-closed on lock-timeout (real PG) | `test_pg_trustlog_contention.py` | 2 |
| Advisory lock released on both commit and rollback | `test_pg_trustlog_contention.py` | 5 |
| Backup/restore scripts reference correct tools and flags | `test_drill_postgres_recovery.py` | 9 |
| Drill runbook documents all scripts, HA boundaries, exit codes | `test_drill_postgres_recovery.py` | 7 |

### What is NOT guaranteed by tests

| Area | Reason |
|------|--------|
| Advisory lock serialisation under CPU/IO saturation | Real-PG tests use an idle CI container (PG 16, no competing load); saturation behaviour not tested |
| WAL archiving / PITR restore | Infrastructure-level; not tested at application layer |
| Cross-version `pg_dump` / `pg_restore` compatibility | Tested only with PostgreSQL 16 in CI |
| Encrypted backup integrity | Backup scripts produce unencrypted dumps |
| Multi-region failover | Application uses single `VERITAS_DATABASE_URL` endpoint |
| Large-scale burst (>20 concurrent writers) | Real-PG tests cap at 20 workers; higher concurrency is future work |

### Planned future enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **pgvector** | Vector similarity search for MemoryOS (`embedding` column + HNSW/IVFFlat index) | High |
| **Online migration** | Live migration with write-ahead buffering (no service quiesce) | Medium |
| **Table partitioning** | Range-partition `trustlog_entries` by `created_at` for archive and query performance | Medium |
| **CDC (Change Data Capture)** | Logical replication / Debezium for streaming TrustLog to external audit systems | Medium |
| **Archive policy** | Automated partitioned table detach + cold storage for aged TrustLog entries | Medium |
| **Read/write splitting** | Route read-only queries to replicas for horizontal scaling | Low |
| **Legacy migrator removal** | Remove `veritas_os/storage/migrations/` once all deployments are on Alembic | Low |
| **Encrypted backups** | Add GPG/age encryption to `backup_postgres.sh` output | Low |
| **Large-scale contention** | Extend real-PG contention tests to >20 concurrent writers under simulated CPU/IO load | Low |

### Operational notes

- **Advisory lock contention**: Under very high TrustLog write rates (>1000 appends/sec),
  the advisory lock on `trustlog_chain_state` may become a bottleneck. Monitor
  `pg_stat_activity` for `pg_advisory_xact_lock` waits.
- **JSONB index maintenance**: GIN indexes on JSONB columns require periodic
  `REINDEX` or `VACUUM` to maintain performance. Schedule during maintenance windows.
- **Alembic version table**: Do not manually modify the `alembic_version` table.
  Use `alembic stamp` to correct version mismatches.

---

## 17. Three-Tier Environment Reference

### Dev (local)

```bash
VERITAS_POSTURE=dev
VERITAS_MEMORY_BACKEND=json          # File-based (no PostgreSQL needed)
VERITAS_TRUSTLOG_BACKEND=jsonl
# VERITAS_DATABASE_URL not required
VERITAS_DB_SSLMODE=disable
VERITAS_DB_AUTO_MIGRATE=true         # OK for dev
```

### Staging

```bash
VERITAS_POSTURE=staging
VERITAS_MEMORY_BACKEND=postgresql
VERITAS_TRUSTLOG_BACKEND=postgresql
VERITAS_DATABASE_URL=postgresql://veritas:staging_pass@db.staging:5432/veritas
VERITAS_DB_POOL_MIN_SIZE=2
VERITAS_DB_POOL_MAX_SIZE=10
VERITAS_DB_SSLMODE=require
VERITAS_DB_STATEMENT_TIMEOUT_MS=15000
VERITAS_DB_AUTO_MIGRATE=false        # Run migrations explicitly
```

### Secure / Prod

```bash
VERITAS_POSTURE=prod
VERITAS_MEMORY_BACKEND=postgresql
VERITAS_TRUSTLOG_BACKEND=postgresql
VERITAS_DATABASE_URL=postgresql://veritas:${DB_PASSWORD}@db.prod:5432/veritas?sslrootcert=/etc/ssl/certs/ca.crt
VERITAS_DB_POOL_MIN_SIZE=5
VERITAS_DB_POOL_MAX_SIZE=20
VERITAS_DB_CONNECT_TIMEOUT=5
VERITAS_DB_STATEMENT_TIMEOUT_MS=10000
VERITAS_DB_SSLMODE=verify-full
VERITAS_DB_AUTO_MIGRATE=false        # Always run migrations as a discrete step
```

---

# PostgreSQL 本番運用ガイド

> **対象読者**: VERITAS OS を PostgreSQL で運用するオペレーション / DevOps / SRE チーム  
> **最終更新**: 2026-04-12

---

## 1. バックエンド選択方針

VERITAS OS は 2 種類のストレージバックエンドをサポートしています:

| バックエンド | 推奨用途 | 制約 |
|-------------|---------|------|
| **JSONL / JSON**（デフォルト） | 単一ノードの開発/デモ、ラピッドプロトタイピング | ファイルロック以上の並行書込み安全性なし、単一プロセスのみ |
| **PostgreSQL** | マルチワーカー本番環境、耐久性のある監査、クエリ可能な TrustLog | PostgreSQL 14+ インフラが必要、接続プール調整、バックアップ運用 |

### PostgreSQL を選ぶべきとき

- 複数のバックエンドワーカーを実行する場合（`WEB_CONCURRENCY > 1` や Kubernetes マルチポッド）
- TrustLog や MemoryOS データに SQL でクエリする必要がある場合
- コンプライアンス上、WAL ベースのポイントインタイムリカバリ可能な監査ストアが必要な場合

## 2. 推奨プール設定

| 変数 | 開発 | ステージング | 本番 |
|------|------|------------|------|
| `VERITAS_DB_POOL_MIN_SIZE` | `1` | `2` | `5` |
| `VERITAS_DB_POOL_MAX_SIZE` | `5` | `10` | `20` |
| `VERITAS_DB_CONNECT_TIMEOUT` | `10` | `5` | `5` |

**サイジングルール**: `max_size` ≤ (`max_connections` − スーパーユーザ予約) / ワーカー数

## 3. SSL/TLS

| 環境 | `VERITAS_DB_SSLMODE` | 備考 |
|------|---------------------|------|
| 開発 | `disable` / `prefer` | ローカル開発ではTLSオーバーヘッドなし |
| ステージング | `require` | 通信暗号化（証明書検証なし） |
| 本番 | `verify-full` | 完全な証明書チェーン＋ホスト名検証 |

## 4. ステートメントタイムアウト

```bash
VERITAS_DB_STATEMENT_TIMEOUT_MS=10000   # 本番推奨: 10秒
```

## 5. マイグレーション運用

- 本番では `VERITAS_DB_AUTO_MIGRATE=false`（デフォルト）を維持
- マイグレーションはデプロイ手順として明示的に実行: `make db-upgrade`
- ロールバックは本番ではバックアップからの復元を推奨

## 6. JSONL → PostgreSQL インポート

`veritas-migrate` CLI でファイルベースデータを PostgreSQL へ安全に移行できます。

```bash
# ドライラン（読み取り専用のバリデーション）
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --dry-run
veritas-migrate memory   --source /data/logs/memory.json      --dry-run

# 本番インポート（ハッシュチェーン検証付き）
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --verify
veritas-migrate memory   --source /data/logs/memory.json

# CI パイプライン向け JSON 出力
veritas-migrate trustlog --source /data/logs/trust_log.jsonl --dry-run --json
```

| 特性 | 説明 |
|------|------|
| **冪等** | 再実行しても同じ最終状態。既存エントリはスキップ（重複カウント） |
| **フェイルソフト** | 不正なエントリはレポートに記録されるが移行を中断しない |
| **チェーン保存** | `sha256` / `sha256_prev` は元の値のまま格納（再計算なし） |
| **再開可能** | 部分的失敗後、同じコマンドを再実行するだけで再開 |
| **暗号化ソース対応** | `ENC:` プレフィックス付き行は自動復号（`VERITAS_ENCRYPTION_KEY` 要設定） |

終了コード: `0` = 成功、`1` = 一部失敗（malformed / failed あり）、`2` = 引数エラーまたは致命的エラー

詳細は英語版 §11 を参照。

## 7. スモークテストとリリースバリデーション

- Tier 1（PR / `main` push）: ガバナンススモーク + モックプールパリティテスト
- Tier 2（`v*` タグ push）: Docker Compose による実 PostgreSQL スモーク
- Tier 3（週次 / 手動）: 長時間実行の本番的検証
- 詳細は英語版 §13 を参照

## 8. レガシーパスの整理

| パス | 状態 |
|------|------|
| ファイルベース TrustLog ヘルパー | 互換性維持（DI ストアに委譲） |
| `veritas_os/storage/migrations/` | Alembic に置き換え済み |
| 後方互換 re-export (`server.py`) | テスト依存あり、段階的削除予定 |

## 9. バックアップ / リストア / リカバリドリル

- **日次論理バックアップ**: `pg_dump -Fc` で圧縮ダンプ（`scripts/backup_postgres.sh`）
- **本番 WAL アーカイブ**: ポイントインタイムリカバリ用に継続的 WAL アーカイブ
- TrustLog は必ず `trustlog_entries` と `trustlog_chain_state` を一緒に復元すること
- **リカバリドリル**: `scripts/drill_postgres_recovery.sh` でバックアップ → リストア → 検証を一括実行
- **CI モード**: `scripts/drill_postgres_recovery.sh --ci` でエフェメラル CI 環境向けドリル
- **Makefile ターゲット**: `make drill-backup`, `make drill-restore`, `make drill-recovery`, `make drill-recovery-ci`
- 詳細は [`postgresql-drill-runbook.md`](postgresql-drill-runbook.md) を参照

## 10. レプリケーション / HA

- VERITAS OS はレプリケーション管理を行いません
- マネージド PostgreSQL（RDS、Cloud SQL 等）の利用を推奨
- TrustLog 書込みは**プライマリのみ**に向けてください（アドバイザリロック前提）
- 安全/非安全の境界は英語版 §9 および [`postgresql-drill-runbook.md` §7](postgresql-drill-runbook.md) を参照

## 11. メトリクスとオブザーバビリティ

PostgreSQL バックエンド使用時、`/v1/metrics` は以下を返します:

| フィールド | 説明 |
|-----------|------|
| `db_pool` | 接続プール利用状況（`in_use`, `available`, `waiting`, `max_size`, `min_size`） |
| `db_health` | `SELECT 1` の成否 |
| `db_activity` | `pg_stat_activity` スナップショット（`long_running`, `idle_in_tx`, `advisory_lock_wait`） |

解釈ガイド:

| 指標 | 意味 |
|------|------|
| `db_pool_in_use ≈ max_size` | プール枯渇リスク |
| `db_pool_waiting > 0` | 接続待ちが発生中 |
| `db_health_status = 0` | データベース到達不能 |
| `long_running_query_count > 0` | 長時間クエリ検出 |
| `slow_append_warning_total` 増加 | TrustLog 書込みが遅い |

テスト: `test_pg_metrics.py`（28 テスト）がメトリクス定義・収集・エンドポイント統合を検証。
詳細は英語版 §15 を参照。

## 12. コンテンション（並行競合）テスト

`test_pg_trustlog_contention.py` は **2 層構造** で advisory-lock 直列化を検証します:

**Layer 1 — モックプールテスト（25 テスト）**: `threading.Lock` でアドバイザリロックを模擬。
PR ごとに実行（Tier 1 CI）。

**Layer 2 — 実 PostgreSQL テスト（13 テスト、`@pytest.mark.postgresql @pytest.mark.contention`）**:
PostgreSQL 16 サービスコンテナを使って実際のアドバイザリロック直列化を検証。
`test-postgresql` ジョブ（Tier 1）と `postgresql-smoke` ジョブ（Tier 3）で継続実行。

実 PostgreSQL 層が検証すること:
- 2 ワーカー同時追記 → チェーン無傷（実 PG でも確認済み）
- 5/10 ワーカーバースト → ハッシュチェーン有効、重複なし
- ロックタイムアウト → fail-closed（実 PG の `statement_timeout` で検証）
- プール待機（max_size=2、8 ワーカー）→ 全追記完了
- ロールバック後の回復 → チェーン状態不変（実 PG トランザクション）
- アドバイザリロック解放（コミット・ロールバック後）→ 次の接続がブロックされない
- 20 ワーカーバースト後の全エントリチェーン検証

ローカル実行:

```bash
# 実 PostgreSQL コンテンションテスト
export VERITAS_DATABASE_URL="postgresql://user:pass@localhost:5432/veritas"
alembic upgrade head
pytest veritas_os/tests/test_pg_trustlog_contention.py \
  -m "postgresql and contention" -v
```

詳細は英語版 §13 を参照。

## 13. 既知の制限事項

| 領域 | 制限 |
|------|------|
| 検索 | トークンベースの `LIKE ANY`（ベクトル類似度検索なし） |
| リードレプリカ | アプリケーション層の読み書き分離なし |
| データインポート | `veritas-migrate` CLI は TrustLog 移行時にサービス停止（quiesce）が必要 |
| マルチデータベース | MemoryOS と TrustLog を別データベースに分割不可 |
| バックアップ暗号化 | ドリルスクリプトは暗号化なしダンプを出力（ファイルシステム暗号化で対応） |
| クロスリージョンリストア | ドリルスクリプトは同一ネットワーク前提 |

### 将来の拡張予定

- **pgvector**: MemoryOS のベクトル類似度検索
- **オンラインマイグレーション**: Write-ahead バッファリングによるサービス無停止移行
- **テーブルパーティショニング**: `trustlog_entries` の日付レンジパーティション
- **CDC**: 外部監査システムへの TrustLog ストリーミング
- **アーカイブポリシー**: 古い TrustLog エントリの自動コールドストレージ移行
- **リード/ライト分離**: リードレプリカへの読み取りクエリルーティング
- **バックアップ暗号化**: `backup_postgres.sh` に GPG/age 暗号化オプション追加
