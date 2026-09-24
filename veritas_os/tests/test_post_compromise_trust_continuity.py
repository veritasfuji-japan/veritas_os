"""TASK-031 frozen corpus for post-compromise trust-state continuity."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from veritas_os.policy.post_compromise_trust_continuity import (
    RecoveryTrustState,
    TrustContinuityObservation,
    evaluate_post_compromise_trust,
)


def _observation(**updates) -> TrustContinuityObservation:
    values = {
        "snapshot_id": "snapshot:task031:baseline",
        "historical_trust_generation": 41,
        "current_trust_generation": 41,
        "observation_generation": 41,
        "authority_state": "VALID",
        "credential_state": "VALID",
        "credential_material_source": "CURRENT_PROVIDER",
        "policy_state": "ADMISSIBLE",
        "human_approval_required": True,
        "human_approval_state": "VERIFIED",
        "action_binding_state": "CURRENT",
        "external_effect_state": "NONE",
        "historical_authorization_present": True,
        "historical_authorization_consumed": False,
    }
    values.update(updates)
    return TrustContinuityObservation(**values)


@dataclass(frozen=True)
class Scenario:
    id: str
    observation: TrustContinuityObservation
    expected_state: RecoveryTrustState
    expected_reason: str
    expected_eligible: bool


SCENARIOS = (
    Scenario(
        "T31-01",
        _observation(),
        RecoveryTrustState.TRUST_REVALIDATED,
        "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        True,
    ),
    Scenario(
        "T31-02",
        _observation(credential_state="REVOKED"),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_CREDENTIAL_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-03",
        _observation(authority_state="REVOKED"),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_AUTHORITY_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-04",
        _observation(human_approval_state="EXPIRED"),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_APPROVAL_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-05",
        _observation(
            current_trust_generation=42,
            observation_generation=42,
            credential_material_source="HISTORICAL_SNAPSHOT",
        ),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_CREDENTIAL_SOURCE_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-06",
        _observation(
            current_trust_generation=42,
            observation_generation=41,
        ),
        RecoveryTrustState.TRUST_NOT_REVALIDATED,
        "PTC_OBSERVATION_GENERATION_STALE",
        False,
    ),
    Scenario(
        "T31-07",
        _observation(authority_state="UNAVAILABLE"),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_AUTHORITY_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-08",
        _observation(policy_state="DENIED"),
        RecoveryTrustState.TRUST_INVALID,
        "PTC_POLICY_NOT_CURRENT",
        False,
    ),
    Scenario(
        "T31-09",
        _observation(
            current_trust_generation=42,
            observation_generation=42,
            historical_authorization_present=True,
            historical_authorization_consumed=True,
        ),
        RecoveryTrustState.TRUST_REVALIDATED,
        "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        True,
    ),
    Scenario(
        "T31-10",
        _observation(
            current_trust_generation=42,
            observation_generation=42,
            historical_authorization_present=True,
            historical_authorization_consumed=True,
        ),
        RecoveryTrustState.TRUST_REVALIDATED,
        "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        True,
    ),
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.id)
def test_task031_frozen_initial_corpus(scenario: Scenario):
    result = evaluate_post_compromise_trust(scenario.observation)
    assert result.state == scenario.expected_state
    assert result.reason_code == scenario.expected_reason
    assert result.new_authorization_eligible is scenario.expected_eligible
    assert result.historical_authorization_reusable is False
    assert result.external_effect_retry_permitted is False
    assert len(result.observation_hash) == 64
    assert len(result.result_hash) == 64


def test_trust_generation_cannot_move_backward():
    result = evaluate_post_compromise_trust(
        _observation(
            historical_trust_generation=42,
            current_trust_generation=41,
            observation_generation=41,
        )
    )
    assert result.state == RecoveryTrustState.TRUST_INVALID
    assert result.reason_code == "PTC_TRUST_GENERATION_ROLLBACK"
    assert not result.new_authorization_eligible


@pytest.mark.parametrize("effect_state", ["EFFECT_UNKNOWN", "CONFIRMED_EFFECT"])
def test_unresolved_or_already_confirmed_effect_never_creates_retry_authority(effect_state):
    result = evaluate_post_compromise_trust(
        _observation(external_effect_state=effect_state)
    )
    assert result.state == RecoveryTrustState.TRUST_NOT_REVALIDATED
    assert result.reason_code == "PTC_EXTERNAL_EFFECT_NOT_CLEAR_FOR_NEW_EXECUTION"
    assert result.external_effect_retry_permitted is False
    assert result.historical_authorization_reusable is False
    assert not result.new_authorization_eligible


def test_no_approval_action_requires_explicit_not_required_state():
    result = evaluate_post_compromise_trust(
        _observation(
            human_approval_required=False,
            human_approval_state="VERIFIED",
        )
    )
    assert result.state == RecoveryTrustState.TRUST_INVALID
    assert result.reason_code == "PTC_APPROVAL_REQUIREMENT_MISMATCH"


def test_fresh_no_approval_action_can_revalidate():
    result = evaluate_post_compromise_trust(
        _observation(
            human_approval_required=False,
            human_approval_state="NOT_REQUIRED",
        )
    )
    assert result.state == RecoveryTrustState.TRUST_REVALIDATED
    assert result.new_authorization_eligible is True
    assert result.historical_authorization_reusable is False


def test_result_is_deterministic_and_snapshot_state_is_not_authority():
    observation = _observation(
        current_trust_generation=42,
        observation_generation=42,
        historical_authorization_present=True,
        historical_authorization_consumed=False,
    )
    first = evaluate_post_compromise_trust(observation)
    second = evaluate_post_compromise_trust(observation)
    assert first == second
    assert first.historical_authorization_reusable is False
    assert first.reason_code == "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED"
