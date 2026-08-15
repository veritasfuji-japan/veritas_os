"""Security, identity, and verifier tests for Canonical Replay Evidence v1."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from veritas_os.api.schemas import DecideResponse
from veritas_os.audit.canonical_decision_trust_link import (
    CanonicalDecisionTrustReceipt,
)
from veritas_os.governance.canonical_decision_artifact import (
    CanonicalDecisionArtifact,
    build_canonical_decision_artifact,
)
from veritas_os.logging.encryption import EncryptionKeyMissing, encrypt
from veritas_os.replay.canonical_replay import (
    CanonicalReplayError,
    CanonicalReplayEvidence,
    ReplayControls,
    ReplaySourceCollisionError,
    build_replay_evidence,
    build_replay_source,
    load_replay_source,
    persist_replay_source,
    verify_canonical_replay_evidence,
    verify_canonical_replay_source,
)
from veritas_os.replay.semantic_profile import strict_canonical_json

ROOT = Path(__file__).resolve().parents[2]
VECTOR = ROOT / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/vector-01.json"
TIMESTAMP = "2031-02-03T04:05:06.123456Z"
KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _payload(request_id: str, *, query: str = "known plaintext query") -> dict:
    vector = json.loads(VECTOR.read_text())
    projection = dict(vector["source_projection"])
    projection["request_id"] = request_id
    response = DecideResponse.model_validate(projection)
    artifact = build_canonical_decision_artifact(response, decision_ts=TIMESTAMP)
    payload = response.model_dump(mode="json")
    payload["query"] = query
    payload["canonical_decision_artifact"] = artifact.model_dump(mode="json")
    payload["deterministic_replay"] = {
        "request_body": {"query": query, "request_id": request_id},
        "final_output": response.model_dump(mode="json"),
        "retrieval_snapshot": {},
        "retrieval_snapshot_checksum": (
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        ),
        "seed": 7,
        "temperature": 0,
    }
    return payload


def _receipt(cda: CanonicalDecisionArtifact, marker: str = "a") -> dict:
    return CanonicalDecisionTrustReceipt(
        format_version="canonical-decision-trust-receipt/v1",
        request_id=cda.request_id,
        canonical_decision_id=cda.decision_id,
        canonical_decision_hash=cda.decision_hash,
        canonical_decision_ts=cda.decision_ts,
        trust_log_entry_sha256=marker * 64,
        trust_log_entry_sha256_prev=None,
        trust_log_created_at="2031-02-03T04:05:07+00:00",
        ledger="encrypted_full_ledger",
        event_type="canonical_decision_link",
    ).model_dump(mode="json")


def _source_and_replay() -> tuple[object, dict]:
    source = build_replay_source(_payload("original-request"))
    return source, _payload("new-replay-request")


def test_source_encrypted_read_back_and_receipt_has_no_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", KEY)
    source = build_replay_source(_payload("original-request"))
    receipt = persist_replay_source(source, tmp_path)
    raw = next(tmp_path.glob("replay_source_*.enc")).read_text()

    assert raw.startswith("ENC:")
    assert "known plaintext query" not in raw
    assert source.original_cda.decision_id not in raw
    assert "path" not in receipt.model_dump(mode="json")
    assert load_replay_source(source.original_cda.decision_id, tmp_path) == source

    response = DecideResponse.model_validate(
        {
            **_payload("response-request"),
            "canonical_replay_source_receipt": receipt.model_dump(mode="json"),
        }
    )
    dumped = response.model_dump(mode="json")
    assert dumped["canonical_replay_source_receipt"] == receipt.model_dump(
        mode="json"
    )
    assert "path" not in dumped["canonical_replay_source_receipt"]


def test_missing_key_creates_no_plaintext_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    source = build_replay_source(_payload("original-request"))

    with pytest.raises(EncryptionKeyMissing):
        persist_replay_source(source, tmp_path)

    assert not list(tmp_path.glob("*.enc"))


def test_tampered_target_source_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", KEY)
    source = build_replay_source(_payload("original-request"))
    persist_replay_source(source, tmp_path)
    path = next(tmp_path.glob("replay_source_*.enc"))
    ciphertext = path.read_text()
    path.write_text(ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B"))

    with pytest.raises(CanonicalReplayError, match="CANONICAL_REPLAY_SOURCE_CORRUPT"):
        load_replay_source(source.original_cda.decision_id, tmp_path)


def test_unrelated_corrupt_source_cannot_substitute(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", KEY)
    source = build_replay_source(_payload("original-request"))
    persist_replay_source(source, tmp_path)
    unrelated = tmp_path / f"replay_source_{'f' * 64}.enc"
    unrelated.write_text("corrupt")

    assert load_replay_source(source.original_cda.decision_id, tmp_path) == source


def test_idempotence_and_collision_refusal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", KEY)
    source = build_replay_source(_payload("original-request"))
    assert persist_replay_source(source, tmp_path) == persist_replay_source(
        source, tmp_path
    )
    different = build_replay_source(_payload("different-request"))
    path = next(tmp_path.glob("replay_source_*.enc"))
    path.write_text(encrypt(json.dumps(different.model_dump(mode="json"))))

    with pytest.raises(ReplaySourceCollisionError):
        persist_replay_source(source, tmp_path)


def test_original_trust_receipt_substitution_is_rejected() -> None:
    original = _payload("original-request")
    other = _payload("other-request")
    other_cda = CanonicalDecisionArtifact.model_validate(
        other["canonical_decision_artifact"]
    )
    original["canonical_decision_trust_receipt"] = _receipt(other_cda)

    with pytest.raises(CanonicalReplayError, match="TRUST_RECEIPT_BINDING_MISMATCH"):
        build_replay_source(original)


def test_semantic_match_and_independent_evidence_verification() -> None:
    source, replay_payload = _source_and_replay()
    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )

    assert evidence.semantic_match is True
    assert evidence.fields_changed == ()
    assert evidence.original_request_id != evidence.replay_request_id
    assert evidence.original_decision_id != evidence.replay_cda.decision_id
    assert verify_canonical_replay_evidence(source, evidence) == evidence


@pytest.mark.parametrize("method", ["copy", "construct"])
def test_source_model_instance_bypasses_are_rejected(method: str) -> None:
    source = build_replay_source(_payload("original-request"))
    if method == "copy":
        corrupt = source.model_copy(update={"source_hash": "f" * 64})
    else:
        raw = source.model_dump(mode="json")
        raw["format_version"] = "forged"
        corrupt = type(source).model_construct(**raw)

    with pytest.raises(CanonicalReplayError):
        verify_canonical_replay_source(corrupt)


@pytest.mark.parametrize(
    "update",
    [
        {"evidence_hash": "f" * 64},
        {"semantic_match": False},
        {"format_version": "forged"},
    ],
)
def test_evidence_model_copy_bypasses_are_rejected(update: dict) -> None:
    source, replay_payload = _source_and_replay()
    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    ).model_copy(update=update)

    with pytest.raises(CanonicalReplayError):
        verify_canonical_replay_evidence(source, evidence)


def test_evidence_model_construct_bypass_is_rejected() -> None:
    source, replay_payload = _source_and_replay()
    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )
    raw = evidence.model_dump(mode="json")
    raw["format_version"] = "forged"
    corrupt = CanonicalReplayEvidence.model_construct(**raw)

    with pytest.raises(CanonicalReplayError):
        verify_canonical_replay_evidence(source, corrupt)


def test_replay_cda_model_copy_substitution_is_rejected() -> None:
    source, replay_payload = _source_and_replay()
    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )
    other = CanonicalDecisionArtifact.model_validate(
        _payload("third-request")["canonical_decision_artifact"]
    )
    corrupt = evidence.model_copy(update={"replay_cda": other})

    with pytest.raises(CanonicalReplayError):
        verify_canonical_replay_evidence(source, corrupt)


def test_replay_cda_and_receipt_substitution_are_rejected() -> None:
    source, replay_payload = _source_and_replay()
    other = _payload("third-request")
    replay_payload["canonical_decision_trust_receipt"] = _receipt(
        CanonicalDecisionArtifact.model_validate(other["canonical_decision_artifact"])
    )

    with pytest.raises(CanonicalReplayError, match="TRUST_RECEIPT_BINDING_MISMATCH"):
        build_replay_evidence(
            source,
            replay_payload,
            ReplayControls(
                strict=True, mock_external_apis=True, seed=7, temperature=0
            ),
        )


def test_replay_trust_receipt_binds_replay_cda_not_original() -> None:
    original = _payload("original-request")
    original_cda = CanonicalDecisionArtifact.model_validate(
        original["canonical_decision_artifact"]
    )
    original["canonical_decision_trust_receipt"] = _receipt(original_cda, "a")
    source = build_replay_source(original)
    replay_payload = _payload("new-replay-request")
    replay_cda = CanonicalDecisionArtifact.model_validate(
        replay_payload["canonical_decision_artifact"]
    )
    replay_payload["canonical_decision_trust_receipt"] = _receipt(replay_cda, "b")

    evidence = build_replay_evidence(
        source,
        replay_payload,
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )

    assert evidence.replay_cda_trust_receipt is not None
    assert evidence.replay_cda_trust_receipt.canonical_decision_id == replay_cda.decision_id
    assert (
        evidence.replay_cda_trust_receipt.trust_log_entry_sha256
        != source.original_cda_trust_receipt.trust_log_entry_sha256
    )


def test_trusted_replay_never_persists_nested_source(monkeypatch) -> None:
    from veritas_os.core import pipeline

    calls = 0

    def persist(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(pipeline, "persist_replay_source", persist)
    payload: dict = {}
    pipeline._persist_canonical_replay_source(
        SimpleNamespace(replay_mode=True), payload, []
    )

    assert calls == 0
    assert "canonical_replay_source_receipt" not in payload


def test_external_context_cannot_enable_replay_mode() -> None:
    from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

    request = SimpleNamespace(query_params={})
    ctx = normalize_pipeline_inputs(
        {
            "query": "normal",
            "context": {
                "_replay_mode": True,
                "_mock_external_apis": True,
            },
        },
        request,
    )
    assert ctx.replay_mode is False
    assert ctx.mock_external_apis is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "value"}, (1,)])
def test_strict_replay_canonicalization_rejects_non_json_values(value) -> None:
    """Replay hashing never stringifies ambiguous or non-finite values."""
    with pytest.raises((TypeError, ValueError)):
        strict_canonical_json(value)
