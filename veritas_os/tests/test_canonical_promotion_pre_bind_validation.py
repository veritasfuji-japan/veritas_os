"""Fail-closed tests for promotion-native pre-Bind validation."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_pre_bind_validation import (
    LOCAL_VALIDATION_CHECKS,
    SCOPE_LIMITATIONS,
    CanonicalPromotionPreBindValidationError,
    build_canonical_promotion_pre_bind_validation_packet,
    verify_canonical_promotion_pre_bind_validation_packet,
)
from veritas_os.tests.test_canonical_promotion_execution_intent_readiness import (
    CHECKED_AT,
    _promotion,
    _readiness,
)

VALIDATED_AT = CHECKED_AT + timedelta(seconds=1)


def _packet():
    return build_canonical_promotion_pre_bind_validation_packet(
        _readiness(), checked_at=VALIDATED_AT
    )


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def test_exact_intent_survives_end_to_end_without_approval_receipt() -> None:
    promotion = _promotion(required_human_approval=True)
    readiness = _readiness()
    packet = build_canonical_promotion_pre_bind_validation_packet(
        readiness, checked_at=VALIDATED_AT
    )
    verified = verify_canonical_promotion_pre_bind_validation_packet(packet)
    intent = ExecutionIntent(**verified.execution_intent)

    assert verified.execution_intent == readiness.execution_intent
    assert verified.execution_intent == promotion.exact_execution_intent
    assert intent.to_dict() == promotion.exact_execution_intent
    assert verified.execution_intent_id == readiness.execution_intent_id
    assert verified.execution_intent_id == promotion.execution_intent_id
    assert verified.execution_intent_hash == readiness.execution_intent_hash
    assert verified.execution_intent_hash == promotion.execution_intent_hash
    assert verified.execution_intent_hash == hash_execution_intent(intent)
    assert verified.approval_context == {
        "required_human_approval": True,
        "policy_context_refs": ["policy-context:one"],
    }
    assert "human_approval_receipt_ref" not in verified.approval_context
    assert "human_approval_receipt_hash" not in verified.approval_context
    assert verified.policy_lineage == readiness.execution_intent["policy_lineage"]
    assert verified.local_validation_checks == LOCAL_VALIDATION_CHECKS
    assert verified.scope_limitations == SCOPE_LIMITATIONS
    assert not hasattr(verified, "human_approval_proven")
    assert not hasattr(verified, "ready_for_bind")


def test_builder_rejects_malformed_readiness_and_timeline() -> None:
    raw = _readiness().model_dump(mode="json")
    raw["readiness_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionPreBindValidationError,
        match="PPBV_READINESS_INVALID",
    ):
        build_canonical_promotion_pre_bind_validation_packet(
            raw, checked_at=VALIDATED_AT
        )
    with pytest.raises(
        CanonicalPromotionPreBindValidationError,
        match="PPBV_CHECKED_AT_INVALID",
    ):
        build_canonical_promotion_pre_bind_validation_packet(
            _readiness(), checked_at=VALIDATED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        CanonicalPromotionPreBindValidationError,
        match="PPBV_CHECKED_BEFORE_READINESS",
    ):
        build_canonical_promotion_pre_bind_validation_packet(
            _readiness(), checked_at=CHECKED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_readiness_id", "peir:v1:sha256:" + "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_readiness_packet.readiness_id", "peir:v1:sha256:" + "0" * 64),
        ("source_readiness_packet.readiness_hash", "0" * 64),
        ("source_readiness_packet.source_promotion_hash", "0" * 64),
        ("source_promotion_id", "cvdp:v1:sha256:" + "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("execution_intent", {}),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("execution_intent.decision_id", "decision:substituted"),
        ("execution_intent.request_id", "request:substituted"),
        ("execution_intent.policy_snapshot_id", "policy:substituted"),
        ("execution_intent.actor_identity", "actor:substituted"),
        ("execution_intent.target_system", "system:substituted"),
        ("execution_intent.target_resource", "resource:substituted"),
        ("execution_intent.intended_action", "action:substituted"),
        ("execution_intent.evidence_refs", []),
        ("execution_intent.evidence_refs", ["evidence:substituted"]),
        ("execution_intent.decision_ts", "not-a-time"),
        ("execution_intent.ttl_seconds", -1),
        ("execution_intent.ttl_seconds", True),
        ("approval_context.required_human_approval", False),
        ("approval_context.policy_context_refs", []),
        ("execution_intent.approval_context.required_human_approval", False),
        ("execution_intent.approval_context.policy_context_refs", []),
        ("policy_lineage.version", "substituted"),
        ("policy_lineage.signer_id", "signer:substituted"),
        ("policy_lineage.verified_at", "2026-08-27T00:00:00Z"),
        ("execution_intent.policy_lineage.signer_id", "signer:substituted"),
        ("checked_at", "2026-08-27T11:00:00+00:00"),
        ("local_validation_checks.no_bind_invocation", False),
        ("local_validation_checks_digest", "0" * 64),
        ("scope_limitations", []),
        ("pre_bind_validation_hash", "0" * 64),
        ("pre_bind_validation_id", "ppbv:v1:sha256:" + "0" * 64),
        ("source_decision_identity.decision_id", "decision:substituted"),
        ("candidate_identity.candidate_id", "candidate:substituted"),
        ("selected_action_lineage.selected_action_evidence_hash", "0" * 64),
        ("policy_snapshot_lineage.policy_snapshot_evidence_hash", "0" * 64),
    ],
)
def test_all_packet_and_lineage_tampering_fails_closed(
    path: str, value: object
) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalPromotionPreBindValidationError):
        verify_canonical_promotion_pre_bind_validation_packet(raw)


def test_unknown_fields_and_noncanonical_values_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["caller_declared_verified"] = True
    with pytest.raises(CanonicalPromotionPreBindValidationError):
        verify_canonical_promotion_pre_bind_validation_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["execution_intent"]["ttl_seconds"] = float("nan")
    with pytest.raises(CanonicalPromotionPreBindValidationError):
        verify_canonical_promotion_pre_bind_validation_packet(raw)
