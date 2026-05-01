"""Schema fixtures for Observe Mode governance observation foundation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veritas_os.api.schemas import GovernanceObservation


def test_governance_observation_enforce_fixture() -> None:
    payload = GovernanceObservation(
        policy_mode="enforce",
        environment="production",
        would_have_blocked=False,
        effective_outcome="block",
        observed_outcome="block",
        operator_warning=False,
        audit_required=True,
    )
    assert payload.policy_mode == "enforce"
    assert payload.environment == "production"
    assert payload.would_have_blocked is False


def test_governance_observation_observe_fixture() -> None:
    payload = GovernanceObservation(
        policy_mode="observe",
        environment="development",
        would_have_blocked=True,
        would_have_blocked_reason="policy_violation:missing_authority_evidence",
        effective_outcome="proceed",
        observed_outcome="block",
        operator_warning=True,
        audit_required=True,
    )
    assert payload.policy_mode == "observe"
    assert payload.would_have_blocked is True
    assert payload.observed_outcome == "block"


def test_governance_observation_invalid_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        GovernanceObservation(
            policy_mode="shadow",
            environment="test",
            would_have_blocked=True,
            effective_outcome="proceed",
        )
