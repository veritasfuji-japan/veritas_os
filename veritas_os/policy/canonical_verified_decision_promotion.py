"""Canonical, deterministic promotion of a verified CDA candidate.

This module stops at an immutable CDA-to-``ExecutionIntent`` mapping.  It does
not establish Bind authority, human approval, authority evidence, adapter
selection, execution, persistence, or an external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.decision_candidate import (
    POLICY_SNAPSHOT_MAX_AGE_SECONDS,
    DecisionCandidate,
    hash_decision_candidate,
    normalize_decision_candidate,
    validate_decision_candidate,
)

if TYPE_CHECKING:
    from veritas_os.governance.canonical_decision_artifact import (
        CanonicalDecisionArtifact,
    )

FORMAT_VERSION = "canonical-verified-decision-promotion/v1"
PROMOTION_MECHANISM = "promote_verified_canonical_decision/v1"
EXECUTION_INTENT_ID_DOMAIN = (
    "veritas.canonical-verified-decision-promotion.execution-intent-id/v1"
)
SELECTED_ACTION_EVIDENCE_DOMAIN = (
    "veritas.canonical-verified-decision-promotion.selected-action-evidence/v1"
)
POLICY_SNAPSHOT_EVIDENCE_DOMAIN = (
    "veritas.canonical-verified-decision-promotion.policy-snapshot-evidence/v1"
)
PACKET_HASH_DOMAIN = "veritas.canonical-verified-decision-promotion.packet/v1"
SCOPE_LIMITATIONS = (
    "NOT_BIND_AUTHORIZATION",
    "NOT_EXECUTION_AUTHORITY",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_ADAPTER_SELECTION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_TRUSTLOG_WRITE",
)


class CanonicalVerifiedDecisionPromotionError(ValueError):
    """Fail-closed canonical promotion construction or verification error."""


class CanonicalVerifiedDecisionPromotionPacket(BaseModel):
    """Strict immutable binding from a verified CDA to one exact intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-verified-decision-promotion/v1"]
    promotion_id: str = Field(pattern=r"^cvdp:v1:sha256:[0-9a-f]{64}$")
    promotion_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    promotion_mechanism: Literal["promote_verified_canonical_decision/v1"]
    promoted_at: str
    canonical_decision_artifact: dict[str, Any]
    canonical_decision_id: str
    canonical_decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_candidate: dict[str, Any]
    candidate_id: str
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_action_evidence: dict[str, Any]
    selected_action_evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_snapshot_evidence: dict[str, Any]
    policy_snapshot_evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    exact_execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_decision_identity: dict[str, Any]
    policy_lineage: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalVerifiedDecisionPromotionError("CVDP_NON_CANONICAL_VALUE")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalVerifiedDecisionPromotionError("CVDP_NON_CANONICAL_VALUE")
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalVerifiedDecisionPromotionError("CVDP_NON_CANONICAL_VALUE")


