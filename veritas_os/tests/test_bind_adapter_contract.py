"""Adapter contract tests for bind-core abstractions."""

from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import (
    ComplianceConfigUpdateAdapter,
    PolicyBundlePromotionAdapter,
)
from veritas_os.policy.bind_core import BindAdapterContract


class _IncompleteAdapter(BindAdapterContract):
    pass


def test_bind_adapter_contract_requires_all_methods() -> None:
    with pytest.raises(TypeError):
        _IncompleteAdapter()


def test_policy_bundle_promotion_adapter_satisfies_contract(tmp_path) -> None:
    adapter = PolicyBundlePromotionAdapter(
        pointer_path=tmp_path / "runtime" / "active_bundle.json",
        allowed_root=tmp_path,
    )
    assert isinstance(adapter, BindAdapterContract)

    intent = ExecutionIntent(
        execution_intent_id="ei-1",
        decision_id="dec-1",
        request_id="req-1",
        policy_snapshot_id="snap-1",
        actor_identity="ops",
        target_system="governance",
        target_resource=str(tmp_path),
        intended_action="promote_policy_bundle",
        decision_hash="a" * 64,
        decision_ts="2026-04-20T00:00:00Z",
    )
    snapshot = adapter.snapshot()
    assert isinstance(adapter.fingerprint_state(snapshot), str)
    assert isinstance(adapter.validate_authority(intent, snapshot), bool)


def test_compliance_config_update_adapter_satisfies_contract() -> None:
    state = {"eu_ai_act_mode": False, "safety_threshold": 0.8}

    def _reader() -> dict[str, float | bool]:
        return dict(state)

    def _updater(*, eu_ai_act_mode: bool, safety_threshold: float):
        state["eu_ai_act_mode"] = eu_ai_act_mode
        state["safety_threshold"] = safety_threshold
        return dict(state)

    adapter = ComplianceConfigUpdateAdapter(
        config_reader=_reader,
        config_updater=_updater,
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.75},
    )
    assert isinstance(adapter, BindAdapterContract)

    intent = ExecutionIntent(
        execution_intent_id="ei-2",
        decision_id="dec-2",
        request_id="req-2",
        policy_snapshot_id="snap-2",
        actor_identity="ops",
        target_system="compliance",
        target_resource="compliance/config",
        intended_action="update_compliance_config",
        decision_hash="b" * 64,
        decision_ts="2026-04-20T00:00:00Z",
        approval_context={"compliance_config_update_approved": True},
    )
    snapshot = adapter.snapshot()
    assert isinstance(adapter.fingerprint_state(snapshot), str)
    assert isinstance(adapter.validate_authority(intent, snapshot), bool)
