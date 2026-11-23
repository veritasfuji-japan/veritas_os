"""Human review and signed approval artifacts for prepared system resumes."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.human_approval_receipt import (
    ApprovedHumanApprovalVerifier,
    HumanApprovalReceipt,
    HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy,
    verify_human_approval_receipt_artifact_to_proof,
    SIGNED_APPROVAL_ARTIFACT_TYPE,
    SIGNED_APPROVAL_ARTIFACT_VERSION,
)
from veritas_os.governance.human_approval_receipt_signing import (
    human_approval_signature_payload,
    TrustedEd25519HumanApprovalVerifier,
)
from veritas_os.security.hash import sha256_hex, sha256_of_canonical_json


class SystemResumePreparation(BaseModel):
    """Server-owned context of a pending resume request."""

    model_config = ConfigDict(frozen=True)
    request_id: str
    execution_intent_id: str
    action: Literal["system_resume"]
    deployment_id: str
    halt_id: str
    execution_principal: str
    policy_snapshot_digest: str

    @property
    def context(self) -> tuple[str, str, str]:
        """Return the authoritative state used to detect stale preparations."""
        return self.deployment_id, self.halt_id, self.policy_snapshot_digest


class ResumeReview(BaseModel):
    preparation: SystemResumePreparation
    context_hash: str


class ResumeApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve"]
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass
class PendingResume:
    preparation: SystemResumePreparation
    artifact: dict[str, Any] | None = None
    expires_at: datetime | None = None


def resume_key_id(key: Ed25519PrivateKey) -> str:
    """Identify the exact signing key used for issuance and cache validation."""
    return sha256_hex(key.public_key().public_bytes_raw())


def sign_resume_approval(
    preparation: SystemResumePreparation,
    approver: str,
    key: Ed25519PrivateKey,
    now: datetime,
) -> tuple[dict[str, Any], datetime]:
    """Issue a five-minute v1 receipt using the provisioned resume signing key."""
    context = preparation.model_dump()
    expiry = now + timedelta(minutes=5)
    receipt = HumanApprovalReceipt(
        approval_receipt_id=uuid4().hex,
        request_ref=preparation.request_id,
        decision_id=preparation.request_id,
        execution_intent_id=preparation.execution_intent_id,
        approver_identity=approver,
        approver_role="system_resume_approver",
        approved_action_class=preparation.action,
        approved_scope=[preparation.action],
        approval_basis_refs=[preparation.request_id],
        approved_at=now.isoformat(),
        expires_at=expiry.isoformat(),
        policy_snapshot_id=preparation.policy_snapshot_digest,
        authority_evidence_id=None,
        approval_result="approved",
        signature_verified=False,
        receipt_hash="",
        bind_context_hash=sha256_of_canonical_json(context),
        metadata={"system_resume": context},
    )
    artifact = {
        "artifact_type": SIGNED_APPROVAL_ARTIFACT_TYPE,
        "artifact_version": SIGNED_APPROVAL_ARTIFACT_VERSION,
        "receipt": receipt.to_dict_for_hash(),
        "receipt_hash": receipt.deterministic_digest(),
        "signer": {
            "key_id": resume_key_id(key),
            "identity": approver,
            "role": receipt.approver_role,
            "algorithm": "Ed25519",
        },
        "signed_at": now.isoformat(),
    }
    signature = key.sign(human_approval_signature_payload(artifact).encode("utf-8"))
    artifact["signature"] = base64.urlsafe_b64encode(signature).decode("ascii")
    return artifact, expiry


def verify_resume_approval(
    record: PendingResume, artifact: dict[str, Any], approver: str,
) -> HumanApprovalReceipt:
    """Verify the issued artifact against the deployment's independently pinned public key."""
    if record.artifact is None or record.artifact != artifact:
        raise ValueError("Resume approval does not match issued receipt")
    public_key = base64.b64decode(
        os.getenv("VERITAS_SYSTEM_RESUME_PUBLIC_KEY", "").strip(), altchars=b"-_", validate=True,
    )
    if len(public_key) != 32:
        raise ValueError("Resume verification key unavailable")
    kid = sha256_hex(public_key)
    role = "system_resume_approver"
    verifier = TrustedEd25519HumanApprovalVerifier(
        {kid: public_key}, {kid: approver}, {kid: role}, "system-resume-ed25519",
    )
    pending = record.preparation
    receipt = verify_human_approval_receipt_artifact_to_proof(
        artifact, verifier.verify, requested_scope=[pending.action], action_class=pending.action,
        policy_snapshot_id=pending.policy_snapshot_digest,
        signer_policy=HumanApprovalSignerPolicy(
            "system-resume", [kid], ["Ed25519"], [role], [approver], [pending.action],
        ),
        verifier_policy=HumanApprovalVerifierPolicy([
            ApprovedHumanApprovalVerifier(verifier.verifier_id, "production", kid,
                                          verifier.verifier_policy_id, verifier.policy_hash()),
        ]),
        require_production_verifier=True, require_structured_signature_result=True,
    ).receipt
    if (receipt.approver_identity != approver or receipt.request_ref != pending.request_id
            or receipt.execution_intent_id != pending.execution_intent_id
            or receipt.bind_context_hash != sha256_of_canonical_json(pending.model_dump())):
        raise ValueError("Resume approval context mismatch")
    return receipt
