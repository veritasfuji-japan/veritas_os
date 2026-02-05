# VERITAS OS - Comprehensive Code Review Report

**Date**: 2026-02-05 (Updated)
**Reviewer**: Claude (Automated Code Review)
**Scope**: All source files in `veritas_os/`

---

## Executive Summary

VERITAS OS is a Python-based AI decision-making framework with ethical guardrails. The codebase implements a multi-stage pipeline (evidence gathering, critique, debate, FUJI validation, telos scoring) with memory persistence, trust logging, and a FastAPI REST API.

**Overall Assessment**: The codebase is functional with thoughtful safety/ethical design. However, there are several HIGH-severity issues (security, data integrity, architectural) and many MEDIUM-severity code quality issues that should be addressed.

### Severity Counts (Updated)

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 12    |
| MEDIUM   | 18    |
| LOW      | 9     |

---

## CRITICAL Severity Findings (NEW)

### C-1: Race Condition in dataset_writer.py - Concurrent Appends Can Corrupt Data
**File:** `veritas_os/logging/dataset_writer.py:218-237`

**Problem:** The `append_dataset_record` function has NO thread synchronization, fsync, or atomic write guarantees. In a multi-threaded environment (FastAPI), concurrent calls to this function can:
1. Interleave writes, corrupting the JSONL file
2. Lose data on crash (no fsync)
3. Create race conditions in file access

**Evidence:**
```python
# Line 233 - No lock acquired
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")  # No fsync
```

Unlike `trust_log.py` which has `with _trust_log_lock:`, this module has zero protection.

**Fix**: Add a module-level `threading.RLock()` and use `atomic_append_line` from `veritas_os.core.atomic_io`.

### C-2: Missing fsync in atomic_write_npz Causes Data Corruption Risk
**File:** `veritas_os/core/atomic_io.py:181`

**Problem:** The `atomic_write_npz()` function calls `np.savez()` without fsync before the atomic rename. If the system crashes after `np.savez()` completes but before OS buffers are flushed to disk, the temporary file may be incompletely written. The subsequent `os.replace()` then renames this corrupt file to the target path, permanently corrupting the vector index.

**Evidence:**
- Line 181: `np.savez(tmp_path, **arrays)` - no fsync after this
- Line 184: `os.replace(tmp_path, path)` - renames potentially incomplete file
- Compare with `_atomic_write_bytes()` (line 67) which properly calls `os.fsync(fd)`

**Fix:** After `np.savez()`, reopen the file in read mode and fsync it before the rename.

### C-3: Missing FastAPI Request Body Size Limit - Denial of Service Vulnerability
**File:** `veritas_os/api/server.py:391`
**Date Added:** 2026-02-05

**Problem:** The FastAPI application is initialized without any request body size limits. This allows an attacker to send extremely large payloads (potentially gigabytes) that will:
1. Consume all server memory causing Out-Of-Memory crashes
2. Block legitimate requests during the slow processing
3. Exhaust disk space if payloads are temporarily cached
4. Bypass application-level MAX_QUERY_LENGTH checks which only validate after parsing

**Evidence:**
```python
# Line 391
app = FastAPI(title="VERITAS Public API", version="1.0.3")
```

No `max_body_size` or similar parameter is configured. While Pydantic schemas define `MAX_QUERY_LENGTH = 10000`, this validation only occurs AFTER FastAPI has already parsed the potentially multi-gigabyte JSON payload into memory.

**Attack Scenario:**
```bash
# Attacker sends 1GB payload
curl -X POST http://api/v1/decide \
  -H "X-API-Key: valid-key" \
  -d "$(python3 -c 'print(\"{\\\"query\\\": \\\"\" + \"A\"*1000000000 + \"\\\"}\")')"
```

This bypasses rate limiting (which counts requests, not bytes) and crashes the server before Pydantic validation runs.

**Fix:** Add middleware to enforce body size limits:

```python
MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10MB

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Request body too large")
    return await call_next(request)
```

Or configure uvicorn startup with explicit limits:
```bash
uvicorn veritas_os.api.server:app \
    --limit-max-requests 1000 \
    --limit-request-line 8190 \
    --limit-request-fields 100
```

---

## HIGH Severity Findings

### H-1: `builtins.MEM` global namespace pollution (`core/memory.py:1354`)

```python
import builtins
builtins.MEM = MEM
```

**Issue**: Setting `MEM` on the `builtins` module pollutes the global namespace for the entire Python process. This makes testing difficult, can cause name collisions with other libraries, and creates an implicit coupling that is invisible at import time.

