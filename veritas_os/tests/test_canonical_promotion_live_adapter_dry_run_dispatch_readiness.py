"""Fail-closed tests for promotion-native dispatch-readiness evidence."""

from __future__ import annotations

from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_dispatch_readiness import (
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunDispatchReadinessError,
    _packet_hash,
    build_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet,
    verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_request import (
    REQUESTED_AT,
    _packet as request_packet,
)

EVALUATED_AT = REQUESTED_AT + timedelta(seconds=1)


def _packet():
    return build_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
        request_packet(), EVALUATED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_dispatch_readiness_hash"] = digest
    raw["promotion_live_adapter_dry_run_dispatch_readiness_id"] = (
        f"pladrdr:v1:sha256:{digest}"
    )


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_preserves_exact_identity_lineage_and_no_effects() -> None:
    source = request_packet()
    packet = verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
        _packet()
    )
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_id == intent.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.adapter_contract_version == source.adapter_contract_version
    assert packet.approval_context == source.approval_context
    assert packet.approval_context["required_human_approval"] is True
    assert packet.policy_lineage == source.policy_lineage
    assert packet.source_promotion_hash == source.source_promotion_hash
    assert packet.source_readiness_hash == source.source_readiness_hash
    assert (
        packet.source_pre_bind_validation_hash == source.source_pre_bind_validation_hash
    )
    assert (
        packet.source_reference_rehearsal_hash == source.source_reference_rehearsal_hash
    )
    assert packet.request_dispatch_state == "NOT_DISPATCHED"
    assert packet.ready_for_promotion_native_endpoint_allowlist_evaluation is True
    assert packet.ready_for_network_dispatch is False
    assert packet.ready_for_real_bind is False
    assert packet.execution_authorized is False
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    for check in packet.dispatch_readiness_checks:
        assert all(getattr(check, field) is False for field in EFFECT_FIELDS)

    legacy = {
        "source_formation_hash",
        "source_eligibility_hash",
        "source_handoff_hash",
        "evidence_lineage",
        "human_approval_receipt",
    }
    assert set(packet.model_dump(mode="json")).isdisjoint(legacy)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("execution_intent.actor_identity", "substitute"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_descriptor.target_system", "substitute"),
        ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("adapter_contract_version", "substitute"),
        ("source_promotion_hash", "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_pre_bind_validation_hash", "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
        ("source_adapter_contract_selection_hash", "0" * 64),
        ("source_adapter_dry_run_plan_hash", "0" * 64),
        ("source_adapter_dry_run_fixture_result_hash", "0" * 64),
        ("source_reference_rehearsal_hash", "0" * 64),
        ("approval_context.required_human_approval", False),
        ("policy_lineage", {}),
        ("dispatch_readiness_checks.0.ordinal", 2),
        ("dispatch_readiness_checks.0.network_used", True),
        ("dispatch_readiness_check_digest", "0" * 64),
        ("future_dispatch_requirements.0.satisfied_by_this_packet", True),
        ("future_dispatch_requirement_digest", "0" * 64),
        ("ready_for_network_dispatch", True),
        ("human_approval_proven", True),
        ("authority_evidence_proven", True),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunDispatchReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(raw)


def test_source_time_hash_id_and_shortcut_claims_fail_closed() -> None:
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunDispatchReadinessError):
        build_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
            request_packet(), REQUESTED_AT - timedelta(seconds=1)
        )

    raw = _packet().model_dump(mode="json")
    raw["source_live_adapter_dry_run_request_packet"] = {}
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunDispatchReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(raw)

    for field, value in (
        ("promotion_live_adapter_dry_run_dispatch_readiness_hash", "0" * 64),
        (
            "promotion_live_adapter_dry_run_dispatch_readiness_id",
            "pladrdr:v1:sha256:" + "0" * 64,
        ),
        ("verified", True),
        ("dispatch_ready", True),
    ):
        raw = _packet().model_dump(mode="json")
        raw[field] = value
        with pytest.raises(CanonicalPromotionLiveAdapterDryRunDispatchReadinessError):
            verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
                raw
            )
