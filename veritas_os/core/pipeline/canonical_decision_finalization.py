"""Finalize and attach canonical decisions at the pipeline boundary.

This adapter preserves the CDA runtime's strict source-class identity while
bridging reloadable API schema modules. It owns no decision, persistence, or
execution-authority semantics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, MutableMapping

from pydantic import ValidationError

from veritas_os.api import schemas as api_schemas
from veritas_os.governance import canonical_decision_artifact as cda_runtime


class CanonicalDecisionFinalizationReason(str, Enum):
    """Stable reason codes for canonical finalization boundary failures."""

    SOURCE_REQUEST_ID_MISSING = "SOURCE_REQUEST_ID_MISSING"
    SOURCE_VALIDATION_FAILED = "SOURCE_VALIDATION_FAILED"
    SOURCE_CLASS_BRIDGE_FAILED = "SOURCE_CLASS_BRIDGE_FAILED"
    ARTIFACT_BUILD_FAILED = "ARTIFACT_BUILD_FAILED"
    ARTIFACT_VERIFICATION_FAILED = "ARTIFACT_VERIFICATION_FAILED"
    REQUEST_ID_MISMATCH = "REQUEST_ID_MISMATCH"
    DECISION_SOURCE_DRIFT = "DECISION_SOURCE_DRIFT"
    PREEXISTING_CANONICAL_ARTIFACT_REFUSED = (
        "PREEXISTING_CANONICAL_ARTIFACT_REFUSED"
    )
    PREEXISTING_TRUST_RECEIPT_REFUSED = "PREEXISTING_TRUST_RECEIPT_REFUSED"


class CanonicalDecisionFinalizationError(ValueError):
    """Fail-closed canonical finalization error without raw-source leakage."""

    def __init__(self, reason_code: CanonicalDecisionFinalizationReason) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)


def finalize_canonical_decision_artifact(
    payload: MutableMapping[str, Any],
    *,
    decision_ts: datetime,
) -> cda_runtime.CanonicalDecisionArtifact:
    """Build and internally verify a CDA from a finalized Stage 7 payload.

    The raw request identifier is checked before either response model can run
    its compatibility UUID generation. A normalized API response is then
    bridged through the exact ``DecideResponse`` class currently bound by the
    CDA runtime module.

    Args:
        payload: Mutable Stage 7 response payload. A null preexisting CDA field
            is removed so Stage 8 receives no CDA key.
        decision_ts: The single timestamp captured by the orchestrator.

    Returns:
        The original, internally verified canonical decision artifact.

    Raises:
        CanonicalDecisionFinalizationError: If any canonical boundary
            invariant fails.
    """
    raw_request_id = payload.get("request_id")
    if type(raw_request_id) is not str or raw_request_id == "":
        _fail(CanonicalDecisionFinalizationReason.SOURCE_REQUEST_ID_MISSING)

    _remove_or_refuse_preexisting_artifact(payload)
    _remove_or_refuse_preexisting_receipt(payload)

    try:
        api_source = api_schemas.DecideResponse.model_validate(payload)
        normalized = api_source.model_dump(mode="json")
    except (TypeError, ValueError, ValidationError):
        _fail(CanonicalDecisionFinalizationReason.SOURCE_VALIDATION_FAILED)

    normalized.pop("canonical_decision_artifact", None)
    normalized.pop("canonical_decision_trust_receipt", None)
    if api_source.request_id != raw_request_id:
        _fail(CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH)

    try:
        runtime_source = cda_runtime.DecideResponse.model_validate(normalized)
    except (TypeError, ValueError, ValidationError):
        _fail(CanonicalDecisionFinalizationReason.SOURCE_CLASS_BRIDGE_FAILED)

    if runtime_source.request_id != raw_request_id:
        _fail(CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH)

    try:
        artifact = cda_runtime.build_canonical_decision_artifact(
            runtime_source,
            decision_ts=decision_ts,
        )
    except (
        cda_runtime.CanonicalDecisionArtifactBuildError,
        TypeError,
        ValidationError,
    ):
        _fail(CanonicalDecisionFinalizationReason.ARTIFACT_BUILD_FAILED)

    if artifact.request_id != raw_request_id:
        _fail(CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH)

    try:
        verification = cda_runtime.verify_canonical_decision_artifact(artifact)
    except (TypeError, ValueError, ValidationError):
        _fail(CanonicalDecisionFinalizationReason.ARTIFACT_VERIFICATION_FAILED)
    if not verification.is_valid:
        _fail(CanonicalDecisionFinalizationReason.ARTIFACT_VERIFICATION_FAILED)
    return artifact


def verify_canonical_decision_source_unchanged(
    payload: MutableMapping[str, Any],
    artifact: cda_runtime.CanonicalDecisionArtifact,
) -> None:
    """Independently rebuild and exactly compare the post-Stage 8 CDA source."""
    try:
        current_artifact = finalize_canonical_decision_artifact(
            payload,
            decision_ts=artifact.decision_ts,
        )
    except CanonicalDecisionFinalizationError as exc:
        if exc.reason_code in {
            CanonicalDecisionFinalizationReason.SOURCE_REQUEST_ID_MISSING,
            CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH,
        }:
            raise CanonicalDecisionFinalizationError(
                CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH
            ) from exc
        if exc.reason_code is (
            CanonicalDecisionFinalizationReason.PREEXISTING_CANONICAL_ARTIFACT_REFUSED
        ):
            raise
        if exc.reason_code is (
            CanonicalDecisionFinalizationReason.PREEXISTING_TRUST_RECEIPT_REFUSED
        ):
            raise
        raise CanonicalDecisionFinalizationError(
            CanonicalDecisionFinalizationReason.DECISION_SOURCE_DRIFT
        ) from exc

    try:
        verification = cda_runtime.verify_canonical_decision_artifact(
            current_artifact
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalDecisionFinalizationError(
            CanonicalDecisionFinalizationReason.DECISION_SOURCE_DRIFT
        ) from exc
    if not verification.is_valid:
        _fail(CanonicalDecisionFinalizationReason.DECISION_SOURCE_DRIFT)
    if current_artifact.model_dump(mode="json") != artifact.model_dump(
        mode="json"
    ):
        _fail(CanonicalDecisionFinalizationReason.DECISION_SOURCE_DRIFT)


def attach_canonical_decision_artifact(
    payload: MutableMapping[str, Any],
    artifact: cda_runtime.CanonicalDecisionArtifact,
) -> None:
    """Attach the original CDA after source-drift verification succeeds."""
    if "canonical_decision_artifact" in payload:
        _fail(
            CanonicalDecisionFinalizationReason.PREEXISTING_CANONICAL_ARTIFACT_REFUSED
        )
    if "canonical_decision_trust_receipt" in payload:
        _fail(CanonicalDecisionFinalizationReason.PREEXISTING_TRUST_RECEIPT_REFUSED)
    payload["canonical_decision_artifact"] = artifact.model_dump(mode="json")


def require_stage_8_payload_without_canonical_artifact(
    payload: MutableMapping[str, Any],
) -> None:
    """Fail closed unless the Stage 8 payload has no CDA key at all."""
    if "canonical_decision_artifact" in payload:
        _fail(
            CanonicalDecisionFinalizationReason.PREEXISTING_CANONICAL_ARTIFACT_REFUSED
        )
    if "canonical_decision_trust_receipt" in payload:
        _fail(CanonicalDecisionFinalizationReason.PREEXISTING_TRUST_RECEIPT_REFUSED)


def _remove_or_refuse_preexisting_artifact(
    payload: MutableMapping[str, Any],
) -> None:
    if "canonical_decision_artifact" not in payload:
        return
    if payload["canonical_decision_artifact"] is None:
        del payload["canonical_decision_artifact"]
        return
    _fail(
        CanonicalDecisionFinalizationReason.PREEXISTING_CANONICAL_ARTIFACT_REFUSED
    )


def _fail(reason_code: CanonicalDecisionFinalizationReason) -> None:
    raise CanonicalDecisionFinalizationError(reason_code)


def _remove_or_refuse_preexisting_receipt(
    payload: MutableMapping[str, Any],
) -> None:
    if "canonical_decision_trust_receipt" not in payload:
        return
    if payload["canonical_decision_trust_receipt"] is None:
        del payload["canonical_decision_trust_receipt"]
        return
    _fail(CanonicalDecisionFinalizationReason.PREEXISTING_TRUST_RECEIPT_REFUSED)
