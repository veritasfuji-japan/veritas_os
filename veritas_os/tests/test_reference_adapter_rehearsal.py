"""Security tests for reference adapter in-memory rehearsal v1."""

from __future__ import annotations

import ast
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from veritas_os.policy.reference_adapter_rehearsal import (
    OUTPUT_DOMAIN,
    PACKET_DOMAIN,
    PLANNED_METHODS,
    RESULTS_DOMAIN,
    ReferenceAdapterRehearsalError,
    _digest,
    _packet_hash,
    build_reference_adapter_in_memory_rehearsal_packet,
    verify_reference_adapter_in_memory_rehearsal_packet,
)
from veritas_os.tests.test_adapter_dry_run_fixture_result import (
    RESULTED_AT,
    _packet as fixture_packet,
)

REHEARSED_AT = RESULTED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/reference_adapter_rehearsal.py")


def _packet(*, semantic_match: bool = True):
    return build_reference_adapter_in_memory_rehearsal_packet(
        fixture_packet(semantic_match=semantic_match),
        {"scenario": "deterministic-reference-v1"},
        REHEARSED_AT,
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["reference_rehearsal_hash"] = digest
    raw["reference_rehearsal_id"] = f"rar:v1:sha256:{digest}"


def test_build_verify_preserves_source_and_records_no_effects(monkeypatch) -> None:
    import veritas_os.policy.reference_adapter_rehearsal as module

    actual = module.verify_adapter_dry_run_fixture_result_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_adapter_dry_run_fixture_result_packet", recording
    )
    source = fixture_packet(semantic_match=False)
    packet = module.build_reference_adapter_in_memory_rehearsal_packet(
        source, {"scenario": "deterministic-reference-v1"}, REHEARSED_AT
    )
    assert len(calls) == 2  # builder source verification and final verifier
    assert module.verify_reference_adapter_in_memory_rehearsal_packet(packet) == packet
    assert len(calls) == 3
    assert packet.reference_rehearsal_id == (
        f"rar:v1:sha256:{packet.reference_rehearsal_hash}"
    )
    assert packet.reference_rehearsal_hash == _packet_hash(
        packet.model_dump(mode="json")
    )
    assert packet.source_adapter_dry_run_fixture_result_packet == source.model_dump(
        mode="json"
    )
    for field in (
        "adapter_contract_descriptor",
        "execution_intent",
        "planned_steps",
        "fixture_step_results",
        "source_decision_identity",
        "candidate_identity",
        "evidence_lineage",
        "replay_summary",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert packet.replay_summary["semantic_match"] is False
    results = list(packet.reference_rehearsal_results)
    assert [item.planned_adapter_method for item in results] == list(PLANNED_METHODS)
    assert set(PLANNED_METHODS).isdisjoint({"apply", "verify_postconditions", "revert"})
    for result in results:
        assert result.reference_adapter_instance_created is True
        assert result.reference_adapter_method_called is True
        assert result.live_adapter_instance_created is False
        assert result.live_adapter_method_called is False
        assert not any(
            (
                result.network_used,
                result.filesystem_used,
                result.external_effect_used,
                result.bind_invoked,
                result.bind_receipt_created,
                result.trustlog_written,
            )
        )
        assert result.output_digest == _digest(OUTPUT_DOMAIN, result.output_summary)
    raw_results = [item.model_dump(mode="json") for item in results]
    assert packet.reference_rehearsal_result_digest == _digest(
        RESULTS_DOMAIN, raw_results
    )


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert verify_reference_adapter_in_memory_rehearsal_packet(packet) == packet


def test_invalid_source_and_timeline_refuse() -> None:
    source = fixture_packet().model_dump(mode="json")
    source["adapter_dry_run_result_hash"] = "0" * 64
    with pytest.raises(
        ReferenceAdapterRehearsalError, match="RAR_FIXTURE_RESULT_INVALID"
    ):
        build_reference_adapter_in_memory_rehearsal_packet(source, {}, REHEARSED_AT)
    with pytest.raises(
        ReferenceAdapterRehearsalError, match="RAR_REHEARSED_AT_INVALID"
    ):
        build_reference_adapter_in_memory_rehearsal_packet(
            fixture_packet(), {}, REHEARSED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        ReferenceAdapterRehearsalError,
        match="RAR_REHEARSED_BEFORE_FIXTURE_RESULT",
    ):
        build_reference_adapter_in_memory_rehearsal_packet(
            fixture_packet(), {}, RESULTED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "reordered",
        "method",
        "output",
        "live_instance",
        "live_call",
        "network",
        "filesystem",
        "effect",
        "bind",
        "receipt",
        "trustlog",
        "planned",
        "fixture",
        "checks",
        "future",
        "scope",
        "hash",
        "id",
    ],
)
def test_tampering_is_refused_even_when_rehashed(mutation) -> None:
    raw = _packet().model_dump(mode="json")
    results = raw["reference_rehearsal_results"]
    if mutation == "missing":
        results.pop()
    elif mutation == "extra":
        results.append(deepcopy(results[-1]))
    elif mutation == "reordered":
        results[0], results[1] = results[1], results[0]
    elif mutation == "method":
        results[0]["planned_adapter_method"] = "snapshot"
    elif mutation == "output":
        results[0]["output_summary"]["ordinal"] = 99
    elif mutation == "live_instance":
        results[0]["live_adapter_instance_created"] = True
    elif mutation == "live_call":
        results[0]["live_adapter_method_called"] = True
    elif mutation in {"network", "filesystem", "effect", "bind", "receipt", "trustlog"}:
        key = {
            "effect": "external_effect_used",
            "bind": "bind_invoked",
            "receipt": "bind_receipt_created",
            "trustlog": "trustlog_written",
        }.get(mutation, f"{mutation}_used")
        results[0][key] = True
    elif mutation == "planned":
        raw["planned_steps"][0]["expected_output_ref"] = "changed"
    elif mutation == "fixture":
        raw["fixture_step_results"][0]["fixture_input_ref"] = "changed"
    elif mutation == "checks":
        raw["local_rehearsal_checks"]["no_network"] = False
    elif mutation == "future":
        raw["future_live_adapter_dry_run_requirements"][
            "live_adapter_instance_required"
        ] = False
    elif mutation == "scope":
        raw["scope_limitations"].pop()
    elif mutation == "hash":
        raw["reference_rehearsal_hash"] = "0" * 64
    elif mutation == "id":
        raw["reference_rehearsal_id"] = "rar:v1:sha256:" + "0" * 64
    if mutation not in {"hash", "id"}:
        _rehash(raw)
    with pytest.raises(ReferenceAdapterRehearsalError):
        verify_reference_adapter_in_memory_rehearsal_packet(raw)


def test_model_validation_bypasses_are_refused() -> None:
    packet = _packet()
    copied = packet.model_copy(update={"reference_rehearsal_hash": "0" * 64})
    constructed = type(packet).model_construct(
        **{**packet.model_dump(mode="python"), "fail_closed": True}
    )
    for candidate in (copied, constructed):
        with pytest.raises(ReferenceAdapterRehearsalError):
            verify_reference_adapter_in_memory_rehearsal_packet(candidate)


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
        "WebhookBindAdapter",
        "requests",
        "httpx",
        "subprocess",
        "uuid4",
        "now",
        "apply",
        "revert",
        "verify_postconditions",
        "create_bind_receipt",
        "write_trustlog",
        "append_trustlog",
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
    assert PACKET_DOMAIN != RESULTS_DOMAIN