def _digest(domain: str, value: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _aware_timestamp(value: str | datetime) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalVerifiedDecisionPromotionError(
            "CVDP_PROMOTED_AT_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_PROMOTED_AT_INVALID")
    return parsed.astimezone(UTC)


def _verified_inputs(
    artifact_value: Any,
    candidate_value: Any,
    promoted_at: datetime,
) -> tuple[CanonicalDecisionArtifact, DecisionCandidate]:
    from veritas_os.governance.canonical_decision_artifact import (
        verify_canonical_decision_artifact,
    )

    verification = verify_canonical_decision_artifact(artifact_value)
    if not verification.is_valid or verification.artifact is None:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_CDA_INVALID")
    artifact = verification.artifact
    try:
        candidate = normalize_decision_candidate(candidate_value)
        validation = validate_decision_candidate(candidate)
    except (TypeError, ValueError) as exc:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_CANDIDATE_INVALID") from exc
    if not validation.promotable:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_CANDIDATE_INVALID")
    action = artifact.decision.selected_action_evidence
    if action is None:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_SELECTED_ACTION_MISSING")
    if (
        action.candidate_hash != hash_decision_candidate(candidate)
        or action.chosen_binding_sha256 != artifact.decision.chosen_binding.sha256
    ):
        raise CanonicalVerifiedDecisionPromotionError("CVDP_SELECTED_ACTION_MISMATCH")
    policy = artifact.decision.policy_snapshot_evidence
    if policy is None or policy.signature_verified is not True:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_POLICY_EVIDENCE_INVALID")
    try:
        verified_at = _aware_timestamp(policy.verified_at)
    except CanonicalVerifiedDecisionPromotionError as exc:
        raise CanonicalVerifiedDecisionPromotionError(
            "CVDP_POLICY_EVIDENCE_INVALID"
        ) from exc
    if (
        verified_at > promoted_at
        or promoted_at - verified_at
        > timedelta(seconds=POLICY_SNAPSHOT_MAX_AGE_SECONDS)
    ):
        raise CanonicalVerifiedDecisionPromotionError("CVDP_POLICY_EVIDENCE_STALE")
    return artifact, candidate


def _mapping(
    artifact: CanonicalDecisionArtifact,
    candidate: DecisionCandidate,
    ttl_seconds: int | None,
    expected_state_fingerprint: str | None,
) -> dict[str, Any]:
    policy = artifact.decision.policy_snapshot_evidence
    assert policy is not None
    return {
        "decision_id": artifact.decision_id,
        "request_id": artifact.request_id,
        "policy_snapshot_id": policy.snapshot_id,
        "actor_identity": candidate.actor_identity,
        "target_system": candidate.target_system,
        "target_resource": candidate.target_resource,
        "intended_action": candidate.intended_action,
        "evidence_refs": list(candidate.evidence_refs),
        "decision_hash": artifact.decision_hash,
        "decision_ts": artifact.decision_ts,
        "ttl_seconds": ttl_seconds,
        "expected_state_fingerprint": expected_state_fingerprint,
        "approval_context": {
            "required_human_approval": candidate.required_human_approval,
            "policy_context_refs": list(candidate.policy_context_refs),
        },
        "policy_lineage": {
            "version": policy.version,
            "semantic_digest": policy.semantic_digest,
            "signer_id": policy.signer_id,
            "verified_at": policy.verified_at,
        },
    }


def _intent(mapping: dict[str, Any]) -> ExecutionIntent:
    intent_id = f"ei:v1:sha256:{_digest(EXECUTION_INTENT_ID_DOMAIN, mapping)}"
    return ExecutionIntent(execution_intent_id=intent_id, **mapping)


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(
        PACKET_HASH_DOMAIN,
        {key: value for key, value in raw.items() if key not in {"promotion_id", "promotion_hash"}},
    )


def build_canonical_verified_decision_promotion_packet(
    canonical_decision_artifact: CanonicalDecisionArtifact | dict[str, Any],
    candidate: DecisionCandidate | dict[str, Any],
    *,
    promoted_at: datetime,
    ttl_seconds: int | None = None,
    expected_state_fingerprint: str | None = None,
) -> CanonicalVerifiedDecisionPromotionPacket:
    """Build the exact deterministic intent after all CDA evidence is verified."""
    promoted = _aware_timestamp(promoted_at)
    artifact, normalized = _verified_inputs(
        canonical_decision_artifact, candidate, promoted
    )
    mapping = _mapping(
        artifact, normalized, ttl_seconds, expected_state_fingerprint
    )
    intent = _intent(mapping)
    action = artifact.decision.selected_action_evidence
    policy = artifact.decision.policy_snapshot_evidence
    assert action is not None and policy is not None
    action_json = action.model_dump(mode="json")
    policy_json = policy.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "promotion_id": "cvdp:v1:sha256:" + "0" * 64,
        "promotion_hash": "0" * 64,
        "promotion_mechanism": PROMOTION_MECHANISM,
        "promoted_at": promoted.isoformat().replace("+00:00", "Z"),
        "canonical_decision_artifact": artifact.model_dump(mode="json"),
        "canonical_decision_id": artifact.decision_id,
        "canonical_decision_hash": artifact.decision_hash,
        "normalized_candidate": normalized.to_dict(),
        "candidate_id": normalized.candidate_id,
        "candidate_hash": hash_decision_candidate(normalized),
        "selected_action_evidence": action_json,
        "selected_action_evidence_hash": _digest(
            SELECTED_ACTION_EVIDENCE_DOMAIN, action_json
        ),
        "policy_snapshot_evidence": policy_json,
        "policy_snapshot_evidence_hash": _digest(
            POLICY_SNAPSHOT_EVIDENCE_DOMAIN, policy_json
        ),
        "exact_execution_intent": intent.to_dict(),
        "execution_intent_id": intent.execution_intent_id,
        "execution_intent_hash": hash_execution_intent(intent),
        "source_decision_identity": {
            "decision_id": artifact.decision_id,
            "decision_hash": artifact.decision_hash,
            "decision_ts": artifact.decision_ts,
            "request_id": artifact.request_id,
        },
        "policy_lineage": mapping["policy_lineage"],
        "selected_action_lineage": {
            "candidate_hash": action.candidate_hash,
            "chosen_binding_sha256": action.chosen_binding_sha256,
        },
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        promotion_hash=digest,
        promotion_id=f"cvdp:v1:sha256:{digest}",
    )
    return CanonicalVerifiedDecisionPromotionPacket.model_validate(raw)


