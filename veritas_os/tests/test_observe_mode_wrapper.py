"""Tests for test-only Observe Mode decision wrapper."""

from __future__ import annotations

import json

import pytest

from veritas_os.governance.observation_evaluator import evaluate_governance_observation
from veritas_os.governance.observe_mode_wrapper import (
    ObserveModeDecisionInput,
    build_governance_observation_for_dry_run,
)


@pytest.mark.parametrize("environment", ["development", "test", "sandbox"])
def test_observe_block_creates_valid_observation(environment: str) -> None:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="observe",
            environment=environment,
            would_be_outcome="block",
            reason="policy_violation:missing_authority_evidence",
        )
    )

    assert observation.policy_mode == "observe"
    assert observation.environment == environment
    assert observation.would_have_blocked is True
    assert observation.would_have_blocked_reason == "policy_violation:missing_authority_evidence"
    assert observation.effective_outcome == "proceed"
    assert observation.observed_outcome == "block"
    assert observation.operator_warning is True
    assert observation.audit_required is True


def test_enforce_production_block_creates_valid_observation() -> None:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="enforce",
            environment="production",
            would_be_outcome="block",
            reason="policy_violation:missing_authority_evidence",
        )
    )

    assert observation.policy_mode == "enforce"
    assert observation.environment == "production"
    assert observation.would_have_blocked is True
    assert observation.would_have_blocked_reason == "policy_violation:missing_authority_evidence"
    assert observation.effective_outcome == "block"
    assert observation.observed_outcome == "block"
    assert observation.operator_warning is True
    assert observation.audit_required is True


def test_observe_production_raises_error() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        build_governance_observation_for_dry_run(
            ObserveModeDecisionInput(
                policy_mode="observe",
                environment="production",
                would_be_outcome="block",
                reason="policy_violation:missing_authority_evidence",
            )
        )


def test_observe_proceed_creates_valid_observation() -> None:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="observe",
            environment="development",
            would_be_outcome="proceed",
        )
    )

    assert observation.would_have_blocked is False
    assert observation.would_have_blocked_reason is None
    assert observation.effective_outcome == "proceed"
    assert observation.observed_outcome == "proceed"
    assert observation.operator_warning is True
    assert observation.audit_required is True


def test_enforce_proceed_creates_valid_observation() -> None:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="enforce",
            environment="production",
            would_be_outcome="proceed",
        )
    )

    assert observation.would_have_blocked is False
    assert observation.would_have_blocked_reason is None
    assert observation.effective_outcome == "proceed"
    assert observation.observed_outcome == "proceed"
    assert observation.operator_warning is False
    assert observation.audit_required is True


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_block_without_reason_raises_error(reason: str | None) -> None:
    with pytest.raises(ValueError, match="requires a non-empty reason"):
        build_governance_observation_for_dry_run(
            ObserveModeDecisionInput(
                policy_mode="observe",
                environment="development",
                would_be_outcome="block",
                reason=reason,
            )
        )


def test_wrapper_generated_observation_can_be_embedded_in_snapshot_fixture() -> None:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="observe",
            environment="development",
            would_be_outcome="block",
            reason="policy_violation:missing_authority_evidence",
        )
    )

    governance_layer_snapshot = {
        "decision_id": "dec_observe_generated_001",
        "bind_receipt_id": "br_observe_generated_001",
        "execution_intent_id": "ei_observe_generated_001",
        "participation_state": "decision_shaping",
        "preservation_state": "degrading",
        "intervention_viability": "minimal",
        "bind_outcome": "ESCALATED",
        "governance_observation": observation.model_dump(mode="json"),
    }

    evaluation = evaluate_governance_observation(observation)

    assert evaluation.valid is True
    assert governance_layer_snapshot["governance_observation"]["policy_mode"] == "observe"
    assert governance_layer_snapshot["governance_observation"]["environment"] == "development"
    assert governance_layer_snapshot["governance_observation"]["would_have_blocked"] is True
    assert (
        governance_layer_snapshot["governance_observation"]["would_have_blocked_reason"]
        == "policy_violation:missing_authority_evidence"
    )
    assert governance_layer_snapshot["governance_observation"]["effective_outcome"] == "proceed"
    assert governance_layer_snapshot["governance_observation"]["observed_outcome"] == "block"
    assert governance_layer_snapshot["governance_observation"]["operator_warning"] is True
    assert governance_layer_snapshot["governance_observation"]["audit_required"] is True
    assert governance_layer_snapshot["decision_id"] == "dec_observe_generated_001"
    assert governance_layer_snapshot["bind_receipt_id"] == "br_observe_generated_001"
    assert governance_layer_snapshot["execution_intent_id"] == "ei_observe_generated_001"

    serialized_snapshot = json.dumps({"governance_layer_snapshot": governance_layer_snapshot})

    assert isinstance(serialized_snapshot, str)
