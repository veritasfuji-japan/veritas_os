"""Fail-closed tests for promotion-native live-request readiness."""

from __future__ import annotations

from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_readiness import (
    SCOPE_LIMITATIONS,
    CanonicalPromotionLiveAdapterDryRunReadinessError,
    _packet_hash,
    build_canonical_promotion_live_adapter_dry_run_request_readiness_packet,
    verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet,
)
from veritas_os.tests.test_canonical_promotion_reference_adapter_rehearsal import (
    REHEARSED_AT,
    _packet as rehearsal_packet,
)

EVALUATED_AT = REHEARSED_AT + timedelta(seconds=1)


def _packet():
    return build_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
        rehearsal_packet(), EVALUATED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_readiness_hash"] = digest
    raw["promotion_live_adapter_dry_run_readiness_id"] = f"pladr:v1:sha256:{digest}"


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_preserves_exact_identity_without_proof_or_effect() -> None:
    source = rehearsal_packet()
    packet = verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
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
    assert packet.planned_steps == source.planned_steps
    assert packet.fixture_step_results == source.fixture_step_results
    assert packet.reference_rehearsal_results == tuple(
        item.model_dump(mode="json") for item in source.reference_rehearsal_results
    )
    assert packet.approval_context == source.approval_context
    assert packet.approval_context["required_human_approval"] is True
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    assert packet.request_created is False
    assert packet.request_dispatched is False
    assert packet.network_used is False
    assert packet.filesystem_used is False
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
        ("source_reference_rehearsal_id", "prar:v1:sha256:" + "0" * 64),
        ("source_reference_rehearsal_hash", "0" * 64),
        ("source_adapter_dry_run_fixture_result_id", "padr:v1:sha256:" + "0" * 64),
        ("source_adapter_dry_run_fixture_result_hash", "0" * 64),
        ("source_adapter_dry_run_plan_id", "padp:v1:sha256:" + "0" * 64),
        ("source_adapter_dry_run_plan_hash", "0" * 64),
        ("source_adapter_contract_selection_hash", "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
        ("source_pre_bind_validation_hash", "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("execution_intent.actor_identity", "substitute"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_descriptor.target_system", "substitute"),
        ("adapter_contract_descriptor.target_resource_scope", "substitute"),
        ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("planned_steps.0.ordinal", 2),
        ("planned_step_digest", "0" * 64),
        ("fixture_step_results.0.ordinal", 2),
        ("fixture_result_digest", "0" * 64),
        ("reference_rehearsal_results.0.output_digest", "0" * 64),
        ("reference_rehearsal_result_digest", "0" * 64),
        ("approval_context.required_human_approval", False),
        ("policy_lineage", {}),
        ("readiness_check_digest", "0" * 64),
        ("local_readiness_checks.no_network", False),
        ("future_requirements.apply_still_forbidden", False),
        ("scope_limitations", []),
        ("human_approval_proven", True),
        ("authority_evidence_proven", True),
        ("request_dispatched", True),
        ("network_used", True),
        ("external_effect_used", True),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)


def test_malformed_source_time_order_and_check_order_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_reference_rehearsal_packet"] = {}
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["readiness_evaluated_at"] = (REHEARSED_AT - timedelta(seconds=1)).isoformat()
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["readiness_checks"][0:2] = reversed(raw["readiness_checks"][0:2])
    _rehash(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)


def test_packet_identity_and_extra_proof_claims_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["promotion_live_adapter_dry_run_readiness_hash"] = "0" * 64
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
        verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)

    for claim in (
        "human_approval_receipt_ref",
        "authority_revalidated",
        "live_adapter_invoked",
    ):
        raw = _packet().model_dump(mode="json")
        raw[claim] = True
        _rehash(raw)
        with pytest.raises(CanonicalPromotionLiveAdapterDryRunReadinessError):
            verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
                raw
            )
