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
| **import (CLI)** | — | ✅ | — | `veritas-migrate trustlog` — idempotent, chain-preserving (reads JSONL source → writes to PG) |
| **import dry-run** | — | ✅ | — | `veritas-migrate trustlog --dry-run` — read-only validation |
| **import verify** | — | ✅ | — | `veritas-migrate trustlog --verify` — post-import chain check |

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
| `test (py3.11)` | JSONL/JSON (default) | Full test suite + 85% coverage gate (includes PG-focused tests with mock pool) |
| `test (py3.12)` | JSONL/JSON (default) | Full test suite + 85% coverage gate (includes PG-focused tests with mock pool) |
| `test-postgresql` | PostgreSQL (mock + real) | Backend parity + contract + contention tests |
| `test-slow` | Default | Slow/heavy tests |
| `governance-smoke` | Default | Smoke tests (Tier 1) |
| `docker-smoke` | PostgreSQL (via compose) | Full-stack health + read/write with real PG (Tier 2/3) |
| `production-tests` | Default | `pytest -m "production or smoke"` (Tier 2) |
| `postgresql-smoke` | Real PostgreSQL (service container) | Backend parity + health endpoint verification (Tier 3) |

### Smoke / Release Validation Path

Smoke tests (`@pytest.mark.smoke`) verify that the active backend —
whichever it is — satisfies governance invariants. In Docker Compose
(which defaults to PostgreSQL), the `docker-smoke` job validates:

1. Schema migrations apply cleanly (`VERITAS_DB_AUTO_MIGRATE=true`)
2. `/health` returns `storage_backends: {memory: postgresql, trustlog: postgresql}`
3. Basic API operations succeed against a real PostgreSQL 16 instance
4. Memory write/read operations succeed against real PostgreSQL
5. TrustLog read path is exercised against real PostgreSQL

The `postgresql-smoke` job (Tier 3) additionally verifies that
`get_backend_info()` reports `postgresql` for both backends, catching
silent fallback to file stores.

The `veritas-migrate` CLI includes a `--verify` flag that runs a
post-import hash-chain integrity check against the PostgreSQL backend.
This serves as the import-specific validation step, complementing the
API-level `/v1/trustlog/verify` endpoint.

