"""Tests for canonical bind coverage registry and route classification."""

from __future__ import annotations

from fastapi.routing import APIRoute

from veritas_os.api.server import app
from veritas_os.policy.bind_coverage import (
    BindCoverageClass,
    classify_bind_coverage,
    get_bind_coverage_registry,
    validate_bind_coverage_registry,
)


def _runtime_api_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append((route.path, method))
    return routes


def test_bind_coverage_registry_is_valid() -> None:
    """Registry must be internally consistent and catalog-aligned."""
    assert validate_bind_coverage_registry() == []


def test_all_effect_bearing_routes_are_classified() -> None:
    """POST/PUT/PATCH/DELETE routes must be explicitly classified."""
    missing: list[str] = []
    for path, method in _runtime_api_routes():
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        if classify_bind_coverage(path, method) is None:
            missing.append(f"{method} {path}")
    assert not missing, f"Unclassified effect-bearing routes: {missing}"


def test_audited_exemptions_include_reason_and_risk() -> None:
    """Audited exemptions must carry explicit governance rationale."""
    for entry in get_bind_coverage_registry():
        if entry.coverage_class != BindCoverageClass.AUDITED_EXEMPTION:
            continue
        assert entry.reason is not None and entry.reason.strip()
        assert entry.risk_level is not None and entry.risk_level.strip()


def test_all_runtime_api_routes_are_classified() -> None:
    """Every runtime API route should have a canonical coverage classification."""
    missing = [
        f"{method} {path}"
        for path, method in _runtime_api_routes()
        if classify_bind_coverage(path, method) is None
    ]
    assert not missing, f"Unclassified runtime API routes: {missing}"
