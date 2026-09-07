"""Issue signed Human Approval only after a verified Real Bind source gate."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
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
    expected_source: Any = None,
) -> dict[str, Any]:
    """Construct and sign approval derived only from an exact verified gate.

    Security-relevant lineage, approval identity, authority identity, action,
    scope, policy snapshot, and Bind context are all gate-derived. The signer
    supplies trusted signer provenance; no private-key storage is prescribed.

    Args:
        source_gate_review_packet: Exact source gate to verify and approve.
        action_contract: Independently trusted policy, also the v0.3 gate anchor.
        expected_source: Independent Authority Evidence Linkage source required
            for v0.3. Never obtain this from the candidate gate's snapshot.
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
            source_gate_review_packet,
            expected_source=expected_source,
            expected_contract=action_contract,
        )
        bind_context_hash = derive_verified_real_bind_context_hash(
            source, expected_source=expected_source, expected_contract=action_contract
        )
    except (TypeError, ValueError) as exc:
        raise GateBoundHumanApprovalIssuanceError("GBHA_SOURCE_GATE_INVALID") from exc

    return _issue_verified_approval(
        source,
        bind_context_hash,
        action_contract=action_contract,
        event=event,
        signer=signer,
    )


def _issue_verified_approval(
    source: Any,
    bind_context_hash: str,
    *,
    action_contract: ActionClassContract,
    event: HumanApprovalEvent,
    signer: HumanApprovalArtifactSigner,
) -> dict[str, Any]:
    """Reuse receipt construction only after a public entry verifies its source."""
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
    approval_scope = _required_text(human_ref, "approval_scope", "GBHA_HUMAN_REFERENCE")
    if approval_scope not in scope:
        raise GateBoundHumanApprovalIssuanceError("GBHA_APPROVAL_SCOPE_MISMATCH")

    approver_identity = _required_text(human_ref, "approver_id", "GBHA_HUMAN_REFERENCE")
    approver_role = _required_text(human_ref, "approver_role", "GBHA_HUMAN_REFERENCE")
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


def issue_promotion_gate_bound_human_approval_artifact(
    replay_review: Any,
    runtime_risk_review: Any,
    source_final_credential_scope_recheck_packet: Any,
    *,
    action_contract: ActionClassContract,
    event: HumanApprovalEvent,
    signer: HumanApprovalArtifactSigner,
    now: datetime,
) -> dict[str, Any]:
    """Sign exact promotion approval after fresh, independently verified reviews.

    A trusted caller must supply an actual human decision, deployment-controlled
    signer, contract, and current clock. This function does not manufacture a
    human decision or establish signer trust. The existing receipt verifier
    remains a separate mandatory boundary; issuing a signature does not grant
    execution authority or consume authorization.

    Raises:
        GateBoundHumanApprovalIssuanceError: Invalid source, event, timing, or
            attempted override of reserved signed promotion lineage.
    """
    from veritas_os.policy.live_adapter_bind_authorization_requirements import (
        verify_promotion_idempotency_replay_review,
    )
    from veritas_os.policy.canonical_promotion_real_bind_authorization_contract import (
        project_verified_promotion_authorization_source,
    )

    try:
        review = verify_promotion_idempotency_replay_review(
            replay_review,
            runtime_risk_review,
            source_final_credential_scope_recheck_packet,
            now=now,
        )
        source = project_verified_promotion_authorization_source(
            source_final_credential_scope_recheck_packet
        )
    except (TypeError, ValueError) as exc:
        raise GateBoundHumanApprovalIssuanceError(
            "GBHA_PROMOTION_SOURCE_INVALID"
        ) from exc
    if not isinstance(event, HumanApprovalEvent):
        raise GateBoundHumanApprovalIssuanceError("GBHA_PROMOTION_EVENT_INVALID")
    try:
        approved, signed, expires = (
            datetime.fromisoformat(value)
            for value in (event.approved_at, event.signed_at, event.expires_at)
        )
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (approved, signed, expires)
        ):
            raise ValueError("naive event time")
        if not (
            datetime.fromisoformat(review.reviewed_at)
            <= approved
            <= signed
            <= now
            < expires
            <= datetime.fromisoformat(review.valid_until)
        ):
            raise ValueError("approval outside verified review window")
    except (TypeError, ValueError) as exc:
        raise GateBoundHumanApprovalIssuanceError(
            "GBHA_PROMOTION_EVENT_TIME_INVALID"
        ) from exc
    if event.approval_result not in ("approved", "denied", "expired", "indeterminate"):
        raise GateBoundHumanApprovalIssuanceError("GBHA_PROMOTION_RESULT_INVALID")
    if event.metadata is not None and not isinstance(event.metadata, dict):
        raise GateBoundHumanApprovalIssuanceError("GBHA_PROMOTION_METADATA_INVALID")
    metadata = dict(event.metadata or {})
    if "promotion_approval_binding" in metadata:
        raise GateBoundHumanApprovalIssuanceError("GBHA_PROMOTION_BINDING_OVERRIDE")
    metadata["promotion_approval_binding"] = {
        "version": "promotion-human-approval-binding/v1",
        "idempotency_replay_review_hash": review.review_hash,
        "runtime_risk_review_hash": review.source_runtime_risk_review_hash,
        "source_projection_digest": review.source_projection_digest,
        "final_credential_scope_recheck_hash": source.source_final_credential_scope_recheck_hash,
        "final_endpoint_identity_binding_digest": source.final_endpoint_identity_binding_digest,
        "final_credential_scope_binding_digest": source.final_credential_scope_binding_digest,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_hash": source.adapter_contract_hash,
        "bind_context_hash": source.bind_context_hash,
        "human_approval_receipt_verification_required": True,
        "execution_authorized": False,
    }
    bound_event = replace(
        event,
        metadata=metadata,
        approved_at=approved.astimezone(timezone.utc).isoformat(),
        signed_at=signed.astimezone(timezone.utc).isoformat(),
        expires_at=expires.astimezone(timezone.utc).isoformat(),
    )
    return _issue_verified_approval(
        source,
        source.bind_context_hash,
        action_contract=action_contract,
        event=bound_event,
        signer=signer,
    )


__all__ = [
    "GateBoundHumanApprovalIssuanceError",
    "HumanApprovalArtifactSigner",
    "HumanApprovalEvent",
    "issue_gate_bound_human_approval_artifact",
    "issue_promotion_gate_bound_human_approval_artifact",
]
