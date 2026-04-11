# TrustLog Storage Consolidation

> Date: 2026-04-11 | Status: Completed | Author: Staff Python Architect

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

### 1. Startup validation (`lifespan.py`)

`validate_backend_config()` is now called **before** store
instantiation during lifespan startup.  This catches misconfiguration
(unknown backend names, missing `VERITAS_DATABASE_URL`) at boot time
rather than at first request.

### 2. Backend-aware dependency helpers (`dependency_resolver.py`)

New helpers allow route handlers to query the active backend:

- `resolve_backend_info()` → `{"memory": "<backend>", "trustlog": "<backend>"}`
- `is_file_backend()` → `True` when TrustLog backend is `jsonl`

### 3. Backend-aware health checks (`routes_system.py`)

`_trust_log_health()` now branches on the configured backend:

- **jsonl**: checks aggregate JSON file status (existing behavior).
- **postgresql**: checks that `app.state.trust_log_store` is wired;
  skips file-based checks that are not meaningful.

The `/v1/metrics` response now includes a `storage_backends` field
reporting the active backend names, and skips file-based aggregate
JSON loading when the backend is `postgresql`.

### 4. Legacy path documentation (`server.py`)

All file-based trust-log helpers in `server.py` are annotated with
`# LEGACY COMPAT:` markers that explain:

- When these paths are active (only for `VERITAS_TRUSTLOG_BACKEND=jsonl`)
- Why they remain (test backward-compatibility, shadow snapshots)
- Migration guidance (use `app.state.trust_log_store` via DI)

## Architecture After Consolidation

```
                       ┌──────────────────────┐
                       │   lifespan.py         │
                       │  validate_backend()   │
                       │  create_*_store()     │
                       │  → app.state.*_store  │
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
├── LOG_DIR, LOG_JSON, LOG_JSONL, SHADOW_DIR     # LEGACY COMPAT
├── _effective_log_paths()                        # LEGACY COMPAT
├── _load_logs_json()                             # LEGACY COMPAT
├── append_trust_log()                            # LEGACY COMPAT
├── write_shadow_decide()                         # LEGACY COMPAT
└── _trust_log_runtime (TrustLogRuntime)          # LEGACY COMPAT
```

These remain for:
- Test monkeypatching (`server.LOG_DIR`, `server.append_trust_log`, etc.)
- Shadow snapshot writes (local file regardless of backend)
- `/v1/metrics` aggregate health (jsonl backend only)

## Backward Compatibility

| Aspect | Status |
|--------|--------|
| Public API endpoints | ✅ No change |
| `server.LOG_DIR` / `LOG_JSON` monkeypatching | ✅ Still works |
| `server.append_trust_log` monkeypatching | ✅ Still works |
| `/v1/trust/logs`, `/v1/trust/{id}` | ✅ Same response shape |
| `/v1/metrics` response | ⚠️ New `storage_backends` field added |
| `/v1/metrics` trust_json_status | ⚠️ Returns `"unknown"` for postgresql backend |

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

4. **Metrics JSONL line count** — `/v1/metrics` counts lines in the
   JSONL file.  For PostgreSQL this always returns 0.  A future
   iteration should query the store's entry count.

---

*See also: `docs/BACKEND_PARITY_COVERAGE.md`, `veritas_os/storage/base.py`*