See [`docs/PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md) for the
complete three-tier validation model and
[`docs/postgresql-production-guide.md`](postgresql-production-guide.md) §13
for PostgreSQL-specific validation guidance.

## 6. Uncovered Areas

| Area | Status | Priority |
|---|---|---|
| **PostgreSQL → JSONL export** | No tooling; manual SQL export + reformat | Low |
| **Real PostgreSQL integration** (full test suite) | CI job `test-postgresql` + `docker-smoke` + `postgresql-smoke` with real PG 16; mock-pool in unit tests | Medium |
| **Search scoring parity** | Covered for result IDs; exact score values may differ slightly (LIKE ANY vs. file scan) | Low |
| **Connection pool failure recovery** | Tested in `test_storage_db.py` + `test_pg_trustlog_contention.py` (pool starvation fail-closed) | ✅ Covered |
| **Concurrent writes under real PostgreSQL advisory locks** | Mock-pool contention (25 tests) + CI `test-postgresql` job against real PG | Medium — real PG timing not tested |
| **Pool/activity metrics** | Tested in `test_pg_metrics.py` (28 tests); `/v1/metrics` integration covered | ✅ Covered |
| **Backup/restore/drill scripts** | Tested in `test_drill_postgres_recovery.py` (31 tests); script syntax + content coherence | ✅ Covered (no live `pg_dump`) |

### What is parity-guaranteed

The following semantics are **guaranteed identical** across JSONL/JSON and
PostgreSQL backends based on the 195+ parity test suite:

- CRUD operations (put/get/delete/upsert) for MemoryStore
- Append/retrieve/iterate operations for TrustLogStore
- User isolation (MemoryStore)
- Hash-chain integrity (TrustLogStore)
- Error handling (missing keys, empty queries, negative limits)
- Concurrent operation correctness (at mock-pool level)
- Factory dispatch and fail-fast validation

### What is covered by the import CLI

The `veritas-migrate` CLI provides the following guarantees for
file-to-PostgreSQL data migration:

- **Idempotent import** — re-running produces the same final state;
  duplicates are skipped, not errors
- **Chain-preserving** — `sha256` / `sha256_prev` stored verbatim;
  hash chain is never recomputed
- **Dry-run validation** — `--dry-run` flag validates source files
  without writing to PostgreSQL
- **Post-import verification** — `--verify` flag runs hash-chain
  integrity check against PostgreSQL after import
- **Encrypted source support** — `ENC:` prefixed JSONL lines are
  automatically decrypted during import

### What is NOT parity-guaranteed

| Area | Reason |
|------|--------|
| `erase_user_data` return count | JSON returns 0; PostgreSQL returns actual `rowcount` (Note 1) |
| `iter_entries` default ordering | JSONL uses `reverse=True` internally (Note 2); PostgreSQL uses `ORDER BY id ASC` |
| Search relevance scoring | Token-based `LIKE ANY` (PostgreSQL) vs. file-scan match (JSON) |
| Advisory lock contention behaviour | Mock pool simulates locks; real PostgreSQL may show different timing |
| Export from PostgreSQL to file backends | No automated tooling; manual SQL export + reformat |

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
| `test_pg_trustlog_contention.py` | 25 | Advisory lock contention + concurrency |
| `test_pg_metrics.py` | 28 | Pool/activity metrics + `/v1/metrics` integration |
| `test_drill_postgres_recovery.py` | 31 | Drill script validation + runbook coherence |
| **Total backend + hardening tests** | **279+** | |

## 8. Contention, Metrics, and Recovery Coverage

### Advisory Lock Contention Tests (`test_pg_trustlog_contention.py`)

These tests exercise TrustLog `append()` under concurrent-access patterns
using an enhanced mock pool that simulates `pg_advisory_xact_lock` via
`threading.Lock`.

| Test Domain | Tests | Covered |
|---|---:|:---:|
| **2-worker simultaneous append** | 2 | ✅ |
| **N-worker burst (5/10/20)** | 4 | ✅ |
| **Statement timeout → fail-closed** | 3 | ✅ |
| **Connection pool starvation → fail-closed** | 2 | ✅ |
| **Rollback recovery (chain intact after failure)** | 2 | ✅ |
| **Advisory lock release (commit + rollback)** | 3 | ✅ |
| **Full chain verification after concurrent writes** | 4 | ✅ |
| **Mixed success/failure contention** | 2 | ✅ |
| **Threaded contention (OS threads)** | 2 | ✅ |
| **Missing encryption key → fail-closed** | 1 | ✅ |
| **Total** | **25** (mock pool, Tier 1 CI) | |

### PostgreSQL Metrics Tests (`test_pg_metrics.py`)

| Test Domain | Tests | Covered |
|---|---:|:---:|
| **Metric definitions (gauges, counters, histograms)** | 4 | ✅ |
| **Recording helpers (pool stats, failures, latency)** | 7 | ✅ |
| **Pool-stats collection (mock pool)** | 3 | ✅ |
| **pg_stat_activity collection** | 3 | ✅ |
| **Health-check gauge emission** | 2 | ✅ |
| **Backend label emission** | 1 | ✅ |
| **High-level collector (file + PG backend)** | 2 | ✅ |
| **`/v1/metrics` endpoint integration** | 3 | ✅ |
| **DB unavailable → safe defaults** | 1 | ✅ |
| **Metric name stability across releases** | 1 | ✅ |
| **Health/metrics backend consistency** | 1 | ✅ |
| **Total** | **28** (mock pool + TestClient, Tier 1 CI) | |

### Recovery Drill Tests (`test_drill_postgres_recovery.py`)

| Test Domain | Tests | Covered |
|---|---:|:---:|
| **Script existence** | 3 | ✅ |
| **Script is executable** | 3 | ✅ |
| **Script has shebang** | 3 | ✅ |
| **Bash syntax valid (`bash -n`)** | 3 | ✅ |
| **`--help` flag exits 0** | 3 | ✅ |
| **Content coherence (tools + flags)** | 6 | ✅ |
| **Runbook coherence (docs ↔ scripts)** | 7 | ✅ |
| **Total** | **31** (no live DB required, Tier 1 CI) | |

### What these tests guarantee

- TrustLog hash chain remains valid after N concurrent appending workers.
- Statement timeout or pool starvation → `RuntimeError` (fail-closed).
- Advisory lock is released on both successful commit and rollback.
- `/v1/metrics` always returns `db_pool`, `db_health`, `db_activity` fields.
- File-backend mode degrades gracefully (null pool, true health).
- Drill scripts are syntactically valid and reference the correct
  PostgreSQL tools and VERITAS tables.
- `postgresql-drill-runbook.md` references all scripts, documents HA
  boundaries, and describes exit codes.

### What these tests do NOT guarantee

| Area | Reason |
|------|--------|
| Real PostgreSQL lock timing under CPU/IO saturation | Mock pool uses zero-delay `threading.Lock` |
| Actual `pg_dump` / `pg_restore` execution | Tests validate syntax and flags, not runtime output |
| WAL archiving / PITR restore | Infrastructure-level concern |
| Cross-version `pg_dump` compatibility | CI uses PostgreSQL 16 only |
| Prometheus scrape correctness | Tests use `_NoOpMetric` / probe stubs, not real `prometheus_client` |
