"""Security tests for Canonical ExecutionIntent Formation v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_execution_intent_formation import (
    EXECUTION_INTENT_FIELDS,
    EXECUTION_INTENT_ID_DOMAIN,
    FIELD_MAPPING_DOMAIN,
    PACKET_DOMAIN,
    SCOPE_LIMITATIONS,
    CanonicalExecutionIntentFormationError,
    CanonicalExecutionIntentFormationPacket,
    _digest,
    _packet_hash,
    build_canonical_execution_intent_formation_packet,
    verify_canonical_execution_intent_formation_packet,
)
from veritas_os.policy.execution_intent_formation_readiness import (
    build_execution_intent_formation_readiness_packet,
)
from veritas_os.tests.test_execution_intent_formation_readiness import (
    NOW,
    _canonical_replay_eligibility,
    _eligibility,
)

FORMED_AT = NOW + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/canonical_execution_intent_formation.py")
SCHEMA = Path("schemas/canonical-execution-intent-formation-v1.schema.json")


def _readiness(*, semantic_match: bool | None = None):
    eligibility = (
        _eligibility()
        if semantic_match is None
        else _canonical_replay_eligibility(
            semantic_match=semantic_match,
            fields_changed=[] if semantic_match else ["outcome.status"],
        )
    )
    return build_execution_intent_formation_readiness_packet(eligibility, NOW)


def _packet(*, semantic_match: bool | None = None):
    return build_canonical_execution_intent_formation_packet(
        _readiness(semantic_match=semantic_match), FORMED_AT
    )


def _resign(raw: dict) -> dict:
    raw["formation_hash"] = _packet_hash(raw)
    raw["formation_id"] = f"eif:v1:sha256:{raw['formation_hash']}"
    return raw


def test_build_verify_mapping_content_addressing_and_no_effects(monkeypatch) -> None:
    import veritas_os.policy.canonical_execution_intent_formation as module

    readiness = _readiness()
    actual = module.verify_execution_intent_formation_readiness_packet
    calls = []

    def recording_verifier(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_execution_intent_formation_readiness_packet", recording_verifier
    )
    packet = module.build_canonical_execution_intent_formation_packet(
        readiness, FORMED_AT
    )
    assert len(calls) == 2  # builder verification, then final verifier verification
    assert module.verify_canonical_execution_intent_formation_packet(packet) == packet
    assert len(calls) == 3
    assert packet.formation_id == f"eif:v1:sha256:{packet.formation_hash}"
    assert packet.formation_hash == _packet_hash(packet.model_dump(mode="json"))
    assert packet.execution_intent_id.startswith("ei:v1:sha256:")
    assert packet.execution_intent["execution_intent_id"] == packet.execution_intent_id
    mapping = readiness.source_to_execution_intent_mapping
    assert packet.execution_intent == {
        "execution_intent_id": packet.execution_intent_id,
        **mapping,
    }
    assert packet.field_mapping_proof == mapping
    intent = ExecutionIntent(
        execution_intent_id=packet.execution_intent_id, **mapping
    )
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.required_field_presence == readiness.required_field_presence
    assert packet.source_decision_identity == readiness.source_decision_identity
    assert packet.candidate_identity == readiness.candidate_identity
    assert packet.evidence_lineage == readiness.evidence_lineage
    assert packet.replay_summary == readiness.replay_summary
    assert packet.scope_limitations == SCOPE_LIMITATIONS
    assert not hasattr(packet, "bind_receipt")
    assert not hasattr(packet, "trustlog_entry")


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_not_gated(semantic_match: bool) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert packet.replay_summary["fields_changed"] == (
        [] if semantic_match else ["outcome.status"]
    )
    assert verify_canonical_execution_intent_formation_packet(packet) == packet


def test_deterministic_execution_intent_id() -> None:
    readiness = _readiness()
    first = build_canonical_execution_intent_formation_packet(readiness, FORMED_AT)
    second = build_canonical_execution_intent_formation_packet(readiness, FORMED_AT)
    value = {
        "source_readiness_id": readiness.readiness_id,
        "source_readiness_hash": readiness.readiness_hash,
        "mapping_value_digest": readiness.mapping_value_digest,
        "source_to_execution_intent_mapping": (
            readiness.source_to_execution_intent_mapping
        ),
        "execution_intent_contract_version": (
            readiness.execution_intent_contract_version
        ),
    }
    assert first == second
    assert first.execution_intent_id == (
        f"ei:v1:sha256:{_digest(EXECUTION_INTENT_ID_DOMAIN, value)}"
    )


def test_invalid_readiness_and_formation_time_refuse() -> None:
    invalid = _readiness().model_dump(mode="json")
    invalid["readiness_hash"] = "0" * 64
    with pytest.raises(CanonicalExecutionIntentFormationError, match="EIF_READINESS_INVALID"):
        build_canonical_execution_intent_formation_packet(invalid, FORMED_AT)
    invalid = _readiness().model_dump(mode="json")
    invalid["readiness_id"] = "eifr:v1:sha256:" + "0" * 64
    with pytest.raises(CanonicalExecutionIntentFormationError, match="EIF_READINESS_INVALID"):
        build_canonical_execution_intent_formation_packet(invalid, FORMED_AT)
    with pytest.raises(
        CanonicalExecutionIntentFormationError, match="EIF_FORMED_AT_INVALID"
    ):
        build_canonical_execution_intent_formation_packet(
            _readiness(), FORMED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        CanonicalExecutionIntentFormationError,
        match="EIF_FORMED_BEFORE_READINESS_CHECKED",
    ):
        build_canonical_execution_intent_formation_packet(
            _readiness(), NOW - timedelta(seconds=1)
        )


@pytest.mark.parametrize("field", EXECUTION_INTENT_FIELDS)
def test_missing_mapping_fields_refuse(field: str) -> None:
    readiness = _readiness().model_dump(mode="json")
    del readiness["source_to_execution_intent_mapping"][field]
    with pytest.raises(CanonicalExecutionIntentFormationError, match="EIF_READINESS_INVALID"):
        build_canonical_execution_intent_formation_packet(readiness, FORMED_AT)


@pytest.mark.parametrize(
    "path",
    [
        ("formation_id",),
        ("formation_hash",),
        ("formed_at",),
        ("source_readiness", "checked_at"),
        ("source_readiness_hash",),
        ("source_readiness_packet", "readiness_hash"),
        ("source_eligibility_hash",),
        ("source_handoff_hash",),
        ("trusted_validation_context_hash",),
        ("validation_result_hash",),
        ("mapping_value_digest",),
        ("execution_intent", "decision_id"),
        ("execution_intent_id",),
        ("execution_intent_hash",),
        ("source_to_execution_intent_mapping", "decision_id"),
        ("field_mapping_proof", "decision_id"),
        ("source_decision_identity", "request_id"),
        ("candidate_identity", "actor_identity"),
        ("evidence_lineage", "policy_snapshot_id"),
        ("replay_summary", "semantic_match"),
        ("replay_summary", "fields_changed"),
        ("scope_limitations",),
    ],
)
def test_single_field_tampering_refuses(path: tuple[str, ...]) -> None:
    raw = _packet(semantic_match=True).model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if key == "formation_id":
        target[key] = "eif:v1:sha256:" + "0" * 64
    elif key in {
        "formation_hash", "source_readiness_hash", "source_eligibility_hash",
        "source_handoff_hash", "trusted_validation_context_hash",
        "validation_result_hash", "mapping_value_digest", "execution_intent_hash",
    }:
        target[key] = "0" * 64
    elif key == "execution_intent_id":
        target[key] = "ei:v1:sha256:" + "0" * 64
    elif key == "formed_at":
        target[key] = (FORMED_AT + timedelta(seconds=1)).isoformat()
    elif key == "readiness_hash":
        target[key] = "0" * 64
    elif key == "semantic_match":
        target[key] = False
    elif key == "fields_changed":
        target[key] = ["outcome.status"]
    elif key == "scope_limitations":
        target[key] = target[key][:-1]
    else:
        target[key] = "tampered"
    with pytest.raises(CanonicalExecutionIntentFormationError):
        verify_canonical_execution_intent_formation_packet(raw)


@pytest.mark.parametrize(
    "updates",
    [
        {"format_version": "wrong"},
        {"formation_hash": "0" * 64},
        {"execution_intent_id": "ei:v1:sha256:" + "0" * 64},
        {"execution_intent": {}},
        {"source_to_execution_intent_mapping": {}},
        {"replay_summary": {}},
    ],
)
@pytest.mark.parametrize("method", ["copy", "construct"])
def test_typed_instance_bypass_refuses(updates: dict, method: str) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates)
        if method == "copy"
        else CanonicalExecutionIntentFormationPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(CanonicalExecutionIntentFormationError):
        verify_canonical_execution_intent_formation_packet(bypass)


def test_schema_accepts_valid_and_rejects_invalid_packet() -> None:
    schema = json.loads(SCHEMA.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    invalid = deepcopy(valid)
    invalid["execution_intent"]["unexpected"] = True
    assert list(validator.iter_errors(invalid))
    invalid = deepcopy(valid)
    invalid["scope_limitations"] = invalid["scope_limitations"][:-1]
    assert list(validator.iter_errors(invalid))


def test_static_import_and_side_effect_boundary() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    forbidden = {
        "BindReceipt", "hash_bind_receipt", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "WebhookBindAdapter",
        "ReferenceBindAdapter", "requests", "httpx", "subprocess", "uuid4",
    }
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(forbidden)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(call, ast.Attribute)
        and isinstance(call.value, ast.Name)
        and call.value.id == "datetime"
        and call.attr == "now"
        for call in calls
    )
    intent_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ExecutionIntent"
    ]
    assert intent_calls
    assert all(
        any(keyword.arg == "execution_intent_id" for keyword in call.keywords)
        for call in intent_calls
    )
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert function_names.isdisjoint(
        {"bind", "execute", "commit", "dispatch", "send", "webhook",
         "adapter_call", "write_trustlog"}
    )
    assert FIELD_MAPPING_DOMAIN != PACKET_DOMAIN
