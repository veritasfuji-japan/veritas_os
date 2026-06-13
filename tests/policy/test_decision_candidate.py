from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.decision_candidate import (
    DecisionCandidate,
    DecisionCandidatePromotionStatus,
    DecisionCandidateRefusalReason,
    hash_decision_candidate,
    normalize_decision_candidate,
    promote_decision_candidate_to_execution_intent,
    try_promote_decision_candidate_to_execution_intent,
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
    assert (
        result.promotion_status
        is DecisionCandidatePromotionStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        DecisionCandidateRefusalReason.HUMAN_APPROVAL_UNCLEAR.value
        in result.reason_codes
    )


def test_ambiguity_flags_prevent_promotion_and_require_review() -> None:
    result = validate_decision_candidate(
        _complete_candidate(
            ambiguity_flags=["target_resource_matches_multiple_records"]
        )
    )

    assert result.promotable is False
    assert result.requires_human_review is True
    assert (
        result.promotion_status
        is DecisionCandidatePromotionStatus.HUMAN_REVIEW_REQUIRED
    )
    assert DecisionCandidateRefusalReason.AMBIGUOUS.value in result.reason_codes
    assert result.ambiguity_flags == ["target_resource_matches_multiple_records"]


def test_regulated_unknown_risk_prevents_promotion() -> None:
    result = validate_decision_candidate(
        _complete_candidate(regulated_or_high_impact=True, risk_level="unknown")
    )

    assert result.promotable is False
    assert result.requires_human_review is True
    assert (
        DecisionCandidateRefusalReason.RISK_INDETERMINATE.value in result.reason_codes
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
    assert DecisionCandidateRefusalReason.RATIONALE_ONLY.value in result.reason_codes
    assert result.missing_required_fields


def test_hashing_is_deterministic_for_equivalent_candidate_payloads() -> None:
    first = _complete_candidate(metadata={"b": 2, "a": 1})
    second = _complete_candidate(metadata={"a": 1, "b": 2})

    assert hash_decision_candidate(first) == hash_decision_candidate(second)


def test_dict_payload_normalizes_into_decision_candidate() -> None:
    candidate = normalize_decision_candidate(_complete_candidate().__dict__)

    assert isinstance(candidate, DecisionCandidate)
    assert candidate.candidate_id == "candidate-1"


def test_normalization_strips_whitespace_from_strings() -> None:
    candidate = normalize_decision_candidate(
        _complete_candidate(
            candidate_id=" candidate-1 ",
            source_model=" fixture-model ",
            action_type=" permission_change ",
            actor_identity=" user:alice ",
            target_system=" policy-admin ",
            target_resource=" policy:bundle-a ",
            intended_action=" promote_policy_bundle ",
            risk_level=" MEDIUM ",
            candidate_rationale_ref=" rationale:1 ",
        )
    )

    assert candidate.candidate_id == "candidate-1"
    assert candidate.source_model == "fixture-model"
    assert candidate.action_type == "permission_change"
    assert candidate.risk_level == "medium"
    assert candidate.candidate_rationale_ref == "rationale:1"


def test_scalar_list_fields_become_single_item_lists() -> None:
    payload = _complete_candidate().to_dict()
    payload.update(
        {
            "required_authority": " policy.bundle.promote ",
            "evidence_refs": " evidence:decision-1 ",
            "policy_context_refs": " policy:snapshot-1 ",
            "ambiguity_flags": " possible_duplicate ",
            "missing_required_fields": " target_resource ",
        }
    )

    candidate = normalize_decision_candidate(payload)

    assert candidate.required_authority == ["policy.bundle.promote"]
    assert candidate.evidence_refs == ["evidence:decision-1"]
    assert candidate.policy_context_refs == ["policy:snapshot-1"]
    assert candidate.ambiguity_flags == ["possible_duplicate"]
    assert candidate.missing_required_fields == ["target_resource"]


def test_list_fields_drop_empty_strings_and_deduplicate_in_order() -> None:
    candidate = normalize_decision_candidate(
        _complete_candidate(
            required_authority=[" alpha ", "", "beta", "alpha", " beta "],
            evidence_refs=[" evidence:1 ", " ", "evidence:1", "evidence:2"],
        )
    )

    assert candidate.required_authority == ["alpha", "beta"]
    assert candidate.evidence_refs == ["evidence:1", "evidence:2"]


def test_required_human_approval_strings_normalize_to_booleans() -> None:
    assert (
        normalize_decision_candidate(
            _complete_candidate(required_human_approval="yes").to_dict()
        ).required_human_approval
        is True
    )
    assert (
        normalize_decision_candidate(
            _complete_candidate(required_human_approval="no").to_dict()
        ).required_human_approval
        is False
    )


def test_unknown_human_approval_normalizes_to_none_and_requires_review() -> None:
    candidate = normalize_decision_candidate(
        _complete_candidate(required_human_approval="maybe").to_dict()
    )
    result = validate_decision_candidate(candidate)

    assert candidate.required_human_approval is None
    assert result.requires_human_review is True
    assert (
        DecisionCandidateRefusalReason.HUMAN_APPROVAL_UNCLEAR.value
        in result.reason_codes
    )


def test_regulated_string_and_blank_risk_normalize() -> None:
    candidate = normalize_decision_candidate(
        _complete_candidate(
            regulated_or_high_impact="regulated",
            risk_level="",
        ).to_dict()
    )

    assert candidate.regulated_or_high_impact is True
    assert candidate.risk_level == "unknown"


def test_hashing_normalizes_equivalent_raw_dict_payloads() -> None:
    first = _complete_candidate(
        required_authority=[" policy.bundle.promote ", "policy.bundle.promote"],
        risk_level=" Medium ",
        metadata={"b": 2, "a": 1},
    ).to_dict()
    second = _complete_candidate(
        risk_level="medium",
        metadata={"a": 1, "b": 2},
    ).to_dict()
    second["required_authority"] = "policy.bundle.promote"

    assert hash_decision_candidate(first) == hash_decision_candidate(second)


def test_try_promote_returns_refusal_result_instead_of_raising() -> None:
    result = try_promote_decision_candidate_to_execution_intent(
        _complete_candidate(target_resource="").to_dict()
    )

    assert result.promoted is False
    assert result.execution_intent is None
    assert result.fail_closed is True
    assert (
        DecisionCandidateRefusalReason.MISSING_REQUIRED_FIELD.value
        in result.refusal_reason_codes
    )


def test_promotable_dict_payload_can_produce_execution_intent() -> None:
    result = try_promote_decision_candidate_to_execution_intent(
        _complete_candidate(actor_identity=" user:alice ").to_dict(),
        decision_id="decision-1",
    )

    assert result.promoted is True
    assert isinstance(result.execution_intent, ExecutionIntent)
    assert result.execution_intent.actor_identity == "user:alice"
    assert result.execution_intent.decision_id == "decision-1"
