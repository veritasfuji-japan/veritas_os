"""Fail-closed tests for the promotion-native Bind gate review boundary."""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta

import pytest

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review as gate_module
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_REQUIREMENTS,
    COPY_FIELDS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    OUTCOMES,
    SOURCE_AUTHORIZATION_REQUIREMENTS,
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


def _packet(*, passed: bool = True, decision=None, recorded_at=RECORDED_AT):
    return build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source_packet(), decision or _decision(passed=passed), recorded_at
    )


def _source_raw():
    return source_packet().model_dump(mode="json")


def _build_from_source_raw(raw):
    return build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
        raw, _decision(), RECORDED_AT
    )


def test_pass_and_fail_route_without_authority_or_effects():
    passed = _packet()
    failed = _packet(passed=False)
    assert (
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            passed
        )
        == passed
    )
    assert (
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            failed
        )
        == failed
    )
    assert passed.ready_for_promotion_native_fresh_verified_source_gate
    assert not passed.fail_closed
    assert not failed.ready_for_promotion_native_fresh_verified_source_gate
    assert failed.fail_closed
    assert passed.gate_review_state == OUTCOMES[0]
    assert failed.gate_review_state == OUTCOMES[1]
    assert passed.fresh_verified_source_gate_still_required is True
    assert failed.fresh_verified_source_gate_still_required is True
    assert passed.bind_authorization_state == "NOT_AUTHORIZED"
    assert passed.bind_context_hash_derived is False
    assert passed.bind_authorization_gate_review_result.derives_bind_context_hash is False
    assert not any(getattr(passed, name) for name in EFFECT_FIELDS)


def test_complete_typed_preservation_and_json_round_trip():
    source = source_packet()
    packet = _packet()
    source_json = source.model_dump(mode="json")
    packet_json = packet.model_dump(mode="json")

    for name in COPY_FIELDS:
        assert name in source.model_fields, name
        assert name in packet.model_fields, name
        assert getattr(packet, name) == getattr(source, name), name
        assert packet_json[name] == source_json[name], name

    assert (
        packet.source_final_bind_authorization_requirements
        == source.future_bind_authorization_requirements
    )
    assert (
        packet.source_final_bind_authorization_requirement_digest
        == source.future_bind_authorization_requirement_digest
    )
    assert (
        packet.source_final_bind_invocation_requirements
        == source.future_bind_invocation_requirements
    )
    assert (
        packet.source_final_bind_invocation_requirement_digest
        == source.future_bind_invocation_requirement_digest
    )
    assert packet.source_final_bind_authorization_readiness_packet == source_json

    verified = verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
        packet_json
    )
    assert verified == packet
    assert verified.bind_authorization_gate_review_context == packet.bind_authorization_gate_review_context
    assert (
        verified.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash
        == packet.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash
    )


def test_source_to_gate_requirement_transition_is_exact():
    source = source_packet()
    packet = _packet()

    source_auth = tuple(item.name for item in source.future_bind_authorization_requirements)
    source_invocation = tuple(item.name for item in source.future_bind_invocation_requirements)
    gate_auth = tuple(item.name for item in packet.future_bind_authorization_requirements)
    gate_invocation = tuple(item.name for item in packet.future_bind_invocation_requirements)

    assert source_auth == SOURCE_AUTHORIZATION_REQUIREMENTS
    assert source_invocation == INVOCATION_REQUIREMENTS
    assert gate_auth == AUTHORIZATION_REQUIREMENTS
    assert gate_auth == source_auth[1:]
    assert gate_invocation == source_invocation
    assert all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *packet.future_bind_authorization_requirements,
            *packet.future_bind_invocation_requirements,
        )
    )


def test_human_and_authority_linkage_identity_are_directly_bound_in_context():
    source = source_packet()
    context = _packet().bind_authorization_gate_review_context
    assert (
        context["source_human_approval_linkage_review_id"]
        == source.source_human_approval_linkage_review_id
    )
    assert (
        context["source_human_approval_linkage_review_hash"]
        == source.source_human_approval_linkage_review_hash
    )
    assert (
        context["source_human_approval_linkage_context_digest"]
        == source.human_approval_linkage_context_digest
    )
    assert (
        context["source_authority_evidence_linkage_review_id"]
        == source.source_authority_evidence_linkage_review_id
    )
    assert (
        context["source_authority_evidence_linkage_review_hash"]
        == source.source_authority_evidence_linkage_review_hash
    )
    assert (
        context["source_authority_evidence_linkage_context_digest"]
        == source.source_authority_evidence_linkage_context_digest
    )


def test_decision_is_bound_to_context_and_packet_hash():
    first = _packet()
    second = _packet(
        decision=_decision(
            reviewer_id="operator:bob",
            reviewer_attestation="Independent local prerequisite review.",
            review_reason="independent review",
        )
    )
    assert (
        first.bind_authorization_gate_review_decision_digest
        != second.bind_authorization_gate_review_decision_digest
    )
    assert (
        first.bind_authorization_gate_review_context_digest
        != second.bind_authorization_gate_review_context_digest
    )
    assert (
        first.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash
        != second.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash
    )


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_false_acknowledgement_fails(field):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: False}))


