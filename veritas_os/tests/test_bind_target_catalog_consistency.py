"""Drift prevention tests for bind target catalog, coverage, and route markers."""

from __future__ import annotations

from fastapi.routing import APIRoute

from veritas_os.api.bind_target_catalog import CATALOG
from veritas_os.api.server import app
from veritas_os.policy.bind_coverage import (
    BindCoverageClass,
    classify_bind_coverage,
    get_bind_coverage_registry,
)
from veritas_os.policy.bind_route_markers import get_bind_boundary_metadata


def test_bind_governed_registry_paths_match_catalog_paths() -> None:
    """bind_governed coverage entries must match canonical catalog targets."""
    governed_paths = {
        entry.path
        for entry in get_bind_coverage_registry()
        if entry.coverage_class == BindCoverageClass.BIND_GOVERNED
    }
    catalog_paths = {entry.target_path for entry in CATALOG}
    assert governed_paths == catalog_paths


def test_bind_governed_routes_declare_marker_metadata() -> None:
    """bind_governed runtime routes should declare bind marker metadata."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            coverage = classify_bind_coverage(route.path, method)
            if coverage is None or coverage.coverage_class != BindCoverageClass.BIND_GOVERNED:
                continue
            metadata = get_bind_boundary_metadata(route.endpoint)
            assert metadata is not None, f"missing marker for {method} {route.path}"
            assert metadata.target_path == route.path


def test_bind_route_markers_align_with_catalog_metadata() -> None:
    """Route marker metadata should align with catalog definitions."""
    catalog_by_path = {entry.target_path: entry for entry in CATALOG}

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        metadata = get_bind_boundary_metadata(route.endpoint)
        if metadata is None:
            continue
        catalog_entry = catalog_by_path.get(metadata.target_path)
        assert catalog_entry is not None
        assert catalog_entry.target_type == metadata.target_type
        assert catalog_entry.target_path_type == metadata.target_path_type
