"""Regression tests for governance schema/policy roundtrip safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.api import governance as gov
from veritas_os.governance.file_repository import FileGovernanceRepository


def _committed_governance_path() -> Path:
    return Path(__file__).resolve().parents[1] / "api" / "governance.json"


def _temp_repo(tmp_path: Path) -> FileGovernanceRepository:
    return FileGovernanceRepository(
        policy_path=tmp_path / "governance.json",
        history_path=tmp_path / "governance_history.jsonl",
        default_factory=lambda: gov.GovernancePolicy().model_dump(),
    )


def test_committed_governance_roundtrip_preserves_retention_fields() -> None:
    committed = json.loads(_committed_governance_path().read_text(encoding="utf-8"))
    dumped = gov.GovernancePolicy.model_validate(committed).model_dump()
    retention = dumped["log_retention"]
    assert retention["retention_days"] == 180
    assert retention["retention_days_high_risk"] == 365


def test_governance_policy_defaults_include_safe_retention_baselines() -> None:
    retention = gov.GovernancePolicy().model_dump()["log_retention"]
    assert retention["retention_days"] == 180
    assert retention["retention_days_high_risk"] == 365


def test_update_policy_empty_patch_preserves_retention_fields(tmp_path: Path) -> None:
    gov.set_governance_repository_factory(lambda: _temp_repo(tmp_path))
    updated = gov.update_policy({})
    retention = updated["log_retention"]
    assert retention["retention_days"] == 180
    assert retention["retention_days_high_risk"] == 365


def test_update_policy_unrelated_field_does_not_drop_high_risk_retention(tmp_path: Path) -> None:
    gov.set_governance_repository_factory(lambda: _temp_repo(tmp_path))
    updated = gov.update_policy({"version": "governance_v2", "updated_by": "auditor"})
    retention = updated["log_retention"]
    assert retention["retention_days"] == 180
    assert retention["retention_days_high_risk"] == 365


def test_rejects_unsafe_log_retention_values(tmp_path: Path) -> None:
    gov.set_governance_repository_factory(lambda: _temp_repo(tmp_path))
    with pytest.raises(ValueError):
        gov.update_policy({"log_retention": {"retention_days": 179}})

    with pytest.raises(ValueError):
        gov.update_policy({"log_retention": {"retention_days_high_risk": 179}})
