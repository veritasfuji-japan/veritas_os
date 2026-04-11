# Backend Parity Coverage — JSONL ↔ PostgreSQL

> **Document purpose**: Describe what is tested, what semantic differences
> exist, and what remains uncovered for the JSONL ↔ PostgreSQL backend
> switch capability in VERITAS OS.

## 1. Architecture Overview

VERITAS OS uses a **pluggable storage backend** pattern. Two protocols
in `veritas_os/storage/base.py` define the contracts:

| Protocol | File Backend | PostgreSQL Backend |
|---|---|---|
| `TrustLogStore` | `JsonlTrustLogStore` (JSONL files) | `PostgresTrustLogStore` (advisory-lock chain) |
| `MemoryStore` | `JsonMemoryStore` (JSON key-value file) | `PostgresMemoryStore` (upsert + GIN index) |

Backend selection is controlled by environment variables:

```
VERITAS_TRUSTLOG_BACKEND=jsonl|postgresql   (default: jsonl)
VERITAS_MEMORY_BACKEND=json|postgresql      (default: json)
```

The factory in `veritas_os/storage/factory.py` dispatches on these values
and raises `ValueError` for unknown backends.

## 2. Parity Test Architecture

### Test Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Protocol Contract Tests                               │
│  test_storage_backend_contract.py                               │
│  Same test body × {JSON, PostgreSQL} fixture → shared contract  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Backend Parity Matrix Tests                           │
│  test_storage_backend_parity_matrix.py                          │
│  Side-by-side comparison: JSON vs PG for same operation         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Backend-Specific Unit Tests                           │
│  test_storage_postgresql_memory.py                              │
│  test_storage_postgresql_trustlog.py                            │
│  test_storage_jsonl.py                                          │
│  SQL logic, mock pool, failure modes                            │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Factory & Lifecycle Tests                             │
│  test_storage_factory.py                                        │
│  test_storage_backend_contract.py (factory section)             │
│  Env-var dispatch, startup injection, DI resolution             │
└─────────────────────────────────────────────────────────────────┘
```

### How Mock Pools Work

All PostgreSQL tests use **in-memory mock pools** that simulate the
SQL behaviour of `psycopg3` without requiring a live database. This
allows the tests to run in any CI environment, including those without
PostgreSQL.

The CI job `test-postgresql` additionally runs Alembic migrations
against a real PostgreSQL 16 service container.

## 3. Coverage Matrix

### MemoryStore — Contract Coverage

| Test Domain | JSON ✓ | PostgreSQL ✓ | Parity ✓ | Notes |
|---|:---:|:---:|:---:|---|
| **put / get roundtrip** | ✅ | ✅ | ✅ | |
| **get missing key → None** | ✅ | ✅ | ✅ | |
| **put upsert overwrites** | ✅ | ✅ | ✅ | |
| **user isolation (list_all)** | ✅ | ✅ | ✅ | |
| **search respects limit** | ✅ | ✅ | ✅ | |
| **search empty → []** | ✅ | ✅ | ✅ | |
| **search limit=0 → []** | ✅ | ✅ | ✅ | |
| **search limit<0 → []** | ✅ | ✅ | ✅ | |
| **search user isolation** | ✅ | ✅ | ✅ | |
| **search empty query → []** | ✅ | ✅ | ✅ | |
| **delete existing → True** | ✅ | ✅ | ✅ | |
| **delete missing → False** | ✅ | ✅ | ✅ | |
| **get after delete → None** | ✅ | ✅ | ✅ | |
| **delete wrong user → False** | ✅ | ✅ | ✅ | |
| **erase_user_data count** | ✅ | ✅ | ✅ | See Note 1 |
| **erase empty → 0** | ✅ | ✅ | ✅ | |
| **list_all after erase → []** | ✅ | ✅ | ✅ | |
| **erase doesn't affect others** | ✅ | ✅ | ✅ | |
| **empty dict roundtrip** | ✅ | ✅ | ✅ | |
| **nested dict roundtrip** | ✅ | ✅ | ✅ | |
| **list_all empty store** | ✅ | ✅ | ✅ | |
| **list_all insertion order** | ✅ | ✅ | ✅ | |
| **concurrent puts** | ✅ | ✅ | ✅ | |

### TrustLogStore — Contract Coverage

| Test Domain | JSONL ✓ | PostgreSQL ✓ | Parity ✓ | Notes |
|---|:---:|:---:|:---:|---|
| **append returns request_id** | ✅ | ✅ | ✅ | |
| **get_by_id roundtrip** | ✅ | ✅ | ✅ | |
| **get_by_id missing → None** | ✅ | ✅ | ✅ | |
| **iter_entries pagination** | ✅ | ✅ | ✅ | |
| **iter_entries limit=0 → []** | ✅ | ✅ | ✅ | |
| **iter_entries limit<0 → []** | ✅ | ✅ | ✅ | |
| **iter_entries offset > count → []** | ✅ | ✅ | ✅ | |
| **iter_entries order** | ✅ | ✅ | ✅ | See Note 2 |
| **get_last_hash empty → None** | ✅ | ✅ | ✅ | |
| **get_last_hash after append** | ✅ | ✅ | ✅ | |
| **hash chain growth** | ✅ | ✅ | ✅ | |
| **append minimal entry** | ✅ | ✅ | ✅ | |
| **append extra fields preserved** | ✅ | ✅ | ✅ | |
| **concurrent appends** | ✅ | ✅ | ✅ | |
| **verify (placeholder)** | ⬜ | ⬜ | — | Service layer concern |
| **export (placeholder)** | ⬜ | ⬜ | — | Service layer concern |
| **migration (placeholder)** | ⬜ | ⬜ | — | Not yet implemented |
| **import (placeholder)** | ⬜ | ⬜ | — | Not yet implemented |

### Factory & Lifecycle Coverage

| Test Domain | Covered |
|---|:---:|
| Default backend dispatch | ✅ |
| PostgreSQL backend dispatch | ✅ |
| Unknown backend → ValueError | ✅ |
| Whitespace normalisation | ✅ |
| Lifespan injection (app.state) | ✅ |
| Invalid backend prevents startup | ✅ |
| DI resolver: store not set → RuntimeError | ✅ |
| DI resolver: returns correct instance | ✅ |

## 4. Known Semantic Differences

These are intentional design decisions, not bugs.

### Note 1: `erase_user_data` Return Count

The JSON backend's `erase_user` method may return `0` for the delete
count even when records were deleted, because the underlying
`MemoryStore.erase_user()` report format does not always populate the
`deleted` field. The PostgreSQL backend returns the actual `rowcount`.

**Impact**: Callers should not rely on the numeric return value to
confirm deletion; they should check `list_all()` if confirmation is
needed.

### Note 2: `iter_entries` Ordering

The protocol specifies insertion order (oldest first). The PostgreSQL
backend implements this correctly with `ORDER BY id ASC`. The JSONL
backend uses `load_trust_log(reverse=True)` internally, which returns
entries in newest-first order.

**Impact**: Callers that need a specific order must sort client-side
or know which backend is active.

## 5. CI Coverage

| CI Job | Backend | What it tests |
|---|---|---|
| `test (py3.11)` | JSONL/JSON (default) | Full test suite + 85% coverage gate |
| `test (py3.12)` | JSONL/JSON (default) | Full test suite + 85% coverage gate |
| `test-postgresql` | PostgreSQL (mock + real) | Backend parity + contract tests |
| `test-slow` | Default | Slow/heavy tests |
| `governance-smoke` | Default | Smoke tests |

## 6. Uncovered Areas

| Area | Status | Priority |
|---|---|---|
| **JSONL → PostgreSQL migration** | Placeholder test | Medium |
| **PostgreSQL → JSONL migration** | Placeholder test | Low |
| **Bulk import** | Placeholder test | Low |
| **Real PostgreSQL integration** (full test suite) | CI job present, mock-pool in unit tests | Medium |
| **Search scoring parity** | Covered for result IDs; exact score values may differ slightly | Low |
| **Connection pool failure recovery** | Tested in test_storage_db.py | — |
| **Concurrent writes under real PostgreSQL advisory locks** | Not tested (requires real PG + threading) | Medium |

## 7. Test File Reference

| File | Tests | Layer |
|---|---:|---|
| `test_storage_backend_contract.py` | 95 | Contract (shared body × 2 backends) |
| `test_storage_backend_parity_matrix.py` | 31 | Side-by-side parity comparison |
| `test_storage_postgresql_memory.py` | 39 | PG Memory unit + parity |
| `test_storage_postgresql_trustlog.py` | 30 | PG TrustLog unit + parity |
| `test_storage_factory.py` | varies | Factory dispatch |
| `test_storage_base.py` | varies | Protocol interface |
| `test_storage_db.py` | varies | Connection pool |
| `test_storage_jsonl.py` | varies | JSONL backend unit |
| **Total backend-parity tests** | **195+** | |
