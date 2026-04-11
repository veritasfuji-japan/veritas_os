# Legacy Path Cleanup — Storage Backend Transition

> **Document purpose**: Track which code paths are official, which are
> backward-compatibility shims, and the plan for removing them.  
> **Last updated**: 2026-04-11

---

## 1. Context

VERITAS OS migrated from direct file-based storage I/O to a
**Dependency-Injected (DI) pluggable backend** pattern.  The official
path uses `app.state.trust_log_store` and `app.state.memory_store`,
resolved at startup via `veritas_os/storage/factory.py`.

Several legacy code paths remain for backward compatibility with
existing tests and deployments.  This document tracks their status
and the plan for phased removal.

---

## 2. Path Inventory

### Official (production) paths

| Component | Location | Purpose |
|-----------|----------|---------|
| `factory.create_trust_log_store()` | `veritas_os/storage/factory.py` | Create TrustLog store from env var |
| `factory.create_memory_store()` | `veritas_os/storage/factory.py` | Create Memory store from env var |
| `app.state.trust_log_store` | Set in `veritas_os/api/lifespan.py` | DI-injected TrustLog store |
| `app.state.memory_store` | Set in `veritas_os/api/lifespan.py` | DI-injected Memory store |
| `get_trust_log_store(request)` | `veritas_os/api/dependency_resolver.py` | FastAPI dependency resolver for TrustLog |
| `get_memory_store(request)` | `veritas_os/api/dependency_resolver.py` | FastAPI dependency resolver for Memory |
| `resolve_backend_info()` | `veritas_os/api/dependency_resolver.py` | Health check backend introspection |
| `is_file_backend()` | `veritas_os/api/dependency_resolver.py` | Predicate for backend-adaptive logic |
| Alembic migrations | `alembic/versions/` | Schema management for PostgreSQL |

### Compatibility (retained for backward compat)

| Component | Location | Why it remains | Removal blocker |
|-----------|----------|----------------|-----------------|
| File-based TrustLog helpers | `server.py` lines 696–710 (`LEGACY COMPAT`) | Tests monkeypatch these functions | Test import audit needed |
| Backward-compat re-exports | `server.py` (route imports, lines 789–833) | Tests import route handlers from `server` | Test import audit needed |
| `LazyState` alias | `server.py` line 282 | Tests reference this class | Minor; can be re-exported from `dependency_resolver` |

### Superseded (should not be used for new work)

| Component | Location | Replacement | Status |
|-----------|----------|-------------|--------|
| Legacy SQL migrator | `veritas_os/storage/migrations/` | Alembic (`alembic/versions/`) | Retained for pre-existing databases; use `alembic stamp head` to transition |
| `veritas_os/storage/migrations/__main__.py` | CLI entry point | `alembic upgrade head` / `make db-upgrade` | No new usage |
| `veritas_os/storage/migrations/sql/` | DDL SQL files | Alembic migration Python files | No new DDL should be added here |

---

## 3. Cleanup Timeline

| Phase | Scope | Status | PR |
|-------|-------|--------|----|
| **Phase 1** | DI-based store injection (`app.state.trust_log_store`, `app.state.memory_store`) | ✅ Done | PR #1291 |
| **Phase 2** | Consolidate legacy TrustLog helpers to delegate to DI store | ✅ Done | PR #1292 |
| **Phase 3** | Remove backward-compat re-exports from `server.py` | 🔲 Planned | Requires: test import audit to update `from veritas_os.api.server import …` → direct module imports |
| **Phase 4** | Remove legacy SQL migrator (`veritas_os/storage/migrations/`) | 🔲 Planned | Requires: confirm all deployments have run `alembic stamp head`; update docs |
| **Phase 5** | Remove `is_file_backend()` predicate | 🔲 Future | Only after JSONL backend is deprecated (not currently planned) |

---

## 4. How to Identify Legacy Paths in Code

Legacy paths are marked with comments:

```python
# LEGACY COMPAT: ...         ← backward-compatible file-based helper
# backward compat             ← re-export for test imports
# noqa: E402,F401 -- backward compat  ← import at module level for tests
```

Search for these markers:

```bash
grep -rn "LEGACY COMPAT\|backward.compat" veritas_os/api/server.py
```

---

## 5. Migration Guide for Existing Deployments

### If you have a database created by the legacy SQL migrator

```bash
# 1. Verify the tables already exist
psql -U veritas -c "\dt" veritas

# 2. Stamp Alembic to mark current state without running DDL
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
alembic stamp head

# 3. Verify
make db-current    # Should show the latest revision
```

After stamping, all future schema changes are managed by Alembic.
The legacy migrator at `veritas_os/storage/migrations/` is no longer invoked.

### If you have no existing database

Use the official Alembic path:

```bash
export VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
make db-upgrade    # alembic upgrade head
```

---

## 6. What Should Not Be Removed

The following are **not** legacy — they are permanent parts of the architecture:

- `is_file_backend()` — needed as long as both backends are supported
- `JsonlTrustLogStore` / `JsonMemoryStore` — production backends for file-based deployments
- `factory.py` dispatch logic — core DI mechanism
- Backend env vars (`VERITAS_MEMORY_BACKEND`, `VERITAS_TRUSTLOG_BACKEND`) — user-facing config

---

# レガシーパス整理 — ストレージバックエンド移行

> **目的**: 公式パス・互換パス・削除計画の追跡  
> **最終更新**: 2026-04-11

## 公式パス

| コンポーネント | 場所 |
|-------------|------|
| `factory.create_trust_log_store()` | `veritas_os/storage/factory.py` |
| `app.state.trust_log_store` | `veritas_os/api/lifespan.py` |
| `get_trust_log_store(request)` | `veritas_os/api/dependency_resolver.py` |
| Alembic マイグレーション | `alembic/versions/` |

## 互換パス（段階的に削除予定）

| コンポーネント | 状態 | 削除条件 |
|-------------|------|---------|
| ファイルベース TrustLog ヘルパー | 維持中 | テストインポート監査完了後 |
| 後方互換 re-export | 維持中 | テストインポート監査完了後 |
| レガシー SQL マイグレータ | 置換済み | 全デプロイメントが Alembic に移行後 |

## クリーンアップ計画

| フェーズ | 状態 |
|---------|------|
| Phase 1: DI ストア注入 | ✅ 完了 |
| Phase 2: レガシーヘルパー統合 | ✅ 完了 |
| Phase 3: server.py re-export 削除 | 🔲 計画中 |
| Phase 4: レガシーマイグレータ削除 | 🔲 計画中 |
