"""Integrity and non-effect tests for dispatch-readiness packet v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_dispatch_readiness import (
    CHECK_NAMES,
    CHECKS_DOMAIN,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENT_NAMES,
    FUTURE_REQUIREMENTS_DOMAIN,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunDispatchReadinessError,
    _digest,
    _packet_hash,
    build_live_adapter_dry_run_dispatch_readiness_packet,
    verify_live_adapter_dry_run_dispatch_readiness_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_request import (
    REQUESTED_AT,
    _packet as request_packet,
)

EVALUATED_AT = REQUESTED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/live_adapter_dry_run_dispatch_readiness.py")
SCHEMA = Path("schemas/live-adapter-dry-run-dispatch-readiness-v1.schema.json")


def _packet(*, semantic_match: bool = True):
    return build_live_adapter_dry_run_dispatch_readiness_packet(
        request_packet(semantic_match=semantic_match), EVALUATED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_dispatch_readiness_hash"] = digest
    raw["live_adapter_dry_run_dispatch_readiness_id"] = f"ladrdr:v1:sha256:{digest}"


def test_builder_and_verifier_reverify_and_preserve_source(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_dispatch_readiness as module

    actual = module.verify_live_adapter_dry_run_request_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(module, "verify_live_adapter_dry_run_request_packet", recording)
    source = request_packet(semantic_match=False)
    packet = module.build_live_adapter_dry_run_dispatch_readiness_packet(
        source, EVALUATED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_dispatch_readiness_packet(packet) == packet
    assert len(calls) == 3
    raw = packet.model_dump(mode="json")
    source_raw = source.model_dump(mode="json")
    assert packet.live_adapter_dry_run_dispatch_readiness_hash == _packet_hash(raw)
    assert packet.live_adapter_dry_run_dispatch_readiness_id.endswith(
        packet.live_adapter_dry_run_dispatch_readiness_hash
    )
    assert packet.source_live_adapter_dry_run_request_packet == source_raw
    for field in (
        "request_descriptor", "dispatch_preconditions", "execution_intent",
        "execution_intent_id", "execution_intent_hash",
        "adapter_contract_descriptor", "adapter_contract_id",
        "adapter_contract_hash", "adapter_contract_version",
        "source_live_adapter_dry_run_readiness_hash",
        "source_reference_rehearsal_hash",
        "source_adapter_dry_run_fixture_result_hash",
        "source_adapter_dry_run_plan_hash",
        "source_adapter_contract_selection_hash",
        "source_bind_preflight_adjudication_hash", "source_formation_hash",
        "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
        "trusted_validation_context_hash", "validation_result_hash",
        "mapping_value_digest", "execution_intent_contract_version",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        assert raw[field] == source_raw[field]


def test_checks_and_future_requirements_are_exact_ordered_and_non_effecting() -> None:
    packet = _packet()
    checks = packet.model_dump(mode="json")["dispatch_readiness_checks"]
    requirements = packet.model_dump(mode="json")["future_dispatch_requirements"]
    assert [check["name"] for check in checks] == list(CHECK_NAMES)
    assert [check["ordinal"] for check in checks] == list(range(1, 22))
    assert all(check[field] is False for check in checks for field in EFFECT_FIELDS)
    assert packet.dispatch_readiness_check_digest == _digest(CHECKS_DOMAIN, checks)
    assert [requirement["name"] for requirement in requirements] == list(
        FUTURE_REQUIREMENT_NAMES
    )
    assert all(not item["satisfied_by_this_packet"] for item in requirements)
    assert packet.future_dispatch_requirement_digest == _digest(
        FUTURE_REQUIREMENTS_DOMAIN, requirements
    )
    assert packet.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_without_authority(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    serialized = json.dumps(packet.model_dump(mode="json"))
    assert "Authority Evidence" not in serialized
    assert verify_live_adapter_dry_run_dispatch_readiness_packet(packet) == packet


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("live_adapter_dry_run_dispatch_readiness_hash", "0" * 64),
        ("live_adapter_dry_run_dispatch_readiness_id", "ladrdr:v1:sha256:" + "0" * 64),
        ("fail_closed", True),
        ("ready_for_endpoint_allowlist_evaluation", False),
        ("scope_limitations", ["NOT_DISPATCHED"]),
        ("request_descriptor", {}),
        ("dispatch_preconditions", []),
        ("execution_intent", {}),
        ("source_live_adapter_dry_run_request_hash", "0" * 64),
    ],
)
def test_top_level_tampering_is_rejected_even_if_rehashed(field, value) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    if "hash" not in field and "id" not in field:
        _rehash(raw)
    with pytest.raises(LiveAdapterDryRunDispatchReadinessError):
        verify_live_adapter_dry_run_dispatch_readiness_packet(raw)


@pytest.mark.parametrize("target", ["check", "requirement"])
def test_ordered_collection_mutation_and_digest_change_are_rejected(target) -> None:
    raw = _packet().model_dump(mode="json")
    if target == "check":
        items = raw["dispatch_readiness_checks"]
        domain = CHECKS_DOMAIN
        digest_field = "dispatch_readiness_check_digest"
    else:
        items = raw["future_dispatch_requirements"]
        domain = FUTURE_REQUIREMENTS_DOMAIN
        digest_field = "future_dispatch_requirement_digest"
    old_digest = raw[digest_field]
    items.reverse()
    assert _digest(domain, items) != old_digest
    raw[digest_field] = _digest(domain, items)
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunDispatchReadinessError):
        verify_live_adapter_dry_run_dispatch_readiness_packet(raw)


def test_extra_missing_and_invalid_source_are_rejected() -> None:
    raw = _packet().model_dump(mode="json")
    extra = deepcopy(raw)
    extra["unexpected"] = True
    missing = deepcopy(raw)
    missing.pop("execution_intent_hash")
    source = deepcopy(raw)
    source["source_live_adapter_dry_run_request_packet"][
        "live_adapter_dry_run_request_hash"
    ] = "0" * 64
    for candidate in (extra, missing, source):
        with pytest.raises(LiveAdapterDryRunDispatchReadinessError):
            verify_live_adapter_dry_run_dispatch_readiness_packet(candidate)


def test_source_dispatch_state_status_and_time_fail_closed(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_dispatch_readiness as module

    source = request_packet().model_copy(update={"request_dispatch_state": "DISPATCHED"})
    monkeypatch.setattr(module, "verify_live_adapter_dry_run_request_packet", lambda _: source)
    with pytest.raises(LiveAdapterDryRunDispatchReadinessError, match="DISPATCHED"):
        module.build_live_adapter_dry_run_dispatch_readiness_packet(source, EVALUATED_AT)
    source = request_packet().model_copy(
        update={"live_adapter_dry_run_request_status": "INVALID"}
    )
    monkeypatch.setattr(module, "verify_live_adapter_dry_run_request_packet", lambda _: source)
    with pytest.raises(LiveAdapterDryRunDispatchReadinessError, match="STATUS"):
        module.build_live_adapter_dry_run_dispatch_readiness_packet(source, EVALUATED_AT)
    monkeypatch.undo()
    with pytest.raises(LiveAdapterDryRunDispatchReadinessError, match="BEFORE"):
        module.build_live_adapter_dry_run_dispatch_readiness_packet(
            request_packet(), REQUESTED_AT - timedelta(seconds=1)
        )


def test_module_has_no_prohibited_capabilities() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    source = MODULE.read_text(encoding="utf-8")
    assert not imports & {"requests", "httpx", "urllib", "socket", "subprocess", "os", "pathlib"}
    for forbidden in (
        "WebhookBindAdapter", "BindReceipt", "TrustLog", "credential_store",
        "provider_client", "os.environ", "open(", ".read_text(", ".write_text(",
        "apply(", "verify_postconditions(", "revert(",
    ):
        assert forbidden not in source


def test_schema_accepts_packet_and_rejects_mutations() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    raw = _packet().model_dump(mode="json")
    validator.validate(raw)
    mutated = deepcopy(raw)
    mutated["dispatch_readiness_checks"][0]["network_used"] = True
    with pytest.raises(ValidationError):
        validator.validate(mutated)
    mutated = deepcopy(raw)
    mutated["unexpected"] = True
    with pytest.raises(ValidationError):
        validator.validate(mutated)
