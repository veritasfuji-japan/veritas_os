from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.decision_candidate import (
    DecisionCandidate,
    DecisionCandidatePromotionStatus,
    DecisionCandidateRefusalReason,
    hash_decision_candidate,
    promote_decision_candidate_to_execution_intent,
    validate_decision_candidate,
)


def _complete_candidate(**overrides: object) -> DecisionCandidate:
    payload = {
        "candidate_id": "candidate-1",
        "source_model": "fixture-model",
        "source_trace_ref": "trace-1",
        "action_type": "permission_change",
        "actor_identity": "user:alice",
        "target_system": "policy-admin",
        "target_resource": "policy:bundle-a",
        "intended_action": "promote_policy_bundle",
        "required_authority": ["policy.bundle.promote"],
        "required_human_approval": False,
        "risk_level": "medium",
        "regulated_or_high_impact": False,
        "evidence_refs": ["evidence:decision-1"],
        "policy_context_refs": ["policy:snapshot-1"],
        "metadata": {"fixture": True},
    }
    payload.update(overrides)
    return DecisionCandidate(**payload)


def test_complete_candidate_validates_as_promotable() -> None:
    result = validate_decision_candidate(_complete_candidate())

    assert result.promotable is True
    assert result.promotion_status is DecisionCandidatePromotionStatus.PROMOTABLE
    assert result.fail_closed is False
    assert result.requires_human_review is False
    assert result.reason_codes == [DecisionCandidateRefusalReason.PROMOTABLE.value]


def test_promotable_candidate_can_be_promoted_into_execution_intent() -> None:
    candidate = _complete_candidate()

    intent = promote_decision_candidate_to_execution_intent(
        candidate,
        decision_id="decision-1",
        request_id="request-1",
        policy_snapshot_id="policy-snapshot-1",
        decision_hash="decision-hash-1",
        decision_ts="2026-06-13T00:00:00Z",
        ttl_seconds=300,
        expected_state_fingerprint="state-fingerprint-1",
        approval_context={"approval_required": False},
        policy_lineage={"bundle": "bundle-a"},
    )

    assert isinstance(intent, ExecutionIntent)
    assert intent.actor_identity == candidate.actor_identity
    assert intent.target_system == candidate.target_system
    assert intent.target_resource == candidate.target_resource
    assert intent.intended_action == candidate.intended_action
    assert intent.evidence_refs == candidate.evidence_refs
    assert intent.decision_id == "decision-1"
    assert intent.ttl_seconds == 300


def test_missing_target_resource_fails_closed_and_cannot_be_promoted() -> None:
    candidate = _complete_candidate(target_resource="")
    result = validate_decision_candidate(candidate)

    assert result.promotable is False
    assert result.fail_closed is True
    assert "target_resource" in result.missing_required_fields
    assert (
        DecisionCandidateRefusalReason.MISSING_REQUIRED_FIELD.value
        in result.reason_codes
    )
    with pytest.raises(ValueError, match="not promotable"):
        promote_decision_candidate_to_execution_intent(candidate)


def test_missing_actor_identity_fails_closed_and_cannot_be_promoted() -> None:
    candidate = _complete_candidate(actor_identity="")
    result = validate_decision_candidate(candidate)

    assert result.promotable is False
    assert result.fail_closed is True
    assert "actor_identity" in result.missing_required_fields
    with pytest.raises(ValueError, match="not promotable"):
        promote_decision_candidate_to_execution_intent(candidate)


def test_empty_required_authority_prevents_promotion() -> None:
    result = validate_decision_candidate(_complete_candidate(required_authority=[]))

    assert result.promotable is False
    assert result.fail_closed is True
    assert (
        DecisionCandidateRefusalReason.AUTHORITY_UNSPECIFIED.value
        in result.reason_codes
    )


def test_unclear_human_approval_prevents_promotion_and_requires_review() -> None:
    result = validate_decision_candidate(
        _complete_candidate(required_human_approval=None)
    )

    assert result.promotable is False
    assert result.requires_human_review is True
    assert result.promotion_status is DecisionCandidatePromotionStatus.HUMAN_REVIEW_REQUIRED
    assert (
        DecisionCandidateRefusalReason.HUMAN_APPROVAL_UNCLEAR.value
        in result.reason_codes
    )


def test_ambiguity_flags_prevent_promotion_and_require_review() -> None:
    result = validate_decision_candidate(
        _complete_candidate(ambiguity_flags=["target_resource_matches_multiple_records"])
    )

    assert result.promotable is False
    assert result.requires_human_review is True
    assert result.promotion_status is DecisionCandidatePromotionStatus.HUMAN_REVIEW_REQUIRED
    assert DecisionCandidateRefusalReason.AMBIGUOUS.value in result.reason_codes
    assert result.ambiguity_flags == ["target_resource_matches_multiple_records"]


def test_regulated_unknown_risk_prevents_promotion() -> None:
    result = validate_decision_candidate(
        _complete_candidate(regulated_or_high_impact=True, risk_level="unknown")
    )

    assert result.promotable is False
    assert result.requires_human_review is True
    assert (
        DecisionCandidateRefusalReason.RISK_INDETERMINATE.value
        in result.reason_codes
    )


def test_rationale_only_candidate_is_not_promotable() -> None:
    candidate = DecisionCandidate(
        candidate_id="candidate-rationale-only",
        source_model="fixture-model",
        candidate_rationale_ref="rationale:only",
    )
    result = validate_decision_candidate(candidate)

    assert result.promotable is False
    assert result.fail_closed is True
    assert (
        DecisionCandidateRefusalReason.RATIONALE_ONLY.value
        in result.reason_codes
    )
    assert result.missing_required_fields


def test_hashing_is_deterministic_for_equivalent_candidate_payloads() -> None:
    first = _complete_candidate(metadata={"b": 2, "a": 1})
    second = _complete_candidate(metadata={"a": 1, "b": 2})

    assert hash_decision_candidate(first) == hash_decision_candidate(second)
