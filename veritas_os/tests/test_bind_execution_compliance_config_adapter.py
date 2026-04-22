"""Unit tests for ComplianceConfigUpdateAdapter behavior."""

from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import ComplianceConfigUpdateAdapter


def _intent(*, approved: bool = True) -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="ei-compliance-adapter",
        decision_id="dec-compliance-adapter",
        request_id="req-compliance-adapter",
        policy_snapshot_id="snapshot-1",
        actor_identity="operator",
        target_system="compliance",
        target_resource="compliance/config",
        intended_action="update_compliance_config",
        decision_hash="e" * 64,
        decision_ts="2026-04-20T00:00:00Z",
        approval_context={"compliance_config_update_approved": approved},
    )


def test_compliance_adapter_snapshot_and_fingerprint() -> None:
    state = {"eu_ai_act_mode": False, "safety_threshold": 0.8}

    def _reader() -> dict[str, bool | float]:
        return dict(state)

    def _updater(*, eu_ai_act_mode: bool, safety_threshold: float):
        state["eu_ai_act_mode"] = eu_ai_act_mode
        state["safety_threshold"] = safety_threshold
        return dict(state)

    adapter = ComplianceConfigUpdateAdapter(
        config_reader=_reader,
        config_updater=_updater,
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.77},
    )
    snapshot = adapter.snapshot()
    assert snapshot == {"config": state}
    assert adapter.fingerprint_state(snapshot)


def test_compliance_adapter_authority_constraint_risk_signals() -> None:
    state = {"eu_ai_act_mode": False, "safety_threshold": 0.8}
    adapter = ComplianceConfigUpdateAdapter(
        config_reader=lambda: dict(state),
        config_updater=lambda **kwargs: dict(kwargs),
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.77},
    )
    snapshot = adapter.snapshot()
    assert adapter.validate_authority(_intent(approved=True), snapshot) is True
    assert adapter.validate_authority(_intent(approved=False), snapshot) is False
    constraints = adapter.validate_constraints(_intent(), snapshot)
    assert constraints == {
        "patch_is_dict": True,
        "snapshot_has_config": True,
        "safety_threshold_in_range": True,
        "contains_supported_fields": True,
    }
    assert adapter.assess_runtime_risk(_intent(), snapshot) is True


def test_compliance_adapter_apply_verify_and_revert() -> None:
    state = {"eu_ai_act_mode": False, "safety_threshold": 0.8}

    def _updater(*, eu_ai_act_mode: bool, safety_threshold: float):
        state["eu_ai_act_mode"] = eu_ai_act_mode
        state["safety_threshold"] = safety_threshold
        return dict(state)

    adapter = ComplianceConfigUpdateAdapter(
        config_reader=lambda: dict(state),
        config_updater=_updater,
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.7},
    )
    snapshot = adapter.snapshot()
    assert adapter.apply(_intent(), snapshot) is True
    assert adapter.verify_postconditions(_intent(), snapshot) is True
    assert state["eu_ai_act_mode"] is True
    assert adapter.revert(_intent(), snapshot) is True
    assert state == {"eu_ai_act_mode": False, "safety_threshold": 0.8}


def test_compliance_adapter_apply_validation_failure() -> None:
    adapter = ComplianceConfigUpdateAdapter(
        config_reader=lambda: {"eu_ai_act_mode": False, "safety_threshold": 0.8},
        config_updater=lambda **kwargs: (_ for _ in ()).throw(ValueError("bad threshold")),
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 1.5},
    )
    with pytest.raises(ValueError, match="COMPLIANCE_CONFIG_VALIDATION_FAILED"):
        adapter.apply(_intent(), adapter.snapshot())


def test_compliance_adapter_revert_failure_on_invalid_snapshot() -> None:
    adapter = ComplianceConfigUpdateAdapter(
        config_reader=lambda: {"eu_ai_act_mode": False, "safety_threshold": 0.8},
        config_updater=lambda **kwargs: dict(kwargs),
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.75},
    )
    assert adapter.revert(_intent(), {"config": None}) is False
