"""Fail-closed tests for promotion-native ExecutionIntent readiness."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)
from veritas_os.policy.canonical_promotion_execution_intent_readiness import (
    CanonicalPromotionExecutionIntentReadinessError,
    build_canonical_promotion_execution_intent_readiness_packet,
    verify_canonical_promotion_execution_intent_readiness_packet,
)
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet,
    verify_canonical_verified_decision_promotion_packet,
)
from veritas_os.policy.decision_candidate import DecisionCandidate

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/vector-01.json"
)
PROMOTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
CHECKED_AT = PROMOTED_AT + timedelta(seconds=1)
SEMANTIC_FIELDS = (
    "decision_id",
    "request_id",
    "policy_snapshot_id",
    "actor_identity",
    "target_system",
    "target_resource",
    "intended_action",
    "evidence_refs",
    "decision_hash",
    "decision_ts",
    "ttl_seconds",
    "expected_state_fingerprint",
    "approval_context",
    "policy_lineage",
)


def _promotion(*, required_human_approval: bool = True):
    candidate = DecisionCandidate(
        candidate_id="candidate-one",
        source_model="verified-planner",
        action_type="update",
        actor_identity="actor:one",
        target_system="inventory",
        target_resource="resource:one",
        intended_action="set_state:one",
        required_authority=["inventory:write"],
        required_human_approval=required_human_approval,
        risk_level="medium",
        evidence_refs=["candidate-evidence:one"],
        policy_context_refs=["policy-context:one"],
    )
    source = json.loads(VECTOR.read_text(encoding="utf-8"))["source_projection"]
    source.update(
        request_id="request-one",
        chosen=candidate.to_dict(),
        governance_identity={
            "digest": "a" * 64,
            "policy_version": "policy-one",
            "signature_verified": True,
            "signer_id": "signer:one",
            "verified_at": (PROMOTED_AT - timedelta(seconds=30))
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )
    artifact = build_canonical_decision_artifact(
        DecideResponse.model_validate(source),
        decision_ts=PROMOTED_AT - timedelta(seconds=20),
    )
    return build_canonical_verified_decision_promotion_packet(
        artifact,
        candidate,
        promoted_at=PROMOTED_AT,
        ttl_seconds=120,
        expected_state_fingerprint="state:one",
    )


def _readiness():
    return build_canonical_promotion_execution_intent_readiness_packet(
        _promotion(), checked_at=CHECKED_AT
    )


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def test_exact_promoted_intent_and_native_shapes_are_preserved() -> None:
    promotion = verify_canonical_verified_decision_promotion_packet(_promotion())
    readiness = verify_canonical_promotion_execution_intent_readiness_packet(
        build_canonical_promotion_execution_intent_readiness_packet(
            promotion, checked_at=CHECKED_AT
        )
    )

    assert readiness.execution_intent == promotion.exact_execution_intent
    assert readiness.execution_intent_id == promotion.execution_intent_id
    assert readiness.execution_intent_hash == promotion.execution_intent_hash
    assert readiness.source_to_execution_intent_mapping == {
        field: promotion.exact_execution_intent[field]
        for field in SEMANTIC_FIELDS
    }
    approval = readiness.source_to_execution_intent_mapping["approval_context"]
    assert approval == promotion.exact_execution_intent["approval_context"]
    assert set(approval) == {
        "required_human_approval",
        "policy_context_refs",
    }
    policy = readiness.source_to_execution_intent_mapping["policy_lineage"]
    assert policy == promotion.exact_execution_intent["policy_lineage"]
    assert set(policy) == {
        "version",
        "semantic_digest",
        "signer_id",
        "verified_at",
    }


def test_human_approval_requirement_needs_no_pre_gate_receipt() -> None:
    readiness = verify_canonical_promotion_execution_intent_readiness_packet(
        build_canonical_promotion_execution_intent_readiness_packet(
            _promotion(required_human_approval=True), checked_at=CHECKED_AT
        )
    )

    approval = readiness.source_to_execution_intent_mapping["approval_context"]
    assert approval["required_human_approval"] is True
    assert "human_approval_receipt_ref" not in approval
    assert "human_approval_receipt_hash" not in approval


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_promotion_packet.format_version", "malformed"),
        ("source_promotion_packet.promotion_hash", "0" * 64),
        ("source_decision_identity.decision_id", "decision:substituted"),
        ("source_decision_identity.decision_hash", "0" * 64),
        ("candidate_identity.candidate_id", "candidate-substituted"),
        ("candidate_identity.candidate_hash", "0" * 64),
        (
            "selected_action_lineage.selected_action_evidence.candidate_hash",
            "0" * 64,
        ),
        (
            "selected_action_lineage.selected_action_evidence_hash",
            "0" * 64,
        ),
        (
            "policy_snapshot_lineage.policy_snapshot_evidence.snapshot_id",
            "0" * 64,
        ),
        ("policy_snapshot_lineage.policy_snapshot_evidence_hash", "0" * 64),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("execution_intent.actor_identity", "actor:substituted"),
        ("execution_intent.target_system", "system:substituted"),
        ("execution_intent.target_resource", "resource:substituted"),
        ("execution_intent.intended_action", "action:substituted"),
        ("execution_intent.evidence_refs", ["evidence:substituted"]),
        (
            "source_to_execution_intent_mapping.approval_context",
            {"required_human_approval": False, "policy_context_refs": []},
        ),
        ("source_to_execution_intent_mapping.policy_lineage", {}),
        (
            (
                "source_to_execution_intent_mapping.approval_context."
                "required_human_approval"
            ),
            False,
        ),
        (
            "source_to_execution_intent_mapping.approval_context.policy_context_refs",
            [],
        ),
        (
            "source_to_execution_intent_mapping.policy_lineage.signer_id",
            "signer:substituted",
        ),
        (
            "source_to_execution_intent_mapping.policy_lineage.verified_at",
            "2026-08-27T11:00:00Z",
        ),
        ("source_promotion_id", "cvdp:v1:sha256:" + "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("readiness_hash", "0" * 64),
        ("readiness_id", "peir:v1:sha256:" + "0" * 64),
    ],
)
def test_readiness_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_readiness().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalPromotionExecutionIntentReadinessError):
        verify_canonical_promotion_execution_intent_readiness_packet(raw)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("canonical_decision_id", "decision:substituted"),
        ("candidate_id", "candidate-substituted"),
        ("selected_action_evidence_hash", "0" * 64),
        ("policy_snapshot_evidence_hash", "0" * 64),
    ],
)
def test_embedded_promotion_lineage_tampering_fails_closed(
    path: str, value: object
) -> None:
    raw = deepcopy(_readiness().model_dump(mode="json"))
    _set_path(raw["source_promotion_packet"], path, value)

    with pytest.raises(CanonicalPromotionExecutionIntentReadinessError):
        verify_canonical_promotion_execution_intent_readiness_packet(raw)
