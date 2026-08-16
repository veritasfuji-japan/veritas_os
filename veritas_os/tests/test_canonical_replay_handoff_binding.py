"""Security tests for Canonical Replay Evidence handoff binding v1."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)
from veritas_os.policy.canonical_decision_handoff import TrustedValueAssertion
from veritas_os.policy.canonical_replay_handoff_binding import (
    CanonicalReplayHandoffBindingError,
    CanonicalReplayHandoffLineage,
    build_canonical_replay_handoff_binding,
    verify_canonical_replay_handoff_binding,
)
from veritas_os.replay.canonical_replay import (
    CanonicalReplayError,
    ReplayControls,
    build_replay_evidence,
    build_replay_source,
)

ROOT = Path(__file__).resolve().parents[2]
VECTOR = ROOT / (
    "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/"
    "vector-01.json"
)
VERIFIED_AT = datetime(2031, 2, 3, 4, 6, tzinfo=timezone.utc)


def _payload(request_id: str, *, divergent: bool = False) -> dict:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    projection = dict(vector["source_projection"])
    projection["request_id"] = request_id
    if divergent:
        projection["decision"] = "REJECT"
    response = DecideResponse.model_validate(projection)
    cda = build_canonical_decision_artifact(
        response, decision_ts="2031-02-03T04:05:06.123456Z"
    )
    payload = response.model_dump(mode="json")
    payload["canonical_decision_artifact"] = cda.model_dump(mode="json")
    payload["deterministic_replay"] = {
        "final_output": response.model_dump(mode="json"),
        "seed": 7,
        "temperature": 0,
    }
    return payload


def _artifacts(*, divergent: bool = False, verified_at: datetime = VERIFIED_AT):
    source = build_replay_source(_payload("original-request"))
    evidence = build_replay_evidence(
        source,
        _payload("distinct-replay-request", divergent=divergent),
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )
    binding = build_canonical_replay_handoff_binding(
        source, evidence, verified_at=verified_at
    )
    return source, evidence, binding


def test_semantic_match_preserves_distinct_original_and_replay_identities() -> None:
    source, evidence, binding = _artifacts()
    lineage = binding.replay_lineage

    assert lineage.semantic_match is True
    assert lineage.fields_changed == []
    assert lineage.request_id == evidence.original_request_id
    assert lineage.replay_request_id == evidence.replay_request_id
    assert lineage.request_id != lineage.replay_request_id
    assert lineage.original_decision_id == source.original_cda.decision_id
    assert lineage.replay_decision_id == evidence.replay_cda.decision_id
    assert lineage.original_decision_id != lineage.replay_decision_id
    assert verify_canonical_replay_handoff_binding(
        source, evidence, lineage, binding.trusted_assertion
    ) == binding


def test_authentic_semantic_divergence_remains_visible_and_verifiable() -> None:
    source, evidence, binding = _artifacts(divergent=True)

    assert binding.replay_lineage.semantic_match is False
    assert binding.replay_lineage.fields_changed
    assert verify_canonical_replay_handoff_binding(
        source, evidence, binding.replay_lineage, binding.trusted_assertion
    ) == binding


def test_assertion_maps_exact_lineage_to_evidence_identity() -> None:
    _, evidence, binding = _artifacts()
    assertion = binding.trusted_assertion

    assert assertion.field_path == "replay_lineage"
    assert assertion.source_artifact_ref == evidence.evidence_id
    assert assertion.source_hash == evidence.evidence_hash
    assert assertion.verification_mechanism == (
        "verify_canonical_replay_evidence/v1"
    )
    assert assertion.verified_at == VERIFIED_AT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format_version", "forged"),
        ("artifact_ref", "cre:v1:sha256:" + "f" * 64),
        ("artifact_hash", "f" * 64),
        ("original_decision_id", "cda:v1:sha256:" + "f" * 64),
        ("replay_decision_id", "cda:v1:sha256:" + "f" * 64),
        ("semantic_match", False),
        ("original_semantic_hash", "f" * 64),
        ("replay_semantic_hash", "f" * 64),
        ("fields_changed", ["decision"]),
        ("severity", "critical"),
        ("divergence_level", "critical_divergence"),
        ("replay_request_id", "original-request"),
    ],
)
def test_lineage_model_copy_tampering_is_rejected(field: str, value: object) -> None:
    source, evidence, binding = _artifacts()
    tampered = binding.replay_lineage.model_copy(update={field: value})

    with pytest.raises(CanonicalReplayHandoffBindingError):
        verify_canonical_replay_handoff_binding(
            source, evidence, tampered, binding.trusted_assertion
        )


def test_lineage_model_construct_bypass_is_rejected() -> None:
    source, evidence, binding = _artifacts()
    raw = binding.replay_lineage.model_dump(mode="json")
    raw["format_version"] = "forged"
    tampered = CanonicalReplayHandoffLineage.model_construct(**raw)

    with pytest.raises(CanonicalReplayHandoffBindingError):
        verify_canonical_replay_handoff_binding(
            source, evidence, tampered, binding.trusted_assertion
        )


def test_source_and_evidence_substitution_are_rejected() -> None:
    source_a, evidence_a, binding_a = _artifacts()
    source_b = build_replay_source(_payload("other-original"))
    evidence_b = build_replay_evidence(
        source_b,
        _payload("other-replay"),
        ReplayControls(
            strict=True, mock_external_apis=True, seed=7, temperature=0
        ),
    )

    for source, evidence in ((source_b, evidence_a), (source_a, evidence_b)):
        with pytest.raises(
            (CanonicalReplayError, CanonicalReplayHandoffBindingError)
        ):
            verify_canonical_replay_handoff_binding(
                source,
                evidence,
                binding_a.replay_lineage,
                binding_a.trusted_assertion,
            )


def test_assertion_substitution_and_naive_clock_are_rejected() -> None:
    source, evidence, binding = _artifacts()
    forged = TrustedValueAssertion(
        **{
            **binding.trusted_assertion.__dict__,
            "source_hash": "f" * 64,
        }
    )
    with pytest.raises(CanonicalReplayHandoffBindingError):
        verify_canonical_replay_handoff_binding(
            source, evidence, binding.replay_lineage, forged
        )
    with pytest.raises(CanonicalReplayHandoffBindingError):
        build_canonical_replay_handoff_binding(
            source, evidence, verified_at=datetime(2031, 1, 1)
        )


def test_closed_schema_accepts_binding_and_rejects_extra_or_bad_id() -> None:
    _, _, binding = _artifacts()
    schema = json.loads(
        (ROOT / "schemas/canonical-replay-handoff-lineage-v1.schema.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    value = binding.replay_lineage.model_dump(mode="json")
    validator.validate(value)
    with pytest.raises(ValidationError):
        validator.validate({**value, "authorized": True})
    with pytest.raises(ValidationError):
        validator.validate({**value, "artifact_ref": "not-content-addressed"})


def test_module_import_boundary_has_no_candidate_execution_or_bind() -> None:
    path = Path("veritas_os/policy/canonical_replay_handoff_binding.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        token in source
        for token in (
            "DecisionCandidate",
            "ExecutionIntent",
            "BindReceipt",
            "WebhookBindAdapter",
            "build_decision_candidate",
            "hash_decision_candidate",
        )
    )
    assert not imported & {"requests", "httpx", "subprocess", "socket"}