**Fix**: Remove the `builtins.MEM` assignment. Modules that need `MEM` should explicitly import it from `veritas_os.core.memory`.

### H-2: Non-atomic file write in `value_core.py:129`

```python
def save(self) -> None:
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"weights": _normalize_weights(self.weights)}
    with CFG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

**Issue**: Uses plain `open("w")` instead of the project's own `atomic_write_json()`. A crash or power failure during write will corrupt the file, losing the learned value weights permanently.

**Fix**: Use `atomic_write_json(CFG_PATH, data, indent=2)` from `veritas_os.core.atomic_io`.

### H-3: Duplicate `append_trust_log` function (`value_core.py:344`)

**Issue**: `value_core.py` defines its own `append_trust_log()` function that writes to `TRUST_LOG_PATH` with a completely different schema than `logging/trust_log.py`'s `append_trust_log()`. The value_core version:
- Uses `fcntl` file locking instead of threading RLock
- Writes a different schema (user_id, score, note) vs the trust_log version (sha256 hash chain)
- Does not participate in the hash chain integrity verification

This creates confusion and potential data integrity issues. The JSONL file could contain mixed schemas that break `verify_trust_log()`.

**Fix**: Remove the duplicate function from `value_core.py` and use the canonical `logging/trust_log.py` implementation.

### H-4: Module-level heavy side effects in `core/memory.py`

**Issue**: Importing `veritas_os.core.memory` triggers:
- Model loading (`SentenceTransformer`, `joblib_load`)
- Directory creation (`mkdir`)
- File I/O (loading vector indexes, memory.json)
- Setting `builtins.MEM`
- Initializing `MEM_VEC` global

This means any module that imports `memory` (even for type checking or testing) triggers these side effects. If any step fails, the import crashes.

**Fix**: Move initialization to a `init()` or `get_instance()` factory function. Use lazy initialization patterns consistent with `server.py`'s `_LazyState` approach.

### H-5: Trust log hash chain inconsistency risk (`logging/trust_log.py:178`)

```python
items = _load_logs_json()  # reads from trust_log.json
sha256_prev = items[-1].get("sha256") if items else None
```

**Issue**: `append_trust_log()` reads `sha256_prev` from `trust_log.json` (the JSON file limited to `MAX_JSON_ITEMS=2000`) but the hash chain is stored in `trust_log.jsonl` (JSONL file, unlimited). If the JSONL has more than 2000 entries and the JSON was trimmed, the `sha256_prev` read from JSON may not match the actual last entry in JSONL.

`get_last_hash()` (which reads from JSONL) exists but is not used in `append_trust_log()`.

**Fix**: Use `get_last_hash()` to read the previous hash from JSONL instead of from the JSON file:

```python
sha256_prev = get_last_hash()
```

### H-6: `strategy.py` wrong import fallback (`core/strategy.py:15`)

```python
except ImportError:
    from veritas.core import world_model as wm  # type: ignore
    from veritas.core import value_core          # type: ignore
```

**Issue**: The fallback import uses `veritas.core` which is the wrong package name (should be `veritas_os.core`). This code path will always fail silently.

**Fix**: Either remove the fallback entirely (the primary import should always work within the package), or fix the package name to `veritas_os.core`.

### H-7: `rotate.py` - `open_trust_log_for_append()` not a proper context manager

```python
def open_trust_log_for_append() -> TextIO:
    trust_log = rotate_if_needed()
    trust_log.parent.mkdir(parents=True, exist_ok=True)
    return open(trust_log, "a", encoding="utf-8")
