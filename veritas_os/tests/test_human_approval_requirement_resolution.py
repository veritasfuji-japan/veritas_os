from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy import human_approval_requirement_resolution as resolution


def _contract(*, required: bool, minimum_approvals: int = 0, level: str = "low") -> ActionClassContract:
    return ActionClassContract(
        id="payments.transfer",
        version="1",
        domain="payments",
        action_class="payment_transfer",
        description="benchmark contract",
        declared_intent="transfer funds",
        allowed_scope=["payments:transfer"],
        prohibited_scope=["payments:admin"],
        authority_sources=["benchmark-authority"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"level": level},
        human_approval_rules={
            "required": required,
            "minimum_approvals": minimum_approvals,
        },
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="deny",
        metadata={"regulated": False},
    )


def _source() -> SimpleNamespace:
    result = SimpleNamespace(
        all_required_references_present=True,
        all_references_structurally_linked=True,
        all_binding_claims_matched=True,
    )
    return SimpleNamespace(
        fail_closed=False,
        authority_evidence_linkage_result=result,
        live_adapter_dry_run_authority_evidence_linkage_review_id="authority-linkage-1",
        live_adapter_dry_run_authority_evidence_linkage_review_hash="a" * 64,
        execution_intent={"intended_action": "payments.transfer"},
        execution_intent_id="execution-intent-1",
        execution_intent_hash="b" * 64,
        authority_evidence_reference_bundle={
            "bundle_scope": ["payments:transfer"]
        },
    )


def _patch_source_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resolution,
        "verify_live_adapter_dry_run_authority_evidence_linkage_review_packet",
        lambda value: value,
    )


def test_explicit_required_contract_resolves_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source_verifier(monkeypatch)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        _source(),
        _contract(required=True),
        datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc),
    )

    assert packet.required_human_approval is True
    assert packet.requirement_state == "REQUIRED"
    assert packet.human_approval_created is False
    assert packet.bind_authorization_created is False
    assert packet.network_used is False
    assert resolution.verify_human_approval_requirement_resolution_packet(packet) == packet


def test_not_required_contract_resolves_without_fabricated_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source_verifier(monkeypatch)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        _source(),
        _contract(required=False),
        datetime(2026, 9, 5, 0, 1, tzinfo=timezone.utc),
    )

    assert packet.required_human_approval is False
    assert packet.requirement_state == "NOT_REQUIRED_BY_ACTION_CONTRACT"
    assert packet.human_approval_created is False
    assert packet.execution_authority_created is False
    assert packet.bind_invoked is False
    assert packet.external_effect_occurred is False


def test_high_irreversibility_with_minimum_approval_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source_verifier(monkeypatch)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        _source(),
        _contract(required=False, minimum_approvals=1, level="high"),
        datetime(2026, 9, 5, 0, 2, tzinfo=timezone.utc),
    )
    assert packet.requirement_state == "REQUIRED"


def test_contract_action_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source_verifier(monkeypatch)
    contract = _contract(required=False)
    mismatched = ActionClassContract(
        **{**contract.to_dict(), "id": "payments.refund"}
    )
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_SOURCE_MISMATCH",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            _source(),
            mismatched,
            datetime(2026, 9, 5, 0, 3, tzinfo=timezone.utc),
        )


def test_scope_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source_verifier(monkeypatch)
    source = _source()
    source.authority_evidence_reference_bundle = {"bundle_scope": ["payments:admin"]}
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_SCOPE_MISMATCH",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            source,
            _contract(required=False),
            datetime(2026, 9, 5, 0, 4, tzinfo=timezone.utc),
        )


def test_hash_tamper_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source_verifier(monkeypatch)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        _source(),
        _contract(required=False),
        datetime(2026, 9, 5, 0, 5, tzinfo=timezone.utc),
    )
    raw = packet.model_dump(mode="python")
    raw["requirement_reason"] = "tampered"
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_HASH_MISMATCH",
    ):
        resolution.verify_human_approval_requirement_resolution_packet(raw)
