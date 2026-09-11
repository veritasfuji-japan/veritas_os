"""Non-executing governance closure for verified external measurement evidence.

A verified external measurement remains evidence only.  This PoC harness keeps
that evidence structurally separate from Policy, AuthorityEvidence, and Human
Approval, then reuses the existing commit-boundary evaluator to produce an
inspectable governance result.  It never creates BindAuthorization, accesses
credentials, dispatches a network action, or performs an external effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence
from veritas_os.governance.commit_boundary import CommitBoundaryEvaluator
from veritas_os.governance.external_measurement_evidence import (
    ExternalMeasurementTrustPolicy,
    VerifiedExternalMeasurementEvidence,
    validate_verified_external_measurement_evidence,
)
from veritas_os.security.hash import sha256_of_canonical_json

CLOSURE_PACKET_VERSION = "external-measurement-governance-closure-v1"


class ExternalMeasurementGovernanceClosureError(ValueError):
    """Fail-closed error raised when the closure inputs are not admissible."""


@dataclass(frozen=True)
class ExternalMeasurementGovernanceClosureResult:
    """Inspectable non-executing governance result and reviewer-facing packet."""

    governance_outcome: str
    authority_validation_status: str
    packet: dict[str, Any]
    packet_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible representation."""
        return {
            "governance_outcome": self.governance_outcome,
            "authority_validation_status": self.authority_validation_status,
            "packet": dict(self.packet),
            "packet_hash": self.packet_hash,
        }


def _normalize_policy_evaluation(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_policy_evaluation_invalid"
        )

    policy_snapshot_id = str(value.get("policy_snapshot_id", "")).strip()
    if not policy_snapshot_id:
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_policy_snapshot_missing"
        )

    admissible = value.get("admissible")
    if not isinstance(admissible, bool):
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_policy_admissibility_invalid"
        )

    evaluation_id = str(value.get("evaluation_id", "")).strip()
    reasons_raw = value.get("reasons", [])
    if not isinstance(reasons_raw, list) or not all(
        isinstance(item, str) for item in reasons_raw
    ):
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_policy_reasons_invalid"
        )

    return {
        "evaluation_id": evaluation_id or "unspecified-policy-evaluation",
        "policy_snapshot_id": policy_snapshot_id,
        "admissible": admissible,
        "reasons": sorted(item.strip() for item in reasons_raw if item.strip()),
        "source": "independent_policy_evaluation",
    }


def _failure_reasons(boundary_result: Any) -> list[str]:
    reasons = {
        str(item.reason)
        for item in (
            list(boundary_result.failed_predicates)
            + list(boundary_result.stale_predicates)
            + list(boundary_result.missing_predicates)
        )
        if str(item.reason).strip()
    }
    reasons.update(str(item) for item in boundary_result.refusal_basis if str(item))
    reasons.update(str(item) for item in boundary_result.escalation_basis if str(item))
    return sorted(reasons)


def _approval_summary(human_approval_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "approved": bool(human_approval_state.get("approved", False)),
        "approval_receipt_id": human_approval_state.get("approval_receipt_id"),
        "receipt_hash": human_approval_state.get("receipt_hash"),
        "source": human_approval_state.get("source"),
        "failure_reasons": sorted(
            str(item)
            for item in human_approval_state.get("failure_reasons", [])
            if str(item)
        ),
    }