```

**Issue**: This returns a raw file handle but is used with `with` in `trust_log.py:209`:
```python
with open_trust_log_for_append() as f:
```

While this technically works because Python file objects are context managers, the function signature and documentation don't make this explicit. More critically, `rotate_if_needed()` and the `open()` call are **not atomic** - another thread could rotate the file between these two calls, causing the write to go to a new empty file while the hash chain references the rotated file.

**Fix**: Make the rotation + open atomic within `_trust_log_lock`, or use `@contextmanager` to make the intent explicit.

### H-8: Pickle deserialization still permitted (`core/memory.py:134-257`)

**Issue**: Despite extensive mitigation (RestrictedUnpickler, deprecation warnings, data validation), pickle deserialization is still permitted when `VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION=1`. The `_find_class` method still allows `_reconstruct` with just a warning (line 182-206). Pickle deserialization is inherently unsafe and the restricted unpickler can be bypassed.

**Fix**: Set a hard deadline for removing pickle support entirely. Consider requiring manual data export/import instead.

---

## MEDIUM Severity Findings

### M-1: `atomic_io.py` - No directory fsync after rename

After `os.replace()`, the directory metadata is not fsynced. On ext4 with `data=ordered` (default), a crash after `os.replace()` but before the next journal checkpoint could lose the rename.

**Fix**: Add `os.fsync(os.open(str(path.parent), os.O_RDONLY))` after `os.replace()`.

### M-2: `paths.py` - Side effects at import time (line 71-83)

`LOG_ROOT.mkdir()`, `DASH_DIR.mkdir()`, and `_ensure_secure_permissions()` are called at module import time. This can fail in test environments or when running in read-only containers.

### M-3: `memory/store.py` - Hardcoded `BASE_DIR` via `parents[2]` (line 9)

```python
BASE_DIR = Path(__file__).resolve().parents[2]
```

This hardcodes the assumption about directory nesting depth. If the file is moved, this silently points to the wrong directory.

### M-4: `planner.py` - Brute-force JSON extraction (lines 455-530)

The `_extract_step_objects()` function implements a manual character-by-character JSON parser. This is fragile, hard to maintain, and could have edge cases with escaped characters in strings.

**Fix**: Consider using `json.JSONDecoder().raw_decode()` which handles partial JSON extraction.

### M-5: `server.py` - Lazy state initialization race conditions

The lazy initialization pattern (e.g., `get_cfg()`, `get_decision_pipeline()`) uses module-level try/except blocks that could have race conditions during concurrent first-access in FastAPI's async environment. Although Python's GIL provides some protection, the pattern is not guaranteed safe.

### M-6: `value_core.py:372-380` - Non-atomic trust log append

```python
with log_file.open("a", encoding="utf-8") as f:
    if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
    finally:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

Uses `fcntl` file locking (POSIX only) instead of the project's `atomic_append_line()` which uses `os.fsync()`. On Windows, there's no locking at all.

### M-7: `schemas.py` - Very complex coercion logic

The Pydantic model validators do extensive type coercion (string-to-float, list-wrapping, None-to-default). While robust for external API input, this can mask bugs in internal callers where type mismatches should be caught early.

### M-8: `trust_log.py` - `_sha256()` and `_compute_sha256()` and `calc_sha256()` redundancy

Three separate functions compute SHA-256 hashes with slightly different semantics:
- `_sha256()` - takes any data, converts to string
- `_compute_sha256()` - takes dict, JSON-encodes with sort_keys
- `calc_sha256()` - takes dict, JSON-encodes with sort_keys

This creates confusion about which to use. `_compute_sha256()` has a bare `except Exception` fallback to `repr()` which could produce inconsistent hashes.

### M-9: `reason.py` - Hardcoded log path (line 22-23)

```python
LOG_DIR = SCRIPTS_DIR / "logs"
```

Uses a hardcoded path relative to the file location instead of the centralized `logging/paths.py` configuration. This means reason logs go to a different directory than trust logs.

### M-10: `memory.py` - `predict_gate_label()` returns hardcoded 0.5

When no model is available (the common case without joblib/sklearn), `predict_gate_label()` always returns `{"allow": 0.5}`. This is a no-op that adds complexity without value.

### M-11: `critique.py` - Mutable default in `_crit()` pattern

```python
def _crit(..., details: Optional[Dict[str, Any]] = None, ...) -> Dict[str, Any]:
    return {"details": details or {}, ...}
```

While `details or {}` protects against the mutable default argument pitfall, the pattern is repeated many times. A frozen dataclass would be cleaner.

### M-12: `self_healing.py` - Budget tracking not persisted

`HealingBudget` and `HealingState` are in-memory only. If the server restarts, the retry budget resets, potentially allowing more retries than intended for a long-running task.

---

## LOW Severity Findings

### L-1: Inconsistent timestamp formats across modules

- `trust_log.py`: `datetime.now(timezone.utc).isoformat()`
- `value_core.py`: `time.strftime("%Y-%m-%d %H:%M:%S")` (no timezone)
- `reason.py`: `time.strftime("%Y-%m-%d %H:%M:%S")` (no timezone)
- `time_utils.py`: Provides `utc_now_iso_z()` but it's not used consistently

### L-2: `evolver.py` uses `print()` for logging instead of `logging` module

Lines 27, 55: Uses `print("[persona]...")` instead of `logger.warning()`/`logger.error()`.

### L-3: `rsi.py` - Stub implementation

`propose_patch()` always returns the same delta (`+1` min_evidence, `+0.1` critique_weight) regardless of input. This is documented as a sample but should be flagged.

