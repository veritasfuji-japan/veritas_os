"""Metrics exporter bootstrap for Prometheus and OTLP."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


_METRICS_ROUTE_INSTALLED = False


def _exporter_mode() -> str:
    return (os.getenv("VERITAS_METRICS_EXPORTER") or "none").strip().lower()


def _metrics_auth_required() -> bool:
    raw = (os.getenv("VERITAS_METRICS_AUTH") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_fastapi_responses() -> tuple[type[Any], type[Any]]:
    try:
        from fastapi.responses import JSONResponse, Response
    except ImportError as exc:
        raise RuntimeError(
            "Prometheus metrics endpoint requires FastAPI response dependencies. "
            "Install API dependencies before enabling VERITAS_METRICS_EXPORTER=prometheus."
        ) from exc
    return JSONResponse, Response


def _resolve_fastapi_depends() -> Any:
    try:
        from fastapi import Depends
    except ImportError as exc:
        raise RuntimeError(
            "Authenticated Prometheus metrics endpoint requires FastAPI. "
            "Install API dependencies before enabling VERITAS_METRICS_AUTH=1."
        ) from exc
    return Depends


def _build_prometheus_endpoint() -> Any:
    JSONResponse, Response = _resolve_fastapi_responses()
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except Exception:
        def endpoint() -> Any:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "error": "prometheus_client is not installed"},
            )

        return endpoint

    def endpoint() -> Any:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return endpoint


def _install_prometheus_endpoint(app: Any, auth_dependency: Optional[Any]) -> None:
    global _METRICS_ROUTE_INSTALLED
    if _METRICS_ROUTE_INSTALLED:
        return

    endpoint = _build_prometheus_endpoint()
    dependencies = []
    if _metrics_auth_required() and auth_dependency is not None:
        Depends = _resolve_fastapi_depends()
        dependencies = [Depends(auth_dependency)]
    app.add_api_route("/metrics", endpoint, methods=["GET"], include_in_schema=False, dependencies=dependencies)
    _METRICS_ROUTE_INSTALLED = True


def _configure_otlp_exporter() -> bool:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry import metrics
    except Exception as exc:
        logger.warning("OTLP exporter requested but OpenTelemetry deps are unavailable: %s", exc)
        return False

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return True


def configure_metrics_exporter(app: Any, auth_dependency: Optional[Any] = None) -> str:
    """Configure runtime metric export mode and endpoints.

    Modes:
      - none (default): collect metrics only.
      - prometheus: expose ``/metrics`` endpoint.
      - otlp: configure OpenTelemetry OTLP exporter.
    """
    mode = _exporter_mode()
    if mode == "prometheus":
        _install_prometheus_endpoint(app, auth_dependency=auth_dependency)
    elif mode == "otlp":
        _configure_otlp_exporter()
    elif mode != "none":
        logger.warning("Unknown VERITAS_METRICS_EXPORTER=%s; falling back to none", mode)
        mode = "none"
    return mode
