"""Observability-only FastAPI middleware.

The middleware records request duration and response status metrics only.
It intentionally avoids modifying auth, headers, or request flow responsibilities
already handled by :mod:`veritas_os.api.middleware`.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import Request

from veritas_os.observability.metrics import record_http_request


_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"})


def _resolve_route_path(request: Request) -> str:
    """Use the route template or a bounded label for unrouted requests."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(getattr(route, "path"))
    return "unmatched"


async def observe_request_metrics(request: Request, call_next: Any):
    """Record per-request latency and status code metrics."""
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = int(getattr(response, "status_code", 500) or 500)
        return response
    finally:
        elapsed = time.perf_counter() - started_at
        record_http_request(
            method=request.method if request.method in _HTTP_METHODS else "OTHER",
            path=_resolve_route_path(request),
            status_code=status_code,
            duration_seconds=elapsed,
        )