### L-4: `reflection.py` - References non-existent `adjust_weights` method

```python
value_core.adjust_weights("prudence", +0.1)
```

`value_core` module doesn't have an `adjust_weights` function. This call always falls through to the `except Exception: pass` block silently.

### L-5: Various `bare except` patterns

Multiple files use `except Exception:` with `pass` or `continue`, silently swallowing errors. While this provides resilience, it makes debugging difficult. Consider logging at DEBUG level.

### L-6: `memory/store.py` and `core/memory.py` name collision

Both files define a class named `MemoryStore` with different APIs. This creates confusion about which one is being used in any given context.

### L-7: Unused imports and dead code

- `trust_log.py`: `_compute_sha256()` is defined but never called (the hash computation is done inline in `append_trust_log()`)
- `trust_log.py`: `_normalize_entry_for_hash()` duplicates the inline logic in `append_trust_log()`

---

## NEW HIGH Severity Findings (Added 2026-02-05)

### H-9: TOCTOU Race Condition in Policy Hot Reload
**File:** `veritas_os/core/fuji.py:461-477`

**Problem:** The `_check_policy_hot_reload()` function has a classic Time-of-Check-Time-of-Use (TOCTOU) race condition. The code checks the file modification time, then loads the policy. Between these two operations, an attacker could replace the policy file with malicious content.

```python
def _check_policy_hot_reload() -> None:
    global POLICY, _POLICY_MTIME
    path = _policy_path()
    current_mtime = path.stat().st_mtime  # TIME-OF-CHECK
    if current_mtime > _POLICY_MTIME:
        POLICY = _load_policy(path)       # TIME-OF-USE
```

**Fix**: Use file descriptors to eliminate the race condition.

### H-10: Race Condition in Global MEM_VEC Access
**File:** `veritas_os/core/memory.py:1199, 1382, 1924`

**Problem:** The global `MEM_VEC` variable is accessed and modified without proper synchronization across multiple functions. While `MemoryStore` has `_cache_lock` for its internal cache, the global `MEM_VEC` can be accessed from multiple threads without protection.

**Fix:** Add a global lock for `MEM_VEC` operations similar to `_trust_log_lock`.

### H-11: Race Condition in rotate.py - TOCTOU Between rotate_if_needed and open
**File:** `veritas_os/logging/rotate.py:45-60`

**Problem:** There's a Time-Of-Check-Time-Of-Use (TOCTOU) race condition between `rotate_if_needed()` returning a path and `open()` being called. Another thread could rotate the file between these two calls.

**Fix:** Move the lock into `rotate.py` or make `open_trust_log_for_append` do rotation and open atomically.

### H-12: Missing get_last_hash Thread Safety When Called Externally
**File:** `veritas_os/logging/trust_log.py:82-105, 467`

**Problem:** `get_last_hash()` is exported in `__all__` but has no internal locking. External callers could call it without the lock, leading to:
1. Reading partial/incomplete JSON lines if another thread is writing
2. `json.loads()` exception → returns None → caller thinks log is empty → breaks hash chain

**Fix**: Either remove from `__all__`, add lock acquisition inside the function, or document that callers MUST hold `_trust_log_lock`.

---

## NEW MEDIUM Severity Findings (Added 2026-02-05)

### M-13: Internal Error Details Exposed in /status Endpoint
**File:** `veritas_os/api/server.py:847-858`

**Problem:** The `/status` endpoint exposes internal error messages through `cfg_error` and `pipeline_error` fields, which can reveal sensitive implementation details to unauthenticated users.

**Fix:** Remove internal error details from the status response, or make them available only in debug mode or authenticated endpoints.

### M-14: Missing HTTP Security Headers
**File:** `veritas_os/api/server.py`, `veritas_os/api/dashboard_server.py`

**Problem:** Neither server implements security headers middleware. Missing:
- `X-Frame-Options` (clickjacking protection)
- `X-Content-Type-Options: nosniff` (MIME sniffing protection)
- `Strict-Transport-Security` (HSTS for HTTPS enforcement)
- `Content-Security-Policy` (XSS protection)

**Fix:** Add a security headers middleware.

### M-15: Unbounded max_results in web_search Allows Resource Exhaustion
**File:** `veritas_os/tools/web_search.py:354-360`

**Problem:** The `max_results` parameter has no upper bound validation. An attacker could pass extremely large values causing excessive API costs and memory exhaustion.

**Fix:** Add an upper bound check, e.g., `if mr > 100: mr = 100`.

