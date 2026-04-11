# PostgreSQL Production Guide

> **Audience**: Operations / DevOps / SRE teams deploying VERITAS OS with PostgreSQL  
> **Last updated**: 2026-04-11

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
See [`docs/database-migrations.md`](database-migrations.md) for the full reference.

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

### Migration path

There is currently no automated JSONL → PostgreSQL data migration tool.
Migration requires manual ETL:

1. **Set up PostgreSQL** and run `alembic upgrade head`.
2. **Export JSONL TrustLog entries** from the file-based store.
3. **Import into PostgreSQL** using a migration script.
4. **Verify chain integrity** after import.
5. **Switch backend** environment variables.

### Key considerations

- **TrustLog chain hashes**: The chain hash (`sha256` / `sha256_prev`) is computed
  identically by both backends via `prepare_entry()`. Entries can be inserted into
  PostgreSQL in order, preserving chain integrity.
- **Memory records**: Simpler — each record is a key/value pair with user isolation.
  Export from JSON, insert into `memory_records` table.
- **Ordering matters**: TrustLog entries must be inserted in the exact original order
  to maintain `prev_hash` → `hash` chain linkage.
- **Test on staging first**: Verify the migrated data with `/v1/trustlog/verify`
  before switching production.

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

---

## 13. Known Limitations and Future Work

### Current limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Search** | Token-based `LIKE ANY` search (no vector similarity) | Lower relevance ranking vs. vector search |
| **Read replicas** | No application-level read/write splitting | All queries go to primary |
| **Data migration** | No automated JSONL ↔ PostgreSQL migration tool | Manual ETL required |
| **Connection pool metrics** | Pool stats not exposed to `/v1/metrics` | Limited observability |
| **Multi-database** | Single `VERITAS_DATABASE_URL` for all backends | Cannot split MemoryOS and TrustLog across databases |
| **Schema versioning in CI** | Mock pool in unit tests, real PG only in `test-postgresql` job | Behavioral drift possible |

### Planned future enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **pgvector** | Vector similarity search for MemoryOS (`embedding` column + HNSW/IVFFlat index) | High |
| **Table partitioning** | Range-partition `trustlog_entries` by `created_at` for archive and query performance | Medium |
| **CDC (Change Data Capture)** | Logical replication / Debezium for streaming TrustLog to external audit systems | Medium |
| **Archive policy** | Automated partitioned table detach + cold storage for aged TrustLog entries | Medium |
| **Read/write splitting** | Route read-only queries to replicas for horizontal scaling | Low |
| **Connection pool metrics** | Expose `psycopg_pool` stats via `/v1/metrics` and Prometheus | Low |
| **Automated migration tool** | CLI command: `veritas-migrate --from jsonl --to postgresql` | Low |

### Operational notes

- **Advisory lock contention**: Under very high TrustLog write rates (>1000 appends/sec),
  the advisory lock on `trustlog_chain_state` may become a bottleneck. Monitor
  `pg_stat_activity` for `pg_advisory_xact_lock` waits.
- **JSONB index maintenance**: GIN indexes on JSONB columns require periodic
  `REINDEX` or `VACUUM` to maintain performance. Schedule during maintenance windows.
- **Alembic version table**: Do not manually modify the `alembic_version` table.
  Use `alembic stamp` to correct version mismatches.

---

## 14. Three-Tier Environment Reference

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
> **最終更新**: 2026-04-11

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

## 6. バックアップ / リストア

- **日次論理バックアップ**: `pg_dump -Fc` で圧縮ダンプ
- **本番 WAL アーカイブ**: ポイントインタイムリカバリ用に継続的 WAL アーカイブ
- TrustLog は必ず `trustlog_entries` と `trustlog_chain_state` を一緒に復元すること

## 7. レプリケーション / HA

- VERITAS OS はレプリケーション管理を行いません
- マネージド PostgreSQL（RDS、Cloud SQL 等）の利用を推奨
- TrustLog 書込みは**プライマリのみ**に向けてください（アドバイザリロック前提）

## 8. 既知の制限事項

| 領域 | 制限 |
|------|------|
| 検索 | トークンベースの `LIKE ANY`（ベクトル類似度検索なし） |
| リードレプリカ | アプリケーション層の読み書き分離なし |
| データ移行 | JSONL ↔ PostgreSQL の自動移行ツールなし |

### 将来の拡張予定

- **pgvector**: MemoryOS のベクトル類似度検索
- **テーブルパーティショニング**: `trustlog_entries` の日付レンジパーティション
- **CDC**: 外部監査システムへの TrustLog ストリーミング
- **アーカイブポリシー**: 古い TrustLog エントリの自動コールドストレージ移行
