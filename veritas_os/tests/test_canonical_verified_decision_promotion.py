"""Fail-closed proofs for canonical verified CDA candidate promotion."""

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
from veritas_os.policy.canonical_verified_decision_promotion import (
    CanonicalVerifiedDecisionPromotionError,
    build_canonical_verified_decision_promotion_packet,
    canonical_verified_decision_promotion_proof,
    verify_canonical_verified_decision_promotion_packet,
)
from veritas_os.policy.decision_candidate import DecisionCandidate

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/vector-01.json"
)
PROMOTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _candidate(marker: str = "one") -> DecisionCandidate:
    return DecisionCandidate(
        candidate_id=f"candidate-{marker}",
        source_model="verified-planner",
        action_type="update",
        actor_identity=f"actor:{marker}",
        target_system="inventory",
        target_resource=f"resource:{marker}",
        intended_action=f"set_state:{marker}",
        required_authority=["inventory:write"],
        required_human_approval=False,
        risk_level="low",
        evidence_refs=[f"evidence:{marker}"],
        policy_context_refs=[f"policy-ref:{marker}"],
    )


def _artifact(candidate: DecisionCandidate | None = None, marker: str = "one"):
    selected = candidate or _candidate(marker)
    source = json.loads(VECTOR.read_text())["source_projection"]
    source.update(
        request_id=f"request-{marker}",
        chosen=selected.to_dict(),
        governance_identity={
            "digest": ("a" if marker == "one" else "b") * 64,
            "policy_version": f"policy-{marker}",
            "signature_verified": True,
            "signer_id": f"signer:{marker}",
            "verified_at": (PROMOTED_AT - timedelta(seconds=30))
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )
    return build_canonical_decision_artifact(
        DecideResponse.model_validate(source),
        decision_ts=(PROMOTED_AT - timedelta(seconds=20)),
    )


def _packet(marker: str = "one"):
    candidate = _candidate(marker)
    return build_canonical_verified_decision_promotion_packet(
        _artifact(candidate, marker),
        candidate,
        promoted_at=PROMOTED_AT,
        ttl_seconds=120,
        expected_state_fingerprint=f"state:{marker}",
    )


def test_repeatable_exact_intent_and_packet_identity() -> None:
    first = _packet()
    second = _packet()

    assert first.exact_execution_intent == second.exact_execution_intent
    assert first.execution_intent_id == second.execution_intent_id
    assert first.execution_intent_hash == second.execution_intent_hash
    assert first.promotion_hash == second.promotion_hash
    assert first.promotion_id == second.promotion_id
    assert verify_canonical_verified_decision_promotion_packet(first) == first
    assert verify_canonical_verified_decision_promotion_packet(second) == second
    proof = canonical_verified_decision_promotion_proof(first)
    assert all(proof[key] is False for key in (
        "authority_evidence_proven",
        "human_approval_proven",
        "real_bind_authorization_issued",
        "external_effect_performed",
        "real_decision_to_effect_e2e",
    ))


def test_different_verified_decision_cannot_collapse_intent_identity() -> None:
    first = _packet("one")
    second = _packet("two")

    assert first.execution_intent_id != second.execution_intent_id
    assert first.execution_intent_hash != second.execution_intent_hash
    assert first.promotion_id != second.promotion_id


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("canonical_decision_artifact.format_version", "bad"),
        ("canonical_decision_artifact.decision_hash", "0" * 64),
        ("canonical_decision_artifact.request_id", "substituted-request"),
        ("normalized_candidate.candidate_id", "substituted-candidate"),
        ("candidate_hash", "0" * 64),
        ("selected_action_evidence.candidate_hash", "0" * 64),
        ("selected_action_lineage.chosen_binding_sha256", "0" * 64),
        ("policy_snapshot_evidence.snapshot_id", "0" * 64),
        ("policy_lineage.semantic_digest", "0" * 64),
        ("exact_execution_intent.actor_identity", "actor:foreign"),
        ("exact_execution_intent.target_system", "foreign-system"),
        ("exact_execution_intent.target_resource", "resource:foreign"),
        ("exact_execution_intent.intended_action", "foreign-action"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("promotion_hash", "0" * 64),
        ("promotion_id", "cvdp:v1:sha256:" + "0" * 64),
    ],
)
def test_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalVerifiedDecisionPromotionError):
        verify_canonical_verified_decision_promotion_packet(raw)


def test_candidate_and_chosen_action_substitution_fail_closed() -> None:
    original = _candidate()
    artifact = _artifact(original)

    with pytest.raises(
        CanonicalVerifiedDecisionPromotionError,
        match="CVDP_SELECTED_ACTION_MISMATCH",
    ):
        build_canonical_verified_decision_promotion_packet(
            artifact,
            _candidate("two"),
            promoted_at=PROMOTED_AT,
        )


def test_stale_policy_evidence_fails_closed() -> None:
    candidate = _candidate()
    artifact = _artifact(candidate)

    with pytest.raises(
        CanonicalVerifiedDecisionPromotionError,
        match="CVDP_POLICY_EVIDENCE_STALE",
    ):
        build_canonical_verified_decision_promotion_packet(
            artifact,
            candidate,
            promoted_at=PROMOTED_AT + timedelta(minutes=10),
        )