### M-16: Invalid JSON serialization in LLM Safety API Call
**File:** `veritas_os/tools/llm_safety.py:213`

**Problem:** The `user_payload` dictionary is being converted to string using Python's default string representation instead of proper JSON serialization. This results in Python dict syntax (single quotes) being sent instead of valid JSON.

**Fix:** Use `json.dumps(user_payload)` to properly serialize the dictionary to JSON format.

### M-17: Denial of Service - Unbounded Memory Allocation in HashEmbedder
**File:** `veritas_os/memory/embedder.py:14-15`

**Problem:** The `embed()` method has no input validation on the size of the `texts` list or the length of individual strings. An attacker can cause memory exhaustion by passing extremely large inputs.

**Fix:** Add maximum text length validation (e.g., MAX_TEXT_LENGTH = 100,000) and maximum batch size limits.

### M-18: Silent Error Handling Hides Index Loading Failures
**File:** `veritas_os/memory/index_cosine.py:77-78, 98-99`

**Problem:** Two bare `except Exception: pass` blocks silently swallow all exceptions during index loading. Users have no way to distinguish between "index doesn't exist yet" and "index is corrupted".

**Fix:** Log the exception at WARNING or ERROR level before falling through to empty initialization.

---

## Test Coverage Gap Findings

### T-1: Missing Request Size Limit Tests for DoS Protection
**Severity:** High
**Problem:** The API server does not appear to have request body size limits configured, and there are no tests validating behavior with extremely large payloads.

### T-2: Missing Subprocess Command Injection Tests
**Severity:** High
**Problem:** `veritas_os/core/kernel.py:1065` uses `subprocess.Popen` but there are no tests covering this subprocess execution path or validating the `sys.executable` validation logic.

### T-3: Missing HMAC Signature Edge Case Tests
**Severity:** Medium
**Problem:** HMAC signature verification tests don't cover edge cases: empty body, malformed UTF-8, extremely long body, body with null bytes.

### T-4: Missing Rate Limit Concurrency Tests
**Severity:** Medium
**Problem:** Rate limiting implementation has no concurrent/parallel test execution to verify thread safety under race conditions.

---

## Architecture Observations

### Strengths
1. **Defense-in-depth**: FUJI safety gate with multiple layers (data, logic, value, security)
2. **Audit trail**: SHA-256 hash chain in trust log provides tamper-evident logging
3. **Graceful degradation**: Extensive fallback patterns ensure the system doesn't crash
4. **Thread safety**: RLock usage in trust log and memory store (mostly)
5. **Atomic I/O**: Well-implemented write-temp-fsync-rename pattern in `atomic_io.py`
6. **Type safety**: Pydantic v2 schemas with thorough validation
7. **Input validation**: Good use of constant-time comparisons for secrets
8. **PII Protection**: Comprehensive PII detection and masking in sanitize.py

### Areas for Improvement
1. **Module initialization**: Heavy side effects at import time (memory.py, paths.py)
2. **Configuration centralization**: Multiple modules resolve their own paths instead of using a single config
3. **Logging consistency**: Mix of `print()`, `logging`, and different timestamp formats
4. **Test isolation**: `builtins.MEM` and module-level state make testing difficult
5. **Error handling**: Too many bare `except` clauses that swallow errors silently
6. **Thread Safety**: Global variables (MEM_VEC) need locks; some functions exported without thread safety documentation
7. **Security Headers**: Missing standard HTTP security headers in API servers

---

## Recommended Priority

### Immediate (CRITICAL + HIGH Security Issues)
1. **C-1, C-2, C-3**: Fix race conditions in dataset_writer and atomic_write_npz, add request body size limits
2. **H-9, H-10, H-11**: Fix TOCTOU race conditions in policy loading, MEM_VEC access, and log rotation
3. **H-5, H-2, H-3**: Fix trust log hash chain consistency, non-atomic writes, and duplicate functions

### Short-term (Remaining HIGH + API Security)
4. **H-1, H-6, H-7**: Remove builtins pollution, fix wrong imports, fix rotation atomicity
5. **M-13, M-14**: Remove internal error exposure, add security headers
6. **M-15, M-16, M-17**: Fix input validation issues in web_search, llm_safety, embedder

### Medium-term (Code Quality + Test Coverage)
7. **M-1 through M-12**: Other code quality improvements
8. **T-1 through T-4**: Add missing security test coverage

### Long-term (Architectural Changes)
9. **H-4, H-8**: Refactor memory module initialization, remove pickle support entirely
10. Standardize timestamp formats and logging patterns across codebase
