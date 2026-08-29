"""Fail-closed tests for promotion-native operator dispatch review evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_operator_dispatch_review import (
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError,
    build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_credential_authorization import (
    EVALUATED_AT,
    _packet as credential_packet,
    _reference,
    _snapshot,
)


def _decision(source, outcome: str = "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW") -> dict:
    return {
        "operator_review_id": "operator-review:promotion:v1",
        "reviewer_id": "reviewer:alice",
        "reviewer_role": "dispatch-operator",
        "reviewer_organization": "veritas-local",
        "reviewed_at": (EVALUATED_AT + timedelta(seconds=1)).isoformat(),
        "review_decision": outcome,
        "review_reason": "Exact inert evidence reviewed.",
        "reviewed_endpoint_candidate_id": source.endpoint_candidate[
            "endpoint_candidate_id"
        ],
        "reviewed_credential_reference_id": (
            source.credential_reference.credential_reference_id
        ),
        "reviewed_adapter_contract_id": source.adapter_contract_id,
        "reviewed_target_system": source.execution_intent["target_system"],
        "reviewed_target_resource_scope": source.execution_intent["target_resource"],
        "acknowledged_scope_limitations": True,
        "acknowledged_non_effect_guarantees": True,
        "acknowledged_future_bind_pre_dispatch_review_required": True,
        "acknowledged_no_dispatch": True,
        "acknowledged_no_credential_access": True,
        "acknowledged_no_network": True,
        "acknowledged_no_bind": True,
        "acknowledged_no_bind_receipt": True,
        "acknowledged_no_trustlog_write": True,
    }


def _review(outcome: str = "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW"):
    source = credential_packet()
    return (
        build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            source,
            _decision(source, outcome),
            EVALUATED_AT + timedelta(seconds=2),
        )
    )


@pytest.mark.parametrize(
    ("outcome", "fail_closed", "ready"),
    [
        ("APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW", False, True),
        ("REJECT", True, False),
        ("HOLD_FOR_MORE_EVIDENCE", True, False),
    ],
)
def test_all_review_outcomes_are_verifiable(
    outcome: str, fail_closed: bool, ready: bool
) -> None:
    packet = _review(outcome)
    verified = (
        verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            packet
        )
    )
    assert verified.fail_closed is fail_closed
    assert verified.ready_for_promotion_native_bind_pre_dispatch_review is ready
    assert verified.execution_intent == credential_packet().execution_intent
    assert verified.operator_review_is_human_approval is False
    assert all(getattr(verified, field) is False for field in EFFECT_FIELDS)


def test_refused_credential_cannot_enter_review() -> None:
    reference = _reference()
    refused = credential_packet(reference, _snapshot(reference, active=False))
    assert refused.credential_authorization_result.authorized is False
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError):
        build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            refused,
            _decision(refused),
            EVALUATED_AT + timedelta(seconds=2),
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("operator_review_decision.reviewer_id", ""),
        ("operator_review_decision.reviewed_target_system", "wrong"),
        ("operator_review_decision.acknowledged_no_network", False),
        ("operator_review_decision_digest", "0" * 64),
        ("operator_review_binding_digest", "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("endpoint_identity_binding_digest", "0" * 64),
        ("credential_scope_binding_digest", "0" * 64),
        ("network_used", True),
        ("human_approval_proven", True),
        ("fail_closed", True),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_review().model_dump(mode="json"))
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError):
        verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            raw
        )


def test_naive_and_out_of_order_timestamps_fail_closed() -> None:
    source = credential_packet()
    for reviewed_at, recorded_at in (
        (EVALUATED_AT.replace(tzinfo=None).isoformat(), EVALUATED_AT),
        (
            (EVALUATED_AT - timedelta(seconds=1)).isoformat(),
            EVALUATED_AT,
        ),
        (
            (EVALUATED_AT + timedelta(seconds=2)).isoformat(),
            EVALUATED_AT + timedelta(seconds=1),
        ),
    ):
        decision = _decision(source)
        decision["reviewed_at"] = reviewed_at
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError
        ):
            build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
                source, decision, recorded_at
            )
