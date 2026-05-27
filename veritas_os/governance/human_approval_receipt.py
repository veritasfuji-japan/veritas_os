"""Local/offline deterministic Human Approval Receipt artifact helpers.

This module intentionally stays local/offline and deterministic for v1.
No live identity-provider, signature service, or network integrations are included.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from veritas_os.security.hash import sha256_of_canonical_json

ApprovalResult = Literal["approved", "denied", "expired", "indeterminate"]


@dataclass(frozen=True)
class HumanApprovalReceipt:
    """Deterministic local/offline human approval receipt artifact."""

    approval_receipt_id: str
    decision_id: str
    execution_intent_id: str
    approver_identity: str
    approver_role: str
    approved_action_class: str
    approved_scope: list[str]
    approval_basis_refs: list[str]
    approved_at: str
    expires_at: str
    policy_snapshot_id: str | None
    authority_evidence_id: str | None
    approval_result: ApprovalResult
    signature_verified: bool
    receipt_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain deterministic dictionary representation."""
        return {
            "approval_receipt_id": self.approval_receipt_id,
            "decision_id": self.decision_id,
            "execution_intent_id": self.execution_intent_id,
            "approver_identity": self.approver_identity,
            "approver_role": self.approver_role,
            "approved_action_class": self.approved_action_class,
            "approved_scope": sorted(str(scope) for scope in self.approved_scope),
            "approval_basis_refs": sorted(str(ref) for ref in self.approval_basis_refs),
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "policy_snapshot_id": self.policy_snapshot_id,
            "authority_evidence_id": self.authority_evidence_id,
            "approval_result": self.approval_result,
            "signature_verified": self.signature_verified,
            "receipt_hash": self.receipt_hash,
            "metadata": self.metadata,
        }

    def to_dict_for_hash(self) -> dict[str, Any]:
        """Return canonical hash payload excluding ``receipt_hash`` recursion."""
        payload = self.to_dict()
        payload.pop("receipt_hash", None)
        return payload

    def deterministic_digest(self) -> str:
        """Compute canonical SHA-256 digest of the receipt hash payload."""
        return sha256_of_canonical_json(self.to_dict_for_hash())


def with_receipt_hash(receipt: HumanApprovalReceipt) -> HumanApprovalReceipt:
    """Return a new receipt finalized with a deterministic ``receipt_hash``."""
    digest = receipt.deterministic_digest()
    data = receipt.to_dict()
    data["receipt_hash"] = digest
    return HumanApprovalReceipt(**data)


@dataclass(frozen=True)
class HumanApprovalValidationResult:
    """Deterministic fail-closed validation result for human approval receipts."""

    is_valid: bool
    failure_reasons: list[str]


def validate_human_approval_receipt(
    receipt: HumanApprovalReceipt | None,
    *,
    requested_scope: list[str],
    action_class: str | None = None,
    policy_snapshot_id: str | None = None,
    now: datetime | None = None,
) -> HumanApprovalValidationResult:
    """Validate a human approval receipt with deterministic fail-closed behavior."""
    if receipt is None:
        return HumanApprovalValidationResult(False, ["human_approval_missing"])

    failure_reasons: list[str] = []
    evaluated_at = now or datetime.now(UTC)

    if receipt.approval_result != "approved":
        failure_reasons.append("human_approval_not_approved")
    if receipt.signature_verified is not True:
        failure_reasons.append("human_approval_signature_unverified")
    if not str(receipt.approver_identity).strip():
        failure_reasons.append("human_approval_approver_identity_missing")
    if not str(receipt.approver_role).strip():
        failure_reasons.append("human_approval_approver_role_missing")

    expiration_dt = _parse_iso_datetime(receipt.expires_at)
    if expiration_dt is None:
        failure_reasons.append("human_approval_expiry_unparseable")
    elif expiration_dt <= evaluated_at:
        failure_reasons.append("human_approval_expired")

    approved_scope = {str(item).strip() for item in receipt.approved_scope if str(item).strip()}
    requested_scope_set = {str(item).strip() for item in requested_scope if str(item).strip()}
    if not requested_scope_set.issubset(approved_scope):
        failure_reasons.append("human_approval_scope_not_granted")

    if policy_snapshot_id is not None and policy_snapshot_id != receipt.policy_snapshot_id:
        failure_reasons.append("human_approval_policy_snapshot_mismatch")

    if action_class is not None and action_class != receipt.approved_action_class:
        failure_reasons.append("human_approval_action_class_mismatch")

    return HumanApprovalValidationResult(not failure_reasons, sorted(set(failure_reasons)))


def build_human_approval_state(
    receipt: HumanApprovalReceipt | None,
    *,
    requested_scope: list[str],
    action_class: str | None = None,
    policy_snapshot_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build runtime-compatible ``human_approval_state`` from a receipt."""
    evaluated_at = now or datetime.now(UTC)
    validation_result = validate_human_approval_receipt(
        receipt,
        requested_scope=requested_scope,
        action_class=action_class,
        policy_snapshot_id=policy_snapshot_id,
        now=evaluated_at,
    )
    if not validation_result.is_valid or receipt is None:
        return {
            "approved": False,
            "failure_reasons": validation_result.failure_reasons,
        }

    finalized_receipt = with_receipt_hash(receipt)

    return {
        "approved": True,
        "approval_receipt_id": finalized_receipt.approval_receipt_id,
        "approver_identity": finalized_receipt.approver_identity,
        "approver_role": finalized_receipt.approver_role,
        "approved_scope": sorted(str(scope) for scope in finalized_receipt.approved_scope),
        "receipt_hash": finalized_receipt.receipt_hash,
        "validated_at": evaluated_at.isoformat(),
    }


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
