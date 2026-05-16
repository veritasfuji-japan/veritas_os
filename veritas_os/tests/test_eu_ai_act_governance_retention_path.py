from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.core.eu_ai_act_compliance_module import (
    _read_governance_log_retention,
    validate_deployment_readiness,
    validate_audit_readiness_for_high_risk,
)
from veritas_os.core.eu_ai_act_config import EUComplianceConfig


def _write_governance(path: Path, retention_days: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"log_retention": {"retention_days": retention_days}}),
        encoding="utf-8",
    )


def _write_flat_governance(path: Path, retention_days: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"log_retention_days": retention_days}),
        encoding="utf-8",
    )


def test_read_governance_log_retention_uses_explicit_governance_path(tmp_path: Path) -> None:
    custom_path = tmp_path / "custom-governance.json"
    _write_governance(custom_path, retention_days=240)

    assert _read_governance_log_retention(governance_path=custom_path) == 240


def test_read_governance_log_retention_uses_repo_root_override(tmp_path: Path) -> None:
    governance_path = tmp_path / "veritas_os" / "api" / "governance.json"
    _write_governance(governance_path, retention_days=365)

    assert _read_governance_log_retention(repo_root=tmp_path) == 365


def test_read_governance_log_retention_prefers_explicit_path_over_repo_root(tmp_path: Path) -> None:
    repo_governance_path = tmp_path / "veritas_os" / "api" / "governance.json"
    explicit_governance_path = tmp_path / "explicit-governance.json"
    _write_governance(repo_governance_path, retention_days=365)
    _write_governance(explicit_governance_path, retention_days=210)

    assert (
        _read_governance_log_retention(
            governance_path=explicit_governance_path,
            repo_root=tmp_path,
        )
        == 210
    )


def test_read_governance_log_retention_falls_back_to_90_for_missing_override(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-governance.json"
    assert _read_governance_log_retention(governance_path=missing_path) == 90


def test_read_governance_log_retention_falls_back_to_90_for_malformed_json(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed-governance.json"
    malformed.write_text("{not-json", encoding="utf-8")

    assert _read_governance_log_retention(governance_path=malformed) == 90


@pytest.mark.parametrize("payload", ["[]", "null"])
def test_read_governance_log_retention_falls_back_to_90_for_non_mapping_json(
    tmp_path: Path,
    payload: str,
) -> None:
    non_mapping = tmp_path / "non-mapping-governance.json"
    non_mapping.write_text(payload, encoding="utf-8")

    assert _read_governance_log_retention(governance_path=non_mapping) == 90


def test_read_governance_log_retention_supports_flat_log_retention_days(
    tmp_path: Path,
) -> None:
    flat_path = tmp_path / "flat-governance.json"
    _write_flat_governance(flat_path, retention_days=180)

    assert _read_governance_log_retention(governance_path=flat_path) == 180


def test_read_governance_log_retention_prefers_nested_retention_over_flat_key(
    tmp_path: Path,
) -> None:
    mixed_path = tmp_path / "mixed-governance.json"
    mixed_path.write_text(
        json.dumps(
            {
                "log_retention": {"retention_days": 240},
                "log_retention_days": 30,
            }
        ),
        encoding="utf-8",
    )

    assert _read_governance_log_retention(governance_path=mixed_path) == 240


def test_read_governance_log_retention_falls_back_to_90_for_invalid_retention_value(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "invalid-governance.json"
    invalid_path.write_text(
        json.dumps({"log_retention": {"retention_days": "not-an-int"}}),
        encoding="utf-8",
    )

    assert _read_governance_log_retention(governance_path=invalid_path) == 90


def test_validate_audit_readiness_uses_governance_path_when_log_retention_missing(
    tmp_path: Path,
) -> None:
    config = EUComplianceConfig(require_audit_for_high_risk=True)
    custom_path = tmp_path / "custom-governance.json"
    _write_governance(custom_path, retention_days=240)

    result = validate_audit_readiness_for_high_risk(
        risk_level="HIGH",
        config=config,
        notification_flow_ready=True,
        encryption_enabled=True,
        governance_path=custom_path,
    )

    assert result["allowed"] is True


def test_validate_audit_readiness_log_retention_days_takes_precedence_over_path(
    tmp_path: Path,
) -> None:
    config = EUComplianceConfig(require_audit_for_high_risk=True)
    custom_path = tmp_path / "custom-governance.json"
    _write_governance(custom_path, retention_days=365)

    result = validate_audit_readiness_for_high_risk(
        risk_level="HIGH",
        config=config,
        log_retention_days=90,
        notification_flow_ready=True,
        encryption_enabled=True,
        governance_path=custom_path,
    )

    assert result["allowed"] is False
    assert "log_retention_days=90 < 180" in result["reason"]


def test_validate_audit_readiness_repo_root_override_can_fail_closed_for_short_retention(
    tmp_path: Path,
) -> None:
    config = EUComplianceConfig(require_audit_for_high_risk=True)
    governance_path = tmp_path / "veritas_os" / "api" / "governance.json"
    _write_governance(governance_path, retention_days=30)

    result = validate_audit_readiness_for_high_risk(
        risk_level="HIGH",
        config=config,
        notification_flow_ready=True,
        encryption_enabled=True,
        repo_root=tmp_path,
    )

    assert result["allowed"] is False
    assert "log_retention_days=30 < 180" in result["reason"]


def test_validate_deployment_readiness_uses_repo_root_for_log_retention(
    tmp_path: Path,
) -> None:
    governance_path = tmp_path / "veritas_os" / "api" / "governance.json"
    _write_governance(governance_path, retention_days=30)

    result = validate_deployment_readiness(repo_root=str(tmp_path))

    assert result["environment"]["log_retention_days"] == 30
    assert any(
        "log_retention: 30 days < 180" in issue
        for issue in result.get("issues", [])
    )


def test_validate_deployment_readiness_repo_root_supports_flat_log_retention_days(
    tmp_path: Path,
) -> None:
    governance_path = tmp_path / "veritas_os" / "api" / "governance.json"
    _write_flat_governance(governance_path, retention_days=180)

    result = validate_deployment_readiness(repo_root=str(tmp_path))

    assert result["environment"]["log_retention_days"] == 180
    assert not any(
        "log_retention: 90 days < 180" in issue
        or "log_retention: 180 days < 180" in issue
        for issue in result.get("issues", [])
    )
