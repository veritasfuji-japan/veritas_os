# TrustLog Storage Consolidation

> Date: 2026-04-11 | Status: Completed (Phase 2) | Author: Staff Python Architect

## Summary

This document describes the consolidation of TrustLog storage paths
in the VERITAS OS API layer, reducing split-brain risk between the
legacy file-based helpers in `server.py` and the backend-aware
`app.state.trust_log_store` / `app.state.memory_store` DI mechanism.

## Problem

Prior to this consolidation, two independent code paths could serve
TrustLog reads and writes:

1. **Legacy file-based path** — `server.py` helpers (`append_trust_log`,
   `_load_logs_json`, `write_shadow_decide`) that operate directly on
   `LOG_DIR / trust_log.jsonl` and `trust_log.json`.
2. **DI store path** — `app.state.trust_log_store` (a `TrustLogStore`
   protocol implementation) created by `storage/factory.py` and wired
   during lifespan startup.

When `VERITAS_TRUSTLOG_BACKEND=postgresql`, the DI store persists to
PostgreSQL, but route handlers and health checks still consulted the
file-based aggregate JSON — a **split-brain** situation where reads
could return stale or empty data.

## Changes Made

### Phase 1 (Initial)

1. **Startup validation** — `validate_backend_config()` called before
   store instantiation in `lifespan.py`.
2. **Backend-aware helpers** — `resolve_backend_info()`, `is_file_backend()`
   in `dependency_resolver.py`.
3. **Backend-aware health** — `_trust_log_health()` branches by backend.
4. **LEGACY COMPAT markers** — Initial documentation of file-based helpers.

### Phase 2 (This PR)

1. **Metrics JSONL line count guard** — `/v1/metrics` now skips JSONL file
   reading when `backend=postgresql`, returning `0` instead of reading a
   stale file that is not the persistence source of truth.

2. **Enhanced LEGACY COMPAT documentation** — All file-based trust-log
   helpers in `server.py`, `trust_log_runtime.py`, and `trust_log_io.py`
   now have detailed docstrings and comments that specify:
   - When the path is active (only `backend=jsonl`)
   - Why it remains (test backward-compat, shadow snapshots)
   - That it is NOT the persistence source of truth for `backend=postgresql`
   - Migration guidance (use `app.state.trust_log_store` via DI)

3. **Source-of-truth boundary tests** — New test class
   `TestSourceOfTruthBoundary` validates that:
   - `app.state.trust_log_store` is the canonical source of truth
   - Legacy helpers are walled off from postgresql persistence
   - Backend switching preserves API semantics
   - Shadow snapshots remain file-based regardless of backend

## Architecture After Consolidation

```
                       ┌──────────────────────┐
                       │   lifespan.py         │
                       │  validate_backend()   │
                       │  create_*_store()     │
                       │  → app.state.*_store  │  ← SOURCE OF TRUTH
                       └──────┬───────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐  ┌────▼──────┐  ┌─────▼──────────┐
    │ JsonlTrustLog  │  │ Postgres  │  │ JsonMemory     │
    │ Store          │  │ TrustLog  │  │ Store /        │
    │ (file-based)   │  │ Store     │  │ PostgresMemory │
    └────────────────┘  └───────────┘  └────────────────┘

Source of truth: app.state.trust_log_store (set once in lifespan)
DI resolver:     dependency_resolver.get_trust_log_store(request)
```

### Legacy Compatibility Layer (jsonl only)

```
server.py
├── LOG_DIR, LOG_JSON, LOG_JSONL, SHADOW_DIR     # LEGACY COMPAT — not SoT for postgresql
├── _effective_log_paths()                        # LEGACY COMPAT — path resolution
├── _load_logs_json()                             # LEGACY COMPAT — file read (jsonl only)
├── append_trust_log()                            # LEGACY COMPAT — file write (jsonl only)
├── write_shadow_decide()                         # LEGACY COMPAT — shadow snapshots (always file)
└── _trust_log_runtime (TrustLogRuntime)          # LEGACY COMPAT — runtime helpers
```

These remain for:
- **Test monkeypatching** — `server.LOG_DIR`, `server.append_trust_log`, etc.
- **Shadow snapshot writes** — local file regardless of backend (replay/audit)
- **Metrics aggregate health** — jsonl backend only; skipped for postgresql

### Split-Brain Risk Reduction

| Risk Area | Before | After |
|-----------|--------|-------|
| `/v1/metrics` JSONL line count | Reads file even for postgresql | Guarded: returns 0 for postgresql |
| `/v1/metrics` trust_json_status | Reads file even for postgresql | Already guarded (Phase 1) |
| Health check | Could report stale file status | Backend-aware (Phase 1) |
| Legacy helper scope | Unclear when active | Documented per-function with backend scope |
| Source of truth | Ambiguous | Explicitly `app.state.trust_log_store` |

## Backward Compatibility

| Aspect | Status |
|--------|--------|
| Public API endpoints | ✅ No change |
| `server.LOG_DIR` / `LOG_JSON` monkeypatching | ✅ Still works |
| `server.append_trust_log` monkeypatching | ✅ Still works |
| `/v1/trust/logs`, `/v1/trust/{id}` | ✅ Same response shape |
| `/v1/metrics` response | ⚠️ `storage_backends` field present |
| `/v1/metrics` trust_json_status | ⚠️ Returns `"unknown"` for postgresql backend |
| `/v1/metrics` trust_jsonl_lines | ⚠️ Returns `0` for postgresql backend (was stale) |

## Remaining Technical Debt

1. **Routes still use `srv.get_trust_log_page()` / `srv.get_trust_logs_by_request()`**
   — These are file-based functions imported from `veritas_os.logging.trust_log`.
   A future iteration should route through `app.state.trust_log_store.iter_entries()`
   so that PostgreSQL backends serve reads directly from the database.

2. **Shadow snapshots always write to local files** — Even with
   `backend=postgresql`, shadow `decide_*.json` files are written to
   `SHADOW_DIR`.  This is acceptable for now (replay support), but
   should eventually be unified.

3. **`trust_log_runtime` in server.py** — The `TrustLogRuntime` wrapper
   remains as a convenience for tests and the jsonl code path.  When
   all consumers migrate to the DI store, this can be removed.

4. **Metrics JSONL line count** — For PostgreSQL this now correctly returns
   0.  A future iteration should query the store's entry count instead.

---

*See also: `docs/BACKEND_PARITY_COVERAGE.md`, `veritas_os/storage/base.py`*
