"""Deterministic local/offline authority evidence ingestion adapter.

This module normalizes external/mock authority payloads into the internal
AuthorityEvidence artifact for bind-time admissibility checks.
"""

from __future__ import annotations

from typing import Any

from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult

_REQUIRED_STRING_FIELDS = (
    "authority_evidence_id",
    "action_contract_id",
    "action_contract_version",
    "actor_identity",
    "actor_role",
    "issued_at",
    "valid_from",
    "valid_until",
)


def ingest_authority_evidence_payload(payload: dict[str, Any]) -> AuthorityEvidence:
    """Normalize a plain payload into an ``AuthorityEvidence`` artifact.

    The adapter is deterministic and local/offline only. Structurally invalid
    payloads fail closed by raising ``ValueError``.
    """
    if not isinstance(payload, dict):
        raise ValueError("authority_evidence_payload_invalid")

    normalized = _normalize_aliases(payload)
    _validate_required_fields(normalized)

    verification_result = _normalize_verification_result(normalized.get("verification_result"))

    metadata = _normalize_metadata(normalized)
    authority_source_refs = _to_sorted_str_list(normalized.get("authority_source_refs", []))
    if not authority_source_refs:
        raise ValueError("authority_evidence_authority_source_refs_missing")

    scope_grants = _to_sorted_str_list(normalized.get("scope_grants", []))
    if not scope_grants:
        raise ValueError("authority_evidence_scope_grants_missing")

    evidence = AuthorityEvidence(
        authority_evidence_id=normalized["authority_evidence_id"],
        action_contract_id=normalized["action_contract_id"],
        action_contract_version=normalized["action_contract_version"],
        actor_identity=normalized["actor_identity"],
        actor_role=normalized["actor_role"],
        authority_source_refs=authority_source_refs,
        role_or_policy_basis=_to_sorted_str_list(normalized.get("role_or_policy_basis", [])),
        scope_grants=scope_grants,
        scope_limitations=_to_sorted_str_list(normalized.get("scope_limitations", [])),
        validity_window={
            "issued_at": normalized["issued_at"],
            "valid_from": normalized["valid_from"],
            "valid_until": normalized["valid_until"],
        },
        issued_at=normalized["issued_at"],
        valid_from=normalized["valid_from"],
        valid_until=normalized["valid_until"],
        revalidated_at=_optional_str(normalized.get("revalidated_at")),
        policy_snapshot_id=_optional_str(normalized.get("policy_snapshot_id")),
        evidence_hash="",
        verification_result=verification_result,
        failure_reasons=_to_sorted_str_list(normalized.get("failure_reasons", [])),
        metadata=metadata,
    )

    evidence_data = evidence.to_dict()
    evidence_data["verification_result"] = evidence.verification_result
    evidence_data["evidence_hash"] = evidence.deterministic_digest()
    return AuthorityEvidence(**evidence_data)


def _normalize_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)

    if "authority_evidence_id" not in normalized and "evidence_id" in normalized:
        normalized["authority_evidence_id"] = normalized["evidence_id"]
    if "actor_identity" not in normalized and "subject" in normalized:
        normalized["actor_identity"] = normalized["subject"]
    if "valid_until" not in normalized and "expires_at" in normalized:
        normalized["valid_until"] = normalized["expires_at"]
    if "scope_grants" not in normalized and "authority_scope" in normalized:
        normalized["scope_grants"] = normalized["authority_scope"]

    return normalized


def _normalize_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("authority_evidence_metadata_invalid")

    normalized = dict(metadata)
    if "issuer" in payload and "issuer" not in normalized:
        normalized["issuer"] = payload["issuer"]
    if "source_type" in payload and "source_type" not in normalized:
        normalized["source_type"] = payload["source_type"]
    return normalized


def _validate_required_fields(payload: dict[str, Any]) -> None:
    for field in _REQUIRED_STRING_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"authority_evidence_{field}_missing")


def _normalize_verification_result(raw_value: Any) -> VerificationResult:
    if isinstance(raw_value, VerificationResult):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return VerificationResult(raw_value.strip().lower())
        except ValueError:
            return VerificationResult.INDETERMINATE
    return VerificationResult.INDETERMINATE


def _to_sorted_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("authority_evidence_list_field_invalid")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return sorted(normalized)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
