"""Unit tests for frontend API contract consistency checker."""

from __future__ import annotations

import pathlib

from scripts.quality import check_frontend_api_contract_consistency as checker


def test_normalize_frontend_path_handles_query_and_template() -> None:
    """Normalizer should drop query strings and map template params."""
    normalized = checker._normalize_frontend_path(
        "/api/veritas/v1/trust/${encodeURIComponent(requestId)}?limit=10"
    )

    assert normalized == "/v1/trust/{param}"


def test_validate_consistency_accepts_known_routes() -> None:
    """No errors should be reported when BFF and OpenAPI both match usage."""
    usages = [
        checker.FrontendRouteUsage(
            method="GET",
            raw_path="/api/veritas/v1/governance/policy",
            file_path=pathlib.Path("frontend/app/governance/hooks/useGovernanceState.ts"),
        )
    ]

    matcher = checker.RouteMatcher(
        method="GET",
        pattern=checker.re.compile(r"^/v1/governance/policy$"),
    )

    errors = checker.validate_consistency(usages, [matcher], [matcher])

    assert errors == []


def test_validate_consistency_reports_missing_bff_and_openapi() -> None:
    """Drift should report missing entries for both control planes."""
    usages = [
        checker.FrontendRouteUsage(
            method="GET",
            raw_path="/api/veritas/v1/trust/abc/prov",
            file_path=pathlib.Path("frontend/app/audit/hooks/useAuditData.ts"),
        )
    ]

    errors = checker.validate_consistency(usages, bff_matchers=[], openapi_matchers=[])

    assert len(errors) == 2
    assert "BFF allowlist missing GET /v1/trust/abc/prov" in errors[0]
    assert "OpenAPI path/method missing GET /v1/trust/abc/prov" in errors[1]
