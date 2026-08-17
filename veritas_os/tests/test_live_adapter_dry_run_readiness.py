"""Security and integrity tests for live-adapter request readiness v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver, ValidationError

from veritas_os.policy.live_adapter_dry_run_readiness import (
    CHECK_NAMES,
    CHECKS_DOMAIN,
    PACKET_DOMAIN,
    LiveAdapterDryRunReadinessError,
    _digest,
    _packet_hash,
    build_live_adapter_dry_run_request_readiness_packet,
    verify_live_adapter_dry_run_request_readiness_packet,
)
from veritas_os.tests.test_reference_adapter_rehearsal import (
    REHEARSED_AT,
    _packet as rehearsal_packet,
)

EVALUATED_AT = REHEARSED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/live_adapter_dry_run_readiness.py")
SCHEMA = Path("schemas/live-adapter-dry-run-readiness-v1.schema.json")


def _packet(*, semantic_match: bool = True):
    return build_live_adapter_dry_run_request_readiness_packet(
        rehearsal_packet(semantic_match=semantic_match), EVALUATED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_readiness_hash"] = digest
    raw["live_adapter_dry_run_readiness_id"] = f"ladr:v1:sha256:{digest}"


def test_build_and_verify_preserve_source_without_effects(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_readiness as module

    actual = module.verify_reference_adapter_in_memory_rehearsal_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_reference_adapter_in_memory_rehearsal_packet", recording
    )
    source = rehearsal_packet(semantic_match=False)
    packet = module.build_live_adapter_dry_run_request_readiness_packet(
        source, EVALUATED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_request_readiness_packet(packet) == packet
    assert len(calls) == 3
    assert packet.live_adapter_dry_run_readiness_id == (
        f"ladr:v1:sha256:{packet.live_adapter_dry_run_readiness_hash}"
    )
    assert packet.live_adapter_dry_run_readiness_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    assert packet.source_reference_rehearsal_packet == source.model_dump(mode="json")
    for field in (
        "adapter_contract_descriptor", "execution_intent", "planned_steps",
        "fixture_step_results", "reference_rehearsal_results",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "source_decision_identity", "candidate_identity", "evidence_lineage",
        "replay_summary",
    ):
        assert packet.model_dump(mode="json")[field] == source.model_dump(mode="json")[
            field
        ]
    assert packet.replay_summary["semantic_match"] is False
    assert [check.check_name for check in packet.readiness_checks] == list(CHECK_NAMES)
    assert packet.readiness_check_digest == _digest(
        CHECKS_DOMAIN,
        [check.model_dump(mode="json") for check in packet.readiness_checks],
    )
    for check in packet.readiness_checks:
        assert not any(
            (
                check.live_observation_used, check.network_used,
                check.filesystem_used, check.credential_accessed,
                check.adapter_instance_created, check.adapter_method_called,
                check.bind_invoked, check.bind_receipt_created,
                check.trustlog_written, check.external_effect_used,
            )
        )


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_live_adapter_dry_run_request_readiness_packet(packet) == packet


def test_invalid_source_and_timeline_refuse() -> None:
    source = rehearsal_packet().model_dump(mode="json")
    source["reference_rehearsal_hash"] = "0" * 64
    with pytest.raises(LiveAdapterDryRunReadinessError, match="LADR_REFERENCE"):
        build_live_adapter_dry_run_request_readiness_packet(source, EVALUATED_AT)
    with pytest.raises(LiveAdapterDryRunReadinessError, match="LADR_EVALUATED_AT"):
        build_live_adapter_dry_run_request_readiness_packet(
            rehearsal_packet(), EVALUATED_AT.replace(tzinfo=None)
        )
    with pytest.raises(LiveAdapterDryRunReadinessError, match="LADR_EVALUATED_BEFORE"):
        build_live_adapter_dry_run_request_readiness_packet(
            rehearsal_packet(), REHEARSED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing", "extra", "reordered", "name", "check_digest", "live",
        "network", "filesystem", "credential", "effect", "adapter_instance",
        "adapter_method", "bind", "receipt", "trustlog", "source", "intent",
        "descriptor", "planned", "fixture", "result", "local", "future",
        "scope", "hash", "id", "request_completed", "apply_performed",
    ],
)
def test_tampering_is_refused_even_when_rehashed(mutation) -> None:
    raw = _packet().model_dump(mode="json")
    checks = raw["readiness_checks"]
    if mutation == "missing":
        checks.pop()
    elif mutation == "extra":
        checks.append(deepcopy(checks[-1]))
    elif mutation == "reordered":
        checks[0], checks[1] = checks[1], checks[0]
    elif mutation == "name":
        checks[0]["check_name"] = CHECK_NAMES[1]
    elif mutation == "check_digest":
        raw["readiness_check_digest"] = "0" * 64
    elif mutation in {"live", "network", "filesystem", "credential", "effect",
                      "adapter_instance", "adapter_method", "bind", "receipt", "trustlog"}:
        key = {
            "live": "live_observation_used", "credential": "credential_accessed",
            "effect": "external_effect_used", "adapter_instance": "adapter_instance_created",
            "adapter_method": "adapter_method_called", "bind": "bind_invoked",
            "receipt": "bind_receipt_created", "trustlog": "trustlog_written",
        }.get(mutation, f"{mutation}_used")
        checks[0][key] = True
    elif mutation == "source":
        raw["source_reference_rehearsal_packet"]["reference_rehearsal_hash"] = "0" * 64
    elif mutation == "intent":
        raw["execution_intent"]["target_resource"] = "changed"
    elif mutation == "descriptor":
        raw["adapter_contract_descriptor"]["target_system"] = "changed"
    elif mutation == "planned":
        raw["planned_steps"][0]["expected_output_ref"] = "changed"
    elif mutation == "fixture":
        raw["fixture_step_results"][0]["fixture_input_ref"] = "changed"
    elif mutation == "result":
        raw["reference_rehearsal_results"][0]["matched_expected_output_ref"] = "changed"
    elif mutation == "local":
        raw["local_readiness_checks"]["no_network"] = False
    elif mutation == "future":
        raw["future_live_adapter_dry_run_request_packet_requirements"]["apply_still_forbidden"] = False
    elif mutation == "scope":
        raw["scope_limitations"].pop()
    elif mutation == "hash":
        raw["live_adapter_dry_run_readiness_hash"] = "0" * 64
    elif mutation == "id":
        raw["live_adapter_dry_run_readiness_id"] = "ladr:v1:sha256:" + "0" * 64
    elif mutation == "request_completed":
        raw["live_dry_run_request_completed"] = True
    elif mutation == "apply_performed":
        raw["apply_performed"] = True
    if mutation not in {"hash", "id"}:
        _rehash(raw)
    with pytest.raises(LiveAdapterDryRunReadinessError):
        verify_live_adapter_dry_run_request_readiness_packet(raw)


def test_model_validation_bypasses_are_refused() -> None:
    packet = _packet()
    candidates = (
        packet.model_copy(update={"live_adapter_dry_run_readiness_hash": "0" * 64}),
        type(packet).model_construct(**{**packet.model_dump(mode="python"), "fail_closed": True}),
    )
    for candidate in candidates:
        with pytest.raises(LiveAdapterDryRunReadinessError):
            verify_live_adapter_dry_run_request_readiness_packet(candidate)


def test_closed_schema_accepts_valid_and_rejects_invalid_packet() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    store = {}
    for path in Path("schemas").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in document:
            store[document["$id"]] = document
        store[f"https://veritas-os.org/schemas/{path.name}"] = document
        store[f"https://veritas-os.example/schemas/{path.name}"] = document
    validator = Draft202012Validator(
        schema,
        resolver=RefResolver(SCHEMA.resolve().as_uri(), schema, store=store),
    )
    raw = _packet().model_dump(mode="json")
    validator.validate(raw)
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        validator.validate(raw)


def test_static_execution_boundary() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    forbidden = {
        "BindReceipt", "hash_bind_receipt", "append_bind_receipt_trustlog",
        "append_execution_intent_trustlog", "build_execution_intent_trustlog_entry",
        "execute_bind_boundary", "execute_bind_adjudication", "BindAdapterContract",
        "BindBoundaryAdapter", "ReferenceBindAdapter", "WebhookBindAdapter", "requests",
        "httpx", "subprocess", "socket", "uuid4", "now", "apply", "revert",
        "verify_postconditions", "create_bind_receipt", "write_trustlog",
        "append_trustlog", "call_live_adapter", "call_webhook", "request_live_dry_run",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    defined = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert forbidden.isdisjoint(imported | called | defined)
    assert PACKET_DOMAIN != CHECKS_DOMAIN