@pytest.mark.parametrize("field", ["reviewer_id", "reviewer_role", "reviewer_attestation"])
def test_empty_reviewer_metadata_fails(field):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: ""}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("fail_closed", True),
        ("ready_for_promotion_native_bind_authorization_gate_review", False),
        ("fresh_verified_source_gate_still_required", False),
    ],
)
def test_source_readiness_state_tamper_fails(field, value):
    raw = _source_raw()
    raw[field] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


def test_rejected_source_final_readiness_cannot_enter_gate():
    raw = _source_raw()
    raw["final_readiness_state"] = (
        "NOT_READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE"
    )
    raw["ready_for_promotion_native_bind_authorization_gate_review"] = False
    raw["fail_closed"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


def test_source_authorization_requirement_lifecycle_drift_fails():
    source = source_packet()
    first = source.future_bind_authorization_requirements[0].model_copy(
        update={"name": "fresh_verified_source_gate"}
    )
    modified = source.model_copy(
        update={
            "future_bind_authorization_requirements": (
                first,
                *source.future_bind_authorization_requirements[1:],
            )
        }
    )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        gate_module._validate_source(modified)


def test_source_invocation_requirement_lifecycle_drift_fails():
    source = source_packet()
    first = source.future_bind_invocation_requirements[0].model_copy(
        update={"name": "network_dispatch"}
    )
    modified = source.model_copy(
        update={
            "future_bind_invocation_requirements": (
                first,
                *source.future_bind_invocation_requirements[1:],
            )
        }
    )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        gate_module._validate_source(modified)


@pytest.mark.parametrize(
    "field",
    [
        "execution_intent_hash",
        "adapter_contract_hash",
        "endpoint_identity_binding_digest",
        "credential_scope_binding_digest",
        "operator_review_binding_digest",
        "bind_boundary_precondition_digest",
        "authority_evidence_linkage_context_digest",
        "human_approval_linkage_context_digest",
        "final_bind_authorization_readiness_review_decision_digest",
        "final_bind_authorization_readiness_result_digest",
        "final_bind_authorization_readiness_check_digest",
        "final_readiness_context_digest",
        "source_human_approval_linkage_review_id",
        "source_human_approval_linkage_review_hash",
        "source_authority_evidence_linkage_review_id",
        "source_authority_evidence_linkage_review_hash",
    ],
)
def test_source_scalar_tamper_fails(field):
    raw = _source_raw()
    raw[field] = "0" * 64
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


@pytest.mark.parametrize("field", ["policy_snapshot_lineage", "policy_lineage", "approval_context"])
def test_source_lineage_or_approval_context_tamper_fails(field):
    raw = _source_raw()
    raw[field] = {"tampered": True}
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


def test_nested_execution_intent_tamper_fails():
    raw = _source_raw()
    raw["execution_intent"] = dict(raw["execution_intent"])
    raw["execution_intent"]["request_id"] = "request:tampered"
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


@pytest.mark.parametrize("field", ["adapter_contract_descriptor", "adapter_contract_version"])
def test_adapter_descriptor_or_version_tamper_fails(field):
    raw = _source_raw()
    if field == "adapter_contract_descriptor":
        raw[field] = dict(raw[field])
        raw[field]["adapter_contract_version"] = "tampered"
    else:
        raw[field] = "tampered"
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _build_from_source_raw(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bind_authorization_gate_review_decision_digest", "0" * 64),
        ("bind_authorization_gate_review_result_digest", "0" * 64),
        ("bind_authorization_gate_review_context_digest", "0" * 64),
        ("bind_authorization_gate_review_check_digest", "0" * 64),
        ("network_used", True),
        ("credential_material_accessed", True),
        ("request_dispatched", True),
        ("bind_invoked", True),
        ("external_effect_used", True),
        ("execution_authorized", True),
        ("bind_authorization_issued", True),
        ("bind_context_hash_derived", True),
    ],
)
def test_output_scalar_tamper_fails(field, value):
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            raw
        )


def test_gate_result_cannot_claim_bind_context_derivation():
    raw = _packet().model_dump(mode="json")
    raw["bind_authorization_gate_review_result"]["derives_bind_context_hash"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            raw
        )


def test_future_authorization_requirement_tamper_fails():
    raw = _packet().model_dump(mode="json")
    raw["future_bind_authorization_requirements"][0]["name"] = (
        "final_endpoint_identity_recheck"
    )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            raw
        )


def test_future_invocation_requirement_tamper_fails():
    raw = _packet().model_dump(mode="json")
    raw["future_bind_invocation_requirements"][0]["name"] = "network_dispatch"
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            raw
        )


def test_unknown_shortcut_and_timestamp_fail_closed():
    raw = _packet().model_dump(mode="json")
    raw["safe_to_bind"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            raw
        )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(reviewed_at="2026-01-01T00:00:00"))
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(recorded_at=SOURCE_AT)


def test_production_module_has_no_test_or_effect_imports():
    tree = ast.parse(inspect.getsource(gate_module))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(name.startswith("veritas_os.tests") for name in imports)
    assert not any(name == "tests" or name.startswith("tests.") for name in imports)
    forbidden = {"socket", "requests", "httpx", "urllib", "subprocess"}
    assert forbidden.isdisjoint(imports)
