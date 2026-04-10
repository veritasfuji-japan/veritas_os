"""Governance identity model for tracking policy/governance artifact provenance.

This module provides a lightweight data model that captures which governance
artifact was in force when a decision was made.  It is threaded into every
``DecideResponse`` so that audit, replay, and compliance surfaces can show
provenance without needing to correlate external logs.

Posture-aware enforcement
-------------------------
In **secure** / **prod** posture the governance artifact *must* carry a valid
Ed25519 signature.  Unsigned or invalidly signed artifacts cause the decision
pipeline to reject the request (fail-closed).

In **dev** / **staging** posture unsigned artifacts are accepted with a
warning so that local development workflows remain frictionless.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GovernanceIdentity:
    """Immutable identity of the governance artifact in force for a decision.

    Attributes:
        policy_version: Governance policy version string (e.g. ``governance_v1``).
        digest: SHA-256 hex digest of the canonical governance policy JSON.
        signature_verified: Whether an Ed25519 signature was successfully verified.
        signer_id: Identity of the signer (key fingerprint or label), if known.
        verified_at: ISO-8601 timestamp when verification was performed.
    """

    policy_version: str = ""
    digest: str = ""
    signature_verified: bool = False
    signer_id: str = ""
    verified_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict suitable for JSON embedding in decision artifacts."""
        return {
            "policy_version": self.policy_version,
            "digest": self.digest,
            "signature_verified": self.signature_verified,
            "signer_id": self.signer_id,
            "verified_at": self.verified_at,
        }


@dataclass(frozen=True)
class GovernanceChangeRecord:
    """Extended governance change record with provenance tracking.

    Captures proposer, approver(s), digest transitions, and timestamps for
    audit-grade governance history.

    Attributes:
        changed_at: ISO-8601 timestamp of the change.
        proposer: Identity of the person/system proposing the change.
        approvers: List of approver identities (from 4-eyes approval).
        previous_digest: SHA-256 hex digest of the governance policy before change.
        new_digest: SHA-256 hex digest of the governance policy after change.
        previous_version: Version string before change.
        new_version: Version string after change.
        event_type: Type of governance event (``update``, ``rollback``, etc.).
        signature_status: Whether the new artifact was signed.
    """

    changed_at: str = ""
    proposer: str = ""
    approvers: List[str] = field(default_factory=list)
    previous_digest: str = ""
    new_digest: str = ""
    previous_version: str = ""
    new_version: str = ""
    event_type: str = "update"
    signature_status: str = "unsigned"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict suitable for JSONL audit trail."""
        return {
            "changed_at": self.changed_at,
            "proposer": self.proposer,
            "approvers": list(self.approvers),
            "previous_digest": self.previous_digest,
            "new_digest": self.new_digest,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "event_type": self.event_type,
            "signature_status": self.signature_status,
        }


def compute_governance_digest(policy_data: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hex digest of a governance policy dict.

    The dict is serialized with sorted keys and no whitespace to ensure
    deterministic hashing across process restarts.

    Args:
        policy_data: Governance policy as a plain dict.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    canonical = json.dumps(policy_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_governance_identity(
    policy_data: Dict[str, Any],
    *,
    signature_verified: bool = False,
    signer_id: str = "",
) -> GovernanceIdentity:
    """Build a ``GovernanceIdentity`` from a governance policy dict.

    Args:
        policy_data: Current governance policy dict.
        signature_verified: Whether the policy has a valid signature.
        signer_id: Identity label of the signer, if known.

    Returns:
        Populated ``GovernanceIdentity`` instance.
    """
    return GovernanceIdentity(
        policy_version=str(policy_data.get("version", "")),
        digest=compute_governance_digest(policy_data),
        signature_verified=signature_verified,
        signer_id=signer_id,
        verified_at=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )


def require_signed_governance(
    policy_data: Dict[str, Any],
    *,
    posture_is_strict: bool,
    signature_verified: bool,
) -> None:
    """Enforce signed governance artifacts in strict posture.

    In **secure** / **prod** posture, raises ``ValueError`` if the governance
    artifact is not signed.  In **dev** / **staging** posture, logs a warning
    but does not block.

    Args:
        policy_data: Current governance policy dict (for logging context).
        posture_is_strict: Whether the active posture is secure or prod.
        signature_verified: Whether a valid signature was verified.

    Raises:
        ValueError: If posture is strict and governance is unsigned.
    """
    if signature_verified:
        return

    version = policy_data.get("version", "unknown")
    if posture_is_strict:
        raise ValueError(
            f"governance artifact (version={version}) is unsigned or has an "
            "invalid signature; rejected in secure/prod posture. "
            "Sign the governance policy or switch to dev/staging posture."
        )

    logger.warning(
        "governance artifact (version=%s) is unsigned; "
        "accepted in non-strict posture but would be rejected in secure/prod.",
        version,
    )
