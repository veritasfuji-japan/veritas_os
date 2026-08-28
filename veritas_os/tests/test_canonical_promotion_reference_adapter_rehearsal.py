"""Fail-closed tests for promotion-native reference adapter rehearsal."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_reference_adapter_rehearsal import (
    CanonicalPromotionReferenceAdapterRehearsalError,
    PLANNED_METHODS,
    SCOPE_LIMITATIONS,
    _results,
    _packet_hash,
    build_canonical_promotion_reference_adapter_in_memory_rehearsal_packet,
    verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet,
)
from veritas_os.policy.reference_adapter_rehearsal import (
    build_reference_adapter_in_memory_rehearsal_packet,
)
from veritas_os.tests.test_adapter_dry_run_fixture_result import (
    RESULTED_AT as LEGACY_RESULTED_AT,
    _packet as legacy_fixture_packet,
)
from veritas_os.tests.test_canonical_promotion_adapter_dry_run_fixture_result import (
    RESULTED_AT,
    _packet as promotion_fixture_packet,
)

REHEARSED_AT = RESULTED_AT + timedelta(seconds=1)
FIXTURE = {"scenario": "promotion-native-deterministic-reference-v1"}


def _packet():
    return build_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(
        promotion_fixture_packet(), FIXTURE, REHEARSED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["promotion_reference_rehearsal_hash"] = digest
    raw["promotion_reference_rehearsal_id"] = f"prar:v1:sha256:{digest}"


def _set(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_promotion_chain_exact_identity_and_no_effect_rehearsal() -> None:
    source = promotion_fixture_packet()
    packet = verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(
        _packet()
    )
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_id == intent.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.approval_context["required_human_approval"] is True
    assert "human_approval_receipt_ref" not in packet.model_dump(mode="json")
    assert len(packet.reference_rehearsal_results) == 7
    packet_json = packet.model_dump(mode="json")
    reconstructed_results = _results(source, FIXTURE)
    assert packet_json["reference_rehearsal_results"] == reconstructed_results
    assert all(
        isinstance(result["rehearsal_scope_limitations"], list)
        for result in reconstructed_results
    )
    assert [item.planned_adapter_method for item in packet.reference_rehearsal_results] == list(PLANNED_METHODS)
    for result in packet.reference_rehearsal_results:
        assert result.reference_adapter_instance_created is True
        assert result.reference_adapter_method_called is True
        assert result.live_adapter_instance_created is False
        assert result.live_adapter_method_called is False
        assert result.network_used is False
        assert result.filesystem_used is False
        assert result.external_effect_used is False
        assert result.bind_invoked is False
        assert result.authority_evidence_proven is False
        assert result.human_approval_proven is False
    forbidden = {
        "source_formation_hash", "source_eligibility_hash", "source_handoff_hash",
        "trusted_validation_context_hash", "validation_result_hash",
        "mapping_value_digest", "replay_summary", "apply",
        "verify_postconditions", "revert",
    }
    assert set(packet.model_dump(mode="json")).isdisjoint(forbidden)
    assert packet.scope_limitations == SCOPE_LIMITATIONS


def test_legacy_and_promotion_rehearsals_share_step_semantics() -> None:
    legacy = build_reference_adapter_in_memory_rehearsal_packet(
        legacy_fixture_packet(), FIXTURE, LEGACY_RESULTED_AT + timedelta(seconds=1)
    )
    promotion = _packet()
    fields = (
        "ordinal", "planned_adapter_method", "rehearsal_mode",
        "reference_adapter_instance_created", "reference_adapter_method_called",
        "live_adapter_instance_created", "live_adapter_method_called",
        "network_used", "filesystem_used", "external_effect_used",
        "matched_expected_output_ref",
    )
    assert [tuple(getattr(item, field) for field in fields) for item in promotion.reference_rehearsal_results] == [
        tuple(getattr(item, field) for field in fields) for item in legacy.reference_rehearsal_results
    ]
    invariant_summary_fields = ("method", "ordinal", "mode")
    assert [
        tuple(item.output_summary[key] for key in invariant_summary_fields)
        for item in promotion.reference_rehearsal_results
    ] == [
        tuple(item.output_summary[key] for key in invariant_summary_fields)
        for item in legacy.reference_rehearsal_results
    ]
    for item in promotion.reference_rehearsal_results:
        assert (
            item.output_summary["target_system"]
            == promotion.execution_intent["target_system"]
        )
        assert (
            item.output_summary["target_resource"]
            == promotion.execution_intent["target_resource"]
        )
    for item in legacy.reference_rehearsal_results:
        assert (
            item.output_summary["target_system"]
            == legacy.execution_intent["target_system"]
        )
        assert (
            item.output_summary["target_resource"]
            == legacy.execution_intent["target_resource"]
        )


@pytest.mark.parametrize(("path", "value"), [
    ("source_adapter_dry_run_fixture_result_id", "padr:v1:sha256:" + "0" * 64),
    ("source_adapter_dry_run_fixture_result_hash", "0" * 64),
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
    ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
    ("adapter_contract_hash", "0" * 64),
    ("planned_steps.0.ordinal", 2),
    ("fixture_step_results.0.ordinal", 2),
    ("fixture_result_digest", "0" * 64),
    ("reference_rehearsal_results.0.planned_adapter_method", "snapshot"),
    ("reference_rehearsal_results.0.output_summary.method", "apply"),
    ("reference_rehearsal_results.0.output_digest", "0" * 64),
    ("reference_rehearsal_results.0.live_adapter_instance_created", True),
    ("reference_rehearsal_results.0.live_adapter_method_called", True),
    ("reference_rehearsal_results.0.network_used", True),
    ("reference_rehearsal_results.0.filesystem_used", True),
    ("reference_rehearsal_results.0.external_effect_used", True),
    ("reference_rehearsal_results.0.bind_invoked", True),
    ("reference_rehearsal_results.0.bind_receipt_created", True),
    ("reference_rehearsal_results.0.human_approval_proven", True),
    ("reference_rehearsal_results.0.authority_evidence_proven", True),
    ("approval_context.required_human_approval", False),
    ("policy_lineage", {}),
    ("local_rehearsal_checks.no_network", False),
    ("future_requirements.apply_still_forbidden", False),
    ("scope_limitations", []),
])
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionReferenceAdapterRehearsalError):
        verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(raw)


@pytest.mark.parametrize("mutation", ["reorder_fixture", "reorder_rehearsal", "drop_rehearsal", "insert_apply"])
def test_order_count_and_forbidden_method_fail_closed(mutation: str) -> None:
    raw = _packet().model_dump(mode="json")
    key = "fixture_step_results" if mutation == "reorder_fixture" else "reference_rehearsal_results"
    if mutation.startswith("reorder"):
        raw[key][0:2] = reversed(raw[key][0:2])
    elif mutation == "drop_rehearsal":
        raw[key].pop()
    else:
        inserted = deepcopy(raw[key][0])
        inserted["planned_adapter_method"] = "apply"
        raw[key].append(inserted)
    _rehash(raw)
    with pytest.raises(CanonicalPromotionReferenceAdapterRehearsalError):
        verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(raw)


def test_time_and_packet_identity_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["rehearsed_at"] = (RESULTED_AT - timedelta(seconds=1)).isoformat()
    _rehash(raw)
    with pytest.raises(CanonicalPromotionReferenceAdapterRehearsalError):
        verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(raw)
    raw = _packet().model_dump(mode="json")
    raw["promotion_reference_rehearsal_hash"] = "0" * 64
    with pytest.raises(CanonicalPromotionReferenceAdapterRehearsalError):
        verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(raw)
