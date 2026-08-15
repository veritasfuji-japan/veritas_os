"""Runtime proofs for the pure Canonical Decision Artifact v1 primitive."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.governance.canonical_decision_artifact import (
    CDA_CHOSEN_BINDING_PROFILE,
    CDA_DECISION_ID_PREFIX,
    CDA_FORMAT_VERSION,
    CDA_GOVERNANCE_IDENTITY_BINDING_PROFILE,
    CDA_HASH_PROFILE,
    CDA_LINEAGE_PROMOTABILITY_BINDING_PROFILE,
    CDA_PROJECTION_VERSION,
    CDA_SOURCE_TYPE,
    CDA_TRANSITION_REFUSAL_BINDING_PROFILE,
    POST_BIND_SOURCE_FIELDS,
    CanonicalDecisionArtifact,
    CanonicalDecisionArtifactBuildError,
    build_canonical_decision_artifact,
    canonical_decision_preimage,
    strict_canonical_json_bytes,
    verify_canonical_decision_artifact,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_hex

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1"
SCHEMA_PATH = ROOT / "schemas/canonical-decision-artifact-v1.schema.json"
MODULE_PATH = ROOT / "veritas_os/governance/canonical_decision_artifact.py"
TIMESTAMP = "2031-02-03T04:05:06.123456Z"
GOLDEN_HASH = "1c6e265c50812c2b86eab04ef5523a7f1e56c45db4888ca527840ec94f0456a8"
GOLDEN_ID = CDA_DECISION_ID_PREFIX + GOLDEN_HASH


def _vector(number: int) -> dict:
    return json.loads((VECTORS / f"vector-{number:02}.json").read_text())


def _source() -> DecideResponse:
    return DecideResponse.model_validate(_vector(1)["source_projection"])


def _artifact() -> CanonicalDecisionArtifact:
    return build_canonical_decision_artifact(_source(), decision_ts=TIMESTAMP)


def _assert_build_reason(source: DecideResponse, reason: str) -> None:
    with pytest.raises(CanonicalDecisionArtifactBuildError) as exc:
        build_canonical_decision_artifact(source, decision_ts=TIMESTAMP)
    assert exc.value.reason_code.value == reason


def test_golden_runtime_artifact_is_exact() -> None:
    vector = _vector(1)
    artifact = _artifact()
    assert artifact.model_dump(mode="json") == vector["artifact"]
    assert artifact.decision_hash == GOLDEN_HASH
    assert artifact.decision_id == GOLDEN_ID
    assert (
        strict_canonical_json_bytes(canonical_decision_preimage(artifact)).decode()
        == vector["expected_canonical_serialized"]
    )


def test_timestamp_normalization_and_refusal() -> None:
    offset = build_canonical_decision_artifact(
        _source(), decision_ts="2031-02-03T05:05:06.123456+01:00"
    )
    assert offset.model_dump(mode="json") == _vector(1)["artifact"]
    whole = build_canonical_decision_artifact(
        _source(), decision_ts=datetime.fromisoformat("2031-02-03T04:05:06+00:00")
    )
    assert whole.decision_ts == "2031-02-03T04:05:06.000000Z"
    for value, reason in (
        (datetime(2031, 2, 3), "NAIVE_TIMESTAMP"),
        ("2031-02-03T04:05:06", "NAIVE_TIMESTAMP"),
        ("", "INVALID_TIMESTAMP"),
        ("bad", "INVALID_TIMESTAMP"),
    ):
        with pytest.raises(CanonicalDecisionArtifactBuildError) as exc:
            build_canonical_decision_artifact(_source(), decision_ts=value)
        assert exc.value.reason_code.value == reason


def test_v12_excluded_fields_are_identity_stable() -> None:
    source = DecideResponse.model_validate(_vector(12)["source_projection"])
    artifact = build_canonical_decision_artifact(source, decision_ts=TIMESTAMP)
    assert (artifact.decision_hash, artifact.decision_id) == (GOLDEN_HASH, GOLDEN_ID)


@pytest.mark.parametrize(
    "mutation",
    [
        {"chosen": {"id": "different"}},
        {"request_id": "different-request"},
        {"gate_decision": "block", "business_decision": "DENY"},
        {"required_evidence": ["different_evidence"]},
        {"governance_identity": {"digest": "different"}},
        {"lineage_promotability": None},
        {"transition_refusal": None},
    ],
)
def test_included_fields_change_identity(mutation: dict) -> None:
    payload = deepcopy(_vector(1)["source_projection"])
    payload.update(mutation)
    artifact = build_canonical_decision_artifact(
        DecideResponse.model_validate(payload), decision_ts=TIMESTAMP
    )
    assert artifact.decision_hash != GOLDEN_HASH


@pytest.mark.parametrize("field", POST_BIND_SOURCE_FIELDS)
def test_every_post_bind_field_is_refused(field: str) -> None:
    payload = deepcopy(_vector(1)["source_projection"])
    value = (
        "COMMITTED"
        if field == "bind_outcome"
        else (
            {}
            if field.endswith("result") or field.startswith("bind_operator")
            else "present"
        )
    )
    if field == "bind_summary":
        value = {"bind_outcome": "BLOCKED"}
    payload[field] = value
    _assert_build_reason(
        DecideResponse.model_validate(payload), "POST_BIND_SOURCE_REFUSED"
    )


@pytest.mark.parametrize("outcome", ["COMMITTED", "BLOCKED", "ROLLED_BACK"])
def test_no_post_bind_outcome_is_exempt(outcome: str) -> None:
    payload = deepcopy(_vector(1)["source_projection"])
    payload["bind_outcome"] = outcome
    _assert_build_reason(
        DecideResponse.model_validate(payload), "POST_BIND_SOURCE_REFUSED"
    )


@pytest.mark.parametrize(
    ("status", "requires_bind", "review"),
    [
        ("reviewable_only", False, False),
        ("bind_required_before_execution", False, False),
        ("human_review_required", False, True),
        ("human_review_required", True, False),
        ("blocked", True, False),
        ("formation_transition_refused", True, True),
    ],
)
def test_actionability_contradictions_are_refused(
    status: str, requires_bind: bool, review: bool
) -> None:
    source = _source()
    source.actionability_status = status
    source.requires_bind_before_execution = requires_bind
    source.human_review_required = review
    _assert_build_reason(source, "ACTIONABILITY_BOUNDARY_INVALID")


def test_post_bind_actionability_and_unresolved_gates_are_refused() -> None:
    source = _source()
    source.actionability_status = "actionable_after_bind"
    _assert_build_reason(source, "POST_BIND_ACTIONABILITY_REFUSED")
    source = _source()
    source.gate_decision = "unknown"
    _assert_build_reason(source, "UNRESOLVED_GATE_DECISION")
    source.gate_decision = "allow"
    _assert_build_reason(source, "SOURCE_NOT_NORMALIZED")


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_are_refused(number: float) -> None:
    source = _source()
    source.chosen = {"score": number}
    _assert_build_reason(source, "NON_CANONICAL_JSON_VALUE")


def test_source_type_is_strict() -> None:
    with pytest.raises(CanonicalDecisionArtifactBuildError) as exc:
        build_canonical_decision_artifact({}, decision_ts=TIMESTAMP)
    assert exc.value.reason_code.value == "SOURCE_NOT_DECIDE_RESPONSE"


def test_schema_runtime_coherence_and_constants() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        _artifact().model_dump(mode="json")
    )
    assert schema["properties"]["format_version"]["const"] == CDA_FORMAT_VERSION
    assert schema["properties"]["hash_profile"]["const"] == CDA_HASH_PROFILE
    source = schema["properties"]["source_contract"]["properties"]
    assert source["type"]["const"] == CDA_SOURCE_TYPE
    assert source["projection_version"]["const"] == CDA_PROJECTION_VERSION
    defs = schema["$defs"]
    expected = {
        "chosenBinding": CDA_CHOSEN_BINDING_PROFILE,
        "governanceIdentityBinding": CDA_GOVERNANCE_IDENTITY_BINDING_PROFILE,
        "lineagePromotabilityBinding": CDA_LINEAGE_PROMOTABILITY_BINDING_PROFILE,
        "transitionRefusalBinding": CDA_TRANSITION_REFUSAL_BINDING_PROFILE,
    }
    for name, profile in expected.items():
        assert defs[name]["properties"]["profile"]["const"] == profile


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"extra": True}),
        lambda value: value.update({"format_version": "wrong"}),
        lambda value: value.update({"hash_profile": "wrong"}),
        lambda value: value["decision"]["chosen_binding"].update({"profile": "wrong"}),
        lambda value: value["decision"].update(
            {"actionability_status": "actionable_after_bind"}
        ),
        lambda value: value["decision"].update({"formation_status": "INCOMPLETE"}),
        lambda value: value["decision"].update({"business_decision": "APPROVE"}),
        lambda value: value.update({"decision_ts": "2031-02-03T04:05:06Z"}),
    ],
)
def test_verifier_rejects_structure_and_semantic_mutations(mutation) -> None:
    value = _artifact().model_dump(mode="json")
    mutation(value)
    assert verify_canonical_decision_artifact(value).reason_codes == (
        "ARTIFACT_SCHEMA_INVALID",
    )


def test_verifier_integrity_mutations_are_independent() -> None:
    valid = _artifact().model_dump(mode="json")
    assert verify_canonical_decision_artifact(valid).is_valid
    assert verify_canonical_decision_artifact(None).reason_codes == (
        "ARTIFACT_MISSING",
    )
    changed = deepcopy(valid)
    changed["decision"]["rationale"] = "tampered"
    assert verify_canonical_decision_artifact(changed).reason_codes == (
        "ARTIFACT_HASH_MISMATCH",
        "ARTIFACT_DECISION_ID_MISMATCH",
    )
    wrong_hash = deepcopy(valid)
    wrong_hash["decision_hash"] = "0" * 64
    assert verify_canonical_decision_artifact(wrong_hash).reason_codes == (
        "ARTIFACT_HASH_MISMATCH",
    )
    wrong_id = deepcopy(valid)
    wrong_id["decision_id"] = CDA_DECISION_ID_PREFIX + "0" * 64
    assert verify_canonical_decision_artifact(wrong_id).reason_codes == (
        "ARTIFACT_DECISION_ID_MISMATCH",
    )


def test_determinism_serializer_compatibility_and_immutability() -> None:
    artifacts = [_artifact() for _ in range(3)]
    dumps = [item.model_dump(mode="json") for item in artifacts]
    preimages = [
        strict_canonical_json_bytes(canonical_decision_preimage(item))
        for item in artifacts
    ]
    assert dumps[0] == dumps[1] == dumps[2]
    assert preimages[0] == preimages[1] == preimages[2]
    assert sha256_hex(preimages[0]) == GOLDEN_HASH
    assert preimages[0].decode() == canonical_json_dumps(
        canonical_decision_preimage(artifacts[0])
    )
    with pytest.raises(ValidationError):
        artifacts[0].decision_hash = "0" * 64
    with pytest.raises(ValidationError):
        artifacts[0].decision.chosen_binding.sha256 = "0" * 64


def test_static_side_effect_guard() -> None:
    tree = ast.parse(MODULE_PATH.read_text())
    forbidden = {
        "requests",
        "httpx",
        "openai",
        "subprocess",
        "socket",
        "random",
        "secrets",
        "uuid4",
        "DecisionCandidate",
        "CanonicalDecisionHandoff",
        "ExecutionIntent",
        "BindReceipt",
        "WebhookBindAdapter",
        "execute_bind_adjudication",
        "execute_bind_boundary",
        "open",
    }
    names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attrs = {
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    assert not forbidden & names
    assert (
        not {
            "datetime.now",
            "datetime.utcnow",
            "time.time",
            "Path.read_text",
            "Path.write_text",
        }
        & attrs
    )
