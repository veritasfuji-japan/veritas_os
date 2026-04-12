# Database Migrations (Alembic)

> **Last updated**: 2026-04-11
> **Applies to**: PostgreSQL backend only (file-based backends are unaffected)

---

## Overview

VERITAS OS uses [Alembic](https://alembic.sqlalchemy.org/) for PostgreSQL
schema management.  Alembic provides:

- **Reproducible schema** — the same migration runs in local dev, CI, and
  production.
- **Version tracking** — every applied migration is recorded in the
  `alembic_version` table.
- **Rollback support** — each migration includes a `downgrade()` path.

> **Note:** Alembic manages schema only.  The runtime storage backends
> (`PostgresMemoryStore`, `PostgresTrustLogStore`) continue to use
> `psycopg` directly — there is no ORM.

---

## Quick Start

```bash
# 1. Start PostgreSQL (local Docker)
docker compose up -d postgres

# 2. Set the connection URL
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas

# 3. Apply all migrations
make db-upgrade          # or: alembic upgrade head

# 4. Verify
make db-current          # shows the current revision
```

---

## Make Targets

| Target              | Description                                  |
|---------------------|----------------------------------------------|
| `make db-upgrade`   | Apply all pending migrations (`upgrade head`) |
| `make db-downgrade` | Roll back one revision (`downgrade -1`)       |
| `make db-downgrade-base` | Roll back **all** migrations (⚠️ destructive) |
| `make db-current`   | Show the currently applied revision          |
| `make db-history`   | Show full migration history                  |
| `make db-revision MSG='description'` | Create a new empty migration file |

---

## Environment Variables

| Variable              | Required | Description                               |
|-----------------------|----------|-------------------------------------------|
| `VERITAS_DATABASE_URL`| Yes      | PostgreSQL DSN (e.g. `postgresql://user:pass@host:5432/db`) |

Alembic reads `VERITAS_DATABASE_URL` at runtime — the DSN is **never**
stored in `alembic.ini`.

---

## Migration Files

Migrations live in `alembic/versions/` and follow this naming pattern:

```
<revision>_<slug>.py      e.g. 0001_initial_schema.py
```

### Current Migrations

| Revision | Description | Tables |
|----------|-------------|--------|
| `0001`   | Initial schema | `memory_records`, `trustlog_entries`, `trustlog_chain_state` |

---

## Creating a New Migration

```bash
make db-revision MSG='add_witness_columns'
# → alembic/versions/xxxx_add_witness_columns.py
```

Edit the generated file to add your `upgrade()` and `downgrade()` logic.

### Checklist for new migrations

- [ ] `upgrade()` creates or alters objects
- [ ] `downgrade()` reverses the upgrade exactly
- [ ] Tested locally: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
- [ ] No data-loss in `upgrade()` (use `ALTER TABLE … ADD COLUMN` with defaults)
- [ ] Documented in this file's "Current Migrations" table

---

## Upgrade / Downgrade Workflow

### Upgrade (normal deployment)

```bash
alembic upgrade head
```

This is safe to run repeatedly — already-applied revisions are skipped.

### Downgrade (rollback)

```bash
# Roll back the last revision
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade 0001

# Roll back ALL revisions (⚠️ drops all managed tables)
alembic downgrade base
```

### ⚠️ Downgrade Warnings

- **Downgrade is destructive** — it drops tables and data.
- **Never run `downgrade base` in production** without a verified backup.
- Downgrade is intended for:
  - Local development iteration
  - CI testing of migration reversibility
  - Emergency rollback with accepted data loss
- In production, prefer **forward-only migrations** (new migration that
  reverts logic) over `alembic downgrade`.

---

## Relationship to Legacy SQL Migrator

The repository retains the original SQL-file migrator at
`veritas_os/storage/migrations/`.  That system tracks state in the
`schema_migrations` table.

**Alembic is the recommended path going forward.**  The legacy migrator
remains for backward compatibility but new schema changes should be
authored as Alembic revisions.

If you are migrating an existing database that was set up with the legacy
migrator:

1. Verify the tables already exist.
2. Run `alembic stamp head` to mark all Alembic revisions as applied
   without executing them.
3. Future `alembic upgrade head` calls will only run new revisions.

---

## Docker Compose Integration

When using `docker compose up`, the PostgreSQL service starts first (with
a health check).  Run migrations before starting the backend:

```bash
docker compose up -d postgres
docker compose exec backend alembic upgrade head
docker compose up -d backend frontend
```

Or use the one-liner:

```bash
docker compose up -d postgres && \
  sleep 5 && \
  VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas \
  alembic upgrade head && \
  docker compose up -d
```

---

## Schema Design Principles

- **BIGSERIAL** primary keys for high-throughput writes.
- **JSONB** columns for flexible, queryable payloads.
- **TIMESTAMPTZ** for timezone-aware timestamps.
- **`metadata` JSONB** columns reserved for future signed-witness /
  provenance extensions (no DDL change needed).
- **GIN indexes** on JSONB columns for containment queries.
- **Single-row enforcement** on `trustlog_chain_state` via `CHECK (id = 1)`.

---

## Troubleshooting

### `VERITAS_DATABASE_URL is not set`

Set the environment variable before running Alembic:

```bash
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
```

### `connection refused` / `could not connect to server`

Ensure PostgreSQL is running:

```bash
docker compose up -d postgres
docker compose ps   # verify "healthy" status
```

### `relation "alembic_version" already exists`

This is normal — Alembic creates the version table on first run.

### Migrating from legacy SQL migrator

If tables already exist from the legacy migrator:

```bash
alembic stamp head   # mark current state without running DDL
```

---

# データベースマイグレーション (Alembic)

> **最終更新**: 2026-04-11
> **対象**: PostgreSQL バックエンドのみ（ファイルベースバックエンドには影響なし）

## 概要

VERITAS OS は PostgreSQL スキーマ管理に
[Alembic](https://alembic.sqlalchemy.org/) を使用します。

- **再現可能なスキーマ** — ローカル開発・CI・本番で同じマイグレーションを実行
- **バージョン追跡** — 適用済みマイグレーションは `alembic_version` テーブルに記録
- **ロールバックサポート** — 各マイグレーションに `downgrade()` パスを含む

## クイックスタート

```bash
# 1. PostgreSQL を起動
docker compose up -d postgres

# 2. 接続 URL を設定
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas

# 3. マイグレーション適用
make db-upgrade

# 4. 確認
make db-current
```

## ⚠️ Downgrade の注意事項

- **downgrade はデータを破壊します** — テーブルとデータが削除されます。
- **本番環境で `downgrade base` を実行しないでください**（バックアップ確認なしに）。
- 本番では **前方のみのマイグレーション** を推奨します。
- downgrade は以下の用途を想定:
  - ローカル開発でのイテレーション
  - CI でのマイグレーション可逆性テスト
  - データ損失を受容した緊急ロールバック
