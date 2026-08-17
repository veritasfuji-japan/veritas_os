"""Security tests for Canonical Adapter Dry-Run Fixture Result v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.adapter_dry_run_plan import STEPS_DOMAIN, _digest as plan_digest
from veritas_os.policy.adapter_dry_run_result import (
    FUTURE_REFERENCE_ADAPTER_REHEARSAL_REQUIREMENTS,
    LOCAL_RESULT_CHECKS,
    RESULT_LIMITATIONS,
    RESULTS_DOMAIN,
    SCOPE_LIMITATIONS,
    VALUE_DOMAIN,
    AdapterDryRunFixtureResultError,
    CanonicalAdapterDryRunFixtureResultPacket,
    _digest,
    _packet_hash,
    build_adapter_dry_run_fixture_result_packet,
    verify_adapter_dry_run_fixture_result_packet,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.tests.test_adapter_dry_run_plan import PLANNED_AT, _packet as plan_packet

RESULTED_AT = PLANNED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/adapter_dry_run_result.py")
SCHEMA = Path("schemas/adapter-dry-run-fixture-result-v1.schema.json")


def _fixtures(plan=None):
    plan = plan or plan_packet()
    return [
        {
            "step_result_id": (
                f"dry-run-fixture-result:v1:{step.ordinal}:"
                f"{step.planned_adapter_method.replace('_', '-')}"
            ),
            "planned_step_id": step.step_id,
            "ordinal": step.ordinal,
            "planned_adapter_method": step.planned_adapter_method,
            "result_mode": "fixture_no_effect",
            "result_source_kind": "unit_test_fixture",
            "live_observed": False,
            "adapter_instance_created": False,
            "adapter_method_called": False,
            "network_used": False,
            "filesystem_used": False,
            "external_effect_used": False,
            "trustlog_written": False,
            "bind_receipt_created": False,
            "fixture_input_ref": f"fixture:{step.planned_adapter_method}",
            "fixture_value_summary": {
                "status": "FIXTURE_RESULT_AVAILABLE",
                "semantic": "no_effect_fixture",
                "live_system_claim": False,
            },
            "matched_expected_output_ref": step.expected_output_ref,
            "refusal_if_missing_later": step.refusal_if_missing_later,
            "result_scope_limitations": RESULT_LIMITATIONS,
        }
        for step in plan.planned_steps
    ]


def _packet(*, semantic_match=None):
    plan = plan_packet(semantic_match=semantic_match)
    return build_adapter_dry_run_fixture_result_packet(
        plan, _fixtures(plan), RESULTED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["adapter_dry_run_result_hash"] = digest
    raw["adapter_dry_run_result_id"] = f"adr:v1:sha256:{digest}"


def test_build_verify_integrity_preservation_and_no_effects(monkeypatch) -> None:
    import veritas_os.policy.adapter_dry_run_result as module

    actual = module.verify_adapter_dry_run_plan_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(module, "verify_adapter_dry_run_plan_packet", recording)
    source = plan_packet(semantic_match=False)
    packet = module.build_adapter_dry_run_fixture_result_packet(
        source, _fixtures(source), RESULTED_AT
    )
    assert len(calls) == 2
    assert module.verify_adapter_dry_run_fixture_result_packet(packet) == packet
    assert len(calls) == 3
    assert packet.adapter_dry_run_result_id == (
        f"adr:v1:sha256:{packet.adapter_dry_run_result_hash}"
    )
    assert packet.adapter_dry_run_result_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    intent = ExecutionIntent(**packet.execution_intent)
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    assert list(packet.planned_steps) == [
        step.model_dump(mode="json") for step in source.planned_steps
    ]
    assert packet.planned_step_digest == plan_digest(
        STEPS_DOMAIN, list(packet.planned_steps)
    )
    methods = [item.planned_adapter_method for item in packet.fixture_step_results]
    assert methods == [
        "describe_target",
        "build_idempotency_key",
        "snapshot",
        "fingerprint_state",
        "validate_authority",
        "validate_constraints",
        "assess_runtime_risk",
    ]
    assert set(methods).isdisjoint({"apply", "verify_postconditions", "revert"})
    for result in packet.fixture_step_results:
        assert result.result_mode == "fixture_no_effect"
        assert not any(
            (
                result.live_observed,
                result.adapter_instance_created,
                result.adapter_method_called,
                result.network_used,
                result.filesystem_used,
                result.external_effect_used,
                result.trustlog_written,
                result.bind_receipt_created,
            )
        )
        assert result.fixture_value_digest == _digest(
            VALUE_DOMAIN, result.fixture_value_summary
        )
    results = [item.model_dump(mode="json") for item in packet.fixture_step_results]
    assert packet.fixture_result_digest == _digest(RESULTS_DOMAIN, results)
    assert packet.local_result_checks == LOCAL_RESULT_CHECKS
    assert (
        packet.future_reference_adapter_rehearsal_requirements
        == FUTURE_REFERENCE_ADAPTER_REHEARSAL_REQUIREMENTS
    )
    for field in (
        "required_field_presence",
        "source_decision_identity",
        "candidate_identity",
        "evidence_lineage",
        "replay_summary",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert packet.replay_summary["semantic_match"] is False
    serialized = json.dumps(packet.model_dump(mode="json"))
    for forbidden in ("bind_receipt_id", "adapter_instance", "live_adapter_result"):
        assert forbidden not in serialized


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_not_gated(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_adapter_dry_run_fixture_result_packet(packet) == packet


def test_invalid_source_and_result_timeline_refuse() -> None:
    source = plan_packet().model_dump(mode="json")
    source["adapter_dry_run_plan_hash"] = "0" * 64
    with pytest.raises(AdapterDryRunFixtureResultError, match="ADR_DRY_RUN_PLAN_INVALID"):
        build_adapter_dry_run_fixture_result_packet(
            source, _fixtures(), RESULTED_AT
        )
    with pytest.raises(AdapterDryRunFixtureResultError, match="ADR_RESULTED_AT_INVALID"):
        build_adapter_dry_run_fixture_result_packet(
            plan_packet(), _fixtures(), RESULTED_AT.replace(tzinfo=None)
        )
    with pytest.raises(AdapterDryRunFixtureResultError, match="ADR_RESULTED_BEFORE_PLAN"):
        build_adapter_dry_run_fixture_result_packet(
            plan_packet(), _fixtures(), PLANNED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "reordered",
        "method",
        "mode",
        "live_observed",
        "adapter_instance_created",
        "adapter_method_called",
        "network_used",
        "filesystem_used",
        "external_effect_used",
        "trustlog_written",
        "bind_receipt_created",
        "apply",
        "verify_postconditions",
        "revert",
        "digest",
    ],
)
def test_fixture_result_refusals(mutation) -> None:
    fixtures = _fixtures()
    if mutation == "missing":
        fixtures.pop()
    elif mutation == "extra":
        fixtures.append(deepcopy(fixtures[-1]))
    elif mutation == "reordered":
        fixtures[0], fixtures[1] = fixtures[1], fixtures[0]
    elif mutation in {"method", "apply", "verify_postconditions", "revert"}:
        fixtures[0]["planned_adapter_method"] = mutation
    elif mutation == "mode":
        fixtures[0]["result_mode"] = "live"
    elif mutation == "digest":
        fixtures[0]["fixture_value_digest"] = "0" * 64
    else:
        fixtures[0][mutation] = True
    with pytest.raises(AdapterDryRunFixtureResultError):
        build_adapter_dry_run_fixture_result_packet(
            plan_packet(), fixtures, RESULTED_AT
        )


@pytest.mark.parametrize(
    "path",
    [
        ("adapter_dry_run_result_id",),
        ("adapter_dry_run_result_hash",),
        ("resulted_at",),
        ("source_adapter_dry_run_plan", "planned_at"),
        ("source_adapter_dry_run_plan_hash",),
        ("source_adapter_dry_run_plan_packet", "adapter_dry_run_plan_hash"),
        ("adapter_contract_descriptor", "adapter_name"),
        ("adapter_contract_id",),
        ("adapter_contract_hash",),
        ("adapter_contract_version",),
        ("execution_intent", "decision_id"),
        ("execution_intent_id",),
        ("execution_intent_hash",),
        ("source_adapter_contract_selection_hash",),
        ("source_bind_preflight_adjudication_hash",),
        ("source_formation_hash",),
        ("source_readiness_hash",),
        ("source_eligibility_hash",),
        ("source_handoff_hash",),
        ("trusted_validation_context_hash",),
        ("validation_result_hash",),
        ("mapping_value_digest",),
        ("planned_steps", 0, "planned_adapter_method"),
        ("planned_step_digest",),
        ("fixture_step_results", 0, "fixture_input_ref"),
        ("fixture_result_digest",),
        ("source_to_execution_intent_mapping", "decision_id"),
        ("field_mapping_proof", "decision_id"),
        ("local_result_checks", "no_bind_invocation"),
        (
            "future_reference_adapter_rehearsal_requirements",
            "snapshot_call_required",
        ),
        ("source_decision_identity", "request_id"),
        ("candidate_identity", "actor_identity"),
        ("evidence_lineage", "policy_snapshot_id"),
        ("replay_summary", "semantic_match"),
        ("replay_summary", "fields_changed"),
        ("scope_limitations",),
    ],
)
def test_single_field_tampering_refuses(path) -> None:
    raw = _packet(semantic_match=True).model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    old = target[key]
    target[key] = (
        not old
        if isinstance(old, bool)
        else [*old, "tampered"]
        if isinstance(old, list)
        else "tampered"
    )
    with pytest.raises(AdapterDryRunFixtureResultError):
        verify_adapter_dry_run_fixture_result_packet(raw)


def test_source_summary_is_closed_even_with_valid_outer_hash() -> None:
    for operation in ("missing", "extra"):
        raw = _packet().model_dump(mode="json")
        if operation == "missing":
            raw["source_adapter_dry_run_plan"].pop("planned_at")
        else:
            raw["source_adapter_dry_run_plan"]["unexpected"] = True
        _rehash(raw)
        with pytest.raises(
            AdapterDryRunFixtureResultError, match="ADR_SOURCE_SUMMARY_MISMATCH"
        ):
            verify_adapter_dry_run_fixture_result_packet(raw)
    assert _packet().scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("method", ["copy", "construct"])
@pytest.mark.parametrize(
    "updates",
    [
        {"format_version": "wrong"},
        {"adapter_dry_run_result_hash": "0" * 64},
        {"execution_intent": {}},
        {"adapter_contract_descriptor": {}},
        {"planned_steps": ()},
        {"fixture_step_results": ()},
        {"local_result_checks": {}},
        {"future_reference_adapter_rehearsal_requirements": {}},
        {"source_adapter_dry_run_plan": {}},
        {"replay_summary": {}},
    ],
)
def test_typed_instance_bypass_refuses(method, updates) -> None:
    packet = _packet()
    bypass = (
        packet.model_copy(update=updates)
        if method == "copy"
        else CanonicalAdapterDryRunFixtureResultPacket.model_construct(
            **{**packet.model_dump(mode="python"), **updates}
        )
    )
    with pytest.raises(AdapterDryRunFixtureResultError):
        verify_adapter_dry_run_fixture_result_packet(bypass)


def test_schema_accepts_valid_and_rejects_extensions() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = _packet().model_dump(mode="json")
    validator.validate(valid)
    for key in (
        "source_adapter_dry_run_plan",
        "source_adapter_dry_run_plan_packet",
        "adapter_contract_descriptor",
        "execution_intent",
        "planned_steps",
        "fixture_step_results",
        "local_result_checks",
        "future_reference_adapter_rehearsal_requirements",
    ):
        invalid = deepcopy(valid)
        target = invalid[key]
        if isinstance(target, list):
            target = target[0]
        target["unexpected"] = True
        assert list(validator.iter_errors(invalid)), key


def test_static_import_and_side_effect_boundary() -> None:
    tree = ast.parse(MODULE.read_text())
    forbidden = {
        "BindReceipt",
        "hash_bind_receipt",
        "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog",
        "build_execution_intent_trustlog_entry",
        "execute_bind_boundary",
        "execute_bind_adjudication",
        "BindAdapterContract",
        "BindBoundaryAdapter",
        "ReferenceBindAdapter",
        "WebhookBindAdapter",
        "bind_core",
        "requests",
        "httpx",
        "subprocess",
        "uuid4",
    }
    imported, functions = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        assert not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
            and node.func.attr == "now"
        )
    assert imported.isdisjoint(forbidden)
    assert functions.isdisjoint(
        {
            "execute",
            "commit",
            "dispatch",
            "send",
            "webhook",
            "adapter_call",
            "write_trustlog",
            "append_trustlog",
            "create_bind_receipt",
            "invoke_bind",
            "call_adapter",
            "instantiate_adapter",
            "snapshot",
            "apply",
            "revert",
            "validate_authority",
            "validate_constraints",
            "assess_runtime_risk",
            "verify_postconditions",
            "describe_target",
            "build_idempotency_key",
        }
    )
    source = MODULE.read_text()
    for forbidden_key in (
        '"bind_receipt_id"',
        '"adapter_instance"',
        '"live_adapter_result"',
        '"live_state_verified"',
    ):
        assert forbidden_key not in source
