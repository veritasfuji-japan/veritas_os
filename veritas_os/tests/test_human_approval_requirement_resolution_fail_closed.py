"""Fast fail-closed coverage for Human Approval requirement resolution.

These tests use deterministic local promotion fixtures. They exercise the
independent-source / trusted-contract resolution boundary without network,
credentials, Human Approval creation, Bind authorization, or external effects.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from veritas_os.policy import human_approval_requirement_resolution as resolution
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    RECORDED_AT,
    _packet as promotion_authority_source,
)
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import (
    _contract as promotion_contract,
)


def _valid_chain():
    source = promotion_authority_source()
    contract = promotion_contract()
    resolved_at = RECORDED_AT + timedelta(seconds=1)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        source,
        contract,
        resolved_at,
    )
    return source, contract, resolved_at, packet


def _rehash(raw: dict) -> None:
    payload = dict(raw)
    payload.pop("human_approval_requirement_resolution_id")
    payload.pop("human_approval_requirement_resolution_hash")
    digest = resolution._digest(payload)
    raw["human_approval_requirement_resolution_hash"] = digest
    raw["human_approval_requirement_resolution_id"] = f"harr:v1:sha256:{digest}"


def test_promotion_source_roundtrip_uses_independent_source_identity() -> None:
    source, contract, _, packet = _valid_chain()

    verified = resolution.verify_human_approval_requirement_resolution_packet(
        packet,
        source,
        contract,
    )

    assert verified == packet
    assert (
        verified.source_authority_evidence_linkage_review_id
        == source.promotion_live_adapter_dry_run_authority_evidence_linkage_review_id
    )
    assert (
        verified.source_authority_evidence_linkage_review_hash
        == source.promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash
    )


def test_promotion_resolution_cannot_predate_verified_source() -> None:
    source = promotion_authority_source()
    contract = promotion_contract()

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_RESOLVED_BEFORE_SOURCE",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            source,
            contract,
            RECORDED_AT - timedelta(microseconds=1),
        )


def test_build_rejects_non_contract_after_source_verification() -> None:
    source = promotion_authority_source()

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_REQUIRED",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            source,
            object(),  # type: ignore[arg-type]
            RECORDED_AT + timedelta(seconds=1),
        )


def test_public_contract_requirement_helper_rejects_non_contract() -> None:
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_REQUIRED",
    ):
        resolution.requires_human_approval_for_action_contract(
            object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "value",
    [
        "not-a-timestamp",
        datetime(2026, 9, 20, 0, 0, 0),
    ],
)
def test_timestamp_requires_valid_timezone_aware_value(value) -> None:
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_TIMESTAMP_INVALID",
    ):
        resolution._timestamp(value)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        {1: "non-string-key"},
    ],
)
def test_canonical_json_rejects_non_json_or_nonfinite_values(value) -> None:
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_INVALID_JSON_VALUE",
    ):
        resolution._json(value)


def test_contract_binding_rejects_missing_intended_action() -> None:
    source = promotion_authority_source()
    contract = promotion_contract()
    invalid = source.model_copy(update={"execution_intent": {}})

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_INTENDED_ACTION_MISSING",
    ):
        resolution._validate_contract_binding(invalid, contract)


@pytest.mark.parametrize(
    "scope",
    [
        "bind-request",
        ["bind-request", "bind-request"],
        [],
    ],
)
def test_contract_binding_rejects_invalid_source_scope(scope) -> None:
    source = promotion_authority_source()
    contract = promotion_contract()
    bundle = source.authority_evidence_reference_bundle.model_copy(
        update={"bundle_scope": scope}
    )
    invalid = source.model_copy(
        update={"authority_evidence_reference_bundle": bundle}
    )

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_SOURCE_SCOPE_INVALID",
    ):
        resolution._validate_contract_binding(invalid, contract)


def test_contract_binding_rejects_scope_outside_trusted_contract() -> None:
    source = promotion_authority_source()
    contract = replace(promotion_contract(), allowed_scope=["different-scope"])

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_SCOPE_MISMATCH",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            source,
            contract,
            RECORDED_AT + timedelta(seconds=1),
        )


def test_contract_binding_rejects_action_contract_source_mismatch() -> None:
    source = promotion_authority_source()
    contract = replace(promotion_contract(), id="different-action")

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_ACTION_CONTRACT_SOURCE_MISMATCH",
    ):
        resolution.build_human_approval_requirement_resolution_packet(
            source,
            contract,
            RECORDED_AT + timedelta(seconds=1),
        )


def test_verify_rejects_packet_schema_extension() -> None:
    source, contract, _, packet = _valid_chain()
    raw = packet.model_dump(mode="json")
    raw["unexpected_field"] = True

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_PACKET_SCHEMA_INVALID",
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw,
            source,
            contract,
        )


def test_verify_rejects_requirement_state_inconsistency_before_hash_check() -> None:
    source, contract, _, packet = _valid_chain()
    raw = packet.model_dump(mode="json")
    raw["requirement_state"] = "NOT_REQUIRED_BY_ACTION_CONTRACT"

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_REQUIREMENT_STATE_INCONSISTENT",
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw,
            source,
            contract,
        )


def test_verify_rejects_hash_mismatch() -> None:
    source, contract, _, packet = _valid_chain()
    raw = packet.model_dump(mode="json")
    raw["requirement_reason"] = "tampered"

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_HASH_MISMATCH",
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw,
            source,
            contract,
        )


def test_verify_rejects_rehashed_semantic_substitution() -> None:
    source, contract, _, packet = _valid_chain()
    raw = packet.model_dump(mode="json")
    raw["requirement_reason"] = "tampered-but-rehashed"
    _rehash(raw)

    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError,
        match="HARR_SOURCE_RECONSTRUCTION_MISMATCH",
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw,
            source,
            contract,
        )
