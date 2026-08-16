"""Bind verified replay evidence to handoff lineage without authority.

This adapter is deterministic and side-effect free.  It verifies replay
artifacts, represents their exact committed values, and produces only a local
handoff assertion; it does not form a candidate, promote, or execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.canonical_decision_handoff import (
    TrustedValueAssertion,
    canonical_handoff_assertion_value_digest,
)
from veritas_os.replay.canonical_replay import (
    CanonicalReplayError,
    CanonicalReplayEvidence,
    CanonicalReplaySource,
    verify_canonical_replay_evidence,
    verify_canonical_replay_source,
)

LINEAGE_VERSION = "canonical-replay-handoff-lineage/v1"
VERIFICATION_MECHANISM = "verify_canonical_replay_evidence/v1"
EVIDENCE_VERIFIED_CLAIM = "CANONICAL_REPLAY_EVIDENCE_VERIFIED"
ORIGINAL_DECISION_BOUND_CLAIM = (
    "CANONICAL_REPLAY_EVIDENCE_BINDS_ORIGINAL_DECISION"
)
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"


class CanonicalReplayHandoffBindingError(ValueError):
    """Fail-closed replay-to-handoff binding refusal."""


class CanonicalReplayHandoffLineage(BaseModel):
    """Exact handoff representation of verified Canonical Replay Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-replay-handoff-lineage/v1"]
    request_id: str
    verified: Literal[True]
    verification_mechanism: Literal["verify_canonical_replay_evidence/v1"]
    artifact_type: Literal["canonical-replay-evidence/v1"]
    artifact_ref: str
    artifact_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_source_id: str
    replay_source_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_decision_id: str
    original_decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_decision_ts: str
    replay_request_id: str
    replay_decision_id: str
    replay_decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_decision_ts: str
    semantic_profile: Literal["veritas.replay-semantic/v1"]
    original_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    semantic_match: bool
    fields_changed: list[str]
    severity: Literal["info", "warning", "critical"]
    divergence_level: Literal[
        "no_divergence", "acceptable_divergence", "critical_divergence"
    ]
    replay_trust_receipt_present: bool


@dataclass(frozen=True)
class CanonicalReplayHandoffBinding:
    """Immutable lineage and its independently usable trusted assertion."""

    replay_lineage: CanonicalReplayHandoffLineage
    trusted_assertion: TrustedValueAssertion


def _lineage(evidence: CanonicalReplayEvidence) -> CanonicalReplayHandoffLineage:
    replay_cda = evidence.replay_cda
    return CanonicalReplayHandoffLineage(
        format_version=LINEAGE_VERSION,
        request_id=evidence.original_request_id,
        verified=True,
        verification_mechanism=VERIFICATION_MECHANISM,
        artifact_type=evidence.format_version,
        artifact_ref=evidence.evidence_id,
        artifact_hash=evidence.evidence_hash,
        replay_source_id=evidence.replay_source_id,
        replay_source_hash=evidence.replay_source_hash,
        original_decision_id=evidence.original_decision_id,
        original_decision_hash=evidence.original_decision_hash,
        original_decision_ts=evidence.original_decision_ts,
        replay_request_id=evidence.replay_request_id,
        replay_decision_id=replay_cda.decision_id,
        replay_decision_hash=replay_cda.decision_hash,
        replay_decision_ts=replay_cda.decision_ts,
        semantic_profile=evidence.semantic_profile,
        original_semantic_hash=evidence.original_semantic_hash,
        replay_semantic_hash=evidence.replay_semantic_hash,
        semantic_match=evidence.semantic_match,
        fields_changed=evidence.fields_changed,
        severity=evidence.severity,
        divergence_level=evidence.divergence_level,
        replay_trust_receipt_present=evidence.replay_cda_trust_receipt is not None,
    )


def _aware(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def build_canonical_replay_handoff_binding(
    source: CanonicalReplaySource,
    evidence: CanonicalReplayEvidence,
    *,
    verified_at: datetime,
) -> CanonicalReplayHandoffBinding:
    """Build lineage only after full replay evidence verification.

    Args:
        source: Canonical replay source for the original decision.
        evidence: Evidence for a distinct replay decision.
        verified_at: Explicit timezone-aware verification time.

    Raises:
        CanonicalReplayHandoffBindingError: If time or identity separation is
            invalid. Replay verifier failures propagate as CanonicalReplayError.
    """
    if not _aware(verified_at):
        raise CanonicalReplayHandoffBindingError("VERIFIED_AT_INVALID")
    verified = verify_canonical_replay_evidence(source, evidence)
    lineage = _lineage(verified)
    if (
        lineage.replay_request_id == lineage.request_id
        or lineage.replay_decision_id == lineage.original_decision_id
    ):
        raise CanonicalReplayHandoffBindingError("REPLAY_IDENTITY_REUSED")
    value = lineage.model_dump(mode="json")
    assertion = TrustedValueAssertion(
        field_path="replay_lineage",
        value_digest=canonical_handoff_assertion_value_digest(value),
        source_artifact_ref=verified.evidence_id,
        source_hash=verified.evidence_hash,
        verification_mechanism=VERIFICATION_MECHANISM,
        verified_at=verified_at,
        claims=(EVIDENCE_VERIFIED_CLAIM, ORIGINAL_DECISION_BOUND_CLAIM),
    )
    return CanonicalReplayHandoffBinding(lineage, assertion)


def verify_canonical_replay_handoff_binding(
    source: Any,
    evidence: Any,
    replay_lineage: Any,
    trusted_assertion: Any,
) -> CanonicalReplayHandoffBinding:
    """Independently revalidate artifacts, exact lineage, and assertion."""
    try:
        verified_source = verify_canonical_replay_source(source)
        verified_evidence = verify_canonical_replay_evidence(
            verified_source, evidence
        )
        raw_lineage = (
            replay_lineage.model_dump(mode="json")
            if isinstance(replay_lineage, BaseModel)
            else replay_lineage
        )
        candidate = CanonicalReplayHandoffLineage.model_validate(raw_lineage)
    except (CanonicalReplayError, ValidationError, TypeError) as exc:
        raise CanonicalReplayHandoffBindingError("REPLAY_BINDING_INVALID") from exc
    expected = _lineage(verified_evidence)
    if candidate != expected:
        raise CanonicalReplayHandoffBindingError("REPLAY_LINEAGE_MISMATCH")
    if not isinstance(trusted_assertion, TrustedValueAssertion):
        raise CanonicalReplayHandoffBindingError("REPLAY_ASSERTION_INVALID")
    assertion = trusted_assertion
    value = candidate.model_dump(mode="json")
    if (
        assertion.field_path != "replay_lineage"
        or assertion.value_digest
        != canonical_handoff_assertion_value_digest(value)
        or assertion.source_artifact_ref != verified_evidence.evidence_id
        or assertion.source_hash != verified_evidence.evidence_hash
        or assertion.verification_mechanism != VERIFICATION_MECHANISM
        or not _aware(assertion.verified_at)
        or assertion.claims
        != (EVIDENCE_VERIFIED_CLAIM, ORIGINAL_DECISION_BOUND_CLAIM)
    ):
        raise CanonicalReplayHandoffBindingError("REPLAY_ASSERTION_MISMATCH")
    return CanonicalReplayHandoffBinding(candidate, assertion)
