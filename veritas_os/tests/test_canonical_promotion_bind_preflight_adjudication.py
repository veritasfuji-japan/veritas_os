"""Fail-closed tests for promotion-native Bind preflight adjudication."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_bind_preflight_adjudication import (
    BIND_ENTRY_REQUIREMENTS,
    LOCAL_ADJUDICATION_CHECKS,
    SCOPE_LIMITATIONS,
    CanonicalPromotionBindPreflightAdjudicationError,
    build_canonical_promotion_bind_preflight_adjudication_packet,
    verify_canonical_promotion_bind_preflight_adjudication_packet,
)
from veritas_os.policy.canonical_promotion_pre_bind_validation import (
    build_canonical_promotion_pre_bind_validation_packet,
)
from veritas_os.tests.test_canonical_promotion_execution_intent_readiness import (
    CHECKED_AT,
    _promotion,
    _readiness,
)

PRE_BIND_CHECKED_AT = CHECKED_AT + timedelta(seconds=1)
ADJUDICATED_AT = PRE_BIND_CHECKED_AT + timedelta(seconds=1)


def _pre_bind():
    return build_canonical_promotion_pre_bind_validation_packet(
        _readiness(), checked_at=PRE_BIND_CHECKED_AT
    )


def _packet():
    return build_canonical_promotion_bind_preflight_adjudication_packet(
        _pre_bind(), ADJUDICATED_AT
    )


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def test_exact_authoritative_intent_survives_full_promotion_native_chain() -> None:
    promotion = _promotion(required_human_approval=True)
    readiness = _readiness()
    pre_bind = build_canonical_promotion_pre_bind_validation_packet(
        readiness, checked_at=PRE_BIND_CHECKED_AT
    )
    packet = verify_canonical_promotion_bind_preflight_adjudication_packet(
        build_canonical_promotion_bind_preflight_adjudication_packet(
            pre_bind, ADJUDICATED_AT
        )
    )
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == pre_bind.execution_intent
    assert packet.execution_intent == readiness.execution_intent
    assert packet.execution_intent == promotion.exact_execution_intent
    assert intent.to_dict() == promotion.exact_execution_intent
    assert packet.execution_intent_id == pre_bind.execution_intent_id
    assert packet.execution_intent_id == readiness.execution_intent_id
    assert packet.execution_intent_id == promotion.execution_intent_id
    assert packet.execution_intent_hash == pre_bind.execution_intent_hash
    assert packet.execution_intent_hash == readiness.execution_intent_hash
    assert packet.execution_intent_hash == promotion.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.approval_context == {
        "required_human_approval": True,
        "policy_context_refs": ["policy-context:one"],
    }
    assert "human_approval_receipt_ref" not in packet.approval_context
    assert "human_approval_receipt_hash" not in packet.approval_context
    assert packet.policy_lineage == promotion.exact_execution_intent["policy_lineage"]
    assert packet.local_adjudication_checks == LOCAL_ADJUDICATION_CHECKS
    assert packet.local_adjudication_checks["no_human_approval_proof"] is True
    assert packet.bind_entry_requirements == BIND_ENTRY_REQUIREMENTS
    assert packet.scope_limitations == SCOPE_LIMITATIONS
    assert not hasattr(packet, "human_approval_proven")
    assert not hasattr(packet, "bind_authorized")
    assert not hasattr(packet, "authority_revalidated")


def test_builder_rejects_malformed_source_and_invalid_timeline() -> None:
    malformed = _pre_bind().model_dump(mode="json")
    malformed["pre_bind_validation_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionBindPreflightAdjudicationError,
        match="PBPA_PRE_BIND_VALIDATION_INVALID",
    ):
        build_canonical_promotion_bind_preflight_adjudication_packet(
            malformed, ADJUDICATED_AT
        )
    with pytest.raises(
        CanonicalPromotionBindPreflightAdjudicationError,
        match="PBPA_ADJUDICATED_AT_INVALID",
    ):
        build_canonical_promotion_bind_preflight_adjudication_packet(
            _pre_bind(), ADJUDICATED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        CanonicalPromotionBindPreflightAdjudicationError,
        match="PBPA_ADJUDICATED_BEFORE_PRE_BIND_VALIDATION",
    ):
        build_canonical_promotion_bind_preflight_adjudication_packet(
            _pre_bind(), PRE_BIND_CHECKED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_pre_bind_validation_id", "ppbv:v1:sha256:" + "0" * 64),
        ("source_pre_bind_validation_hash", "0" * 64),
        ("source_pre_bind_validation_packet.pre_bind_validation_hash", "0" * 64),
        ("source_readiness_id", "peir:v1:sha256:" + "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_promotion_id", "cvdp:v1:sha256:" + "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("source_decision_identity.decision_id", "decision:substituted"),
        ("candidate_identity.candidate_id", "candidate:substituted"),
        ("selected_action_lineage.selected_action_evidence_hash", "0" * 64),
        ("policy_snapshot_lineage.policy_snapshot_evidence_hash", "0" * 64),
        ("execution_intent", {}),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("execution_intent.actor_identity", "actor:substituted"),
        ("execution_intent.target_system", "system:substituted"),
        ("execution_intent.target_resource", "resource:substituted"),
        ("execution_intent.intended_action", "action:substituted"),
        ("execution_intent.evidence_refs", ["evidence:substituted"]),
        ("approval_context.required_human_approval", False),
        ("approval_context.policy_context_refs", []),
        ("policy_lineage.version", "policy:substituted"),
        ("policy_lineage.signer_id", "signer:substituted"),
        ("policy_lineage.verified_at", "2026-08-27T00:00:00Z"),
        ("adjudicated_at", "malformed"),
        ("adjudicated_at", "2026-08-27T11:00:00+00:00"),
        ("local_adjudication_checks.no_bind_invocation", False),
        ("local_adjudication_checks_digest", "0" * 64),
        ("bind_entry_requirements.adapter_required", False),
        ("bind_entry_requirements_digest", "0" * 64),
        ("scope_limitations", []),
        ("bind_preflight_adjudication_hash", "0" * 64),
        ("bind_preflight_adjudication_id", "pbpa:v1:sha256:" + "0" * 64),
    ],
)
def test_packet_substitutions_fail_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalPromotionBindPreflightAdjudicationError):
        verify_canonical_promotion_bind_preflight_adjudication_packet(raw)


def test_unknown_trust_shortcut_fails_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["verified"] = True
    with pytest.raises(CanonicalPromotionBindPreflightAdjudicationError):
        verify_canonical_promotion_bind_preflight_adjudication_packet(raw)
