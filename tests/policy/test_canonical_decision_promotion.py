"""Tests for the verified canonical-decision promotion boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)
from veritas_os.policy.decision_candidate import (
    DecisionCandidate,
    try_promote_verified_canonical_decision_candidate_to_execution_intent,
)

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1"
    / "vector-01.json"
)


def _artifact():
    source = DecideResponse.model_validate(
        json.loads(VECTOR.read_text(encoding="utf-8"))["source_projection"]
    )
    return build_canonical_decision_artifact(
        source,
        decision_ts=datetime(2031, 2, 3, 4, 5, 6, tzinfo=UTC),
    )


def _candidate(**overrides: object) -> DecisionCandidate:
    values = {
        "action_type": "synthetic_external_webhook",
        "actor_identity": "test-actor:decision-bind-poc",
        "target_system": "local-synthetic-fixture",
        "target_resource": "external-bind-poc.example.test/action",
        "intended_action": "post_synthetic_review",
        "required_authority": ["synthetic:review:create"],
        "required_human_approval": False,
        "risk_level": "low",
    }
    values.update(overrides)
    return DecisionCandidate(**values)


def _promote(artifact=None, **kwargs):
    return try_promote_verified_canonical_decision_candidate_to_execution_intent(
        _candidate(),
        canonical_decision_artifact=artifact or _artifact(),
        policy_snapshot_id=kwargs.pop(
            "policy_snapshot_id", "controlled-synthetic-policy-v1"
        ),
        **kwargs,
    )


def test_verified_cda_supplies_exact_execution_intent_lineage() -> None:
    artifact = _artifact()
    result = _promote(artifact)

    assert result.promoted is True
    assert result.execution_intent is not None
    intent = result.execution_intent
    assert intent.decision_id == artifact.decision_id
    assert intent.decision_hash == artifact.decision_hash
    assert intent.decision_ts == artifact.decision_ts
    assert intent.request_id == artifact.request_id
    assert intent.policy_snapshot_id == "controlled-synthetic-policy-v1"


def test_tampered_cda_hash_and_id_fail_closed() -> None:
    artifact = _artifact().model_dump(mode="json")
    for field, value in (
        ("decision_hash", "0" * 64),
        ("decision_id", "decision:" + "1" * 64),
    ):
        tampered = {**artifact, field: value}
        result = _promote(tampered)
        assert result.promoted is False
        assert result.execution_intent is None
        assert result.fail_closed is True


def test_lineage_overrides_are_not_part_of_helper_contract() -> None:
    artifact = _artifact()
    result = _promote(artifact)

    assert result.execution_intent is not None
    assert result.execution_intent.decision_id == artifact.decision_id
    assert result.execution_intent.decision_hash == artifact.decision_hash
    with pytest.raises(TypeError):
        _promote(artifact, decision_id="caller-decision")
    with pytest.raises(TypeError):
        _promote(artifact, decision_hash="caller-hash")


def test_policy_snapshot_is_explicit_and_required() -> None:
    result = _promote(policy_snapshot_id="")

    assert result.promoted is False
    assert result.execution_intent is None
    assert result.refusal_reason_codes == ["POLICY_SNAPSHOT_ID_MISSING"]


def test_non_promotable_candidate_preserves_existing_refusal() -> None:
    result = try_promote_verified_canonical_decision_candidate_to_execution_intent(
        _candidate(target_resource=""),
        canonical_decision_artifact=_artifact(),
        policy_snapshot_id="controlled-synthetic-policy-v1",
    )

    assert result.promoted is False
    assert result.execution_intent is None
    assert "DECISION_CANDIDATE_MISSING_REQUIRED_FIELD" in (result.refusal_reason_codes)
