"""Tests for canonical bind coverage registry and route classification."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.routing import APIRoute

import veritas_os.policy.bind_coverage as bind_coverage_module

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



def test_validator_rejects_duplicate_registry_entry(monkeypatch) -> None:
    """Duplicate method/path classification must fail closed."""
    entry = get_bind_coverage_registry()[0]
    monkeypatch.setattr(
        bind_coverage_module,
        "BIND_COVERAGE_REGISTRY",
        (entry, entry),
    )

    errors = validate_bind_coverage_registry()

    assert any("duplicate bind coverage entry" in error for error in errors)


def test_validator_rejects_audited_exemption_without_required_metadata(
    monkeypatch,
) -> None:
    """Audited exemptions need both rationale and risk metadata."""
    invalid = bind_coverage_module.BindCoverageEntry(
        path="/test/audited-exemption",
        method="POST",
        coverage_class=BindCoverageClass.AUDITED_EXEMPTION,
        reason="   ",
        risk_level=None,
    )
    monkeypatch.setattr(
        bind_coverage_module,
        "BIND_COVERAGE_REGISTRY",
        (invalid,),
    )
    monkeypatch.setattr(bind_coverage_module, "CATALOG", ())

    errors = validate_bind_coverage_registry()

    assert any("audited exemption missing reason" in error for error in errors)
    assert any("audited exemption missing risk_level" in error for error in errors)


def test_validator_rejects_bind_governed_route_without_target_metadata_or_catalog(
    monkeypatch,
) -> None:
    """A governed route must resolve to bind metadata and exist in the catalog."""
    invalid = bind_coverage_module.BindCoverageEntry(
        path="/v1/test/unregistered-effect",
        method="POST",
        coverage_class=BindCoverageClass.BIND_GOVERNED,
    )
    monkeypatch.setattr(
        bind_coverage_module,
        "BIND_COVERAGE_REGISTRY",
        (invalid,),
    )
    monkeypatch.setattr(bind_coverage_module, "CATALOG", ())
    monkeypatch.setattr(
        bind_coverage_module,
        "resolve_bind_target_metadata",
        lambda *_args, **_kwargs: {"target_path_type": "other"},
    )

    errors = validate_bind_coverage_registry()

    assert any("missing bind target metadata" in error for error in errors)
    assert any("missing from bind target catalog" in error for error in errors)


def test_validator_rejects_catalog_route_missing_governed_registry_entry(
    monkeypatch,
) -> None:
    """Catalog targets cannot exist without a bind-governed registry row."""
    monkeypatch.setattr(bind_coverage_module, "BIND_COVERAGE_REGISTRY", ())
    monkeypatch.setattr(
        bind_coverage_module,
        "CATALOG",
        (SimpleNamespace(target_path="/v1/test/catalog-only"),),
    )

    errors = validate_bind_coverage_registry()

    assert any(
        "bind target catalog route missing bind_governed registry entry" in error
        for error in errors
    )