def verify_canonical_verified_decision_promotion_packet(
    packet: CanonicalVerifiedDecisionPromotionPacket | Mapping[str, Any],
) -> CanonicalVerifiedDecisionPromotionPacket:
    """Independently reconstruct and fail closed on every declared identity."""
    try:
        raw = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else dict(packet)
        parsed = CanonicalVerifiedDecisionPromotionPacket.model_validate(raw)
        promoted = _aware_timestamp(parsed.promoted_at)
        artifact, candidate = _verified_inputs(
            parsed.canonical_decision_artifact,
            parsed.normalized_candidate,
            promoted,
        )
        declared_intent = ExecutionIntent(**parsed.exact_execution_intent)
        mapping = _mapping(
            artifact,
            candidate,
            declared_intent.ttl_seconds,
            declared_intent.expected_state_fingerprint,
        )
        expected_intent = _intent(mapping)
        action = artifact.decision.selected_action_evidence
        policy = artifact.decision.policy_snapshot_evidence
        assert action is not None and policy is not None
        expected = build_canonical_verified_decision_promotion_packet(
            artifact,
            candidate,
            promoted_at=promoted,
            ttl_seconds=declared_intent.ttl_seconds,
            expected_state_fingerprint=declared_intent.expected_state_fingerprint,
        )
        if (
            parsed.canonical_decision_id != artifact.decision_id
            or parsed.canonical_decision_hash != artifact.decision_hash
            or parsed.candidate_id != candidate.candidate_id
            or parsed.candidate_hash != hash_decision_candidate(candidate)
            or parsed.selected_action_evidence != action.model_dump(mode="json")
            or parsed.policy_snapshot_evidence != policy.model_dump(mode="json")
            or parsed.exact_execution_intent != expected_intent.to_dict()
            or parsed.execution_intent_id != expected_intent.execution_intent_id
            or parsed.execution_intent_hash != hash_execution_intent(expected_intent)
            or parsed.model_dump(mode="json") != expected.model_dump(mode="json")
        ):
            raise CanonicalVerifiedDecisionPromotionError("CVDP_PACKET_MISMATCH")
        return parsed
    except CanonicalVerifiedDecisionPromotionError:
        raise
    except (AssertionError, TypeError, ValueError, ValidationError) as exc:
        raise CanonicalVerifiedDecisionPromotionError("CVDP_PACKET_INVALID") from exc


def canonical_verified_decision_promotion_proof(
    packet: CanonicalVerifiedDecisionPromotionPacket | Mapping[str, Any],
) -> dict[str, bool]:
    """Return only pre-Bind claims established by independent verification."""
    verify_canonical_verified_decision_promotion_packet(packet)
    return {
        "canonical_decision_verified": True,
        "selected_action_verified": True,
        "policy_snapshot_verified": True,
        "candidate_binding_verified": True,
        "deterministic_execution_intent_id_verified": True,
        "execution_intent_hash_verified": True,
        "decision_lineage_proven": True,
        "execution_intent_lineage_proven": True,
        "authority_evidence_proven": False,
        "human_approval_proven": False,
        "real_bind_authorization_issued": False,
        "external_effect_performed": False,
        "real_decision_to_effect_e2e": False,
    }
