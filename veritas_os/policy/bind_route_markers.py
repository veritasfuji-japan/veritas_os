"""Route-level metadata markers for bind-boundary governance coverage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class BindBoundaryRouteMetadata:
    """Declarative metadata describing bind-boundary requirements."""

    target_path: str
    target_type: str
    target_path_type: str


def requires_bind_boundary(
    *,
    target_path: str,
    target_type: str,
    target_path_type: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach bind-boundary metadata to a route handler function.

    This decorator is intentionally additive-only in this PR. It does not modify
    runtime behavior and is used by tests to verify route/bind coverage drift.
    """

    metadata = BindBoundaryRouteMetadata(
        target_path=target_path,
        target_type=target_type,
        target_path_type=target_path_type,
    )

    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func._requires_bind_boundary = True  # type: ignore[attr-defined]
        func._bind_boundary_metadata = metadata  # type: ignore[attr-defined]
        return func

    return _decorator


def get_bind_boundary_metadata(func: Callable[..., Any]) -> BindBoundaryRouteMetadata | None:
    """Return bind-boundary metadata from a route handler when present."""

    metadata = getattr(func, "_bind_boundary_metadata", None)
    if isinstance(metadata, BindBoundaryRouteMetadata):
        return metadata
    return None