def close_verified_external_measurement_governance(
    *,
    verified_measurement: VerifiedExternalMeasurementEvidence,
    measurement_trust_policy: ExternalMeasurementTrustPolicy,
    action_contract: ActionClassContract,
    authority_evidence: AuthorityEvidence | None,
    human_approval_state: dict[str, Any],
    policy_evaluation: dict[str, Any],
    requested_scope: list[str],
    required_evidence_metadata: dict[str, Any],
    evidence_freshness_metadata: dict[str, Any],
    actor_identity: str,
    now: datetime | None = None,
) -> ExternalMeasurementGovernanceClosureResult:
    """Close the post-measurement governance path without executing anything.

    The external measurement is revalidated only as external evidence.  The
    policy evaluation, AuthorityEvidence, and Human Approval state are supplied
    independently and are evaluated through the existing commit-boundary
    machinery.  The returned ``commit`` outcome means only that the supplied
    governance inputs are admissible at this non-executing review boundary.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_now_timezone_required"
        )

    measurement_failures = validate_verified_external_measurement_evidence(
        verified_measurement,
        trust_policy=measurement_trust_policy,
        now=current,
    )
    if measurement_failures:
        raise ExternalMeasurementGovernanceClosureError(
            "external_measurement_closure_measurement_invalid:"
            + ",".join(sorted(set(measurement_failures)))
        )

    normalized_policy = _normalize_policy_evaluation(policy_evaluation)
    policy_snapshot_id = normalized_policy["policy_snapshot_id"]

    boundary_result = CommitBoundaryEvaluator().evaluate(
        execution_intent={
            "action_class": action_contract.action_class,
            "admissible": normalized_policy["admissible"],
            "non_executing_poc": True,
        },
        action_contract=action_contract,
        authority_evidence=authority_evidence,
        requested_scope=list(requested_scope),
        required_evidence_metadata=dict(required_evidence_metadata),
        evidence_freshness_metadata=dict(evidence_freshness_metadata),
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        human_approval_state=dict(human_approval_state),
        bind_context_metadata={
            "poc_closure_harness": True,
            "execution_disabled": True,
        },
        now=current,
    )

    authority_summary = {
        "authority_evidence_id": (
            authority_evidence.authority_evidence_id
            if authority_evidence is not None
            else None
        ),
        "authority_evidence_hash": (
            authority_evidence.evidence_hash if authority_evidence is not None else None
        ),
        "source": "independent_authority_evidence",
    }
    decision_record = {
        "decision_type": "commit_boundary_result",
        "outcome": boundary_result.commit_boundary_result,
        "authority_validation_status": boundary_result.authority_validation_status,
        "reason_summary": boundary_result.reason_summary,
        "failure_reasons": _failure_reasons(boundary_result),
        "refusal_basis": sorted(str(item) for item in boundary_result.refusal_basis),
        "escalation_basis": sorted(
            str(item) for item in boundary_result.escalation_basis
        ),
        "irreversibility_boundary_id": boundary_result.irreversibility_boundary_id,
        "evaluated_at": boundary_result.evaluated_at,
        "execution_performed": False,
        "semantics": "non_executing_governance_admissibility_only",
    }

    packet_without_hash = {
        "packet_version": CLOSURE_PACKET_VERSION,
        "generated_at": current.isoformat(),
        "external_measurement": {
            "evidence_id": verified_measurement.evidence.evidence_id,
            "provider_id": verified_measurement.evidence.provider_id,
            "artifact_id": verified_measurement.evidence.artifact_id,
            "evidence_hash": verified_measurement.evidence_hash,
            "verification_proof_hash": (
                verified_measurement.verification_proof_hash
            ),
            "trust_policy_id": verified_measurement.trust_policy_id,
            "trust_policy_hash": verified_measurement.trust_policy_hash,
            "replay_key": verified_measurement.replay_key,
            "role": "external_measurement_evidence_only",
        },
        "policy_evaluation": normalized_policy,
        "authority": authority_summary,
        "human_approval": _approval_summary(human_approval_state),
        "governance_decision": decision_record,
        "requested_scope": sorted(str(item) for item in requested_scope),
        "claim_boundary": {
            "external_measurement_converted_to_authority": False,
            "external_measurement_converted_to_human_approval": False,
            "external_measurement_converted_to_bind_authorization": False,
            "external_measurement_directly_controls_governance_outcome": False,
            "governance_decision_created": True,
            "bind_authorization_created": False,
            "credentials_accessed": False,
            "network_dispatch_performed": False,
            "external_effect_performed": False,
            "outcome_is_non_executing_governance_evaluation": True,
        },
        "non_claims": [
            "not production validation",
            "not live external interoperability by itself",
            "not execution authority",
            "not BindAuthorization issuance",
            "not credential use",
            "not network dispatch",
            "not an external effect",
        ],
    }
    packet_hash = sha256_of_canonical_json(packet_without_hash)
    packet = {**packet_without_hash, "packet_hash": packet_hash}

    return ExternalMeasurementGovernanceClosureResult(
        governance_outcome=boundary_result.commit_boundary_result,
        authority_validation_status=boundary_result.authority_validation_status,
        packet=packet,
        packet_hash=packet_hash,
    )
