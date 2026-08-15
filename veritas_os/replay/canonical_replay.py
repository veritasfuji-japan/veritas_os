"""Canonical Replay Source and Evidence v1.

These content-addressed artifacts prove replay linkage and semantic comparison
only.  They confer no execution authority and deliberately keep the original
decision identity separate from the replay execution identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veritas_os.core.atomic_io import atomic_write_text
from veritas_os.governance.canonical_decision_artifact import (
    CanonicalDecisionArtifact,
    verify_canonical_decision_artifact,
)
from veritas_os.logging.encryption import decrypt, encrypt

SOURCE_VERSION = "canonical-replay-source/v1"
SOURCE_HASH_PROFILE = "veritas.canonical-replay-source/v1"
BASELINE_VERSION = "canonical-replay-semantic-baseline/v1"
EVIDENCE_VERSION = "canonical-replay-evidence/v1"
EVIDENCE_HASH_PROFILE = "veritas.canonical-replay-evidence/v1"
SOURCE_ID_PREFIX = "crs:v1:sha256:"
EVIDENCE_ID_PREFIX = "cre:v1:sha256:"
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
TRUSTED_REPLAY_MARKER = object()


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class SemanticBaseline(_FrozenModel):
    """Versioned projection compared independently of decision identity."""

    format_version: Literal["canonical-replay-semantic-baseline/v1"]
    payload: dict[str, Any]
    semantic_hash: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> "SemanticBaseline":
        if self.semantic_hash != _hash(self.payload):
            raise ValueError("semantic baseline hash mismatch")
        return self


class CanonicalReplaySource(_FrozenModel):
    """Encrypted-at-rest source binding a verified CDA to replay inputs."""

    format_version: Literal["canonical-replay-source/v1"]
    hash_profile: Literal["veritas.canonical-replay-source/v1"]
    source_id: str
    source_hash: str = Field(pattern=_DIGEST_PATTERN)
    original_cda: CanonicalDecisionArtifact
    original_cda_trust_receipt: dict[str, Any] | None = None
    deterministic_replay: dict[str, Any]
    semantic_baseline: SemanticBaseline

    @model_validator(mode="after")
    def verify_identity(self) -> "CanonicalReplaySource":
        verification = verify_canonical_decision_artifact(self.original_cda)
        if not verification.is_valid:
            raise ValueError("original CDA invalid")
        content = self.model_dump(mode="json", exclude={"source_id", "source_hash"})
        expected = _hash(content)
        if self.source_hash != expected or self.source_id != SOURCE_ID_PREFIX + expected:
            raise ValueError("replay source identity mismatch")
        return self


class ReplayControls(_FrozenModel):
    """Deterministic controls applied at the trusted replay boundary."""

    strict: bool
    mock_external_apis: bool
    seed: int
    temperature: float


class CanonicalReplayEvidence(_FrozenModel):
    """Content-addressed linkage between source, original CDA, and replay CDA."""

    format_version: Literal["canonical-replay-evidence/v1"]
    hash_profile: Literal["veritas.canonical-replay-evidence/v1"]
    evidence_id: str
    evidence_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_source_id: str
    original_cda_id: str
    replay_cda_id: str
    original_request_id: str
    replay_request_id: str
    controls: ReplayControls
    semantic_comparison_version: Literal[
        "canonical-replay-semantic-baseline/v1"
    ]
    original_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    replay_semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    semantic_hash: str = Field(pattern=_DIGEST_PATTERN)
    semantic_match: bool

    @model_validator(mode="after")
    def verify_identity_separation(self) -> "CanonicalReplayEvidence":
        if self.original_request_id == self.replay_request_id:
            raise ValueError("replay request identity reused")
        if self.original_cda_id == self.replay_cda_id:
            raise ValueError("replay CDA identity reused")
        content = self.model_dump(mode="json", exclude={"evidence_id", "evidence_hash"})
        expected = _hash(content)
        if self.evidence_hash != expected or self.evidence_id != EVIDENCE_ID_PREFIX + expected:
            raise ValueError("replay evidence identity mismatch")
        return self


def build_semantic_baseline(payload: dict[str, Any]) -> SemanticBaseline:
    """Build the v1 semantic projection without volatile or identity fields."""
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    fuji = payload.get("fuji") if isinstance(payload.get("fuji"), dict) else {}
    projection = {
        "chosen": payload.get("chosen"),
        "decision_status": payload.get("decision_status"),
        "business_decision": payload.get("business_decision"),
        "gate_decision": payload.get("gate_decision"),
        "decision": {"output": decision.get("output"), "answer": decision.get("answer")},
        "fuji": {"result": fuji.get("result"), "status": fuji.get("status")},
        "value_scores": payload.get("value_scores"),
    }
    return SemanticBaseline(
        format_version=BASELINE_VERSION,
        payload=projection,
        semantic_hash=_hash(projection),
    )


def build_replay_source(payload: dict[str, Any]) -> CanonicalReplaySource:
    """Build a source only from a verified CDA and deterministic snapshot."""
    cda = CanonicalDecisionArtifact.model_validate(payload["canonical_decision_artifact"])
    replay = payload.get("deterministic_replay")
    if not isinstance(replay, dict):
        raise ValueError("deterministic replay snapshot missing")
    fields = {
        "format_version": SOURCE_VERSION,
        "hash_profile": SOURCE_HASH_PROFILE,
        "original_cda": cda.model_dump(mode="json"),
        "original_cda_trust_receipt": payload.get("canonical_decision_trust_receipt"),
        "deterministic_replay": replay,
        "semantic_baseline": build_semantic_baseline(payload).model_dump(mode="json"),
    }
    digest = _hash(fields)
    return CanonicalReplaySource(
        **fields, source_id=SOURCE_ID_PREFIX + digest, source_hash=digest
    )


def persist_replay_source(source: CanonicalReplaySource, directory: Path) -> Path:
    """Atomically persist ciphertext and verify it by decrypting and validating."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source.source_id.replace(':', '_')}.enc"
    ciphertext = encrypt(_canonical_json(source.model_dump(mode="json")))
    if not ciphertext.startswith("ENC:"):
        raise ValueError("replay source encryption refused")
    atomic_write_text(path, ciphertext)
    loaded = CanonicalReplaySource.model_validate_json(decrypt(path.read_text().strip()))
    if loaded != source:
        path.unlink(missing_ok=True)
        raise ValueError("replay source read-back mismatch")
    return path


