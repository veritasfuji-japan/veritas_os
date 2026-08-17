"""Security and integrity tests for live-adapter dry-run request packet v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver, ValidationError

from veritas_os.policy.live_adapter_dry_run_request import (
    DISPATCH_PRECONDITIONS_DOMAIN,
    PACKET_DOMAIN,
    PRECONDITION_NAMES,
    LiveAdapterDryRunRequestError,
    _build_expected_dispatch_preconditions,
    _digest,
    _packet_hash,
    build_live_adapter_dry_run_request_packet,
    verify_live_adapter_dry_run_request_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_readiness import (
    EVALUATED_AT,
    _packet as readiness_packet,
)

REQUESTED_AT = EVALUATED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/live_adapter_dry_run_request.py")
SCHEMA = Path("schemas/live-adapter-dry-run-request-v1.schema.json")


def _packet(*, semantic_match: bool = True):
    return build_live_adapter_dry_run_request_packet(
        readiness_packet(semantic_match=semantic_match), REQUESTED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_request_hash"] = digest
    raw["live_adapter_dry_run_request_id"] = f"ladrq:v1:sha256:{digest}"


def test_build_verify_preserves_source_without_dispatch(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_request as module

    actual = module.verify_live_adapter_dry_run_request_readiness_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_live_adapter_dry_run_request_readiness_packet", recording
    )
    source = readiness_packet(semantic_match=False)
    packet = module.build_live_adapter_dry_run_request_packet(source, REQUESTED_AT)
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_request_packet(packet) == packet
    assert len(calls) == 3
    assert packet.live_adapter_dry_run_request_id == (
        f"ladrq:v1:sha256:{packet.live_adapter_dry_run_request_hash}"
    )
    assert packet.live_adapter_dry_run_request_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    assert packet.source_live_adapter_dry_run_readiness_packet == source.model_dump(
        mode="json"
    )
    for field in (
        "adapter_contract_descriptor",
        "planned_steps",
        "fixture_step_results",
        "reference_rehearsal_results",
        "readiness_checks",
        "source_to_execution_intent_mapping",
        "field_mapping_proof",
        "required_field_presence",
        "source_decision_identity",
        "candidate_identity",
        "evidence_lineage",
        "replay_summary",
    ):
        assert (
            packet.model_dump(mode="json")[field]
            == source.model_dump(mode="json")[field]
        )
    assert packet.replay_summary["semantic_match"] is False
    assert packet.request_dispatch_state == "NOT_DISPATCHED"
    assert packet.request_descriptor.dispatch_mode == "not_dispatched"
    assert packet.request_descriptor.credential_material_included is False
    assert packet.request_descriptor.endpoint_material_included is False
    assert [item.precondition_name for item in packet.dispatch_preconditions] == list(
        PRECONDITION_NAMES
    )
    assert packet.dispatch_precondition_digest == _digest(
        DISPATCH_PRECONDITIONS_DOMAIN,
        [item.model_dump(mode="json") for item in packet.dispatch_preconditions],
    )
    for item in packet.dispatch_preconditions:
        assert not any(
            (
                item.live_observation_used,
                item.network_used,
                item.filesystem_used,
                item.credential_accessed,
                item.adapter_instance_created,
                item.adapter_method_called,
                item.request_dispatched,
                item.webhook_called,
                item.bind_invoked,
                item.bind_receipt_created,
                item.trustlog_written,
                item.external_effect_used,
            )
        )


def test_expected_dispatch_preconditions_are_canonical_and_deterministic() -> None:
    """The shared helper returns the exact canonical JSON representation."""
    source = readiness_packet()
    packet = _packet()
    descriptor = packet.request_descriptor.model_dump(mode="json")
    first = _build_expected_dispatch_preconditions(source, descriptor)
    second = _build_expected_dispatch_preconditions(source, descriptor)

    assert first == second
    assert first == packet.model_dump(mode="json")["dispatch_preconditions"]
    assert [item["precondition_name"] for item in first] == list(PRECONDITION_NAMES)
    assert all(
        isinstance(item["precondition_scope_limitations"], list) for item in first
    )


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_live_adapter_dry_run_request_packet(packet) == packet


def test_invalid_source_and_timeline_refuse() -> None:
    source = readiness_packet().model_dump(mode="json")
    source["live_adapter_dry_run_readiness_hash"] = "0" * 64
    with pytest.raises(LiveAdapterDryRunRequestError, match="LADRQ_READINESS"):
        build_live_adapter_dry_run_request_packet(source, REQUESTED_AT)
    with pytest.raises(LiveAdapterDryRunRequestError, match="LADRQ_REQUESTED_AT"):
        build_live_adapter_dry_run_request_packet(
            readiness_packet(), REQUESTED_AT.replace(tzinfo=None)
        )
    with pytest.raises(LiveAdapterDryRunRequestError, match="LADRQ_REQUESTED_BEFORE"):
        build_live_adapter_dry_run_request_packet(
            readiness_packet(), EVALUATED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "reordered",
        "name",
        "digest",
        "live",
        "network",
        "filesystem",
        "credential",
        "effect",
        "adapter_instance",
        "adapter_method",
        "dispatch",
        "webhook",
        "bind",
        "receipt",
        "trustlog",
        "source",
        "intent",
        "descriptor",
        "adapter",
        "planned",
        "fixture",
        "rehearsal",
        "readiness",
        "construction",
        "future",
        "scope",
        "hash",
        "id",
        "apply_performed",
    ],
)
def test_tampering_is_refused_even_when_rehashed(mutation) -> None:
    raw = _packet().model_dump(mode="json")
    items = raw["dispatch_preconditions"]
    if mutation == "missing":
        items.pop()
    elif mutation == "extra":
        items.append(deepcopy(items[-1]))
    elif mutation == "reordered":
        items[0], items[1] = items[1], items[0]
    elif mutation == "name":
        items[0]["precondition_name"] = PRECONDITION_NAMES[1]
    elif mutation == "digest":
        raw["dispatch_precondition_digest"] = "0" * 64
    elif mutation in {
        "live",
        "network",
        "filesystem",
        "credential",
        "effect",
        "adapter_instance",
        "adapter_method",
        "dispatch",
        "webhook",
        "bind",
        "receipt",
        "trustlog",
    }:
        key = {
            "live": "live_observation_used",
            "credential": "credential_accessed",
            "effect": "external_effect_used",
            "adapter_instance": "adapter_instance_created",
            "adapter_method": "adapter_method_called",
            "dispatch": "request_dispatched",
            "webhook": "webhook_called",
            "bind": "bind_invoked",
            "receipt": "bind_receipt_created",
            "trustlog": "trustlog_written",
        }.get(mutation, f"{mutation}_used")
        items[0][key] = True
    elif mutation == "source":
        raw["source_live_adapter_dry_run_readiness_packet"][
            "live_adapter_dry_run_readiness_hash"
        ] = "0" * 64
    elif mutation == "intent":
        raw["execution_intent"]["target_resource"] = "changed"
    elif mutation == "descriptor":
        raw["request_descriptor"]["target_system"] = "changed"
    elif mutation == "adapter":
        raw["adapter_contract_descriptor"]["target_system"] = "changed"
    elif mutation == "planned":
        raw["planned_steps"][0]["expected_output_ref"] = "changed"
    elif mutation == "fixture":
        raw["fixture_step_results"][0]["fixture_input_ref"] = "changed"
    elif mutation == "rehearsal":
        raw["reference_rehearsal_results"][0]["matched_expected_output_ref"] = "changed"
    elif mutation == "readiness":
        raw["readiness_checks"][0]["evidence_ref"] = "changed"
    elif mutation == "construction":
        raw["request_construction_checks"]["no_network"] = False
    elif mutation == "future":
        raw["future_live_adapter_dry_run_dispatch_requirements"][
            "apply_still_forbidden"
        ] = False
    elif mutation == "scope":
        raw["scope_limitations"].pop()
    elif mutation == "hash":
        raw["live_adapter_dry_run_request_hash"] = "0" * 64
    elif mutation == "id":
        raw["live_adapter_dry_run_request_id"] = "ladrq:v1:sha256:" + "0" * 64
    elif mutation == "apply_performed":
        raw["apply_performed"] = True
    if mutation not in {"hash", "id"}:
        _rehash(raw)
    with pytest.raises(LiveAdapterDryRunRequestError):
        verify_live_adapter_dry_run_request_packet(raw)


def test_model_validation_bypasses_are_refused() -> None:
    packet = _packet()
    candidates = (
        packet.model_copy(update={"live_adapter_dry_run_request_hash": "0" * 64}),
        type(packet).model_construct(
            **{**packet.model_dump(mode="python"), "fail_closed": True}
        ),
    )
    for candidate in candidates:
        with pytest.raises(LiveAdapterDryRunRequestError):
            verify_live_adapter_dry_run_request_packet(candidate)


def test_closed_schema_accepts_valid_and_rejects_invalid_packet() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    store = {}
    for path in Path("schemas").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in document:
            store[document["$id"]] = document
        store[f"https://veritas-os.org/schemas/{path.name}"] = document
    validator = Draft202012Validator(
        schema, resolver=RefResolver(SCHEMA.resolve().as_uri(), schema, store=store)
    )
    raw = _packet().model_dump(mode="json")
    validator.validate(raw)
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        validator.validate(raw)


def test_static_execution_boundary() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
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
        "requests",
        "httpx",
        "subprocess",
        "socket",
        "uuid4",
        "now",
        "apply",
        "revert",
        "verify_postconditions",
        "create_bind_receipt",
        "write_trustlog",
        "append_trustlog",
        "call_live_adapter",
        "call_webhook",
        "dispatch_request",
        "send_request",
        "perform_http",
        "request_live_dry_run",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert forbidden.isdisjoint(imported | called | defined)
    assert PACKET_DOMAIN != DISPATCH_PRECONDITIONS_DOMAIN
