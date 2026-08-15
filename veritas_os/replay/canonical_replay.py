"""Canonical Replay Source and Evidence v1 without execution authority."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.audit.canonical_decision_trust_link import (
    CanonicalDecisionTrustReceipt,
)
from veritas_os.core.atomic_io import atomic_write_text
from veritas_os.governance.canonical_decision_artifact import (
    CanonicalDecisionArtifact,
    verify_canonical_decision_artifact,
)
from veritas_os.logging.encryption import decrypt, encrypt
from veritas_os.replay.semantic_profile import (
    SEMANTIC_PROFILE,
    semantic_hash,
    semantic_projection,
    strict_canonical_json,
)

SOURCE_VERSION = "canonical-replay-source/v1"
SOURCE_HASH_PROFILE = "veritas.canonical-replay-source/v1"
BASELINE_VERSION = "canonical-replay-semantic-baseline/v1"
SOURCE_RECEIPT_VERSION = "canonical-replay-source-receipt/v1"
EVIDENCE_VERSION = "canonical-replay-evidence/v1"
EVIDENCE_HASH_PROFILE = "veritas.canonical-replay-evidence/v1"
SOURCE_ID_PREFIX = "crs:v1:sha256:"
EVIDENCE_ID_PREFIX = "cre:v1:sha256:"
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
TRUSTED_REPLAY_MARKER = object()


class CanonicalReplayError(ValueError):
    """Stable canonical replay refusal without source content."""


class ReplaySourceCollisionError(CanonicalReplayError):
    """Refuse overwriting different verified content at a canonical locator."""

    def __init__(self) -> None:
        super().__init__("REPLAY_SOURCE_COLLISION")


class ReplaySourceLoadStatus(str, Enum):
    ABSENT = "absent"
    FOUND = "found"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticBaseline(_FrozenModel):
    """Versioned semantic projection and its domain-separated digest."""

    format_version: Literal["canonical-replay-semantic-baseline/v1"]
    profile: Literal["veritas.replay-semantic/v1"]
    projection: dict[str, Any]
    semantic_hash: str = Field(pattern=_DIGEST_PATTERN)


class CanonicalReplaySource(_FrozenModel):
    """Content-addressed input for one original verified decision."""

    format_version: Literal["canonical-replay-source/v1"]
    hash_profile: Literal["veritas.canonical-replay-source/v1"]
    source_id: str
    source_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_cda: CanonicalDecisionArtifact
    original_cda_trust_receipt: CanonicalDecisionTrustReceipt | None = None
    deterministic_replay: dict[str, Any]
    semantic_baseline: SemanticBaseline


class CanonicalReplaySourceReceipt(_FrozenModel):
    """Receipt for encrypted persistence and successful read-back only."""

    format_version: Literal["canonical-replay-source-receipt/v1"]
    replay_source_id: str
    replay_source_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_request_id: str
    original_decision_id: str
    original_decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_decision_ts: str
    storage_backend: Literal["encrypted_local_file"]


class ReplayControls(_FrozenModel):
    """Deterministic controls applied at the trusted replay boundary."""

    strict: bool
    mock_external_apis: bool
    seed: int
    temperature: float


class CanonicalReplayEvidence(_FrozenModel):
    """Content-addressed proof of a distinct replay execution."""

    format_version: Literal["canonical-replay-evidence/v1"]
    hash_profile: Literal["veritas.canonical-replay-evidence/v1"]
    evidence_id: str
    evidence_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_source_id: str
    replay_source_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_request_id: str
    original_decision_id: str
    original_decision_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_decision_ts: str
    replay_request_id: str
    replay_cda: CanonicalDecisionArtifact
    replay_cda_trust_receipt: CanonicalDecisionTrustReceipt | None = None
    controls: ReplayControls
    semantic_profile: Literal["veritas.replay-semantic/v1"]
    original_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_semantic_projection: dict[str, Any]
    semantic_match: bool
    fields_changed: tuple[str, ...]
    severity: Literal["info", "warning", "critical"]
    divergence_level: Literal[
        "no_divergence",
        "acceptable_divergence",
        "critical_divergence",
    ]


def _raw(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(strict_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_receipt_binding(
    value: Any,
    cda: CanonicalDecisionArtifact,
) -> CanonicalDecisionTrustReceipt | None:
    if value is None:
        return None
    receipt = CanonicalDecisionTrustReceipt.model_validate(_raw(value))
    expected = (
        cda.request_id,
        cda.decision_id,
        cda.decision_hash,
        cda.decision_ts,
    )
    actual = (
        receipt.request_id,
        receipt.canonical_decision_id,
        receipt.canonical_decision_hash,
        receipt.canonical_decision_ts,
    )
    if actual != expected:
        raise CanonicalReplayError("TRUST_RECEIPT_BINDING_MISMATCH")
    return receipt


def _verified_cda(value: Any) -> CanonicalDecisionArtifact:
    cda = CanonicalDecisionArtifact.model_validate(_raw(value))
    result = verify_canonical_decision_artifact(cda)
    if not result.is_valid or result.artifact is None:
        raise CanonicalReplayError("CDA_INVALID")
    return result.artifact


def build_semantic_baseline(payload: dict[str, Any]) -> SemanticBaseline:
    """Build the single v1 replay semantic baseline."""
    projection = semantic_projection(payload)
    return SemanticBaseline(
        format_version=BASELINE_VERSION,
        profile=SEMANTIC_PROFILE,
        projection=projection,
        semantic_hash=semantic_hash(projection),
    )


def _verify_retrieval_checksum(replay: dict[str, Any]) -> None:
    expected = replay.get("retrieval_snapshot_checksum")
    if expected is None:
        return
    snapshot = replay.get("retrieval_snapshot")
    if not isinstance(snapshot, dict) or str(expected) != _digest(snapshot):
        raise CanonicalReplayError("RETRIEVAL_CHECKSUM_MISMATCH")


def verify_canonical_replay_source(value: Any) -> CanonicalReplaySource:
    """Independently revalidate every canonical replay source commitment."""
    raw = _raw(value)
    try:
        source = CanonicalReplaySource.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalReplayError("REPLAY_SOURCE_INVALID") from exc
    cda = _verified_cda(source.original_cda)
    _validate_receipt_binding(source.original_cda_trust_receipt, cda)
    baseline = SemanticBaseline.model_validate(
        source.semantic_baseline.model_dump(mode="json")
    )
    if baseline.semantic_hash != semantic_hash(baseline.projection):
        raise CanonicalReplayError("SEMANTIC_HASH_MISMATCH")
    final_output = source.deterministic_replay.get("final_output")
    if not isinstance(final_output, dict):
        raise CanonicalReplayError("REPLAY_FINAL_OUTPUT_MISSING")
    if semantic_projection(final_output) != baseline.projection:
        raise CanonicalReplayError("SEMANTIC_BASELINE_MISMATCH")
    _verify_retrieval_checksum(source.deterministic_replay)
    content = source.model_dump(mode="json", exclude={"source_id", "source_hash"})
    digest = _digest(content)
    if source.source_hash != digest or source.source_id != SOURCE_ID_PREFIX + digest:
        raise CanonicalReplayError("REPLAY_SOURCE_IDENTITY_MISMATCH")
    if strict_canonical_json(raw) != strict_canonical_json(source.model_dump(mode="json")):
        raise CanonicalReplayError("REPLAY_SOURCE_NOT_EXACT")
    return source


def build_replay_source(payload: dict[str, Any]) -> CanonicalReplaySource:
    """Build a canonical source from verified decision and replay inputs."""
    cda = _verified_cda(payload["canonical_decision_artifact"])
    receipt = _validate_receipt_binding(
        payload.get("canonical_decision_trust_receipt"), cda
    )
    replay = payload.get("deterministic_replay")
    if not isinstance(replay, dict):
        raise CanonicalReplayError("DETERMINISTIC_REPLAY_MISSING")
    _verify_retrieval_checksum(replay)
    fields = {
        "format_version": SOURCE_VERSION,
        "hash_profile": SOURCE_HASH_PROFILE,
        "original_cda": cda.model_dump(mode="json"),
        "original_cda_trust_receipt": _raw(receipt),
        "deterministic_replay": replay,
        "semantic_baseline": build_semantic_baseline(payload).model_dump(mode="json"),
    }
    digest = _digest(fields)
    return verify_canonical_replay_source(
        {**fields, "source_id": SOURCE_ID_PREFIX + digest, "source_hash": digest}
    )


def _source_path(source: CanonicalReplaySource, directory: Path) -> Path:
    return directory / f"replay_source_{source.original_cda.decision_hash}.enc"


def persist_replay_source(
    source: CanonicalReplaySource,
    directory: Path,
) -> CanonicalReplaySourceReceipt:
    """Persist encrypted source atomically with idempotent collision refusal."""
    verified = verify_canonical_replay_source(source)
    directory.mkdir(parents=True, exist_ok=True)
    path = _source_path(verified, directory)
    if path.exists():
        existing = verify_canonical_replay_source(
            json.loads(decrypt(path.read_text(encoding="utf-8").strip()))
        )
        if existing != verified:
            raise ReplaySourceCollisionError()
    else:
        ciphertext = encrypt(strict_canonical_json(verified.model_dump(mode="json")))
        if not ciphertext.startswith("ENC:"):
            raise CanonicalReplayError("REPLAY_SOURCE_ENCRYPTION_REFUSED")
        atomic_write_text(path, ciphertext)
    read_back = verify_canonical_replay_source(
        json.loads(decrypt(path.read_text(encoding="utf-8").strip()))
    )
    if read_back != verified:
        raise CanonicalReplayError("REPLAY_SOURCE_READ_BACK_MISMATCH")
    return CanonicalReplaySourceReceipt(
        format_version=SOURCE_RECEIPT_VERSION,
        replay_source_id=verified.source_id,
        replay_source_hash=verified.source_hash,
        original_request_id=verified.original_cda.request_id,
        original_decision_id=verified.original_cda.decision_id,
        original_decision_hash=verified.original_cda.decision_hash,
        original_decision_ts=verified.original_cda.decision_ts,
        storage_backend="encrypted_local_file",
    )


def load_replay_source(
    decision_id: str,
    directory: Path,
) -> CanonicalReplaySource | None:
    """Load the identity-specific source; corruption never becomes absence."""
    prefix = "cda:v1:sha256:"
    if not decision_id.startswith(prefix):
        return None
    digest = decision_id.removeprefix(prefix)
    path = directory / f"replay_source_{digest}.enc"
    if not path.exists():
        return None
    try:
        raw = json.loads(decrypt(path.read_text(encoding="utf-8").strip()))
        source = verify_canonical_replay_source(raw)
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CanonicalReplayError("CANONICAL_REPLAY_SOURCE_CORRUPT") from exc
    if source.original_cda.decision_id != decision_id:
        raise CanonicalReplayError("CANONICAL_REPLAY_SOURCE_SUBSTITUTION")
    return source


def _diff_metadata(
    original: dict[str, Any],
    replayed: dict[str, Any],
) -> tuple[tuple[str, ...], str, str]:
    fields = tuple(
        key for key in sorted(set(original) | set(replayed))
        if original.get(key) != replayed.get(key)
    )
    severities = {
        "decision": "critical",
        "fuji": "critical",
        "value_scores": "warning",
        "continuation_state": "warning",
        "continuation_receipt": "warning",
    }
    levels = [severities.get(key, "info") for key in fields]
    severity = "critical" if "critical" in levels else "warning" if "warning" in levels else "info"
    divergence = "critical_divergence" if severity == "critical" else "acceptable_divergence" if fields else "no_divergence"
    return fields, severity, divergence


def build_replay_evidence(
    source: CanonicalReplaySource,
    replay_payload: dict[str, Any],
    controls: ReplayControls,
) -> CanonicalReplayEvidence:
    """Build evidence only from independently verified source and replay CDA."""
    verified_source = verify_canonical_replay_source(source)
    replay_cda = _verified_cda(replay_payload["canonical_decision_artifact"])
    if replay_cda.request_id != str(replay_payload.get("request_id") or ""):
        raise CanonicalReplayError("REPLAY_REQUEST_ID_MISMATCH")
    if (
        replay_cda.request_id == verified_source.original_cda.request_id
        or replay_cda.decision_id == verified_source.original_cda.decision_id
    ):
        raise CanonicalReplayError("REPLAY_IDENTITY_REUSED")
    replay_receipt = _validate_receipt_binding(
        replay_payload.get("canonical_decision_trust_receipt"), replay_cda
    )
    original_projection = verified_source.semantic_baseline.projection
    replay_projection = semantic_projection(replay_payload)
    fields_changed, severity, divergence = _diff_metadata(
        original_projection, replay_projection
    )
    fields = {
        "format_version": EVIDENCE_VERSION,
        "hash_profile": EVIDENCE_HASH_PROFILE,
        "replay_source_id": verified_source.source_id,
        "replay_source_hash": verified_source.source_hash,
        "original_request_id": verified_source.original_cda.request_id,
        "original_decision_id": verified_source.original_cda.decision_id,
        "original_decision_hash": verified_source.original_cda.decision_hash,
        "original_decision_ts": verified_source.original_cda.decision_ts,
        "replay_request_id": replay_cda.request_id,
        "replay_cda": replay_cda.model_dump(mode="json"),
        "replay_cda_trust_receipt": _raw(replay_receipt),
        "controls": controls.model_dump(mode="json"),
        "semantic_profile": SEMANTIC_PROFILE,
        "original_semantic_hash": semantic_hash(original_projection),
        "replay_semantic_hash": semantic_hash(replay_projection),
        "replay_semantic_projection": replay_projection,
        "semantic_match": not fields_changed,
        "fields_changed": fields_changed,
        "severity": severity,
        "divergence_level": divergence,
    }
    digest = _digest(fields)
    evidence = CanonicalReplayEvidence.model_validate(
        {**fields, "evidence_id": EVIDENCE_ID_PREFIX + digest, "evidence_hash": digest}
    )
    return verify_canonical_replay_evidence(verified_source, evidence)


def verify_canonical_replay_evidence(
    source: Any,
    evidence: Any,
) -> CanonicalReplayEvidence:
    """Independently verify source linkage and all replay event commitments."""
    verified_source = verify_canonical_replay_source(source)
    raw = _raw(evidence)
    try:
        candidate = CanonicalReplayEvidence.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalReplayError("REPLAY_EVIDENCE_INVALID") from exc
    replay_cda = _verified_cda(candidate.replay_cda)
    _validate_receipt_binding(candidate.replay_cda_trust_receipt, replay_cda)
    if (
        candidate.replay_source_id != verified_source.source_id
        or candidate.replay_source_hash != verified_source.source_hash
        or candidate.original_request_id != verified_source.original_cda.request_id
        or candidate.original_decision_id != verified_source.original_cda.decision_id
        or candidate.original_decision_hash != verified_source.original_cda.decision_hash
        or candidate.original_decision_ts != verified_source.original_cda.decision_ts
        or candidate.replay_request_id != replay_cda.request_id
        or candidate.replay_request_id == candidate.original_request_id
        or replay_cda.decision_id == candidate.original_decision_id
    ):
        raise CanonicalReplayError("REPLAY_EVIDENCE_LINK_MISMATCH")
    replay_projection = semantic_projection(
        {
            **candidate.replay_semantic_projection,
            "continuation": {
                "state": candidate.replay_semantic_projection.get(
                    "continuation_state"
                ),
                "receipt": candidate.replay_semantic_projection.get(
                    "continuation_receipt"
                ),
            }
            if "continuation_state" in candidate.replay_semantic_projection
            else None,
        }
    )
    if replay_projection != candidate.replay_semantic_projection:
        raise CanonicalReplayError("REPLAY_SEMANTIC_PROJECTION_INVALID")
    original_projection = verified_source.semantic_baseline.projection
    changed, severity, divergence = _diff_metadata(original_projection, replay_projection)
    expected = (
        semantic_hash(original_projection),
        semantic_hash(replay_projection),
        not changed,
        changed,
        severity,
        divergence,
    )
    actual = (
        candidate.original_semantic_hash,
        candidate.replay_semantic_hash,
        candidate.semantic_match,
        candidate.fields_changed,
        candidate.severity,
        candidate.divergence_level,
    )
    if actual != expected:
        raise CanonicalReplayError("REPLAY_EVIDENCE_SEMANTIC_MISMATCH")
    content = candidate.model_dump(mode="json", exclude={"evidence_id", "evidence_hash"})
    digest = _digest(content)
    if candidate.evidence_hash != digest or candidate.evidence_id != EVIDENCE_ID_PREFIX + digest:
        raise CanonicalReplayError("REPLAY_EVIDENCE_IDENTITY_MISMATCH")
    if strict_canonical_json(raw) != strict_canonical_json(candidate.model_dump(mode="json")):
        raise CanonicalReplayError("REPLAY_EVIDENCE_NOT_EXACT")
    return candidate
