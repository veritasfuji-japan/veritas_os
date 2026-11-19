"""Human review and signed approval artifacts for prepared system resumes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    SIGNED_APPROVAL_ARTIFACT_TYPE,
    SIGNED_APPROVAL_ARTIFACT_VERSION,
)
from veritas_os.governance.human_approval_receipt_signing import (
    human_approval_signature_payload,
)
from veritas_os.security.hash import sha256_hex, sha256_of_canonical_json
from veritas_os.security.signing import load_ed25519_private_key


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


def sign_resume_approval(
    preparation: SystemResumePreparation,
    approver: str,
    key_path: Path,
    now: datetime,
) -> tuple[dict[str, Any], datetime]:
    """Issue a five-minute v1 receipt using the provisioned resume signing key."""
    key = load_ed25519_private_key(key_path)
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
            "key_id": sha256_hex(key.public_key().public_bytes_raw()),
            "identity": approver,
            "role": receipt.approver_role,
            "algorithm": "Ed25519",
        },
        "signed_at": now.isoformat(),
    }
    signature = key.sign(human_approval_signature_payload(artifact).encode("utf-8"))
    artifact["signature"] = base64.urlsafe_b64encode(signature).decode("ascii")
    return artifact, expiry
