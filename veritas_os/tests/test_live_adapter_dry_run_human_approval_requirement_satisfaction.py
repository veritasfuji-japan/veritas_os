"""v0.3 tests for contract-bound Human Approval requirement satisfaction."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.human_approval_requirement_resolution import (
    build_human_approval_requirement_resolution_packet,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    build_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    build_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_linkage import (
    build_live_adapter_dry_run_human_approval_linkage_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_requirement_satisfaction import (
    LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
    build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet,
    verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_authority_evidence_linkage import (
    _packet as authority_source_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT as GATE_RECORDED_AT,
    _decision as gate_decision,
)
from veritas_os.tests.test_live_adapter_dry_run_final_bind_authorization_readiness import (
    RECORDED_AT as FINAL_RECORDED_AT,
    _decision as final_decision,
)
from veritas_os.tests.test_live_adapter_dry_run_human_approval_linkage import (
    RECORDED_AT as HUMAN_RECORDED_AT,
    _bundle as human_bundle,
)


SATISFACTION_RECORDED_AT = HUMAN_RECORDED_AT + timedelta(milliseconds=500)


def _contract(source, *, required: bool) -> ActionClassContract:
    scope = list(source.authority_evidence_reference_bundle.bundle_scope)
    return ActionClassContract(
        id=source.execution_intent["intended_action"],
        version="1",
        domain="benchmark",
        action_class="benchmark_action",
        description="v0.3 approval requirement compatibility contract",
        declared_intent="exercise native dry-run bind governance",
        allowed_scope=scope,
        prohibited_scope=["benchmark:admin"],
        authority_sources=["benchmark-authority"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"level": "low"},
        human_approval_rules={
            "required": required,
            "minimum_approvals": 1 if required else 0,
        },
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="deny",
        metadata={"regulated": False},
    )


def _build_satisfaction(*, required: bool):
    source = authority_source_packet()
    contract = _contract(source, required=required)
    resolution = build_human_approval_requirement_resolution_packet(
        source,
        contract,
        HUMAN_RECORDED_AT,
    )
    linkage = (
        build_live_adapter_dry_run_human_approval_linkage_review_packet(
            source,
            human_bundle(source),
            HUMAN_RECORDED_AT,
        )
        if required
        else None
    )
    packet = build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
        source,
        resolution,
        contract,
        linkage,
        SATISFACTION_RECORDED_AT,
    )
    return source, contract, resolution, linkage, packet


def _build_gate(satisfaction, source, contract):
    final = build_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        satisfaction,
        final_decision(),
        FINAL_RECORDED_AT,
        expected_source=source,
        expected_contract=contract,
    )
    gate = build_live_adapter_dry_run_bind_authorization_gate_review_packet(
        final,
        gate_decision(),
        GATE_RECORDED_AT,
        expected_source=source,
        expected_contract=contract,
    )
    return final, gate


def test_not_required_path_reaches_native_gate_without_fabricated_approval() -> None:
    source, contract, _, linkage, satisfaction = _build_satisfaction(required=False)

    assert linkage is None
    assert satisfaction.required_human_approval is False
    assert satisfaction.requirement_state == "NOT_REQUIRED_BY_ACTION_CONTRACT"
    assert (
        satisfaction.requirement_satisfaction_state
        == "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT"
    )
    assert satisfaction.source_required_human_approval_linkage_review_packet is None
    assert (
        satisfaction.human_approval_reference_bundle["human_approval_references"] == []
    )
    assert satisfaction.human_approval_created is False
    assert satisfaction.execution_authority_created is False
    assert satisfaction.bind_authorization_created is False

    final, gate = _build_gate(satisfaction, source, contract)

    assert final.final_readiness_state == "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    assert gate.gate_review_state == "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
    assert gate.human_approval_created is False
    assert gate.execution_authority_created is False
    assert gate.bind_authorization_created is False
    assert gate.bind_invoked is False
    assert gate.request_dispatched is False
    assert gate.network_used is False


def test_required_path_preserves_existing_verified_linkage_and_reaches_gate() -> None:
    source, contract, _, linkage, satisfaction = _build_satisfaction(required=True)

    assert linkage is not None
    assert satisfaction.required_human_approval is True
    assert satisfaction.requirement_state == "REQUIRED"
    assert (
        satisfaction.requirement_satisfaction_state
        == "SATISFIED_BY_VERIFIED_HUMAN_APPROVAL_LINKAGE"
    )
    assert (
        satisfaction.source_required_human_approval_linkage_review_hash
        == linkage.live_adapter_dry_run_human_approval_linkage_review_hash
    )
    assert satisfaction.human_approval_reference_bundle["human_approval_references"]

    final, gate = _build_gate(satisfaction, source, contract)

    assert final.final_readiness_state == "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    assert gate.gate_review_state == "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"


def test_not_required_contract_rejects_unexpected_human_approval_linkage() -> None:
    source = authority_source_packet()
    contract = _contract(source, required=False)
    resolution = build_human_approval_requirement_resolution_packet(
        source,
        contract,
        HUMAN_RECORDED_AT,
    )
    linkage = build_live_adapter_dry_run_human_approval_linkage_review_packet(
        source,
        human_bundle(source),
        HUMAN_RECORDED_AT,
    )

    with pytest.raises(
        LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
        match="LADHARS_APPROVAL_LINKAGE_UNEXPECTED_FOR_CONTRACT",
    ):
        build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
            source,
            resolution,
            contract,
            linkage,
            SATISFACTION_RECORDED_AT,
        )


def test_required_contract_rejects_missing_human_approval_linkage() -> None:
    source = authority_source_packet()
    contract = _contract(source, required=True)
    resolution = build_human_approval_requirement_resolution_packet(
        source,
        contract,
        HUMAN_RECORDED_AT,
    )

    with pytest.raises(
        LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
        match="LADHARS_REQUIRED_LINKAGE_MISSING",
    ):
        build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
            source,
            resolution,
            contract,
            None,
            SATISFACTION_RECORDED_AT,
        )


def test_contract_snapshot_tamper_fails_closed() -> None:
    source, contract, _, _, satisfaction = _build_satisfaction(required=False)
    raw = satisfaction.model_dump(mode="json")
    raw["action_contract_snapshot"]["id"] = "tampered.action"

    with pytest.raises(
        LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
        match="LADHARS_EXPECTED_BINDING_MISMATCH",
    ):
        verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
            raw, expected_source=source, expected_contract=contract
        )


def test_packet_hash_tamper_fails_closed() -> None:
    source, contract, _, _, satisfaction = _build_satisfaction(required=False)
    raw = deepcopy(satisfaction.model_dump(mode="json"))
    raw["live_adapter_dry_run_human_approval_linkage_review_hash"] = "0" * 64

    with pytest.raises(
        LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
        match="LADHARS_HASH_MISMATCH",
    ):
        verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
            raw, expected_source=source, expected_contract=contract
        )
