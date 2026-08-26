"""Tests for authenticated CDA-to-ExecutionIntent promotion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    CDA_DECISION_ID_PREFIX,
    build_canonical_decision_artifact,
    canonical_decision_preimage,
    strict_canonical_json_bytes,
)
from veritas_os.policy.decision_candidate import (
    DecisionCandidate,
    try_promote_verified_canonical_decision_candidate_to_execution_intent,
    verified_canonical_promotion_proof_report,
)
from veritas_os.security.hash import sha256_hex

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1"
    / "vector-01.json"
)
NOW = datetime(2031, 2, 3, 4, 5, 6, tzinfo=UTC)
POLICY_DIGEST = "a" * 64


def _candidate(**overrides: object) -> DecisionCandidate:
    values = {
        "candidate_id": "selected-candidate-1",
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


def _artifact(
    *,
    candidate: DecisionCandidate | None = None,
    verified_at: datetime = NOW,
    signature_verified: bool = True,
    include_selected_action: bool = True,
):
    source_payload = json.loads(VECTOR.read_text(encoding="utf-8"))[
        "source_projection"
    ]
    source_payload["chosen"] = (
        (candidate or _candidate()).to_dict()
        if include_selected_action
        else {"id": "not-a-structured-action"}
    )
    source_payload["governance_identity"] = {
        "policy_version": "synthetic-v7",
        "digest": POLICY_DIGEST,
        "signature_verified": signature_verified,
        "signer_id": "policy-root-1",
        "verified_at": verified_at.isoformat().replace("+00:00", "Z"),
    }
    source = DecideResponse.model_validate(source_payload)
    return build_canonical_decision_artifact(source, decision_ts=NOW)


def _promote(candidate: DecisionCandidate | None = None, artifact=None, **kwargs):
    return try_promote_verified_canonical_decision_candidate_to_execution_intent(
        candidate or _candidate(),
        canonical_decision_artifact=artifact or _artifact(),
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


def test_verified_evidence_supplies_all_execution_intent_lineage() -> None:
    artifact = _artifact()
    result = _promote(artifact=artifact)

    assert result.promoted is True
    assert result.execution_intent is not None
    intent = result.execution_intent
    assert intent.decision_id == artifact.decision_id
    assert intent.decision_hash == artifact.decision_hash
    assert intent.decision_ts == artifact.decision_ts
    assert intent.request_id == artifact.request_id
    assert intent.policy_snapshot_id == POLICY_DIGEST
    assert intent.policy_lineage == {
        "version": "synthetic-v7",
        "semantic_digest": POLICY_DIGEST,
        "signer_id": "policy-root-1",
        "verified_at": "2031-02-03T04:05:06Z",
    }
    assert verified_canonical_promotion_proof_report(result, artifact) == {
        "policy_snapshot_lineage_proven": True,
        "selected_action_lineage_proven": True,
        "decision_lineage_proven": True,
        "execution_intent_lineage_proven": True,
    }


def test_foreign_caller_policy_snapshot_is_rejected() -> None:
    result = _promote(policy_snapshot_id="b" * 64)

    assert result.promoted is False
    assert result.refusal_reason_codes == ["POLICY_SNAPSHOT_ID_MISMATCH"]


@pytest.mark.parametrize(
    ("artifact", "reason"),
    [
        (
            _artifact(verified_at=NOW - timedelta(seconds=301)),
            "POLICY_SNAPSHOT_PROVENANCE_STALE",
        ),
        (
            _artifact(signature_verified=False),
            "POLICY_SNAPSHOT_PROVENANCE_INVALID",
        ),
    ],
)
def test_stale_or_unverifiable_policy_snapshot_is_rejected(
    artifact, reason: str
) -> None:
    result = _promote(artifact=artifact)

    assert result.promoted is False
    assert reason in result.refusal_reason_codes


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(candidate_id="foreign-candidate"),
        _candidate(intended_action="tampered_after_decision"),
    ],
)
def test_candidate_different_from_selected_action_is_rejected(
    candidate: DecisionCandidate,
) -> None:
    result = _promote(candidate=candidate)

    assert result.promoted is False
    assert result.refusal_reason_codes == ["SELECTED_ACTION_BINDING_MISMATCH"]


def test_chosen_binding_hash_tampering_is_rejected() -> None:
    raw = _artifact().model_dump(mode="json")
    raw["decision"]["chosen_binding"]["sha256"] = "0" * 64
    provisional = type(_artifact()).model_validate(raw)
    decision_hash = sha256_hex(
        strict_canonical_json_bytes(canonical_decision_preimage(provisional))
    )
    raw["decision_hash"] = decision_hash
    raw["decision_id"] = CDA_DECISION_ID_PREFIX + decision_hash

    result = _promote(artifact=raw)

    assert result.promoted is False
    assert result.refusal_reason_codes == ["SELECTED_ACTION_BINDING_MISMATCH"]


def test_missing_selected_action_evidence_is_rejected() -> None:
    result = _promote(artifact=_artifact(include_selected_action=False))

    assert result.promoted is False
    assert result.refusal_reason_codes == ["SELECTED_ACTION_EVIDENCE_MISSING"]


def test_caller_cannot_override_verified_policy_lineage() -> None:
    result = _promote(
        policy_snapshot_id=POLICY_DIGEST,
        policy_lineage={"version": "attacker-version"},
    )

    assert result.promoted is False
    assert result.execution_intent is None
    assert result.refusal_reason_codes == [
        "POLICY_SNAPSHOT_LINEAGE_OVERRIDE_REFUSED"
    ]


def test_decision_lineage_override_is_not_part_of_contract() -> None:
    with pytest.raises(TypeError):
        _promote(decision_hash="caller-hash")
