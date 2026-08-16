"""Security tests for Canonical ExecutionIntent Pre-Bind Validation v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.execution_intent_pre_bind_validation import (
    LOCAL_CHECKS_DOMAIN,
    LOCAL_VALIDATION_CHECKS,
    PACKET_DOMAIN,
    SCOPE_LIMITATIONS,
    CanonicalExecutionIntentPreBindValidationPacket,
    ExecutionIntentPreBindValidationError,
    _packet_hash,
    build_execution_intent_pre_bind_validation_packet,
    verify_execution_intent_pre_bind_validation_packet,
)
from veritas_os.tests.test_canonical_execution_intent_formation import (
    FORMED_AT,
    _packet as formation_packet,
)

CHECKED_AT = FORMED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/execution_intent_pre_bind_validation.py")
SCHEMA = Path("schemas/execution-intent-pre-bind-validation-v1.schema.json")


def _packet(*, semantic_match: bool | None = None):
    return build_execution_intent_pre_bind_validation_packet(
        formation_packet(semantic_match=semantic_match), CHECKED_AT
    )


def test_build_verify_integrity_preservation_and_local_only(monkeypatch) -> None:
    import veritas_os.policy.execution_intent_pre_bind_validation as module

    formation = formation_packet()
    actual = module.verify_canonical_execution_intent_formation_packet
    calls = []

    def recording_verifier(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_canonical_execution_intent_formation_packet", recording_verifier
    )
    packet = module.build_execution_intent_pre_bind_validation_packet(
        formation, CHECKED_AT
    )
    assert len(calls) == 2
    assert module.verify_execution_intent_pre_bind_validation_packet(packet) == packet
    assert len(calls) == 3
    assert packet.pre_bind_validation_id == (
        f"eipbv:v1:sha256:{packet.pre_bind_validation_hash}"
    )
    assert packet.pre_bind_validation_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.execution_intent_id == formation.execution_intent_id
    assert packet.source_to_execution_intent_mapping == (
        formation.source_to_execution_intent_mapping
    )
    assert packet.field_mapping_proof == formation.field_mapping_proof
    assert packet.local_validation_checks == LOCAL_VALIDATION_CHECKS
    for field in (
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        assert getattr(packet, field) == getattr(formation, field)
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
    assert verify_execution_intent_pre_bind_validation_packet(packet) == packet


@pytest.mark.parametrize("field", [
    "decision_id", "request_id", "policy_snapshot_id", "actor_identity",
    "target_system", "target_resource", "intended_action", "decision_hash",
])
def test_missing_required_intent_field_refuses(field: str) -> None:
    formation = formation_packet().model_dump(mode="json")
    del formation["execution_intent"][field]
    with pytest.raises(ExecutionIntentPreBindValidationError, match="EIPBV_FORMATION_INVALID"):
        build_execution_intent_pre_bind_validation_packet(formation, CHECKED_AT)


@pytest.mark.parametrize("mutation,code", [
    (lambda raw: raw["execution_intent"].update(evidence_refs=[]), "EIPBV_FORMATION_INVALID"),
    (lambda raw: raw["execution_intent"].update(evidence_refs=[1]), "EIPBV_FORMATION_INVALID"),
    (lambda raw: raw["execution_intent"].update(decision_ts="invalid"), "EIPBV_FORMATION_INVALID"),
    (lambda raw: raw["execution_intent"].update(ttl_seconds=-1), "EIPBV_FORMATION_INVALID"),
])
def test_invalid_formation_intent_refuses(mutation, code: str) -> None:
    raw = formation_packet().model_dump(mode="json")
    mutation(raw)
    with pytest.raises(ExecutionIntentPreBindValidationError, match=code):
        build_execution_intent_pre_bind_validation_packet(raw, CHECKED_AT)


def test_invalid_formation_and_timeline_refuse() -> None:
    for field in ("formation_hash", "formation_id"):
        raw = formation_packet().model_dump(mode="json")
        raw[field] = ("eif:v1:sha256:" if field.endswith("id") else "") + "0" * 64
        with pytest.raises(ExecutionIntentPreBindValidationError, match="EIPBV_FORMATION_INVALID"):
            build_execution_intent_pre_bind_validation_packet(raw, CHECKED_AT)
    with pytest.raises(ExecutionIntentPreBindValidationError, match="EIPBV_CHECKED_AT_INVALID"):
        build_execution_intent_pre_bind_validation_packet(
            formation_packet(), CHECKED_AT.replace(tzinfo=None)
        )
    with pytest.raises(ExecutionIntentPreBindValidationError, match="EIPBV_CHECKED_BEFORE_FORMED"):
        build_execution_intent_pre_bind_validation_packet(
            formation_packet(), FORMED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize("path", [
    ("pre_bind_validation_id",), ("pre_bind_validation_hash",), ("checked_at",),
    ("source_formation", "formed_at"), ("source_formation_hash",),
    ("source_formation_packet", "formation_hash"), ("source_readiness_hash",),
    ("source_eligibility_hash",), ("source_handoff_hash",),
    ("trusted_validation_context_hash",), ("validation_result_hash",),
    ("mapping_value_digest",), ("execution_intent", "decision_id"),
    ("execution_intent_id",), ("execution_intent_hash",),
    ("source_to_execution_intent_mapping", "decision_id"),
    ("field_mapping_proof", "decision_id"),
    ("local_validation_checks", "formation_verified"),
    ("source_decision_identity", "request_id"),
    ("candidate_identity", "actor_identity"),
    ("evidence_lineage", "policy_snapshot_id"),
    ("replay_summary", "semantic_match"), ("replay_summary", "fields_changed"),
    ("scope_limitations",),
])
def test_single_field_tampering_refuses(path: tuple[str, ...]) -> None:
    raw = _packet(semantic_match=True).model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if key.endswith("_id"):
        target[key] = ("eipbv:v1:sha256:" if key.startswith("pre") else "ei:v1:sha256:") + "0" * 64
    elif key.endswith("hash") or key.endswith("digest"):
        target[key] = "0" * 64
    elif key == "checked_at":
        target[key] = (CHECKED_AT + timedelta(seconds=1)).isoformat()
    elif key == "semantic_match":
        target[key] = False
    elif key == "fields_changed":
        target[key] = ["outcome.status"]
    elif key == "formation_verified":
        target[key] = False
    elif key == "scope_limitations":
        target[key] = target[key][:-1]
    else:
        target[key] = "tampered"
    with pytest.raises(ExecutionIntentPreBindValidationError):
        verify_execution_intent_pre_bind_validation_packet(raw)


@pytest.mark.parametrize("method", ["copy", "construct"])
@pytest.mark.parametrize("updates", [
    {"format_version": "wrong"}, {"pre_bind_validation_hash": "0" * 64},
    {"execution_intent": {}}, {"source_to_execution_intent_mapping": {}},
    {"local_validation_checks": {}}, {"replay_summary": {}},
])
def test_typed_instance_bypass_refuses(method: str, updates: dict) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates)
        if method == "copy"
        else CanonicalExecutionIntentPreBindValidationPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(ExecutionIntentPreBindValidationError):
        verify_execution_intent_pre_bind_validation_packet(bypass)


def test_schema_accepts_valid_and_rejects_invalid_packet() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    invalid_mutations = (
        lambda packet: packet["execution_intent"].update(unexpected=True),
        lambda packet: packet[
            "source_to_execution_intent_mapping"
        ].update(unexpected=True),
        lambda packet: packet["source_formation_packet"][
            "execution_intent"
        ].update(unexpected=True),
        lambda packet: packet["local_validation_checks"].update(
            unexpected=True
        ),
        lambda packet: packet.update(
            scope_limitations=packet["scope_limitations"][:-1]
        ),
    )
    for mutate in invalid_mutations:
        invalid = deepcopy(valid)
        mutate(invalid)
        assert list(validator.iter_errors(invalid))

    refs: set[str] = set()

    def collect_refs(value) -> None:
        """Collect every local reference from the self-contained schema."""
        if isinstance(value, dict):
            if "$ref" in value:
                refs.add(value["$ref"])
            for nested in value.values():
                collect_refs(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_refs(nested)

    collect_refs(schema)
    assert refs
    for ref in refs:
        assert ref.startswith("#/$defs/")
        assert ref.removeprefix("#/$defs/") in schema["$defs"]


def test_static_import_and_side_effect_boundary() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    forbidden = {
        "BindReceipt", "hash_bind_receipt", "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "BindBoundaryAdapter",
        "ReferenceBindAdapter", "WebhookBindAdapter", "requests", "httpx",
        "subprocess", "uuid4",
    }
    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    assert imported.isdisjoint(forbidden)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name)
        and call.value.id == "datetime" and call.attr == "now" for call in calls
    )
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert names.isdisjoint({
        "bind", "execute", "commit", "dispatch", "send", "webhook",
        "adapter_call", "write_trustlog", "append_trustlog",
        "create_bind_receipt", "invoke_bind",
    })
    assert "bind_receipt_id" not in source
    assert LOCAL_CHECKS_DOMAIN != PACKET_DOMAIN
