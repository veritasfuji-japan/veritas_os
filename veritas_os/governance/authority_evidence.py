"""AuthorityEvidence artifact model and validation helpers.

AuthorityEvidence is distinct from TrustLog/audit records. A TrustLog entry records
what happened, while AuthorityEvidence captures bind-time proof that an action was
authorized, admissible, in-scope, fresh, and valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


class VerificationResult(str, Enum):
    """Verification outcome for authority evidence adjudication."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    MISSING = "missing"
    STALE = "stale"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class AuthorityEvidence:
    """First-class bind-time authority artifact.

    The artifact is deterministic and hashable via canonical JSON serialization.
    """

    authority_evidence_id: str
    action_contract_id: str
    action_contract_version: str
    actor_identity: str
    actor_role: str
    authority_source_refs: list[str]
    role_or_policy_basis: list[str]
    scope_grants: list[str]
    scope_limitations: list[str]
    validity_window: dict[str, str]
    issued_at: str
    valid_from: str
    valid_until: str
    revalidated_at: str | None = None
    policy_snapshot_id: str | None = None
    evidence_hash: str = ""
    verification_result: VerificationResult = VerificationResult.INDETERMINATE
    failure_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable authority evidence fields."""
        return {
            "authority_evidence_id": self.authority_evidence_id,
            "action_contract_id": self.action_contract_id,
            "action_contract_version": self.action_contract_version,
            "actor_identity": self.actor_identity,
            "actor_role": self.actor_role,
            "authority_source_refs": list(self.authority_source_refs),
            "role_or_policy_basis": list(self.role_or_policy_basis),
            "scope_grants": list(self.scope_grants),
            "scope_limitations": list(self.scope_limitations),
            "validity_window": dict(self.validity_window),
            "issued_at": self.issued_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "revalidated_at": self.revalidated_at,
            "policy_snapshot_id": self.policy_snapshot_id,
            "evidence_hash": self.evidence_hash,
            "verification_result": self.verification_result.value,
            "failure_reasons": list(self.failure_reasons),
            "metadata": dict(self.metadata),
        }

    def deterministic_serialization(self) -> str:
        """Serialize artifact with stable ordering using canonical JSON."""
        return canonical_json_dumps(self.to_dict_for_hash())

    def deterministic_digest(self) -> str:
        """Compute deterministic SHA-256 digest with stable field ordering."""
        return sha256_of_canonical_json(self.to_dict_for_hash())

    def to_dict_for_hash(self) -> dict[str, Any]:
        """Return canonical hash payload excluding self-referential evidence_hash."""
        payload = self.to_dict()
        payload["evidence_hash"] = ""
        return payload


@dataclass(frozen=True)
class AuthorityEvidenceValidationResult:
    """Validation result for authority evidence admissibility checks."""

    is_valid: bool
    failure_reasons: list[str] = field(default_factory=list)


def is_present(authority_evidence: AuthorityEvidence | None) -> bool:
    """Return True when AuthorityEvidence artifact exists."""
    return authority_evidence is not None


def is_expired(authority_evidence: AuthorityEvidence, *, now: datetime | None = None) -> bool:
    """Return True when validity window has elapsed."""
    now_dt = now or datetime.now()
    valid_until_dt = datetime.fromisoformat(authority_evidence.valid_until)
    return now_dt > valid_until_dt


def is_indeterminate(authority_evidence: AuthorityEvidence) -> bool:
    """Return True when verification result is indeterminate."""
    return authority_evidence.verification_result == VerificationResult.INDETERMINATE


def is_scope_granting(authority_evidence: AuthorityEvidence, scope: str) -> bool:
    """Return True when scope is granted and not explicitly limited."""
    return (
        scope in authority_evidence.scope_grants
        and scope not in authority_evidence.scope_limitations
    )


def is_valid(
    authority_evidence: AuthorityEvidence | None,
    *,
    policy_snapshot_required: bool = False,
    now: datetime | None = None,
) -> bool:
    """Return validation pass/fail for authority evidence artifact."""
    return validate_authority_evidence(
        authority_evidence,
        policy_snapshot_required=policy_snapshot_required,
        now=now,
    ).is_valid


def validate_authority_evidence(
    authority_evidence: AuthorityEvidence | None,
    *,
    policy_snapshot_required: bool = False,
    now: datetime | None = None,
) -> AuthorityEvidenceValidationResult:
    """Validate AuthorityEvidence according to fail-closed governance rules."""
    failures: list[str] = []

    if authority_evidence is None:
        return AuthorityEvidenceValidationResult(
            is_valid=False,
            failure_reasons=["authority_evidence_missing"],
        )

    if not authority_evidence.actor_identity.strip():
        failures.append("actor_identity_missing")

    if not authority_evidence.authority_source_refs:
        failures.append("authority_source_refs_missing")

    if policy_snapshot_required and not (authority_evidence.policy_snapshot_id or "").strip():
        failures.append("policy_snapshot_id_missing")

    if authority_evidence.verification_result in {
        VerificationResult.MISSING,
        VerificationResult.INDETERMINATE,
        VerificationResult.EXPIRED,
        VerificationResult.INVALID,
    }:
        failures.append(
            f"verification_result_{authority_evidence.verification_result.value}"
        )

    try:
        if is_expired(authority_evidence, now=now):
            failures.append("authority_expired")
    except ValueError:
        failures.append("validity_window_unparseable")

    return AuthorityEvidenceValidationResult(
        is_valid=len(failures) == 0,
        failure_reasons=failures,
    )
