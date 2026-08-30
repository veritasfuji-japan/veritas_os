"""Fail-closed tests for promotion-native Human Approval reference linkage."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    BINDINGS,
    CHECK_MODE,
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError,
    build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    RECORDED_AT as AUTHORITY_RECORDED_AT,
    _packet as authority_packet,
)

RECORDED_AT = AUTHORITY_RECORDED_AT + timedelta(seconds=5)


def _value(value) -> str:
    if isinstance(value, (dict, tuple, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def _expected(source) -> dict:
    credential = source.credential_reference
    return {
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": source.endpoint_candidate["endpoint_candidate_id"],
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": credential["credential_reference_id"],
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "authority_evidence_linkage_review_id": source.promotion_live_adapter_dry_run_authority_evidence_linkage_review_id,
        "authority_evidence_linkage_review_hash": source.promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash,
        "authority_evidence_linkage_context_digest": source.authority_evidence_linkage_context_digest,
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": credential["target_resource_scope"],
        "purpose": credential["credential_purpose"],
        "authority_evidence_reference_ids": list(
            source.authority_evidence_reference_digests
        ),
        "authority_evidence_reference_digests": source.authority_evidence_reference_digests,
    }


def _bundle(source=None) -> dict:
    source = source or authority_packet()
    expected = _expected(source)
    reference = {
        "human_approval_reference_id": "approval-ref:promotion:1",
        "approval_source_type": "upstream-approval-service",
        "approval_source_id": "approval:metadata-only",
        "approver_id": "operator:alice",
        "approver_role": "bind-approver",
        "approval_scope": "bind-request",
        "approval_subject": "execution-intent",
        "approval_reason": "declared upstream approval metadata",
        "approval_issued_at": (RECORDED_AT - timedelta(minutes=1)).isoformat(),
        "approval_expires_at": (RECORDED_AT + timedelta(minutes=5)).isoformat(),
        "approval_evidence_hash": "sha256:" + "b" * 64,
        "approval_evidence_format": "opaque-human-approval-reference/v1",
        "declared_approval_state": "DECLARED_APPROVED_BY_UPSTREAM_ARTIFACT",
        **{attribute: expected[name] for name, attribute in BINDINGS},
    }
    claims = [
        {
            "binding_claim_id": f"pladhal-claim:v1:approval-ref:promotion:1:{name}",
            "human_approval_reference_id": "approval-ref:promotion:1",
            "claim_type": name,
            "expected_value": _value(expected[name]),
            "actual_value": _value(expected[name]),
            "matched": True,
            "comparison_mode": CHECK_MODE,
        }
        for name, _ in BINDINGS
    ]
    return {
        "human_approval_reference_bundle_id": "approval-bundle:promotion:1",
        "bundle_declared_by": "operator:alice",
        "bundle_declared_at": RECORDED_AT.isoformat(),
        "bundle_scope": ["bind-request"],
        "human_approval_references": [reference],
        "human_approval_binding_claims": claims,
        "bundle_limitations": ["metadata-only", "not-external-verification"],
    }


def _packet():
    source = authority_packet()
    return build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
        source, _bundle(source), RECORDED_AT
    )


def test_full_chain_preserves_source_without_proof_or_effects() -> None:
    source = authority_packet()
    packet = _packet()
    for field in (
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_id",
        "adapter_contract_hash",
        "endpoint_identity_binding_digest",
        "credential_scope_binding_digest",
        "operator_review_binding_digest",
        "bind_boundary_precondition_digest",
        "authority_evidence_reference_bundle_digest",
        "authority_evidence_binding_matrix_digest",
        "authority_evidence_linkage_context_digest",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert len(packet.human_approval_reference_digests) == 1
    assert packet.human_approval_state == "NOT_APPROVED"
    assert packet.ready_for_promotion_native_final_bind_authorization_readiness_review
    assert packet.human_approval_proven is False
    assert packet.authority_evidence_proven is False
    assert packet.execution_authorized is False
    assert packet.bind_authorization_issued is False
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)


def test_json_round_trip_preserves_canonical_derived_values() -> None:
    """Canonical JSON output must independently verify without coercion drift."""
    packet = _packet()
    raw = json.loads(packet.model_dump_json())
    parsed = type(packet).model_validate(raw)
    verified = verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
        parsed
    )
    context = packet.human_approval_linkage_context
    assert isinstance(context["authority_evidence_reference_ids"], list)
    assert context == raw["human_approval_linkage_context"]
    assert verified.human_approval_linkage_context == context


def test_check_names_describe_human_approval_reference_linkage() -> None:
    names = [check.name for check in _packet().human_approval_linkage_checks]
    assert names[0:6] == [
        "source_promotion_native_authority_evidence_linkage_verified",
        "source_authority_evidence_linkage_structurally_accepted",
        "source_request_not_dispatched",
        "source_not_bound",
        "source_not_authorized",
        "required_human_approval_true_preserved",
    ]
    assert "exact_authority_evidence_reference_linkage_preserved" in names
    assert "all_supplied_binding_claims_equal_derived_matrix" in names
    assert "future_gate_bound_signed_human_approval_required" in names
    assert not any("bind_pre_dispatch_review_accepted" in name for name in names)


def test_required_human_approval_false_fails_closed() -> None:
    source = authority_packet().model_dump(mode="json")
    source["approval_context"]["required_human_approval"] = False
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            source, _bundle(), RECORDED_AT
        )


@pytest.mark.parametrize("mutation", ["omission", "addition", "reorder", "mismatch"])
def test_caller_claim_matrix_mutations_fail_closed(mutation) -> None:
    bundle = deepcopy(_bundle())
    claims = bundle["human_approval_binding_claims"]
    if mutation == "omission":
        claims.pop()
    elif mutation == "addition":
        claims.append(deepcopy(claims[-1]))
    elif mutation == "reorder":
        claims[0], claims[1] = claims[1], claims[0]
    else:
        claims[0]["actual_value"] = "wrong"
        claims[0]["matched"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            authority_packet(), bundle, RECORDED_AT
        )


@pytest.mark.parametrize("mutation", ["ids", "digest"])
def test_authority_reference_set_mutations_fail_closed(mutation) -> None:
    bundle = deepcopy(_bundle())
    reference = bundle["human_approval_references"][0]
    if mutation == "ids":
        reference["linked_authority_evidence_reference_ids"] = ["wrong"]
    else:
        key = next(iter(reference["linked_authority_evidence_reference_digests"]))
        reference["linked_authority_evidence_reference_digests"][key] = "wrong"
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            authority_packet(), bundle, RECORDED_AT
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("human_approval_references", 0, "declared_approval_state"),
            "DECLARED_PENDING_EXTERNAL_APPROVAL_VERIFICATION",
        ),
        (("human_approval_references", 0, "linked_execution_intent_id"), "wrong"),
        (
            ("human_approval_references", 0, "approval_expires_at"),
            RECORDED_AT.isoformat(),
        ),
    ],
)
def test_builder_rejects_state_binding_and_expiry(path, value) -> None:
    bundle = deepcopy(_bundle())
    target = bundle
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            authority_packet(), bundle, RECORDED_AT
        )


@pytest.mark.parametrize(
    "field",
    [
        "human_approval_proven",
        "human_approval_externally_verified",
        "authority_evidence_proven",
        "authority_evidence_externally_verified",
        "execution_authorized",
        "network_used",
        "external_effect_used",
    ],
)
def test_verifier_rejects_proof_authority_and_effect_mutations(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            raw
        )


def test_verifier_rejects_unknown_shortcut() -> None:
    raw = _packet().model_dump(mode="json")
    raw["approved"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            raw
        )
