"""Fail-closed tests for the promotion-native Bind gate review boundary."""

from __future__ import annotations

from datetime import timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    OUTCOMES,
    CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError,
    build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness import (
    RECORDED_AT as SOURCE_AT,
    _packet as source_packet,
)

RECORDED_AT = SOURCE_AT + timedelta(seconds=1)


def _decision(*, passed: bool = True, **changes):
    value = {
        "bind_authorization_gate_review_decision_id": "gate-review:1",
        "reviewer_id": "operator:alice",
        "reviewer_role": "bind-gate-reviewer",
        "reviewer_attestation": "I reviewed only the local prerequisite gate.",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_outcome": OUTCOMES[0] if passed else OUTCOMES[1],
        "review_reason": "verified final readiness packet",
        **{name: True for name in ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _packet(*, passed=True, decision=None):
    return build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source_packet(), decision or _decision(passed=passed), RECORDED_AT
    )


def test_pass_and_fail_route_without_authority_or_effects():
    passed = _packet()
    failed = _packet(passed=False)
    assert verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(passed) == passed
    assert verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(failed) == failed
    assert passed.ready_for_promotion_native_fresh_verified_source_gate
    assert not passed.fail_closed
    assert not failed.ready_for_promotion_native_fresh_verified_source_gate
    assert failed.fail_closed
    assert passed.gate_review_state == OUTCOMES[0]
    assert failed.gate_review_state == OUTCOMES[1]
    assert not any(getattr(passed, name) for name in EFFECT_FIELDS)
    assert passed.bind_context_hash_derived is False


def test_exact_typed_preservation_and_json_round_trip():
    source = source_packet()
    packet = _packet()
    for name in source.model_fields:
        if name in packet.model_fields and name not in {
            "future_bind_authorization_requirements",
            "future_bind_authorization_requirement_digest",
        }:
            assert getattr(packet, name) == getattr(source, name)
    raw = packet.model_dump(mode="json")
    assert verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(raw) == packet
    assert packet.source_final_bind_authorization_readiness_packet == source.model_dump(mode="json")


def test_decision_is_bound_to_context_and_packet_hash():
    first = _packet()
    second = _packet(decision=_decision(reviewer_id="operator:bob", review_reason="independent review"))
    assert first.bind_authorization_gate_review_decision_digest != second.bind_authorization_gate_review_decision_digest
    assert first.bind_authorization_gate_review_context_digest != second.bind_authorization_gate_review_context_digest
    assert first.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash != second.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash


def test_remaining_requirements_are_exact_and_unsatisfied():
    packet = _packet()
    assert tuple(item.name for item in packet.future_bind_authorization_requirements) == AUTHORIZATION_REQUIREMENTS
    assert tuple(item.name for item in packet.future_bind_invocation_requirements) == INVOCATION_REQUIREMENTS
    assert all(not item.satisfied_by_this_packet for item in (*packet.future_bind_authorization_requirements, *packet.future_bind_invocation_requirements))


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_false_acknowledgement_fails(field):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: False}))


@pytest.mark.parametrize("field", ["reviewer_id", "reviewer_role", "reviewer_attestation"])
def test_empty_reviewer_metadata_fails(field):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: ""}))


@pytest.mark.parametrize("field", [
    "execution_intent_hash", "adapter_contract_hash", "endpoint_identity_binding_digest",
    "credential_scope_binding_digest", "operator_review_binding_digest",
    "bind_boundary_precondition_digest", "authority_evidence_linkage_context_digest",
    "human_approval_linkage_context_digest", "final_readiness_context_digest",
])
def test_source_tamper_fails(field):
    raw = source_packet().model_dump(mode="json")
    raw[field] = "0" * 64
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(raw, _decision(), RECORDED_AT)


@pytest.mark.parametrize("field,value", [
    ("bind_authorization_gate_review_decision_digest", "0" * 64),
    ("bind_authorization_gate_review_result_digest", "0" * 64),
    ("bind_authorization_gate_review_context_digest", "0" * 64),
    ("network_used", True), ("credential_material_accessed", True),
    ("request_dispatched", True), ("bind_invoked", True),
    ("external_effect_used", True), ("execution_authorized", True),
    ("bind_authorization_issued", True), ("bind_context_hash_derived", True),
])
def test_output_tamper_fails(field, value):
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


def test_unknown_shortcut_and_timestamp_fail_closed():
    raw = _packet().model_dump(mode="json")
    raw["safe_to_bind"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(reviewed_at="2026-01-01T00:00:00"))
