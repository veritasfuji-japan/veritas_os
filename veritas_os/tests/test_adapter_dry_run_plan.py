"""Security and integrity tests for Canonical Adapter Dry-Run Plan v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.adapter_dry_run_plan import (
    EFFECT_POLICY,
    FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS,
    LOCAL_PLAN_CHECKS,
    SCOPE_LIMITATIONS,
    STEPS_DOMAIN,
    AdapterDryRunPlanError,
    CanonicalAdapterDryRunPlanPacket,
    _digest,
    _packet_hash,
    build_adapter_dry_run_plan_packet,
    verify_adapter_dry_run_plan_packet,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.tests.test_bind_adapter_contract_selection import (
    SELECTED_AT,
    _packet as selection_packet,
)

PLANNED_AT = SELECTED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/adapter_dry_run_plan.py")
SCHEMA = Path("schemas/adapter-dry-run-plan-v1.schema.json")


def _packet(*, semantic_match: bool | None = None):
    return build_adapter_dry_run_plan_packet(
        selection_packet(semantic_match=semantic_match), PLANNED_AT
    )


def _rehash(raw: dict) -> None:
    digest = _packet_hash(raw)
    raw["adapter_dry_run_plan_hash"] = digest
    raw["adapter_dry_run_plan_id"] = f"adp:v1:sha256:{digest}"


def test_build_verify_integrity_and_no_effects(monkeypatch) -> None:
    import veritas_os.policy.adapter_dry_run_plan as module

    actual = module.verify_bind_adapter_contract_selection_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_bind_adapter_contract_selection_packet", recording
    )
    source = selection_packet()
    packet = module.build_adapter_dry_run_plan_packet(source, PLANNED_AT)
    assert len(calls) == 2
    assert module.verify_adapter_dry_run_plan_packet(packet) == packet
    assert len(calls) == 3
    assert packet.adapter_dry_run_plan_id == (
        f"adp:v1:sha256:{packet.adapter_dry_run_plan_hash}"
    )
    assert packet.adapter_dry_run_plan_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    methods = [step.planned_adapter_method for step in packet.planned_steps]
    assert methods == [
        "describe_target", "build_idempotency_key", "snapshot",
        "fingerprint_state", "validate_authority", "validate_constraints",
        "assess_runtime_risk",
    ]
    assert set(methods).isdisjoint({"apply", "verify_postconditions", "revert"})
    assert [step.ordinal for step in packet.planned_steps] == list(range(1, 8))
    assert all(step.execution_mode == "planned_no_effect"
               and step.effect_policy == EFFECT_POLICY
               for step in packet.planned_steps)
    steps = [step.model_dump(mode="json") for step in packet.planned_steps]
    assert packet.planned_step_digest == _digest(STEPS_DOMAIN, steps)
    assert packet.local_plan_checks == LOCAL_PLAN_CHECKS
    assert (packet.future_dry_run_execution_requirements ==
            FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS)
    for field in (
        "required_field_presence", "source_decision_identity",
        "candidate_identity", "evidence_lineage", "replay_summary",
    ):
        assert getattr(packet, field) == getattr(source, field)
    raw = packet.model_dump(mode="json")
    assert "bind_receipt_id" not in json.dumps(raw)
    assert "adapter_instance" not in raw and "adapter_result" not in raw


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_not_gated(semantic_match: bool) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_adapter_dry_run_plan_packet(packet) == packet


def test_invalid_source_and_timeline_refuse() -> None:
    source = selection_packet().model_dump(mode="json")
    source["adapter_contract_selection_hash"] = "0" * 64
    with pytest.raises(AdapterDryRunPlanError, match="ADP_ADAPTER_SELECTION_INVALID"):
        build_adapter_dry_run_plan_packet(source, PLANNED_AT)
    with pytest.raises(AdapterDryRunPlanError, match="ADP_PLANNED_AT_INVALID"):
        build_adapter_dry_run_plan_packet(
            selection_packet(), PLANNED_AT.replace(tzinfo=None)
        )
    with pytest.raises(AdapterDryRunPlanError, match="ADP_PLANNED_BEFORE_SELECTION"):
        build_adapter_dry_run_plan_packet(
            selection_packet(), SELECTED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize("path", [
    ("adapter_dry_run_plan_id",), ("adapter_dry_run_plan_hash",), ("planned_at",),
    ("source_adapter_contract_selection", "selected_at"),
    ("source_adapter_contract_selection_hash",),
    ("source_adapter_contract_selection_packet", "adapter_contract_selection_hash"),
    ("adapter_contract_descriptor", "adapter_name"), ("adapter_contract_id",),
    ("adapter_contract_hash",), ("adapter_contract_version",),
    ("execution_intent", "decision_id"), ("execution_intent_id",),
    ("execution_intent_hash",), ("source_bind_preflight_adjudication_hash",),
    ("source_formation_hash",), ("source_readiness_hash",),
    ("source_eligibility_hash",), ("source_handoff_hash",),
    ("trusted_validation_context_hash",), ("validation_result_hash",),
    ("mapping_value_digest",), ("planned_steps", 0, "planned_adapter_method"),
    ("planned_step_digest",), ("source_to_execution_intent_mapping", "decision_id"),
    ("field_mapping_proof", "decision_id"),
    ("local_plan_checks", "no_bind_invocation"),
    ("future_dry_run_execution_requirements", "snapshot_call_required"),
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
    with pytest.raises(AdapterDryRunPlanError):
        verify_adapter_dry_run_plan_packet(raw)


@pytest.mark.parametrize("mutation", [
    "missing", "extra", "reordered", "mode", "method", "apply",
    "verify_postconditions", "revert", "adapter_call", "network", "filesystem",
    "external", "trustlog", "receipt",
])
def test_step_and_effect_policy_refusals(mutation: str) -> None:
    raw = _packet().model_dump(mode="json")
    steps = raw["planned_steps"]
    if mutation == "missing":
        steps.pop()
    elif mutation == "extra":
        steps.append(deepcopy(steps[-1]))
    elif mutation == "reordered":
        steps[0], steps[1] = steps[1], steps[0]
    elif mutation == "mode":
        steps[0]["execution_mode"] = "effect"
    elif mutation in {"method", "apply", "verify_postconditions", "revert"}:
        steps[0]["planned_adapter_method"] = mutation
    else:
        key = {
            "adapter_call": "adapter_method_call_allowed_now", "network": "network_allowed",
            "filesystem": "filesystem_allowed", "external": "external_effect_allowed",
            "trustlog": "trustlog_write_allowed", "receipt": "bind_receipt_allowed",
        }[mutation]
        steps[0]["effect_policy"][key] = True
    raw["planned_step_digest"] = _digest(STEPS_DOMAIN, steps)
    _rehash(raw)
    with pytest.raises(AdapterDryRunPlanError):
        verify_adapter_dry_run_plan_packet(raw)


@pytest.mark.parametrize("method", ["copy", "construct"])
@pytest.mark.parametrize("updates", [
    {"format_version": "wrong"}, {"adapter_dry_run_plan_hash": "0" * 64},
    {"execution_intent": {}}, {"adapter_contract_descriptor": {}},
    {"planned_steps": ()}, {"local_plan_checks": {}},
    {"future_dry_run_execution_requirements": {}},
    {"source_adapter_contract_selection": {}}, {"replay_summary": {}},
])
def test_typed_instance_bypass_refuses(method: str, updates: dict) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates) if method == "copy" else
        CanonicalAdapterDryRunPlanPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(AdapterDryRunPlanError):
        verify_adapter_dry_run_plan_packet(bypass)


def test_source_summary_closed_and_scope_exact() -> None:
    for operation in ("missing", "extra"):
        raw = _packet().model_dump(mode="json")
        if operation == "missing":
            raw["source_adapter_contract_selection"].pop("selected_at")
        else:
            raw["source_adapter_contract_selection"]["unexpected"] = True
        _rehash(raw)
        with pytest.raises(AdapterDryRunPlanError, match="ADP_SOURCE_SUMMARY_MISMATCH"):
            verify_adapter_dry_run_plan_packet(raw)
    assert _packet().scope_limitations == SCOPE_LIMITATIONS


def test_schema_accepts_valid_and_rejects_extensions() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    for key in ("source_adapter_contract_selection", "planned_steps",
                "local_plan_checks"):
        invalid = deepcopy(valid)
        target = invalid[key][0] if key == "planned_steps" else invalid[key]
        target["unexpected"] = True
        assert list(validator.iter_errors(invalid))


def test_static_import_and_side_effect_boundary() -> None:
    tree = ast.parse(MODULE.read_text())
    forbidden = {
        "BindReceipt", "hash_bind_receipt", "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "BindAdapterContract",
        "BindBoundaryAdapter", "ReferenceBindAdapter", "WebhookBindAdapter",
        "bind_core", "requests", "httpx", "subprocess", "uuid4",
    }
    imported, functions = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        assert not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "datetime"
                    and node.func.attr == "now")
    assert imported.isdisjoint(forbidden)
    assert functions.isdisjoint({
        "execute", "commit", "dispatch", "send", "webhook", "adapter_call",
        "write_trustlog", "append_trustlog", "create_bind_receipt", "invoke_bind",
        "call_adapter", "instantiate_adapter", "snapshot", "apply", "revert",
        "validate_authority", "validate_constraints", "assess_runtime_risk",
        "verify_postconditions", "describe_target", "build_idempotency_key",
    })
