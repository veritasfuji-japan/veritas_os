"""Security tests for Canonical Bind Adapter Contract Selection v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.bind_adapter_contract_selection import (
    ADAPTER_METHODS,
    DESCRIPTOR_SCOPE_LIMITATIONS,
    EFFECT_PROFILE,
    FUTURE_BIND_DRY_RUN_REQUIREMENTS,
    LOCAL_SELECTION_CHECKS,
    PROHIBITED_DURING_SELECTION,
    SCOPE_LIMITATIONS,
    BindAdapterContractSelectionError,
    CanonicalBindAdapterContractSelectionPacket,
    _descriptor_hash,
    _packet_hash,
    build_bind_adapter_contract_selection_packet,
    verify_bind_adapter_contract_selection_packet,
)
from veritas_os.tests.test_canonical_bind_preflight_adjudication import (
    ADJUDICATED_AT,
    _packet as preflight_packet,
)

SELECTED_AT = ADJUDICATED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/bind_adapter_contract_selection.py")
SCHEMA = Path("schemas/bind-adapter-contract-selection-v1.schema.json")


def _descriptor() -> dict:
    source = preflight_packet()
    return {
        "adapter_contract_version": "bind-adapter-contract/v1",
        "adapter_kind": "reference",
        "adapter_name": "inert-reference-declaration",
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": source.execution_intent["target_resource"],
        "supported_methods": list(ADAPTER_METHODS),
        "required_methods": list(ADAPTER_METHODS),
        "prohibited_during_selection": list(PROHIBITED_DURING_SELECTION),
        "effect_profile": EFFECT_PROFILE,
        "declared_by": "local-test",
        "declared_at": ADJUDICATED_AT.isoformat(),
        "descriptor_scope_limitations": list(DESCRIPTOR_SCOPE_LIMITATIONS),
    }


def _packet(*, semantic_match: bool | None = None):
    return build_bind_adapter_contract_selection_packet(
        preflight_packet(semantic_match=semantic_match), _descriptor(), SELECTED_AT
    )


def test_build_verify_integrity_preservation_and_no_effects(monkeypatch) -> None:
    import veritas_os.policy.bind_adapter_contract_selection as module

    actual = module.verify_canonical_bind_preflight_adjudication_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_canonical_bind_preflight_adjudication_packet", recording
    )
    source = preflight_packet()
    packet = module.build_bind_adapter_contract_selection_packet(
        source, _descriptor(), SELECTED_AT
    )
    assert len(calls) == 2
    assert module.verify_bind_adapter_contract_selection_packet(packet) == packet
    assert len(calls) == 3
    assert packet.adapter_contract_selection_id == (
        f"bac:v1:sha256:{packet.adapter_contract_selection_hash}"
    )
    assert packet.adapter_contract_selection_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    descriptor = packet.adapter_contract_descriptor
    assert descriptor["adapter_contract_hash"] == _descriptor_hash(descriptor)
    assert descriptor["adapter_contract_id"] == (
        f"adapter-contract:v1:sha256:{descriptor['adapter_contract_hash']}"
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.execution_intent_id == source.execution_intent_id
    assert descriptor["target_system"] == intent.target_system
    assert descriptor["target_resource_scope"] == intent.target_resource
    assert tuple(descriptor["supported_methods"]) == ADAPTER_METHODS
    assert tuple(descriptor["required_methods"]) == ADAPTER_METHODS
    assert tuple(descriptor["prohibited_during_selection"]) == PROHIBITED_DURING_SELECTION
    assert descriptor["effect_profile"] == EFFECT_PROFILE
    assert packet.local_selection_checks == LOCAL_SELECTION_CHECKS
    assert packet.future_bind_dry_run_requirements == FUTURE_BIND_DRY_RUN_REQUIREMENTS
    for field in (
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert not hasattr(packet, "bind_receipt")
    assert "adapter_instance" not in packet.model_dump(mode="json")


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_not_gated(semantic_match: bool) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_bind_adapter_contract_selection_packet(packet) == packet


@pytest.mark.parametrize("field", ["adapter_name", "adapter_kind"])
def test_missing_descriptor_fields_refuse(field: str) -> None:
    descriptor = _descriptor()
    descriptor.pop(field)
    with pytest.raises(BindAdapterContractSelectionError, match="BAC_DESCRIPTOR_INVALID"):
        build_bind_adapter_contract_selection_packet(
            preflight_packet(), descriptor, SELECTED_AT
        )


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("adapter_kind",), "unknown", "BAC_DESCRIPTOR_INVALID"),
        (("target_system",), "other", "BAC_DESCRIPTOR_TARGET_MISMATCH"),
        (("target_resource_scope",), "broader", "BAC_DESCRIPTOR_TARGET_MISMATCH"),
        (("supported_methods",), ["apply"], "BAC_METHODS_MISMATCH"),
        (("required_methods",), ["revert"], "BAC_METHODS_MISMATCH"),
        (("prohibited_during_selection",), ["snapshot"], "BAC_METHODS_MISMATCH"),
        (("effect_profile", "adapter_instantiated"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "adapter_methods_called"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "network_allowed"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "filesystem_allowed"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "external_effect_allowed"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "trustlog_write_allowed"), True, "BAC_EFFECT_PROFILE_INVALID"),
        (("effect_profile", "bind_receipt_allowed"), True, "BAC_EFFECT_PROFILE_INVALID"),
    ],
)
def test_descriptor_refusals(path, value, code) -> None:
    descriptor = deepcopy(_descriptor())
    target = descriptor
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(BindAdapterContractSelectionError, match=code):
        build_bind_adapter_contract_selection_packet(
            preflight_packet(), descriptor, SELECTED_AT
        )


def test_invalid_source_and_timeline_refuse() -> None:
    source = preflight_packet().model_dump(mode="json")
    source["bind_preflight_adjudication_hash"] = "0" * 64
    with pytest.raises(BindAdapterContractSelectionError, match="BAC_BIND_PREFLIGHT"):
        build_bind_adapter_contract_selection_packet(source, _descriptor(), SELECTED_AT)
    with pytest.raises(BindAdapterContractSelectionError, match="BAC_SELECTED_AT"):
        build_bind_adapter_contract_selection_packet(
            preflight_packet(), _descriptor(), SELECTED_AT.replace(tzinfo=None)
        )
    with pytest.raises(BindAdapterContractSelectionError, match="BAC_SELECTED_BEFORE"):
        build_bind_adapter_contract_selection_packet(
            preflight_packet(), _descriptor(), ADJUDICATED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize("path", [
    ("adapter_contract_selection_id",), ("adapter_contract_selection_hash",),
    ("selected_at",), ("source_bind_preflight_adjudication", "adjudicated_at"),
    ("source_bind_preflight_adjudication_hash",),
    ("source_bind_preflight_adjudication_packet", "bind_preflight_adjudication_hash"),
    ("adapter_contract_descriptor", "adapter_name"), ("adapter_contract_id",),
    ("adapter_contract_hash",), ("adapter_contract_version",),
    ("execution_intent", "decision_id"), ("execution_intent_id",),
    ("execution_intent_hash",), ("source_formation_hash",),
    ("source_readiness_hash",), ("source_eligibility_hash",),
    ("source_handoff_hash",), ("trusted_validation_context_hash",),
    ("validation_result_hash",), ("mapping_value_digest",),
    ("source_to_execution_intent_mapping", "decision_id"),
    ("field_mapping_proof", "decision_id"),
    ("local_selection_checks", "no_bind_invocation"),
    ("future_bind_dry_run_requirements", "snapshot_required"),
    ("source_decision_identity", "request_id"),
    ("candidate_identity", "actor_identity"),
    ("evidence_lineage", "policy_snapshot_id"),
    ("replay_summary", "semantic_match"), ("replay_summary", "fields_changed"),
    ("scope_limitations",),
])
def test_single_field_tampering_refuses(path) -> None:
    raw = _packet(semantic_match=True).model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    old = target[key]
    target[key] = (not old if isinstance(old, bool) else
                   [*old, "tampered"] if isinstance(old, list) else "tampered")
    with pytest.raises(BindAdapterContractSelectionError):
        verify_bind_adapter_contract_selection_packet(raw)


@pytest.mark.parametrize("method", ["copy", "construct"])
@pytest.mark.parametrize("updates", [
    {"format_version": "wrong"}, {"adapter_contract_selection_hash": "0" * 64},
    {"execution_intent": {}}, {"adapter_contract_descriptor": {}},
    {"local_selection_checks": {}}, {"future_bind_dry_run_requirements": {}},
    {"source_bind_preflight_adjudication": {}}, {"replay_summary": {}},
])
def test_typed_instance_bypass_refuses(method: str, updates: dict) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates) if method == "copy" else
        CanonicalBindAdapterContractSelectionPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(BindAdapterContractSelectionError):
        verify_bind_adapter_contract_selection_packet(bypass)


def test_schema_accepts_valid_and_rejects_extensions() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    for key in ("adapter_contract_descriptor", "local_selection_checks",
                "source_bind_preflight_adjudication"):
        invalid = deepcopy(valid)
        invalid[key]["unexpected"] = True
        assert list(validator.iter_errors(invalid))


def test_static_import_and_side_effect_boundary() -> None:
    tree = ast.parse(MODULE.read_text())
    forbidden_imports = {
        "BindReceipt", "hash_bind_receipt", "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "BindAdapterContract",
        "BindBoundaryAdapter", "ReferenceBindAdapter", "WebhookBindAdapter",
        "bind_core", "requests", "httpx", "subprocess", "uuid4",
    }
    imported = set()
    functions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        assert not (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime" and node.func.attr == "now"
        )
    assert imported.isdisjoint(forbidden_imports)
    assert functions.isdisjoint({
        "execute", "commit", "dispatch", "send", "webhook", "adapter_call",
        "write_trustlog", "append_trustlog", "create_bind_receipt", "invoke_bind",
        "call_adapter", "instantiate_adapter", "snapshot", "apply", "revert",
        "validate_authority",
    })
