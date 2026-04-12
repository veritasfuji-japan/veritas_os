"""Distributed tracing bootstrap for OpenTelemetry trace/span support.

Provides request_id-based end-to-end tracing across pipeline stages.
All tracing is optional: when ``opentelemetry`` packages are unavailable
the helpers degrade to no-ops, matching the existing metrics pattern.

Configuration:
    - ``VERITAS_TRACE_EXPORTER``:  ``none`` (default) | ``otlp`` | ``console``
    - ``OTEL_EXPORTER_OTLP_ENDPOINT``:  gRPC collector URL for OTLP.
    - ``OTEL_SERVICE_NAME``:  Service name (default ``veritas-os``).
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OpenTelemetry imports with graceful degradation
# ---------------------------------------------------------------------------

_OTEL_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import StatusCode

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]
    BatchSpanProcessor = None  # type: ignore[assignment,misc]
    ConsoleSpanExporter = None  # type: ignore[assignment,misc]
    Resource = None  # type: ignore[assignment,misc]
    StatusCode = None  # type: ignore[assignment,misc]


_tracer: Any = None
_provider: Any = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _trace_exporter_mode() -> str:
    """Return the configured trace exporter mode."""
    return (os.getenv("VERITAS_TRACE_EXPORTER") or "none").strip().lower()


def _service_name() -> str:
    """Return the configured OTEL service name."""
    return os.getenv("OTEL_SERVICE_NAME", "veritas-os")


def configure_trace_exporter() -> str:
    """Configure the OpenTelemetry TracerProvider and exporter.

    Returns:
        The active exporter mode string (``none``, ``otlp``, ``console``).
    """
    global _tracer, _provider

    mode = _trace_exporter_mode()

    if mode == "none" or not _OTEL_AVAILABLE:
        if mode != "none" and not _OTEL_AVAILABLE:
            logger.warning(
                "VERITAS_TRACE_EXPORTER=%s but OpenTelemetry deps are unavailable; "
                "falling back to none",
                mode,
            )
            mode = "none"
        return mode

    resource = Resource.create({"service.name": _service_name()})
    provider = TracerProvider(resource=resource)

    if mode == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as exc:
            logger.warning(
                "OTLP trace exporter requested but setup failed: %s; "
                "falling back to console",
                exc,
            )
            provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
            mode = "console"

    elif mode == "console":
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
    else:
        logger.warning(
            "Unknown VERITAS_TRACE_EXPORTER=%s; falling back to none",
            mode,
        )
        return "none"

    trace.set_tracer_provider(provider)
    _provider = provider
    _tracer = trace.get_tracer("veritas_os.pipeline", "2.0.0")
    return mode


def get_tracer() -> Any:
    """Return the configured tracer, or ``None`` when tracing is disabled."""
    return _tracer


# ---------------------------------------------------------------------------
# Span helpers — safe to call even when tracing is disabled
# ---------------------------------------------------------------------------


@contextmanager
def pipeline_root_span(
    request_id: str,
    *,
    query: str = "",
    user_id: str = "",
    fast_mode: bool = False,
    attributes: Optional[dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """Create a root span for the entire decide pipeline.

    Usage::

        with pipeline_root_span(request_id, query=q) as span:
            ...  # pipeline stages run here

    When tracing is disabled the context manager yields ``None`` and has
    zero overhead.
    """
    if _tracer is None:
        yield None
        return

    attrs: dict[str, Any] = {
        "veritas.request_id": request_id,
        "veritas.fast_mode": fast_mode,
    }
    if query:
        # Truncate long queries to keep span attributes manageable.
        attrs["veritas.query"] = query[:256]
    if user_id:
        attrs["veritas.user_id"] = user_id
    if attributes:
        attrs.update(attributes)

    with _tracer.start_as_current_span(
        "decide_pipeline",
        attributes=attrs,
    ) as span:
        yield span


@contextmanager
def pipeline_stage_span(
    stage_name: str,
    *,
    attributes: Optional[dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """Create a child span for a single pipeline stage.

    Usage::

        with pipeline_stage_span("input_norm") as span:
            ...  # stage logic

    Automatically records exceptions as span events and sets the span
    status to ERROR on unhandled exceptions (while re-raising).
    """
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(
        f"pipeline.{stage_name}",
        attributes=attributes or {},
    ) as span:
        try:
            yield span
        except Exception as exc:
            if span is not None and StatusCode is not None:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
            raise


def record_span_event(
    span: Any,
    name: str,
    attributes: Optional[dict[str, Any]] = None,
) -> None:
    """Record an event on a span (no-op when span is None)."""
    if span is not None:
        span.add_event(name, attributes=attributes or {})


def set_span_attribute(
    span: Any,
    key: str,
    value: Any,
) -> None:
    """Set an attribute on a span (no-op when span is None)."""
    if span is not None:
        span.set_attribute(key, value)


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def shutdown_tracing() -> None:
    """Flush and shut down the trace provider if active."""
    global _tracer, _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error shutting down trace provider: %s", exc)
    _tracer = None
    _provider = None
