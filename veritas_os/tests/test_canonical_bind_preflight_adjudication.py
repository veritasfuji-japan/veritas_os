"""Security tests for Canonical Bind Preflight Adjudication v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_bind_preflight_adjudication import (
    BIND_ENTRY_REQUIREMENTS,
    ENTRY_REQUIREMENTS_DOMAIN,
    LOCAL_ADJUDICATION_CHECKS,
    LOCAL_CHECKS_DOMAIN,
    PACKET_DOMAIN,
    SCOPE_LIMITATIONS,
    BindPreflightAdjudicationError,
    CanonicalBindPreflightAdjudicationPacket,
    _packet_hash,
    build_canonical_bind_preflight_adjudication_packet,
    verify_canonical_bind_preflight_adjudication_packet,
)
from veritas_os.tests.test_execution_intent_pre_bind_validation import (
    CHECKED_AT,
    _packet as pre_bind_packet,
)

ADJUDICATED_AT = CHECKED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/canonical_bind_preflight_adjudication.py")
SCHEMA = Path("schemas/canonical-bind-preflight-adjudication-v1.schema.json")


def _packet(*, semantic_match: bool | None = None):
    return build_canonical_bind_preflight_adjudication_packet(
        pre_bind_packet(semantic_match=semantic_match), ADJUDICATED_AT
    )


def test_build_verify_integrity_and_preservation(monkeypatch) -> None:
    import veritas_os.policy.canonical_bind_preflight_adjudication as module

    actual = module.verify_execution_intent_pre_bind_validation_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_execution_intent_pre_bind_validation_packet", recording
    )
    source = pre_bind_packet()
    packet = module.build_canonical_bind_preflight_adjudication_packet(
        source, ADJUDICATED_AT
    )
    assert len(calls) == 2  # builder source verification and final verification
    assert module.verify_canonical_bind_preflight_adjudication_packet(packet) == packet
    assert len(calls) == 3
    assert packet.bind_preflight_adjudication_id == (
        f"bpa:v1:sha256:{packet.bind_preflight_adjudication_hash}"
    )
    assert packet.bind_preflight_adjudication_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.source_to_execution_intent_mapping == (
        source.source_to_execution_intent_mapping
    )
    assert packet.field_mapping_proof == source.field_mapping_proof
    assert packet.local_adjudication_checks == LOCAL_ADJUDICATION_CHECKS
    assert packet.bind_entry_requirements == BIND_ENTRY_REQUIREMENTS
    for field in (
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert not hasattr(packet, "bind_receipt")
    assert not hasattr(packet, "trustlog_entry")


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_not_gated(semantic_match: bool) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_canonical_bind_preflight_adjudication_packet(packet) == packet


def test_invalid_source_and_timeline_refuse() -> None:
    source = pre_bind_packet().model_dump(mode="json")
    source["pre_bind_validation_hash"] = "0" * 64
    with pytest.raises(BindPreflightAdjudicationError, match="BPA_PRE_BIND"):
        build_canonical_bind_preflight_adjudication_packet(source, ADJUDICATED_AT)
    with pytest.raises(BindPreflightAdjudicationError, match="BPA_ADJUDICATED_AT"):
        build_canonical_bind_preflight_adjudication_packet(
            pre_bind_packet(), ADJUDICATED_AT.replace(tzinfo=None)
        )
    with pytest.raises(BindPreflightAdjudicationError, match="BPA_ADJUDICATED_BEFORE"):
        build_canonical_bind_preflight_adjudication_packet(
            pre_bind_packet(), CHECKED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize("path", [
    ("bind_preflight_adjudication_id",),
    ("bind_preflight_adjudication_hash",), ("adjudicated_at",),
    ("source_pre_bind_validation", "checked_at"),
    ("source_pre_bind_validation_hash",),
    ("source_pre_bind_validation_packet", "pre_bind_validation_hash"),
    ("source_formation_hash",), ("source_readiness_hash",),
    ("source_eligibility_hash",), ("source_handoff_hash",),
    ("trusted_validation_context_hash",), ("validation_result_hash",),
    ("mapping_value_digest",), ("execution_intent", "decision_id"),
    ("execution_intent_id",), ("execution_intent_hash",),
    ("source_to_execution_intent_mapping", "decision_id"),
    ("field_mapping_proof", "decision_id"),
    ("local_adjudication_checks", "no_bind_invocation"),
    ("bind_entry_requirements", "adapter_required"),
    ("source_decision_identity", "request_id"),
    ("candidate_identity", "actor_identity"),
    ("evidence_lineage", "policy_snapshot_id"),
    ("replay_summary", "semantic_match"),
    ("replay_summary", "fields_changed"), ("scope_limitations",),
])
def test_single_field_tampering_refuses(path: tuple[str, ...]) -> None:
    raw = _packet(semantic_match=True).model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if key.endswith("_id"):
        prefix = "bpa:v1:sha256:" if key.startswith("bind_") else "ei:v1:sha256:"
        target[key] = prefix + "0" * 64
    elif key.endswith("hash") or key.endswith("digest"):
        target[key] = "0" * 64
    elif key == "adjudicated_at":
        target[key] = (ADJUDICATED_AT + timedelta(seconds=1)).isoformat()
    elif key in {"semantic_match", "no_bind_invocation", "adapter_required"}:
        target[key] = not target[key]
    elif key == "fields_changed":
        target[key] = ["outcome.status"]
    elif key == "scope_limitations":
        target[key] = target[key][:-1]
    else:
        target[key] = "tampered"
    with pytest.raises(BindPreflightAdjudicationError):
        verify_canonical_bind_preflight_adjudication_packet(raw)


@pytest.mark.parametrize("method", ["copy", "construct"])
@pytest.mark.parametrize("updates", [
    {"format_version": "wrong"},
    {"bind_preflight_adjudication_hash": "0" * 64},
    {"execution_intent": {}}, {"source_to_execution_intent_mapping": {}},
    {"local_adjudication_checks": {}}, {"bind_entry_requirements": {}},
    {"replay_summary": {}},
])
def test_typed_instance_bypass_refuses(method: str, updates: dict) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates)
        if method == "copy"
        else CanonicalBindPreflightAdjudicationPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(BindPreflightAdjudicationError):
        verify_canonical_bind_preflight_adjudication_packet(bypass)


def test_schema_accepts_valid_and_rejects_nested_extensions() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    for path in (
        ("execution_intent",), ("local_adjudication_checks",),
        ("bind_entry_requirements",), ("source_pre_bind_validation",),
    ):
        invalid = deepcopy(valid)
        invalid[path[0]]["unexpected"] = True
        assert list(validator.iter_errors(invalid))


def test_static_import_and_side_effect_boundary() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    forbidden = {
        "BindReceipt", "hash_bind_receipt", "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "BindBoundaryAdapter",
        "ReferenceBindAdapter", "WebhookBindAdapter", "bind_core", "requests",
        "httpx", "subprocess", "uuid4",
    }
    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    assert imported.isdisjoint(forbidden)
    assert "datetime.now" not in source
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert names.isdisjoint({
        "execute", "commit", "dispatch", "send", "webhook", "adapter_call",
        "write_trustlog", "append_trustlog", "create_bind_receipt", "invoke_bind",
        "call_adapter",
    })
    assert "bind_receipt_id" not in source
    assert len({LOCAL_CHECKS_DOMAIN, ENTRY_REQUIREMENTS_DOMAIN, PACKET_DOMAIN}) == 3
