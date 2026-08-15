"""Focused security and identity tests for Canonical Replay Evidence v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)
from veritas_os.replay.canonical_replay import (
    ReplayControls,
    build_replay_evidence,
    build_replay_source,
    load_replay_source,
    persist_replay_source,
)

ROOT = Path(__file__).resolve().parents[2]
VECTOR = ROOT / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/vector-01.json"
TIMESTAMP = "2031-02-03T04:05:06.123456Z"


def _payload(request_id: str) -> dict:
    vector = json.loads(VECTOR.read_text())
    projection = dict(vector["source_projection"])
    projection["request_id"] = request_id
    response = DecideResponse.model_validate(projection)
    artifact = build_canonical_decision_artifact(
        response,
        decision_ts=TIMESTAMP,
    )
    payload = response.model_dump(mode="json")
    payload["canonical_decision_artifact"] = artifact.model_dump(mode="json")
    payload["deterministic_replay"] = {
        "request_body": {"query": "controlled", "request_id": request_id},
        "final_output": response.model_dump(mode="json"),
        "seed": 7,
        "temperature": 0,
    }
    return payload


def test_source_is_encrypted_and_read_back_verified(monkeypatch, tmp_path: Path) -> None:
    """Canonical replay source must never expose plaintext on disk."""
    monkeypatch.setenv(
        "VERITAS_ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    source = build_replay_source(_payload("original-request"))

    path = persist_replay_source(source, tmp_path)

    stored = path.read_text()
    assert stored.startswith("ENC:")
    assert source.original_cda.decision_id not in stored
    assert load_replay_source(source.original_cda.decision_id, tmp_path) == source


def test_source_ciphertext_tampering_fails_closed(monkeypatch, tmp_path: Path) -> None:
    """Authenticated encryption must reject a modified replay source."""
    monkeypatch.setenv(
        "VERITAS_ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    source = build_replay_source(_payload("original-request"))
    path = persist_replay_source(source, tmp_path)
    ciphertext = path.read_text().strip()
    path.write_text(ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B"))

    with pytest.raises((RuntimeError, ValueError, ValidationError)):
        load_replay_source(source.original_cda.decision_id, tmp_path)


def test_semantic_match_preserves_distinct_execution_identity() -> None:
    """A semantic match must not imply request or CDA identity equality."""
    source = build_replay_source(_payload("original-request"))
    replay_payload = _payload("new-replay-request")

    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True,
            mock_external_apis=True,
            seed=7,
            temperature=0,
        ),
    )

    assert evidence.semantic_match is True
    assert evidence.original_request_id != evidence.replay_request_id
    assert evidence.original_cda_id != evidence.replay_cda_id


def test_external_context_cannot_enable_replay_mode() -> None:
    """User-controlled context flags are stripped at the pipeline boundary."""
    from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

    class Request:
        query_params: dict = {}

    ctx = normalize_pipeline_inputs(
        {
            "query": "normal",
            "context": {
                "_replay_mode": True,
                "_mock_external_apis": True,
            },
        },
        Request(),
    )

    assert ctx.replay_mode is False
    assert ctx.mock_external_apis is False
