"""Verified Canonical Decision to Real Bind Authorization issuance boundary.

This module adds no authority or review primitive.  It composes the existing
canonical decision, recursive gate-review, ExecutionIntent, and signed Real
Bind Authorization verifiers and refuses issuance if any copy of the intent
lineage differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from veritas_os.governance.canonical_decision_artifact import (
    CanonicalDecisionArtifact,
    verify_canonical_decision_artifact,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.decision_candidate import (
    DecisionCandidate,
    try_promote_verified_canonical_decision_candidate_to_execution_intent,
)
from veritas_os.policy.live_adapter_bind_authorization import (
    BindAuthorizationSigner,
    BindAuthorizationTrustInputs,
    CanonicalLiveAdapterBindAuthorizationArtifact,
    RealBindAuthorizationGovernanceInputs,
    build_live_adapter_bind_authorization_artifact,
    verify_live_adapter_bind_authorization_artifact,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)


class RealDecisionBindAuthorizationError(ValueError):
    """Raised when independently verified decision lineage is not identical."""


@dataclass(frozen=True)
class VerifiedRealDecisionBindAuthorization:
    """Result of the non-effecting, fail-closed issuance composition."""

    canonical_decision_artifact: CanonicalDecisionArtifact
    execution_intent: ExecutionIntent
    execution_intent_hash: str
    authorization: CanonicalLiveAdapterBindAuthorizationArtifact


def _require_exact_intent(
    expected: ExecutionIntent,
    actual: Any,
    actual_id: str,
    actual_hash: str,
    *,
    boundary: str,
) -> None:
    """Require object, content-addressed identity, and digest equality."""
    expected_raw = expected.to_dict()
    actual_raw = (
        actual.model_dump(mode="json")
        if hasattr(actual, "model_dump")
        else actual
    )
    expected_hash = hash_execution_intent(expected)
    if (
        actual_raw != expected_raw
        or actual_id != expected.execution_intent_id
        or actual_hash != expected_hash
    ):
        raise RealDecisionBindAuthorizationError(
            f"RDBA_{boundary}_EXECUTION_INTENT_MISMATCH"
        )


def issue_verified_real_decision_bind_authorization(
    *,
    canonical_decision_artifact: CanonicalDecisionArtifact | dict[str, Any],
    candidate: DecisionCandidate | dict[str, Any],
    policy_snapshot_id: str,
    source_gate_review_packet: Any,
    signed_authorization_decision_artifact: Any,
    valid_from: datetime | str,
    valid_until: datetime | str,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    authorization_issuer_signer: BindAuthorizationSigner,
    ttl_seconds: int | None = None,
    expected_state_fingerprint: str | None = None,
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
) -> VerifiedRealDecisionBindAuthorization:
    """Issue authorization only for one independently verified decision intent.

    The function deliberately accepts no decision or ExecutionIntent identity
    override.  The CDA verifier supplies decision lineage, the canonical
    promotion helper derives the intent, and both the recursively verified
    source packet and independently verified authorization must contain the
    exact same intent object, identity, and content-derived hash.

    Raises:
        RealDecisionBindAuthorizationError: If verification or lineage differs.
        LiveAdapterBindAuthorizationError: If existing governance fails closed.
    """
    cda_result = verify_canonical_decision_artifact(canonical_decision_artifact)
    if not cda_result.is_valid or cda_result.artifact is None:
        raise RealDecisionBindAuthorizationError("RDBA_CANONICAL_DECISION_INVALID")
    cda = cda_result.artifact

    promotion = try_promote_verified_canonical_decision_candidate_to_execution_intent(
        candidate,
        canonical_decision_artifact=cda,
        policy_snapshot_id=policy_snapshot_id,
        ttl_seconds=ttl_seconds,
        expected_state_fingerprint=expected_state_fingerprint,
        approval_context=approval_context,
        policy_lineage=policy_lineage,
    )
    if not promotion.promoted or promotion.execution_intent is None:
        raise RealDecisionBindAuthorizationError("RDBA_PROMOTION_REFUSED")
    intent = promotion.execution_intent
    if (
        intent.decision_id != cda.decision_id
        or intent.decision_hash != cda.decision_hash
        or intent.decision_ts != cda.decision_ts
        or intent.request_id != cda.request_id
    ):
        raise RealDecisionBindAuthorizationError("RDBA_DECISION_LINEAGE_MISMATCH")

    if not isinstance(governance_inputs, RealBindAuthorizationGovernanceInputs):
        raise RealDecisionBindAuthorizationError("RDBA_GOVERNANCE_INPUTS_REQUIRED")
    source = verify_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source_gate_review_packet,
        expected_source=governance_inputs.expected_source,
        expected_contract=governance_inputs.action_contract,
    )
    _require_exact_intent(
        intent,
        source.execution_intent,
        source.execution_intent_id,
        source.execution_intent_hash,
        boundary="SOURCE",
    )
    issued = build_live_adapter_bind_authorization_artifact(
        source,
        signed_authorization_decision_artifact,
        valid_from,
        valid_until,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
        authorization_issuer_signer=authorization_issuer_signer,
    )
    verified = verify_live_adapter_bind_authorization_artifact(
        issued,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    _require_exact_intent(
        intent,
        verified.execution_intent,
        verified.execution_intent_id,
        verified.execution_intent_hash,
        boundary="AUTHORIZATION",
    )
    return VerifiedRealDecisionBindAuthorization(
        canonical_decision_artifact=cda,
        execution_intent=intent,
        execution_intent_hash=hash_execution_intent(intent),
        authorization=verified,
    )


__all__ = [
    "RealDecisionBindAuthorizationError",
    "VerifiedRealDecisionBindAuthorization",
    "issue_verified_real_decision_bind_authorization",
]
