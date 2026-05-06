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


class _SafeSpanContextManager:
    """Wrap a span context manager and set attributes on the activated span."""

    def __init__(self, span_cm: Any, attributes: dict[str, Any] | None = None) -> None:
        self._span_cm = span_cm
        self._attributes = attributes or {}

    def __enter__(self) -> Any:
        span = self._span_cm.__enter__()
        if self._attributes:
            for key, value in self._attributes.items():
                try:
                    span.set_attribute(key, value)
                except Exception:
                    continue
        return span

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self._span_cm.__exit__(exc_type, exc_val, exc_tb)


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
    """Start a span context manager with optional privacy-safe attributes.

    Attributes are attached after span activation to avoid writing to a stale
    current span in real OpenTelemetry runtimes.
    """
    tracer = get_tracer()
    if tracer is None:
        return _NoOpContextManager()
    try:
        span_cm = tracer.start_as_current_span(name)
    except Exception:
        return _NoOpContextManager()

    return _SafeSpanContextManager(span_cm, attributes=attributes)


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
