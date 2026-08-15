"""Bind a verified Canonical Decision Artifact to an existing TrustLog row.

This module performs only cross-object evidence matching.  It neither grants
execution authority nor proves that the ledger, witness signer, or producer is
trusted.  Persistence remains owned by the injected production TrustLog.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.governance.canonical_decision_artifact import (
    CanonicalDecisionArtifact,
    verify_canonical_decision_artifact,
)

REFERENCE_VERSION = "canonical-decision-reference/v1"
LINK_SCHEMA_VERSION = "canonical_decision_trust_link/v1"
RECEIPT_VERSION = "canonical-decision-trust-receipt/v1"
LINK_EVENT_TYPE = "canonical_decision_link"
LINK_PIPELINE_PHASE = "post_persistence_drift_verified"
FULL_LEDGER = "encrypted_full_ledger"
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_DECISION_ID_PATTERN = r"^cda:v1:sha256:[0-9a-f]{64}$"
_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T"
    r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{6}Z$"
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalDecisionTrustLinkReason(str, Enum):
    """Stable, content-free trust-link refusal codes."""

    CDA_INVALID = "CDA_INVALID"
    REQUEST_ID_MISMATCH = "REQUEST_ID_MISMATCH"
    TRUSTLOG_APPEND_FAILED = "TRUSTLOG_APPEND_FAILED"
    TRUSTLOG_ENTRY_INVALID = "TRUSTLOG_ENTRY_INVALID"
    TRUSTLOG_ENTRY_HASH_INVALID = "TRUSTLOG_ENTRY_HASH_INVALID"
    TRUSTLOG_REFERENCE_MISMATCH = "TRUSTLOG_REFERENCE_MISMATCH"
    TRUSTLOG_RECEIPT_INVALID = "TRUSTLOG_RECEIPT_INVALID"


class CanonicalDecisionTrustLinkError(ValueError):
    """Trust-link failure exposing a stable reason but no source content."""

    def __init__(self, reason_code: CanonicalDecisionTrustLinkReason) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)


class CanonicalDecisionReference(_FrozenModel):
    """Compact exact identity copied from an internally verified CDA v1."""

    format_version: Literal["canonical-decision-reference/v1"]
    artifact_format_version: Literal["canonical-decision-artifact/v1"]
    hash_profile: Literal["veritas.canonical-decision/v1"]
    request_id: str = Field(min_length=1)
    decision_id: str = Field(pattern=_DECISION_ID_PATTERN)
    decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    decision_ts: str = Field(pattern=_TIMESTAMP_PATTERN)


class CanonicalDecisionTrustReceipt(_FrozenModel):
    """Locator for the matching encrypted full-ledger row."""

    format_version: Literal["canonical-decision-trust-receipt/v1"]
    request_id: str = Field(min_length=1)
    canonical_decision_id: str = Field(pattern=_DECISION_ID_PATTERN)
    canonical_decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    canonical_decision_ts: str = Field(pattern=_TIMESTAMP_PATTERN)
    trust_log_entry_sha256: str = Field(pattern=_DIGEST_PATTERN)
    trust_log_entry_sha256_prev: str | None = Field(
        default=None, pattern=_DIGEST_PATTERN
    )
    trust_log_created_at: str = Field(min_length=1)
    ledger: Literal["encrypted_full_ledger"]
    event_type: Literal["canonical_decision_link"]


class CanonicalDecisionTrustVerificationResult(_FrozenModel):
    """Pure cross-object verification result; not a provenance assertion."""

    ok: bool
    cda_integrity_ok: bool
    entry_link_match: bool
    reason_codes: tuple[str, ...]


def build_canonical_decision_reference(
    artifact: CanonicalDecisionArtifact,
) -> CanonicalDecisionReference:
    """Build an exact compact reference only after CDA v1 verification."""
    verification = verify_canonical_decision_artifact(artifact)
    if not verification.is_valid or verification.artifact is None:
        _fail(CanonicalDecisionTrustLinkReason.CDA_INVALID)
    verified = verification.artifact
    return CanonicalDecisionReference(
        format_version=REFERENCE_VERSION,
        artifact_format_version=verified.format_version,
        hash_profile=verified.hash_profile,
        request_id=verified.request_id,
        decision_id=verified.decision_id,
        decision_hash=verified.decision_hash,
        decision_ts=verified.decision_ts,
    )


def build_canonical_decision_trust_event(
    artifact: CanonicalDecisionArtifact,
) -> dict[str, Any]:
    """Construct the dedicated post-drift TrustLog event."""
    reference = build_canonical_decision_reference(artifact)
    return {
        "event_type": LINK_EVENT_TYPE,
        "audit_schema_version": LINK_SCHEMA_VERSION,
        "request_id": artifact.request_id,
        "pipeline_phase": LINK_PIPELINE_PHASE,
        "canonical_decision_ref": reference.model_dump(mode="json"),
    }


def record_canonical_decision_trust_link(
    artifact: CanonicalDecisionArtifact,
    *,
    append_trust_log_fn: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> CanonicalDecisionTrustReceipt:
    """Append and validate the actual returned full-ledger link entry."""
    reference = build_canonical_decision_reference(artifact)
    event = build_canonical_decision_trust_event(artifact)
    try:
        entry = append_trust_log_fn(event)
    except Exception as exc:
        raise CanonicalDecisionTrustLinkError(
            CanonicalDecisionTrustLinkReason.TRUSTLOG_APPEND_FAILED
        ) from exc
    _validate_entry(entry, artifact, reference)
    return CanonicalDecisionTrustReceipt(
        format_version=RECEIPT_VERSION,
        request_id=artifact.request_id,
        canonical_decision_id=artifact.decision_id,
        canonical_decision_hash=artifact.decision_hash,
        canonical_decision_ts=artifact.decision_ts,
        trust_log_entry_sha256=entry["sha256"],
        trust_log_entry_sha256_prev=entry["sha256_prev"],
        trust_log_created_at=entry["created_at"],
        ledger=FULL_LEDGER,
        event_type=LINK_EVENT_TYPE,
    )


def verify_canonical_decision_trust_entry(
    artifact: CanonicalDecisionArtifact | Mapping[str, Any],
    receipt: CanonicalDecisionTrustReceipt | Mapping[str, Any],
    trust_entry: Mapping[str, Any],
) -> CanonicalDecisionTrustVerificationResult:
    """Verify exact CDA, receipt, and full-entry matching without file I/O."""
    cda_result = verify_canonical_decision_artifact(artifact)
    if not cda_result.is_valid or cda_result.artifact is None:
        return _result(False, False, CanonicalDecisionTrustLinkReason.CDA_INVALID)
    verified = cda_result.artifact
    try:
        parsed_receipt = CanonicalDecisionTrustReceipt.model_validate(receipt)
        reference = build_canonical_decision_reference(verified)
        _validate_entry(trust_entry, verified, reference)
    except CanonicalDecisionTrustLinkError as exc:
        return _result(True, False, exc.reason_code)
    except (ValidationError, TypeError):
        return _result(
            True, False, CanonicalDecisionTrustLinkReason.TRUSTLOG_RECEIPT_INVALID
        )
    matches = (
        parsed_receipt.request_id == verified.request_id
        and parsed_receipt.canonical_decision_id == verified.decision_id
        and parsed_receipt.canonical_decision_hash == verified.decision_hash
        and parsed_receipt.canonical_decision_ts == verified.decision_ts
        and parsed_receipt.trust_log_entry_sha256 == trust_entry.get("sha256")
        and parsed_receipt.trust_log_entry_sha256_prev == trust_entry.get("sha256_prev")
        and parsed_receipt.trust_log_created_at == trust_entry.get("created_at")
    )
    return _result(
        True,
        matches,
        None
        if matches
        else CanonicalDecisionTrustLinkReason.TRUSTLOG_REFERENCE_MISMATCH,
    )


def _validate_entry(
    entry: Mapping[str, Any],
    artifact: CanonicalDecisionArtifact,
    reference: CanonicalDecisionReference,
) -> None:
    if not isinstance(entry, Mapping):
        _fail(CanonicalDecisionTrustLinkReason.TRUSTLOG_ENTRY_INVALID)
    if entry.get("request_id") != artifact.request_id:
        _fail(CanonicalDecisionTrustLinkReason.REQUEST_ID_MISMATCH)
    if (
        entry.get("event_type") != LINK_EVENT_TYPE
        or entry.get("audit_schema_version") != LINK_SCHEMA_VERSION
        or entry.get("pipeline_phase") != LINK_PIPELINE_PHASE
        or entry.get("canonical_decision_ref") != reference.model_dump(mode="json")
    ):
        _fail(CanonicalDecisionTrustLinkReason.TRUSTLOG_REFERENCE_MISMATCH)
    try:
        digest = entry["sha256"]
        previous = entry["sha256_prev"]
        created_at = entry["created_at"]
    except KeyError:
        _fail(CanonicalDecisionTrustLinkReason.TRUSTLOG_ENTRY_INVALID)
    if not _is_digest(digest) or (previous is not None and not _is_digest(previous)):
        _fail(CanonicalDecisionTrustLinkReason.TRUSTLOG_ENTRY_HASH_INVALID)
    if type(created_at) is not str or not created_at:
        _fail(CanonicalDecisionTrustLinkReason.TRUSTLOG_ENTRY_INVALID)


def _is_digest(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _result(
    cda_ok: bool,
    entry_ok: bool,
    reason: CanonicalDecisionTrustLinkReason | None,
) -> CanonicalDecisionTrustVerificationResult:
    return CanonicalDecisionTrustVerificationResult(
        ok=cda_ok and entry_ok,
        cda_integrity_ok=cda_ok,
        entry_link_match=entry_ok,
        reason_codes=() if reason is None else (reason.value,),
    )


def _fail(reason: CanonicalDecisionTrustLinkReason) -> None:
    raise CanonicalDecisionTrustLinkError(reason)
