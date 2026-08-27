"""Issue signed Human Approval only after a verified Real Bind source gate."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.human_approval_receipt import (
    SIGNED_APPROVAL_ARTIFACT_TYPE,
    SIGNED_APPROVAL_ARTIFACT_VERSION,
    ApprovalResult,
    HumanApprovalReceipt,
    with_receipt_hash,
)
from veritas_os.governance.human_approval_receipt_signing import (
    human_approval_signature_payload,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.policy.real_bind_context import (
    derive_verified_real_bind_context_hash,
)


class GateBoundHumanApprovalIssuanceError(ValueError):
    """Raised when a verified gate cannot safely produce an approval artifact."""


class HumanApprovalArtifactSigner(Protocol):
    """Signer-controlled metadata and backend-agnostic signing boundary."""

    @property
    def key_id(self) -> str:
        """Return the deployment-controlled signing key identifier."""
        ...

    @property
    def identity(self) -> str:
        """Return the deployment-controlled approver identity."""
        ...

    @property
    def role(self) -> str:
        """Return the deployment-controlled approver role."""
        ...

    @property
    def algorithm(self) -> str:
        """Return the signature algorithm identifier."""
        ...

    def sign(self, payload: bytes) -> bytes:
        """Sign the final canonical artifact-envelope payload."""
        ...


@dataclass(frozen=True)
class HumanApprovalEvent:
    """Legitimate event data supplied after the source gate exists."""

    approval_result: ApprovalResult
    approval_basis_refs: list[str]
    approved_at: str
    expires_at: str
    signed_at: str
    metadata: dict[str, Any] | None = None


def _one_reference(bundle: Any, field: str, code: str) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise GateBoundHumanApprovalIssuanceError(f"{code}_BUNDLE_INVALID")
    references = bundle.get(field)
    if not isinstance(references, list) or len(references) != 1:
        raise GateBoundHumanApprovalIssuanceError(f"{code}_CARDINALITY_UNSUPPORTED")
    reference = references[0]
    if not isinstance(reference, dict):
        raise GateBoundHumanApprovalIssuanceError(f"{code}_INVALID")
    return reference


def _required_text(mapping: dict[str, Any], field: str, code: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GateBoundHumanApprovalIssuanceError(f"{code}_{field.upper()}_INVALID")
    return value.strip()


def issue_gate_bound_human_approval_artifact(
    source_gate_review_packet: Any,
    *,
    action_contract: ActionClassContract,
    event: HumanApprovalEvent,
    signer: HumanApprovalArtifactSigner,
) -> dict[str, Any]:
    """Construct and sign approval derived only from an exact verified gate.

    Security-relevant lineage, approval identity, authority identity, action,
    scope, policy snapshot, and Bind context are all gate-derived. The signer
    supplies trusted signer provenance; no private-key storage is prescribed.

    Args:
        source_gate_review_packet: Exact source gate to verify and approve.
        action_contract: Contract used only to resolve gate action semantics.
        event: Approval decision, timing, basis, and non-security metadata.
        signer: Deployment-controlled signing backend and signer provenance.

    Returns:
        An existing v1 signed Human Approval artifact envelope.

    Raises:
        GateBoundHumanApprovalIssuanceError: If any binding is ambiguous or
            inconsistent with the verified gate or signer.
    """
    try:
        source = verify_live_adapter_dry_run_bind_authorization_gate_review_packet(
            source_gate_review_packet
        )
        bind_context_hash = derive_verified_real_bind_context_hash(source)
    except (TypeError, ValueError) as exc:
        raise GateBoundHumanApprovalIssuanceError(
            "GBHA_SOURCE_GATE_INVALID"
        ) from exc

    intent = source.execution_intent
    if not isinstance(intent, dict):
        raise GateBoundHumanApprovalIssuanceError("GBHA_INTENT_INVALID")
    intended_action = _required_text(intent, "intended_action", "GBHA_INTENT")
    if not isinstance(action_contract, ActionClassContract):
        raise GateBoundHumanApprovalIssuanceError("GBHA_ACTION_CONTRACT_INVALID")
    if action_contract.id != intended_action:
        raise GateBoundHumanApprovalIssuanceError("GBHA_ACTION_CONTRACT_MISMATCH")

    authority_bundle = source.authority_evidence_reference_bundle
    human_bundle = source.human_approval_reference_bundle
    authority_ref = _one_reference(
        authority_bundle,
        "authority_evidence_references",
        "GBHA_AUTHORITY_REFERENCE",
    )
    human_ref = _one_reference(
        human_bundle,
        "human_approval_references",
        "GBHA_HUMAN_REFERENCE",
    )
    scope = authority_bundle.get("bundle_scope")
    if (
        not isinstance(scope, list)
        or not scope
        or any(not isinstance(item, str) or not item.strip() for item in scope)
        or len(set(scope)) != len(scope)
        or any(item not in action_contract.allowed_scope for item in scope)
    ):
        raise GateBoundHumanApprovalIssuanceError("GBHA_APPROVAL_SCOPE_INVALID")
    approval_scope = _required_text(
        human_ref, "approval_scope", "GBHA_HUMAN_REFERENCE"
    )
    if approval_scope not in scope:
        raise GateBoundHumanApprovalIssuanceError("GBHA_APPROVAL_SCOPE_MISMATCH")

    approver_identity = _required_text(
        human_ref, "approver_id", "GBHA_HUMAN_REFERENCE"
    )
    approver_role = _required_text(
        human_ref, "approver_role", "GBHA_HUMAN_REFERENCE"
    )
    signer_fields = (signer.key_id, signer.identity, signer.role, signer.algorithm)
    if any(not isinstance(item, str) or not item.strip() for item in signer_fields):
        raise GateBoundHumanApprovalIssuanceError("GBHA_SIGNER_METADATA_INVALID")
    if signer.identity != approver_identity:
        raise GateBoundHumanApprovalIssuanceError("GBHA_SIGNER_IDENTITY_MISMATCH")
    if signer.role != approver_role:
        raise GateBoundHumanApprovalIssuanceError("GBHA_SIGNER_ROLE_MISMATCH")

    basis_refs = event.approval_basis_refs
    if (
        not isinstance(basis_refs, list)
        or not basis_refs
        or any(not isinstance(item, str) or not item.strip() for item in basis_refs)
    ):
        raise GateBoundHumanApprovalIssuanceError("GBHA_APPROVAL_BASIS_INVALID")
    receipt = with_receipt_hash(
        HumanApprovalReceipt(
            approval_receipt_id=_required_text(
                human_ref,
                "human_approval_reference_id",
                "GBHA_HUMAN_REFERENCE",
            ),
            decision_id=_required_text(intent, "decision_id", "GBHA_INTENT"),
            execution_intent_id=source.execution_intent_id,
            approver_identity=approver_identity,
            approver_role=approver_role,
            approved_action_class=action_contract.action_class,
            approved_scope=list(scope),
            approval_basis_refs=list(basis_refs),
            approved_at=event.approved_at,
            expires_at=event.expires_at,
            policy_snapshot_id=_required_text(
                intent, "policy_snapshot_id", "GBHA_INTENT"
            ),
            authority_evidence_id=_required_text(
                authority_ref,
                "authority_evidence_reference_id",
                "GBHA_AUTHORITY_REFERENCE",
            ),
            approval_result=event.approval_result,
            signature_verified=False,
            receipt_hash="",
            request_ref=_required_text(intent, "request_id", "GBHA_INTENT"),
            bind_context_hash=bind_context_hash,
            metadata=dict(event.metadata or {}),
        )
    )
    artifact: dict[str, Any] = {
        "artifact_type": SIGNED_APPROVAL_ARTIFACT_TYPE,
        "artifact_version": SIGNED_APPROVAL_ARTIFACT_VERSION,
        "receipt": receipt.to_dict(),
        "receipt_hash": receipt.receipt_hash,
        "signer": {
            "key_id": signer.key_id,
            "identity": signer.identity,
            "role": signer.role,
            "algorithm": signer.algorithm,
        },
        "signed_at": event.signed_at,
    }
    payload = human_approval_signature_payload(artifact).encode("utf-8")
    signature = signer.sign(payload)
    if not isinstance(signature, bytes) or not signature:
        raise GateBoundHumanApprovalIssuanceError("GBHA_SIGNATURE_INVALID")
    artifact["signature"] = base64.urlsafe_b64encode(signature).decode("ascii")
    return artifact


__all__ = [
    "GateBoundHumanApprovalIssuanceError",
    "HumanApprovalArtifactSigner",
    "HumanApprovalEvent",
    "issue_gate_bound_human_approval_artifact",
]
