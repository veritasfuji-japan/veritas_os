"""Observability metric definitions and safe recording helpers.

This module exposes a stable helper API used by core/api modules.
When ``prometheus_client`` is unavailable, all helpers degrade to no-op,
keeping runtime compatibility for environments without observability extras.
"""
from __future__ import annotations

import logging
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
