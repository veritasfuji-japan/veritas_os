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
        "authority_evidence_reference_ids": tuple(
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


def test_verifier_rejects_tamper_and_unknown_shortcut() -> None:
    raw = _packet().model_dump(mode="json")
    raw["human_approval_proven"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            raw
        )
    raw = _packet().model_dump(mode="json")
    raw["approved"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError):
        verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            raw
        )
