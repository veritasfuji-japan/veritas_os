# PostgreSQL Recovery Drill Runbook

> **Audience**: SRE / DevOps / Incident Response engineers  
> **Last updated**: 2026-04-12  
> **Prerequisite**: [PostgreSQL Production Guide](postgresql-production-guide.md)

---

## 1. Overview

This runbook documents the standard procedure for PostgreSQL backup, restore,
and recovery drill execution for VERITAS OS.  The accompanying scripts
automate each step; this document explains **when**, **why**, and **how** to
run them, including manual fallback procedures.

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/backup_postgres.sh` | Logical backup via `pg_dump -Fc` |
| `scripts/restore_postgres.sh` | Restore into test or production database |
| `scripts/drill_postgres_recovery.sh` | End-to-end recovery drill |

### Drill cadence

| Environment | Cadence | Mode |
|-------------|---------|------|
| CI | Every release-gate run | `--ci` (lightweight, ephemeral) |
| Staging | Monthly | Full drill |
| Production | Quarterly | Full drill (restore to staging) |

---

## 2. Prerequisites

### Tools

- PostgreSQL client tools: `pg_dump`, `pg_restore`, `psql` (≥ 14)
- `curl` (for health check and API verification)
- `python3` (for JSON parsing in health checks)
- Bash 4+ (for associative arrays in drill report)

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PGHOST` | Yes | PostgreSQL host |
| `PGPORT` | No | Port (default: 5432) |
| `PGUSER` | Yes | Database user |
| `PGPASSWORD` | Yes | User password (or use `.pgpass`) |
| `PGDATABASE` | No | Database name (default: `veritas`) |
| `VERITAS_DATABASE_URL` | Alt. | Full DSN — parsed if `PGHOST` is unset |
| `VERITAS_API_KEY` | Opt. | For `/v1/trustlog/verify` API call |
| `VERITAS_BACKEND_URL` | Opt. | Backend URL (default: `http://localhost:8000`) |
| `VERITAS_RESTORE_TEST_DB` | Opt. | Test DB name (default: `veritas_drill_test`) |
| `VERITAS_DRILL_BACKUP_DIR` | Opt. | Backup storage (default: `backups/drill/`) |

### Access

- The drill user needs `CREATE DATABASE` privilege for test-mode restores.
- Production backups should use a read-only replica or a service account with
  `pg_read_all_data` role.

---

## 3. Backup Procedure

### Automated

```bash
# Default: backup to ./backups/
scripts/backup_postgres.sh

# Custom output directory
scripts/backup_postgres.sh --output /mnt/backup/veritas

# Data only (no DDL — useful for cross-version migrations)
scripts/backup_postgres.sh --tables-only
```

### Manual fallback

```bash
# Full compressed dump
pg_dump -Fc --no-owner --no-privileges \
  -U veritas -h db.prod -d veritas \
  > veritas_$(date -u +%Y%m%dT%H%M%SZ).dump

# Verify backup is readable
pg_restore --list veritas_*.dump
```

### What is backed up

All three VERITAS core tables:

| Table | Role | Notes |
|-------|------|-------|
| `trustlog_entries` | Append-only hash-chained audit log | **Must** be restored together with `trustlog_chain_state` |
| `trustlog_chain_state` | Singleton chain head pointer | Contains `last_hash` and `last_id` |
| `memory_records` | MemoryOS key-value store | Standard CRUD data |

Plus all Alembic migration tracking (`alembic_version`).

### Retention

- Keep **at least 3** recent backups on-site.
- Archive to off-site / object storage for regulatory retention (see
  Production Guide §8 for retention periods).
- Rotate old drill backups weekly in CI.

---

## 4. Restore Procedure

### Test restore (non-destructive)

```bash
# Restore into a temporary database
scripts/restore_postgres.sh --mode=test --verify BACKUP_FILE

# The test database is retained for inspection.
# Drop manually when done:
psql -d postgres -c "DROP DATABASE veritas_drill_test;"
```

### Production restore (destructive)

```bash
# ⚠ DESTRUCTIVE — drops and recreates objects in the target database
scripts/restore_postgres.sh --mode=clean --verify BACKUP_FILE
```

### Manual fallback

```bash
# Test restore
createdb -U veritas veritas_restore_test
pg_restore --no-owner --no-privileges -d veritas_restore_test BACKUP_FILE

# Production restore
pg_restore --clean --if-exists --no-owner --no-privileges -d veritas BACKUP_FILE
```

---

## 5. Recovery Drill

### Full drill

```bash
scripts/drill_postgres_recovery.sh
```

This executes:

1. **Pre-flight** — verifies `pg_dump`, `pg_restore`, `psql` exist and database
   is reachable.
2. **Backup** — creates a compressed dump via `backup_postgres.sh`.
3. **Restore** — restores into a test database via `restore_postgres.sh --mode=test`.
4. **Verify** —
   - Row count comparison (`trustlog_entries`, `memory_records`).
   - SQL-level chain hash consistency (no `prev_hash` breaks).
   - `trustlog_chain_state` singleton match.
   - (If `VERITAS_API_KEY` set) API `/v1/trustlog/verify` call.
5. **Health check** — `GET /health` returns `ok` or `degraded`.
6. **Cleanup** — drops the test database (unless `--keep-test-db`).
7. **Report** — structured pass/fail summary.

### CI mode

```bash
scripts/drill_postgres_recovery.sh --ci
```

Differences from full mode:
- Backup file is removed after drill.
- Intended for ephemeral CI databases (Docker Compose).
- Skips health check if backend is unreachable.

### Options

| Flag | Description |
|------|-------------|
| `--ci` | CI-safe mode (cleanup backup, tolerate missing backend) |
| `--keep-test-db` | Retain test database for post-mortem inspection |
| `--skip-health` | Skip `/health` check phase |
| `--backup-dir=DIR` | Override backup storage directory |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Drill passed |
| 1 | Pre-flight failure |
| 2 | Backup failed |
| 3 | Restore failed |
| 4 | Verification failed |
| 5 | Health check failed |

---

## 6. Post-Restore Verification Deep Dive

### SQL-level chain verification

The drill runs this query against the restored database:

```sql
WITH ordered AS (
    SELECT id, hash, prev_hash,
           LAG(hash) OVER (ORDER BY id) AS expected_prev_hash
    FROM trustlog_entries
)
SELECT COUNT(*)
FROM ordered
WHERE id > (SELECT MIN(id) FROM trustlog_entries)
  AND prev_hash IS DISTINCT FROM expected_prev_hash;
```

A result of **0** means the chain is intact.  Any non-zero value indicates a
break — likely a partial restore or data corruption.

### API-level verification

```bash
curl -H "X-API-Key: $VERITAS_API_KEY" http://localhost:8000/v1/trustlog/verify
```

This exercises the full `verify_full_ledger()` / `verify_witness_ledger()`
logic in `veritas_os/audit/trustlog_verify.py`, including:

- Chain hash validation (SHA-256 canonical JSON)
- Ed25519 signature verification (if signed ledger is active)
- Artifact linkage checks
- Mirror receipt validation

### CLI verification (standalone)

For air-gapped environments or third-party audit:

```bash
veritas-trustlog-verify \
  --full-ledger /path/to/trust_log.jsonl \
  --witness-ledger /path/to/trustlog.jsonl \
  --json
```

---

## 7. HA / Replication: Safe and Unsafe Boundaries

### Current architecture

VERITAS OS connects to **a single `VERITAS_DATABASE_URL` endpoint**.  The
application does **not** manage replication, failover, or read/write splitting.

### Single writable primary (MUST)

The TrustLog chain-hash integrity depends on **serialized writes** using
`pg_advisory_xact_lock(0x5645524954415301)`.  This advisory lock only
provides mutual exclusion on a **single PostgreSQL instance**.

> **RULE**: TrustLog `append` calls MUST target a single writable primary.

### Safe operations on read replicas

| Operation | Safe on replica? | Reason |
|-----------|-----------------|--------|
| MemoryOS `get` / `search` / `list_all` | ✅ Yes | Read-only |
| TrustLog query / export | ✅ Yes | Read-only |
| `/health` check | ✅ Yes | Read-only |
| Backup (`pg_dump`) | ✅ Yes | Read-only |
| Verification queries | ✅ Yes | Read-only |

### Unsafe operations on read replicas

| Operation | Safe on replica? | Reason |
|-----------|-----------------|--------|
| TrustLog `append` | ❌ **NO** | Advisory lock not shared across replicas; chain would fork |
| MemoryOS `put` / `delete` | ❌ **NO** | Write operations |
| MemoryOS `erase_user_data` | ❌ **NO** | Write operation |
| Alembic migrations | ❌ **NO** | DDL changes |

### What VERITAS will NOT do

- ❌ Multi-primary replication
- ❌ Automatic read/write splitting
- ❌ Routing `append` to a different endpoint than reads
- ❌ Managing Patroni / repmgr / pg_auto_failover

### What you should do (infrastructure level)

