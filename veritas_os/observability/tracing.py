"""Privacy-safe tracing helpers with OpenTelemetry-compatible fallback.

The helper APIs in this module are intentionally fail-safe:
- If OpenTelemetry is unavailable, helpers become no-op.
- If tracing operations fail at runtime, business logic continues.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

try:
    from opentelemetry import trace as otel_trace
except Exception:  # pragma: no cover - fallback behavior tested via monkeypatch
    otel_trace = None


class _NoOpSpan:
    """No-op span implementation used when OpenTelemetry is unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        return None


_NOOP_SPAN = _NoOpSpan()


class _NoOpContextManager:
    """Context manager that yields a no-op span."""

    def __enter__(self) -> _NoOpSpan:
        return _NOOP_SPAN

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def get_tracer():
    """Return OpenTelemetry tracer when available, otherwise a no-op tracer."""
    if otel_trace is None:
        return None
    try:
        return otel_trace.get_tracer("veritas_os")
    except Exception:
        return None


def _active_span() -> Any:
    """Return current active span or no-op span."""
    if otel_trace is None:
        return _NOOP_SPAN
    try:
        return otel_trace.get_current_span()
    except Exception:
        return _NOOP_SPAN


def start_span(name: str, attributes: dict[str, Any] | None = None):
    """Start a span context manager with optional privacy-safe attributes."""
    tracer = get_tracer()
    if tracer is None:
        return _NoOpContextManager()
    try:
        span_cm = tracer.start_as_current_span(name)
    except Exception:
        return _NoOpContextManager()

    if attributes:
        try:
            current = _active_span()
            for key, value in attributes.items():
                current.set_attribute(key, value)
        except Exception:
            pass
    return span_cm


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Append event to current span; silently no-op on tracing failures."""
    try:
        _active_span().add_event(name, attributes=attributes)
    except Exception:
        return None


def set_span_attribute(key: str, value: Any) -> None:
    """Set attribute on current span; silently no-op on tracing failures."""
    try:
        _active_span().set_attribute(key, value)
    except Exception:
        return None


@contextmanager
def trace_step(name: str, attributes: dict[str, Any] | None = None):
    """Wrap a governance/audit step in a child span without affecting runtime semantics."""
    with start_span(name, attributes=attributes):
        try:
            yield
        except Exception as exc:
            add_span_event("step.exception", attributes={"error": str(exc), "step": name})
            set_span_attribute("error", True)
            raise