def load_replay_source(decision_id: str, directory: Path) -> CanonicalReplaySource | None:
    """Load and verify the encrypted source for an original CDA identity."""
    if not directory.exists():
        return None
    for path in directory.glob("crs_v1_sha256_*.enc"):
        source = CanonicalReplaySource.model_validate_json(decrypt(path.read_text().strip()))
        if source.original_cda.decision_id == decision_id:
            return source
    return None


def build_replay_evidence(
    source: CanonicalReplaySource,
    replay_payload: dict[str, Any],
    controls: ReplayControls,
) -> CanonicalReplayEvidence:
    """Build evidence while enforcing distinct original and replay identities."""
    replay_cda = CanonicalDecisionArtifact.model_validate(
        replay_payload["canonical_decision_artifact"]
    )
    replay_baseline = build_semantic_baseline(replay_payload)
    original_hash = source.semantic_baseline.semantic_hash
    comparison_hash = _hash(
        {"original": original_hash, "replay": replay_baseline.semantic_hash}
    )
    fields = {
        "format_version": EVIDENCE_VERSION,
        "hash_profile": EVIDENCE_HASH_PROFILE,
        "replay_source_id": source.source_id,
        "original_cda_id": source.original_cda.decision_id,
        "replay_cda_id": replay_cda.decision_id,
        "original_request_id": source.original_cda.request_id,
        "replay_request_id": replay_cda.request_id,
        "controls": controls.model_dump(mode="json"),
        "semantic_comparison_version": BASELINE_VERSION,
        "original_semantic_hash": original_hash,
        "replay_semantic_hash": replay_baseline.semantic_hash,
        "semantic_hash": comparison_hash,
        "semantic_match": original_hash == replay_baseline.semantic_hash,
    }
    digest = _hash(fields)
    return CanonicalReplayEvidence(
        **fields, evidence_id=EVIDENCE_ID_PREFIX + digest, evidence_hash=digest
    )
