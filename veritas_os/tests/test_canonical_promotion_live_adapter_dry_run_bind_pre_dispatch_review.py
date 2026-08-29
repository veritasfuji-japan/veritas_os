"""Fail-closed tests for promotion-native Bind pre-dispatch review."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review import (
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError,
    build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_operator_dispatch_review import (
    EVALUATED_AT,
    _review as operator_review,
)


def _decision(outcome: str = "ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW"):
    return {
        "bind_pre_dispatch_review_decision_id": "bind-review:promotion:v1",
        "reviewer_id": "reviewer:bob",
        "reviewer_role": "bind-boundary-reviewer",
        "reviewer_attestation": "Exact promotion-native evidence reviewed.",
        "reviewed_at": (EVALUATED_AT + timedelta(seconds=3)).isoformat(),
        "review_outcome": outcome,
        "review_reason": "Review recorded without authority or effects.",
        "acknowledged_not_bind_authorization": True,
        "acknowledged_no_bind_invocation": True,
        "acknowledged_no_bind_receipt": True,
        "acknowledged_no_trustlog_write": True,
        "acknowledged_no_dispatch": True,
        "acknowledged_no_credential_access": True,
        "acknowledged_no_network_call": True,
        "acknowledged_semantic_match_not_authority": True,
    }


def _packet(outcome: str = "ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW"):
    return (
        build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            operator_review(),
            _decision(outcome),
            EVALUATED_AT + timedelta(seconds=4),
        )
    )


@pytest.mark.parametrize(
    ("outcome", "accepted", "fail_closed"),
    [
        ("ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW", True, False),
        ("REJECTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW", False, True),
    ],
)
def test_accepted_and_rejected_are_verifiable(
    outcome: str, accepted: bool, fail_closed: bool
) -> None:
    source = operator_review()
    packet = _packet(outcome)
    verified = (
        verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            packet
        )
    )
    assert verified.fail_closed is fail_closed
    assert (
        verified.ready_for_promotion_native_authority_evidence_linkage_review
        is accepted
    )
    assert verified.execution_intent == source.execution_intent
    assert verified.execution_intent_id == source.execution_intent_id
    assert verified.execution_intent_hash == source.execution_intent_hash
    assert verified.adapter_contract_hash == source.adapter_contract_hash
    assert verified.endpoint_identity_binding_digest == (
        source.endpoint_identity_binding_digest
    )
    assert verified.credential_scope_binding_digest == (
        source.credential_scope_binding_digest
    )
    assert verified.operator_review_binding_digest == (
        source.operator_review_binding_digest
    )
    assert all(getattr(verified, field) is False for field in EFFECT_FIELDS)


@pytest.mark.parametrize("operator_outcome", ["REJECT", "HOLD_FOR_MORE_EVIDENCE"])
def test_non_approved_operator_source_cannot_enter(operator_outcome: str) -> None:
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError):
        build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            operator_review(operator_outcome),
            _decision(),
            EVALUATED_AT + timedelta(seconds=4),
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_operator_dispatch_review_hash", "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("endpoint_identity_binding_digest", "0" * 64),
        ("credential_reference_digest", "0" * 64),
        ("credential_scope_binding_digest", "0" * 64),
        ("operator_review_decision_digest", "0" * 64),
        ("operator_review_binding_digest", "0" * 64),
        ("bind_pre_dispatch_review_decision.reviewer_id", ""),
        ("bind_pre_dispatch_review_decision.acknowledged_no_network_call", False),
        ("bind_pre_dispatch_review_decision_digest", "0" * 64),
        ("bind_pre_dispatch_review_result.review_reason", "tampered"),
        ("bind_pre_dispatch_review_result_digest", "0" * 64),
        ("bind_boundary_preconditions.execution_intent_id", "tampered"),
        ("bind_boundary_precondition_digest", "0" * 64),
        ("selected_action_lineage", {"tampered": True}),
        ("approval_context", {"tampered": True}),
        ("policy_lineage", {"tampered": True}),
        ("bind_pre_dispatch_review_checks.0.name", "bind_not_invoked"),
        ("future_requirements.0.name", "network_dispatch"),
        ("fail_closed", True),
        ("network_used", True),
        ("credential_material_accessed", True),
        ("request_dispatched", True),
        ("bind_invoked", True),
        ("bind_authorization_issued", True),
        ("human_approval_proven", True),
        ("authority_evidence_proven", True),
        ("execution_authorized", True),
        ("promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash", "0" * 64),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    final = parts[-1]
    if final.isdigit():
        target[int(final)] = value
    else:
        target[final] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            raw
        )


def test_invalid_decisions_and_timestamp_order_fail_closed() -> None:
    source = operator_review()
    invalid_decisions = []
    for field in ("reviewer_id", "reviewer_role", "reviewer_attestation"):
        decision = _decision()
        decision[field] = ""
        invalid_decisions.append(decision)
    decision = _decision()
    decision["review_outcome"] = "UNKNOWN"
    invalid_decisions.append(decision)
    decision = _decision()
    decision["reviewed_at"] = EVALUATED_AT.replace(tzinfo=None).isoformat()
    invalid_decisions.append(decision)
    decision = _decision()
    decision["reviewed_at"] = (EVALUATED_AT + timedelta(seconds=1)).isoformat()
    invalid_decisions.append(decision)
    for decision in invalid_decisions:
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError
        ):
            build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
                source, decision, EVALUATED_AT + timedelta(seconds=4)
            )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError):
        build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            source,
            _decision(),
            EVALUATED_AT + timedelta(seconds=2),
        )


def test_unknown_shortcut_field_is_forbidden() -> None:
    raw = _packet().model_dump(mode="json")
    raw["safe"] = True
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError):
        verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            raw
        )
