"""Tests for promotion-native final Bind authorization readiness evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness import (
    ACCEPTED,
    REJECTED,
    CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError,
    build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet,
    verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    _packet as _source_packet,
)


def _decision(source, outcome: str = ACCEPTED) -> dict:
    reviewed_at = datetime.fromisoformat(
        source.human_approval_linkage_review_recorded_at
    ) + timedelta(seconds=1)
    return {
        "final_bind_authorization_readiness_review_decision_id": "final-review-1",
        "reviewer_id": "reviewer-1",
        "reviewer_role": "bind-readiness-reviewer",
        "reviewer_attestation": "I reviewed only local metadata readiness.",
        "reviewed_at": reviewed_at.isoformat(),
        "review_outcome": outcome,
        "review_reason": "Prerequisite metadata is complete." if outcome == ACCEPTED else "Local review rejected.",
        "acknowledged_not_bind_authorization": True,
        "acknowledged_no_bind_invocation": True,
        "acknowledged_no_bind_receipt": True,
        "acknowledged_no_trustlog_write": True,
        "acknowledged_no_dispatch": True,
        "acknowledged_no_execution_authority": True,
        "acknowledged_no_human_approval_creation": True,
        "acknowledged_no_human_approval_verification": True,
        "acknowledged_no_authority_evidence_creation": True,
        "acknowledged_no_authority_evidence_verification": True,
        "acknowledged_no_credential_access": True,
        "acknowledged_no_authorization_header": True,
        "acknowledged_no_network_call": True,
        "acknowledged_final_fresh_source_gate_still_required": True,
        "acknowledged_gate_bound_human_approval_still_required": True,
        "acknowledged_cryptographic_authority_verification_still_required": True,
    }


def _packet(outcome: str = ACCEPTED):
    source = _source_packet()
    decision = _decision(source, outcome)
    recorded_at = datetime.fromisoformat(decision["reviewed_at"]) + timedelta(seconds=1)
    return build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        source, decision, recorded_at
    )


@pytest.mark.parametrize(
    ("outcome", "ready", "fail_closed"),
    ((ACCEPTED, True, False), (REJECTED, False, True)),
)
def test_accept_and_reject_are_independently_verifiable(
    outcome: str, ready: bool, fail_closed: bool
) -> None:
    packet = _packet(outcome)
    verified = verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        packet.model_dump(mode="json")
    )
    assert verified.ready_for_promotion_native_bind_authorization_gate_review is ready
    assert verified.fail_closed is fail_closed
    assert not verified.human_approval_proven
    assert not verified.authority_evidence_proven
    assert not verified.execution_authorized
    assert not verified.bind_authorization_issued
    assert not verified.network_used
    assert not verified.credential_material_accessed
    assert not verified.external_effect_used


def test_exact_promotion_native_chain_is_preserved() -> None:
    source = _source_packet()
    packet = _packet()
    for field in (
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_id",
        "adapter_contract_hash",
        "endpoint_candidate_digest",
        "endpoint_identity_binding_digest",
        "credential_reference_digest",
        "credential_scope_binding_digest",
        "operator_review_binding_digest",
        "bind_boundary_precondition_digest",
        "authority_evidence_reference_bundle_digest",
        "authority_evidence_binding_matrix_digest",
        "authority_evidence_linkage_context_digest",
        "human_approval_reference_bundle_digest",
        "human_approval_binding_matrix_digest",
        "human_approval_linkage_context_digest",
    ):
        assert getattr(packet, field) == getattr(source, field)


@pytest.mark.parametrize(
    "path",
    (
        ("execution_intent_hash",),
        ("adapter_contract_hash",),
        ("endpoint_identity_binding_digest",),
        ("credential_scope_binding_digest",),
        ("operator_review_binding_digest",),
        ("bind_boundary_precondition_digest",),
        ("authority_evidence_reference_bundle_digest",),
        ("human_approval_reference_bundle_digest",),
        ("final_bind_authorization_readiness_review_decision_digest",),
        ("final_bind_authorization_readiness_result_digest",),
        ("final_bind_authorization_readiness_context_digest",),
        ("final_bind_authorization_readiness_check_digest",),
        ("future_bind_authorization_requirement_digest",),
        ("network_used",),
        ("request_dispatched",),
        ("bind_invoked",),
        ("external_effect_used",),
    ),
)
def test_tamper_fails_closed(path: tuple[str, ...]) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    key = path[0]
    raw[key] = True if isinstance(raw[key], bool) else f"{raw[key]}-tampered"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            raw
        )


@pytest.mark.parametrize("field", ("reviewer_id", "reviewer_role", "reviewer_attestation"))
def test_empty_reviewer_metadata_is_rejected(field: str) -> None:
    source = _source_packet()
    decision = _decision(source)
    decision[field] = ""
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source, decision, datetime.fromisoformat(decision["reviewed_at"])
        )


def test_false_acknowledgement_and_unknown_shortcut_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["final_bind_authorization_readiness_review_decision"][
        "acknowledged_no_network_call"
    ] = False
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["safe_to_bind"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)


def test_naive_and_out_of_order_timestamps_are_rejected() -> None:
    source = _source_packet()
    decision = _decision(source)
    decision["reviewed_at"] = "2026-01-01T00:00:00"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source, decision, datetime.now().astimezone()
        )

    decision = _decision(source)
    before = datetime.fromisoformat(decision["reviewed_at"]) - timedelta(seconds=1)
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source, decision, before
        )
