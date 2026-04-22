"""Adapter contract tests for bind-core abstractions."""

from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import PolicyBundlePromotionAdapter
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
