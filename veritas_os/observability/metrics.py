"""Observability metric definitions and safe recording helpers.

This module exposes a stable helper API used by core/api modules.
When ``prometheus_client`` is unavailable, all helpers degrade to no-op,
keeping runtime compatibility for environments without observability extras.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


class _NoOpMetric:
    """No-op metric object compatible with Counter/Histogram/Gauge usage."""

    def labels(self, **_: Any) -> "_NoOpMetric":
        return self

    def inc(self, _: float = 1.0) -> None:
        return None

    def observe(self, _: float) -> None:
        return None

    def set(self, _: float) -> None:
        return None


try:
    from prometheus_client import Counter, Gauge, Histogram

    _PROMETHEUS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency path
    Counter = Gauge = Histogram = None  # type: ignore
    _PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus_client unavailable, using no-op metrics: %s", exc)


def _counter(*args: Any, **kwargs: Any) -> Any:
    if not _PROMETHEUS_AVAILABLE:
        return _NoOpMetric()
    return Counter(*args, **kwargs)


def _histogram(*args: Any, **kwargs: Any) -> Any:
    if not _PROMETHEUS_AVAILABLE:
        return _NoOpMetric()
    return Histogram(*args, **kwargs)


def _gauge(*args: Any, **kwargs: Any) -> Any:
    if not _PROMETHEUS_AVAILABLE:
        return _NoOpMetric()
    return Gauge(*args, **kwargs)


VERITAS_DECIDE_TOTAL = _counter(
    "veritas_decide_total",
    "Total number of /v1/decide calls",
    labelnames=("status", "mode", "intent"),
)
VERITAS_FUJI_DECISIONS_TOTAL = _counter(
    "veritas_fuji_decisions_total",
    "FUJI gate decisions by status",
    labelnames=("decision_status",),
)
VERITAS_FUJI_VIOLATIONS_TOTAL = _counter(
    "veritas_fuji_violations_total",
    "FUJI violations by type",
    labelnames=("violation_type",),
)
VERITAS_AUTH_REJECTIONS_TOTAL = _counter(
    "veritas_auth_rejections_total",
    "Authentication rejections by reason",
    labelnames=("reason",),
)
VERITAS_MEMORY_OPERATIONS_TOTAL = _counter(
    "veritas_memory_operations_total",
    "Memory operations by operation and kind",
    labelnames=("operation", "kind"),
)

VERITAS_DECIDE_DURATION_SECONDS = _histogram(
    "veritas_decide_duration_seconds",
    "Latency of /v1/decide",
    labelnames=("mode",),
)
VERITAS_PIPELINE_STAGE_DURATION_SECONDS = _histogram(
    "veritas_pipeline_stage_duration_seconds",
    "Per-stage latency for decide pipeline",
    labelnames=("stage",),
)
VERITAS_LLM_CALL_DURATION_SECONDS = _histogram(
    "veritas_llm_call_duration_seconds",
    "LLM provider call latency",
    labelnames=("provider",),
)

VERITAS_TELOS_SCORE = _gauge(
    "veritas_telos_score",
    "Latest telos_score",
    labelnames=("user_id",),
)
VERITAS_MEMORY_STORE_ENTRIES = _gauge(
    "veritas_memory_store_entries",
    "Memory store entry count per user",
    labelnames=("user_id",),
)
VERITAS_DEGRADED_SUBSYSTEMS = _gauge(
    "veritas_degraded_subsystems",
    "Count of degraded subsystems",
)

VERITAS_HTTP_REQUEST_DURATION_SECONDS = _histogram(
    "veritas_http_request_duration_seconds",
    "HTTP request duration by method/path",
    labelnames=("method", "path"),
)
VERITAS_HTTP_REQUESTS_TOTAL = _counter(
    "veritas_http_requests_total",
    "HTTP request count by method/path/status",
    labelnames=("method", "path", "status_code"),
)

TRUSTLOG_APPEND_SUCCESS_TOTAL = _counter(
    "trustlog_append_success_total",
    "Total successful TrustLog append operations",
    labelnames=("posture",),
)
TRUSTLOG_APPEND_FAILURE_TOTAL = _counter(
    "trustlog_append_failure_total",
    "Total failed TrustLog append operations",
    labelnames=("posture", "reason"),
)
TRUSTLOG_SIGN_FAILURE_TOTAL = _counter(
    "trustlog_sign_failure_total",
    "Total signing failures while appending TrustLog witness entries",
    labelnames=("signer_backend", "reason"),
)
TRUSTLOG_MIRROR_FAILURE_TOTAL = _counter(
    "trustlog_mirror_failure_total",
    "Total TrustLog mirror write failures",
    labelnames=("backend", "reason"),
)
TRUSTLOG_ANCHOR_FAILURE_TOTAL = _counter(
    "trustlog_anchor_failure_total",
    "Total TrustLog transparency anchor failures",
    labelnames=("backend", "reason"),
)
TRUSTLOG_VERIFY_FAILURE_TOTAL = _counter(
    "trustlog_verify_failure_total",
    "Total TrustLog verification failures",
    labelnames=("ledger", "reason"),
)
TRUSTLOG_LAST_SUCCESS_TIMESTAMP = _gauge(
    "trustlog_last_success_timestamp",
    "Unix timestamp of the latest successful TrustLog append",
)
TRUSTLOG_ANCHOR_LAG_SECONDS = _gauge(
    "trustlog_anchor_lag_seconds",
    "Lag between local anchor time and external transparency timestamp",
    labelnames=("backend",),
)
TRUSTLOG_MIRROR_LATENCY_SECONDS = _histogram(
    "trustlog_mirror_latency_seconds",
    "Latency of TrustLog mirror operations",
    labelnames=("backend",),
)
TRUSTLOG_SIGN_LATENCY_SECONDS = _histogram(
    "trustlog_sign_latency_seconds",
    "Latency of TrustLog signing operations",
    labelnames=("signer_backend",),
)

# ---------------------------------------------------------------------------
# PostgreSQL / connection-pool metrics
# ---------------------------------------------------------------------------

DB_POOL_IN_USE = _gauge(
    "db_pool_in_use",
    "Number of connections currently checked out from the pool",
)
DB_POOL_AVAILABLE = _gauge(
    "db_pool_available",
    "Number of idle connections available in the pool",
)
DB_POOL_WAITING = _gauge(
    "db_pool_waiting",
    "Number of requests waiting for a connection from the pool",
)
DB_POOL_MAX_SIZE = _gauge(
    "db_pool_max_size",
    "Configured maximum size of the connection pool",
)
DB_POOL_MIN_SIZE = _gauge(
    "db_pool_min_size",
    "Configured minimum size of the connection pool",
)
DB_CONNECT_FAILURES_TOTAL = _counter(
    "db_connect_failures_total",
    "Total connection failures to the database",
    labelnames=("reason",),
)
DB_STATEMENT_TIMEOUTS_TOTAL = _counter(
    "db_statement_timeouts_total",
    "Total SQL statement timeouts",
)
TRUSTLOG_APPEND_LATENCY_SECONDS = _histogram(
    "trustlog_append_latency_seconds",
    "Latency of TrustLog append operations (end-to-end)",
)
TRUSTLOG_APPEND_CONFLICT_TOTAL = _counter(
    "trustlog_append_conflict_total",
    "Total TrustLog append uniqueness-constraint conflicts",
)
DB_BACKEND_SELECTED = _gauge(
    "db_backend_selected",
    "Active storage backend (1 = selected)",
    labelnames=("component", "backend"),
)
DB_HEALTH_STATUS = _gauge(
    "db_health_status",
    "Database health (1 = healthy, 0 = unhealthy)",
)

# Desirable / advanced PostgreSQL metrics
LONG_RUNNING_QUERY_COUNT = _gauge(
    "long_running_query_count",
    "Number of queries running longer than the statement timeout threshold",
)
IDLE_IN_TRANSACTION_COUNT = _gauge(
    "idle_in_transaction_count",
    "Number of connections idle in a transaction",
)
ADVISORY_LOCK_CONTENTION_COUNT = _gauge(
    "advisory_lock_contention_count",
    "Number of sessions waiting on advisory locks",
)
SLOW_APPEND_WARNING_TOTAL = _counter(
    "slow_append_warning_total",
    "Total TrustLog appends exceeding the slow-append threshold",
)


def _label(value: Any, fallback: str = "unknown") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def record_decide(status: Any, mode: Any, intent: Any, duration_seconds: Optional[float] = None) -> None:
    """Record /v1/decide call count and latency."""
    status_label = _label(status, "unknown")
    mode_label = _label(mode, "normal")
    intent_label = _label(intent, "unknown")
    VERITAS_DECIDE_TOTAL.labels(
        status=status_label,
        mode=mode_label,
        intent=intent_label,
    ).inc()
    if duration_seconds is not None:
        VERITAS_DECIDE_DURATION_SECONDS.labels(mode=mode_label).observe(max(0.0, duration_seconds))


def observe_pipeline_stage_duration(stage: str, duration_seconds: float) -> None:
    VERITAS_PIPELINE_STAGE_DURATION_SECONDS.labels(stage=_label(stage)).observe(max(0.0, duration_seconds))


def observe_llm_call_duration(provider: Any, duration_seconds: float) -> None:
    VERITAS_LLM_CALL_DURATION_SECONDS.labels(provider=_label(provider)).observe(max(0.0, duration_seconds))


def record_fuji_decision(decision_status: Any) -> None:
    VERITAS_FUJI_DECISIONS_TOTAL.labels(decision_status=_label(decision_status)).inc()


def record_fuji_violations(violation_types: Optional[Iterable[Any]]) -> None:
    for violation in violation_types or []:
        VERITAS_FUJI_VIOLATIONS_TOTAL.labels(violation_type=_label(violation)).inc()


def record_auth_rejection(reason: Any) -> None:
    VERITAS_AUTH_REJECTIONS_TOTAL.labels(reason=_label(reason)).inc()


def record_memory_operation(operation: Any, kind: Any) -> None:
    VERITAS_MEMORY_OPERATIONS_TOTAL.labels(
        operation=_label(operation),
        kind=_label(kind, "unknown"),
    ).inc()


def set_telos_score(user_id: Any, score: Any) -> None:
    try:
        VERITAS_TELOS_SCORE.labels(user_id=_label(user_id, "anonymous")).set(float(score))
    except (TypeError, ValueError):
        return


def set_memory_store_entries(user_id: Any, entries: Any) -> None:
    try:
        VERITAS_MEMORY_STORE_ENTRIES.labels(user_id=_label(user_id, "anonymous")).set(float(entries))
    except (TypeError, ValueError):
        return


def set_degraded_subsystems(count: Any) -> None:
    try:
        VERITAS_DEGRADED_SUBSYSTEMS.set(float(count))
    except (TypeError, ValueError):
        return


def record_http_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    """Record generic HTTP request latency and status metrics."""
    method_label = _label(method, "UNKNOWN")
    path_label = _label(path, "unknown")
    code_label = _label(status_code, "0")
    VERITAS_HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method_label,
        path=path_label,
    ).observe(max(0.0, duration_seconds))
    VERITAS_HTTP_REQUESTS_TOTAL.labels(
        method=method_label,
        path=path_label,
        status_code=code_label,
    ).inc()


def _now_unix_timestamp() -> float:
    return datetime.now(timezone.utc).timestamp()


def _posture_label() -> str:
    try:
        from veritas_os.core.posture import get_active_posture

        return _label(get_active_posture().value)
    except Exception:
        return "unknown"


def record_trustlog_append_success() -> None:
    posture = _posture_label()
    TRUSTLOG_APPEND_SUCCESS_TOTAL.labels(posture=posture).inc()
    TRUSTLOG_LAST_SUCCESS_TIMESTAMP.set(_now_unix_timestamp())


def record_trustlog_append_failure(reason: Any) -> None:
    TRUSTLOG_APPEND_FAILURE_TOTAL.labels(
        posture=_posture_label(),
        reason=_label(reason, "unknown_error"),
    ).inc()


def observe_trustlog_sign_latency(signer_backend: Any, duration_seconds: float) -> None:
    TRUSTLOG_SIGN_LATENCY_SECONDS.labels(
        signer_backend=_label(signer_backend, "unknown"),
    ).observe(max(0.0, duration_seconds))


def record_trustlog_sign_failure(signer_backend: Any, reason: Any) -> None:
    TRUSTLOG_SIGN_FAILURE_TOTAL.labels(
        signer_backend=_label(signer_backend, "unknown"),
        reason=_label(reason, "unknown_error"),
    ).inc()


def observe_trustlog_mirror_latency(backend: Any, duration_seconds: float) -> None:
    TRUSTLOG_MIRROR_LATENCY_SECONDS.labels(
        backend=_label(backend, "unknown"),
    ).observe(max(0.0, duration_seconds))


def record_trustlog_mirror_failure(backend: Any, reason: Any) -> None:
    TRUSTLOG_MIRROR_FAILURE_TOTAL.labels(
        backend=_label(backend, "unknown"),
        reason=_label(reason, "unknown_error"),
    ).inc()


def record_trustlog_anchor_failure(backend: Any, reason: Any) -> None:
    TRUSTLOG_ANCHOR_FAILURE_TOTAL.labels(
        backend=_label(backend, "unknown"),
        reason=_label(reason, "unknown_error"),
    ).inc()


def set_trustlog_anchor_lag_seconds(backend: Any, lag_seconds: float) -> None:
    TRUSTLOG_ANCHOR_LAG_SECONDS.labels(
        backend=_label(backend, "unknown"),
    ).set(max(0.0, lag_seconds))


def record_trustlog_verify_failure(ledger: Any, reason: Any) -> None:
    TRUSTLOG_VERIFY_FAILURE_TOTAL.labels(
        ledger=_label(ledger, "unknown"),
        reason=_label(reason, "unknown_error"),
    ).inc()


# ---------------------------------------------------------------------------
# PostgreSQL / connection-pool recording helpers
# ---------------------------------------------------------------------------

# Threshold for slow TrustLog appends (in seconds).
# Configurable via VERITAS_SLOW_APPEND_THRESHOLD_SECONDS env var.
_SLOW_APPEND_THRESHOLD_SECONDS = float(
    os.getenv("VERITAS_SLOW_APPEND_THRESHOLD_SECONDS", "1.0")
)


def set_db_pool_stats(
    *,
    in_use: int,
    available: int,
    waiting: int,
    max_size: int,
    min_size: int,
) -> None:
    """Update all pool-size gauges in one call."""
    try:
        DB_POOL_IN_USE.set(float(in_use))
        DB_POOL_AVAILABLE.set(float(available))
        DB_POOL_WAITING.set(float(waiting))
        DB_POOL_MAX_SIZE.set(float(max_size))
        DB_POOL_MIN_SIZE.set(float(min_size))
    except (TypeError, ValueError):
        return


def record_db_connect_failure(reason: Any) -> None:
    DB_CONNECT_FAILURES_TOTAL.labels(reason=_label(reason, "unknown")).inc()


def record_db_statement_timeout() -> None:
    DB_STATEMENT_TIMEOUTS_TOTAL.inc()


def observe_trustlog_append_latency(duration_seconds: float) -> None:
    """Record TrustLog append latency and emit a slow-append warning if needed."""
    TRUSTLOG_APPEND_LATENCY_SECONDS.observe(max(0.0, duration_seconds))
    if duration_seconds > _SLOW_APPEND_THRESHOLD_SECONDS:
        SLOW_APPEND_WARNING_TOTAL.inc()


def record_trustlog_append_conflict() -> None:
    TRUSTLOG_APPEND_CONFLICT_TOTAL.inc()


def set_db_backend_selected(component: str, backend: str) -> None:
    """Mark the active backend for a storage component.

    Emits ``db_backend_selected{component="…", backend="…"} = 1``
    for the active combination.
    """
    DB_BACKEND_SELECTED.labels(
        component=_label(component),
        backend=_label(backend),
    ).set(1.0)


def set_db_health_status(healthy: bool) -> None:
    DB_HEALTH_STATUS.set(1.0 if healthy else 0.0)


def set_long_running_query_count(count: int) -> None:
    try:
        LONG_RUNNING_QUERY_COUNT.set(float(count))
    except (TypeError, ValueError):
        return


def set_idle_in_transaction_count(count: int) -> None:
    try:
        IDLE_IN_TRANSACTION_COUNT.set(float(count))
    except (TypeError, ValueError):
        return


def set_advisory_lock_contention_count(count: int) -> None:
    try:
        ADVISORY_LOCK_CONTENTION_COUNT.set(float(count))
    except (TypeError, ValueError):
        return
