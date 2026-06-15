"""Local/offline deterministic Human Approval Receipt artifact helpers.

This module intentionally stays local/offline and deterministic for v1.
No live identity-provider, signature service, or network integrations are included.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4
from typing import Any, Callable, Literal

from veritas_os.security.hash import sha256_of_canonical_json

HUMAN_APPROVAL_STATE_SOURCE = "validated_human_approval_receipt"

ApprovalResult = Literal["approved", "denied", "expired", "indeterminate"]
SIGNED_APPROVAL_ARTIFACT_TYPE = "human_approval_receipt"
SIGNED_APPROVAL_ARTIFACT_VERSION = "v1"
VERIFICATION_SOURCE_SIGNED_ARTIFACT = "signed_human_approval_artifact"
VERIFICATION_PROOF_HASH_FIELDS = (
    "receipt_hash",
    "artifact_type",
    "artifact_version",
    "signer_key_id",
    "signer_algorithm",
    "signed_at",
    "verified_at",
    "verification_source",
)
VERIFIER_DERIVED_PROVENANCE_KEYS = frozenset(
    {
        "verification_source",
        "artifact_type",
        "artifact_version",
        "signer_key_id",
        "signer_algorithm",
        "signed_at",
        "verified_at",
        "receipt_hash_verified",
        "signature_verified_by_runtime",
    }
)
_VERIFIED_RECEIPT_REGISTRY: dict[int, str] = {}


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


@dataclass(frozen=True)
class VerifiedHumanApprovalReceipt:
    """Sealed runtime proof for a verified Human Approval Receipt artifact.

    Instances are emitted only by
    ``verify_human_approval_receipt_artifact_to_proof`` after receipt hash,
    signature, scope, action-class, policy-snapshot, and expiry checks pass.
    The ``verification_proof_hash`` seals verifier-derived provenance so runtime
    code can detect tampering when the proof crosses process boundaries.
    """

    receipt: HumanApprovalReceipt
    artifact_type: str
    artifact_version: str
    receipt_hash: str
    signer_key_id: str | None
    signer_algorithm: str | None
    signed_at: str | None
    verified_at: str
    verification_source: Literal["signed_human_approval_artifact"]
    verification_proof_hash: str

    def proof_hash_payload(self) -> dict[str, Any]:
        """Return canonical verifier-derived proof fields for hashing."""
        return {
            "receipt_hash": self.receipt_hash,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "signer_key_id": self.signer_key_id,
            "signer_algorithm": self.signer_algorithm,
            "signed_at": self.signed_at,
            "verified_at": self.verified_at,
            "verification_source": self.verification_source,
        }


def _verification_proof_hash(payload: dict[str, Any]) -> str:
    """Compute the canonical proof hash for verifier-derived fields."""
    proof_payload = {field: payload.get(field) for field in VERIFICATION_PROOF_HASH_FIELDS}
    return sha256_of_canonical_json(proof_payload)


def with_receipt_hash(receipt: HumanApprovalReceipt) -> HumanApprovalReceipt:
    """Return a new receipt finalized with a deterministic ``receipt_hash``."""
    digest = receipt.deterministic_digest()
    data = receipt.to_dict()
    data["receipt_hash"] = digest
    return HumanApprovalReceipt(**data)


def _receipt_from_signed_payload(payload: dict[str, Any]) -> HumanApprovalReceipt:
    """Build a receipt from signed artifact payload without trusting signature state."""
    receipt_payload = dict(payload)
    receipt_payload.pop("receipt_hash", None)
    receipt_payload["signature_verified"] = False
    receipt_payload["receipt_hash"] = ""
    receipt_payload["metadata"] = _without_verifier_derived_provenance(
        receipt_payload.get("metadata")
    )
    return HumanApprovalReceipt(**receipt_payload)


def _without_verifier_derived_provenance(value: Any) -> dict[str, Any]:
    """Return caller metadata with verifier-controlled provenance stripped."""
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if str(key) not in VERIFIER_DERIVED_PROVENANCE_KEYS
    }


def _artifact_signer_metadata(artifact: dict[str, Any]) -> tuple[str | None, str | None]:
    signer = artifact.get("signer")
    if not isinstance(signer, dict):
        return None, None
    key_id = signer.get("key_id")
    algorithm = signer.get("algorithm")
    return (
        None if key_id is None else str(key_id),
        None if algorithm is None else str(algorithm),
    )


def has_verified_human_approval_artifact_provenance(
    receipt: HumanApprovalReceipt,
) -> bool:
    """Return whether a receipt has in-process verifier-derived provenance.

    The public metadata fields are inspectable and serializable, but they are
    not cryptographically sealed. This in-process registry prevents a naked
    caller-constructed dataclass with forged metadata from being accepted in
    the current runtime process. A serialized copy still requires future sealed
    receipt/proof-object work before it can be distinguished cryptographically.
    """
    metadata = receipt.metadata
    runtime_token = metadata.get("_runtime_verification_token")
    return (
        isinstance(runtime_token, str)
        and _VERIFIED_RECEIPT_REGISTRY.get(id(receipt)) == runtime_token
        and receipt.signature_verified is True
        and metadata.get("verification_source") == VERIFICATION_SOURCE_SIGNED_ARTIFACT
        and metadata.get("artifact_type") == SIGNED_APPROVAL_ARTIFACT_TYPE
        and metadata.get("artifact_version") == SIGNED_APPROVAL_ARTIFACT_VERSION
        and metadata.get("signature_verified_by_runtime") is True
        and metadata.get("receipt_hash_verified") is True
    )


def verify_human_approval_receipt_artifact_to_proof(
    artifact: dict[str, Any],
    verify_signature_fn: Callable[[dict[str, Any]], bool] | None,
    *,
    requested_scope: list[str],
    action_class: str | None,
    policy_snapshot_id: str | None,
    now: datetime | None = None,
) -> VerifiedHumanApprovalReceipt:
    """Verify a signed artifact and return a sealed approval proof.

    The caller-supplied ``signature_verified`` value in raw artifact data is
    never trusted. This helper recomputes the canonical receipt hash, requires
    an explicit signature verifier, rejects bad signatures, validates receipt
    scope/action/policy/expiry, and only then emits a
    ``VerifiedHumanApprovalReceipt`` with a canonical proof hash.
    """
    if not isinstance(artifact, dict):
        raise ValueError("human_approval_artifact_invalid")
    if artifact.get("artifact_type") != SIGNED_APPROVAL_ARTIFACT_TYPE:
        raise ValueError("human_approval_artifact_type_invalid")
    if artifact.get("artifact_version") != SIGNED_APPROVAL_ARTIFACT_VERSION:
        raise ValueError("human_approval_artifact_version_invalid")
    if verify_signature_fn is None:
        raise ValueError("human_approval_signature_verifier_required")

    receipt_payload = artifact.get("receipt")
    if not isinstance(receipt_payload, dict):
        raise ValueError("human_approval_receipt_missing")

    unsigned_receipt = _receipt_from_signed_payload(receipt_payload)
    expected_hash = unsigned_receipt.deterministic_digest()
    if artifact.get("receipt_hash") != expected_hash:
        raise ValueError("human_approval_receipt_hash_mismatch")

    if verify_signature_fn(artifact) is not True:
        raise ValueError("human_approval_signature_verification_failed")

    signer_key_id, signer_algorithm = _artifact_signer_metadata(artifact)
    verified_at = (now or datetime.now(UTC)).isoformat()
    runtime_token = uuid4().hex
    verified_payload = unsigned_receipt.to_dict()
    verified_payload["signature_verified"] = True
    verified_payload["receipt_hash"] = expected_hash
    verified_metadata = dict(verified_payload.get("metadata") or {})
    verified_metadata.update(
        {
            "verification_source": VERIFICATION_SOURCE_SIGNED_ARTIFACT,
            "artifact_type": SIGNED_APPROVAL_ARTIFACT_TYPE,
            "artifact_version": SIGNED_APPROVAL_ARTIFACT_VERSION,
            "signer_key_id": signer_key_id,
            "signer_algorithm": signer_algorithm,
            "signed_at": artifact.get("signed_at"),
            "verified_at": verified_at,
            "receipt_hash_verified": True,
            "signature_verified_by_runtime": True,
            "_runtime_verification_token": runtime_token,
        }
    )
    verified_payload["metadata"] = verified_metadata
    verified_receipt = HumanApprovalReceipt(**verified_payload)
    _VERIFIED_RECEIPT_REGISTRY[id(verified_receipt)] = runtime_token
    validation_result = validate_human_approval_receipt(
        verified_receipt,
        requested_scope=requested_scope,
        action_class=action_class,
        policy_snapshot_id=policy_snapshot_id,
        now=now,
    )
    if not validation_result.is_valid:
        raise ValueError(validation_result.failure_reasons[0])

    proof_payload = {
        "receipt": verified_receipt,
        "artifact_type": SIGNED_APPROVAL_ARTIFACT_TYPE,
        "artifact_version": SIGNED_APPROVAL_ARTIFACT_VERSION,
        "receipt_hash": expected_hash,
        "signer_key_id": signer_key_id,
        "signer_algorithm": signer_algorithm,
        "signed_at": artifact.get("signed_at"),
        "verified_at": verified_at,
        "verification_source": VERIFICATION_SOURCE_SIGNED_ARTIFACT,
    }
    proof_payload["verification_proof_hash"] = _verification_proof_hash(proof_payload)
    return VerifiedHumanApprovalReceipt(**proof_payload)


def verify_human_approval_receipt_artifact(
    artifact: dict[str, Any],
    verify_signature_fn: Callable[[dict[str, Any]], bool] | None,
    *,
    requested_scope: list[str],
    action_class: str | None,
    policy_snapshot_id: str | None,
    now: datetime | None = None,
) -> HumanApprovalReceipt:
    """Verify a signed artifact and return its validated receipt.

    Compatibility wrapper for callers that still consume
    ``HumanApprovalReceipt``. Secure/prod runtime validation should prefer
    ``verify_human_approval_receipt_artifact_to_proof`` and pass the resulting
    ``VerifiedHumanApprovalReceipt``.
    """
    return verify_human_approval_receipt_artifact_to_proof(
        artifact,
        verify_signature_fn,
        requested_scope=requested_scope,
        action_class=action_class,
        policy_snapshot_id=policy_snapshot_id,
        now=now,
    ).receipt


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

    state = {
        "approved": True,
        "approval_state_source": HUMAN_APPROVAL_STATE_SOURCE,
        "approval_receipt_id": finalized_receipt.approval_receipt_id,
        "approver_identity": finalized_receipt.approver_identity,
        "approver_role": finalized_receipt.approver_role,
        "approved_scope": sorted(str(scope) for scope in finalized_receipt.approved_scope),
        "approved_action_class": finalized_receipt.approved_action_class,
        "policy_snapshot_id": finalized_receipt.policy_snapshot_id,
        "receipt_hash": finalized_receipt.receipt_hash,
        "validated_at": evaluated_at.isoformat(),
    }
    state["approval_validation_hash"] = human_approval_state_validation_hash(state)
    return state


def human_approval_state_validation_hash(state: dict[str, Any]) -> str:
    """Hash receipt-derived approval validation metadata for tamper detection."""
    payload = {
        "approval_receipt_id": state.get("approval_receipt_id"),
        "receipt_hash": state.get("receipt_hash"),
        "approved_scope": sorted(str(scope) for scope in state.get("approved_scope", [])),
        "policy_snapshot_id": state.get("policy_snapshot_id"),
        "approved_action_class": state.get("approved_action_class"),
        "validated_at": state.get("validated_at"),
    }
    return sha256_of_canonical_json(payload)


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
