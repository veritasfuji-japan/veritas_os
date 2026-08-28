"""Fail-closed tests for the promotion-native dry-run request boundary."""

from __future__ import annotations

from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_request import (
    SCOPE_LIMITATIONS,
    CanonicalPromotionLiveAdapterDryRunRequestError,
    _packet_hash,
    build_canonical_promotion_live_adapter_dry_run_request_packet,
    verify_canonical_promotion_live_adapter_dry_run_request_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_readiness import (
    EVALUATED_AT,
    _packet as readiness_packet,
)

REQUESTED_AT = EVALUATED_AT + timedelta(seconds=1)


def _packet():
    return build_canonical_promotion_live_adapter_dry_run_request_packet(
        readiness_packet(), REQUESTED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_request_hash"] = digest
    raw["promotion_live_adapter_dry_run_request_id"] = f"pladrq:v1:sha256:{digest}"


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_preserves_identity_and_constructs_without_dispatch() -> None:
    source = readiness_packet()
    packet = verify_canonical_promotion_live_adapter_dry_run_request_packet(_packet())
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_id == intent.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.planned_steps == source.planned_steps
    assert packet.fixture_step_results == source.fixture_step_results
    assert packet.reference_rehearsal_results == tuple(
        item.model_dump(mode="json") for item in source.reference_rehearsal_results
    )
    assert packet.readiness_checks == tuple(
        item.model_dump(mode="json") for item in source.readiness_checks
    )
    assert packet.approval_context == source.approval_context
    assert packet.approval_context["required_human_approval"] is True
    assert packet.request_created is True
    assert packet.request_dispatched is False
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    assert packet.network_used is False
    assert packet.credential_accessed is False
    assert packet.endpoint_contacted is False
    assert packet.webhook_contacted is False
    assert packet.external_effect_used is False
    assert packet.scope_limitations == SCOPE_LIMITATIONS

    forbidden = {
        "source_formation_hash",
        "source_eligibility_hash",
        "source_handoff_hash",
        "trusted_validation_context_hash",
        "validation_result_hash",
        "mapping_value_digest",
        "source_to_execution_intent_mapping",
        "field_mapping_proof",
        "required_field_presence",
        "evidence_lineage",
        "replay_summary",
        "human_approval_receipt_ref",
        "human_approval_receipt_hash",
    }
    assert set(packet.model_dump(mode="json")).isdisjoint(forbidden)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_live_adapter_dry_run_readiness_hash", "0" * 64),
        ("source_reference_rehearsal_hash", "0" * 64),
        ("source_adapter_dry_run_fixture_result_hash", "0" * 64),
        ("source_adapter_dry_run_plan_hash", "0" * 64),
        ("source_adapter_contract_selection_hash", "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("execution_intent.actor_identity", "substitute"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_descriptor.target_system", "substitute"),
        ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("request_descriptor.target_system", "substitute"),
        ("request_descriptor.action_name", "substitute"),
        ("request_descriptor.dry_run_only", False),
        ("request_descriptor.no_apply", False),
        ("request_descriptor.no_commit", False),
        ("request_descriptor.credential_material_included", True),
        ("request_descriptor.endpoint_material_included", True),
        ("request_descriptor.network_used", True),
        ("request_dispatched", True),
        ("request_dispatch_state", "DISPATCHED"),
        ("planned_steps.0.ordinal", 2),
        ("fixture_step_results.0.ordinal", 2),
        ("reference_rehearsal_results.0.output_digest", "0" * 64),
        ("readiness_checks.0.ordinal", 2),
        ("approval_context.required_human_approval", False),
        ("policy_lineage", {}),
        ("dispatch_precondition_digest", "0" * 64),
        ("request_construction_checks.no_network", False),
        (
            "future_live_adapter_dry_run_dispatch_requirements.apply_still_forbidden",
            False,
        ),
        ("scope_limitations", []),
        ("human_approval_proven", True),
        ("authority_evidence_proven", True),
        ("credential_accessed", True),
        ("endpoint_contacted", True),
        ("webhook_contacted", True),
        ("network_used", True),
        ("external_effect_used", True),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRequestError):
        verify_canonical_promotion_live_adapter_dry_run_request_packet(raw)


def test_malformed_source_time_order_precondition_order_and_extra_claim_fail() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_live_adapter_dry_run_readiness_packet"] = {}
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRequestError):
        verify_canonical_promotion_live_adapter_dry_run_request_packet(raw)

    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRequestError):
        build_canonical_promotion_live_adapter_dry_run_request_packet(
            readiness_packet(), EVALUATED_AT - timedelta(seconds=1)
        )

    raw = _packet().model_dump(mode="json")
    raw["dispatch_preconditions"][0:2] = reversed(raw["dispatch_preconditions"][0:2])
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRequestError):
        verify_canonical_promotion_live_adapter_dry_run_request_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["caller_declared_verified"] = True
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRequestError):
        verify_canonical_promotion_live_adapter_dry_run_request_packet(raw)