| Topology | Tool | Notes |
|----------|------|-------|
| **Managed PostgreSQL** | RDS Multi-AZ, Cloud SQL HA, Azure DB | Recommended — automatic failover, managed backups |
| **Self-hosted HA** | Patroni + etcd / pg_auto_failover | Maintain a single VIP for the primary |
| **Connection pooling** | PgBouncer (transaction mode) | Place between VERITAS and PostgreSQL |
| **Backup from replica** | `pg_dump` against standby | Reduces load on primary |

### Failover validation checklist

After a failover event (primary ↔ replica promotion):

1. Confirm new primary is writable: `psql -c "SELECT pg_is_in_recovery();"`
   — must return `f`.
2. Verify `VERITAS_DATABASE_URL` points to new primary (or VIP).
3. Run recovery drill: `scripts/drill_postgres_recovery.sh --skip-health`
4. Verify `/health` returns `ok`:
   ```bash
   curl -s http://localhost:8000/health | python3 -c "
   import json, sys; print(json.load(sys.stdin)['status'])
   "
   ```
5. Check TrustLog append works (create a test decision).
6. Confirm no chain breaks in the drill report.

---

## 8. Incident Response: Database Recovery

### Scenario: Database corruption or loss

```
1. STOP the VERITAS backend
   docker compose stop backend

2. ASSESS the damage
   psql -d veritas -c "SELECT COUNT(*) FROM trustlog_entries;"
   psql -d veritas -c "SELECT * FROM trustlog_chain_state;"

3. RESTORE from latest backup
   scripts/restore_postgres.sh --mode=clean --verify LATEST_BACKUP.dump

4. VERIFY chain integrity
   scripts/drill_postgres_recovery.sh --skip-health

5. RESTART the backend
   docker compose start backend

6. VERIFY health
   curl -s http://localhost:8000/health

7. DOCUMENT the incident
   - Time of failure
   - Backup used (filename, timestamp)
   - Chain verification result
   - Data loss window (time between last backup and failure)
```

### Scenario: Suspected TrustLog tampering

```
1. PRESERVE evidence — do NOT modify the database
   pg_dump -Fc -U veritas -d veritas > evidence_$(date +%s).dump

2. RUN full verification
   curl -H "X-API-Key: $VERITAS_API_KEY" http://localhost:8000/v1/trustlog/verify

3. RUN SQL chain check
   psql -d veritas -c "
   WITH ordered AS (
       SELECT id, hash, prev_hash,
              LAG(hash) OVER (ORDER BY id) AS expected_prev_hash
       FROM trustlog_entries
   )
   SELECT id, prev_hash, expected_prev_hash
   FROM ordered
   WHERE id > (SELECT MIN(id) FROM trustlog_entries)
     AND prev_hash IS DISTINCT FROM expected_prev_hash;
   "

4. COMPARE with off-site backup
   scripts/restore_postgres.sh --mode=test --verify evidence_*.dump

5. ESCALATE with evidence bundle
```

---

## 9. Makefile Targets

```bash
make drill-backup       # Run backup only
make drill-restore      # Run restore (test mode)
make drill-recovery     # Full recovery drill
make drill-recovery-ci  # CI-safe recovery drill
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `pg_dump: not found` | PostgreSQL client not installed | `apt install postgresql-client-16` |
| `CREATE DATABASE` fails | User lacks `CREATEDB` privilege | `ALTER USER veritas CREATEDB;` |
| Chain break after restore | Partial restore or table mismatch | Restore full backup (all tables) |
| `trustlog_chain_state` empty | Fresh database or failed migration | Run `make db-upgrade` then re-restore |
| Health check returns 500 | Backend can't connect to DB | Check `VERITAS_DATABASE_URL` |
| Advisory lock timeout | Long-running transaction holding lock | Check `pg_stat_activity` |

---

## 11. Known Limitations

1. **Logical backup only** — these scripts use `pg_dump` / `pg_restore`.  For
   PITR (point-in-time recovery) via WAL archiving, configure at the
   PostgreSQL infrastructure level.
2. **No cross-region restore** — scripts assume the restore target is on the
   same network as the backup source.
3. **No encrypted backup** — backups are not encrypted at rest by these scripts.
   Use filesystem-level or object-storage encryption.
4. **Single database** — scripts assume a single VERITAS database.  Multi-tenant
   deployments need per-tenant backup logic.
5. **Test-mode requires CREATEDB** — the drill creates a temporary database,
   which requires the PostgreSQL user to have `CREATEDB` privilege.
6. **API verification requires running backend** — SQL-level verification works
   standalone, but the `/v1/trustlog/verify` call requires the backend to be up.
