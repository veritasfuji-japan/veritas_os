"""Integrity and non-effect tests for Bind pre-dispatch review packet v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_bind_pre_dispatch_review import (
    CHECK_NAMES,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENT_NAMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunBindPreDispatchReviewError,
    _digest,
    _packet_hash,
    build_live_adapter_dry_run_bind_pre_dispatch_review_packet,
    verify_live_adapter_dry_run_bind_pre_dispatch_review_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_operator_dispatch_review import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _packet as operator_packet,
)

RECORDED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
MODULE = Path(
    "veritas_os/policy/live_adapter_dry_run_bind_pre_dispatch_review.py"
)
SCHEMA = Path(
    "schemas/live-adapter-dry-run-bind-pre-dispatch-review-v1.schema.json"
)


def _decision(outcome="ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW", **changes):
    value = {
        "bind_pre_dispatch_review_decision_id": "bind-review:billing:v1",
        "reviewer_id": "reviewer:bob",
        "reviewer_role": "bind-boundary-reviewer",
        "reviewer_attestation": "Reviewed as local evidence, not authority.",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_outcome": outcome,
        "review_reason": "Suitable for a separate future Bind gate review.",
        "acknowledged_not_bind_authorization": True,
        "acknowledged_no_bind_invocation": True,
        "acknowledged_no_bind_receipt": True,
        "acknowledged_no_trustlog_write": True,
        "acknowledged_no_dispatch": True,
        "acknowledged_no_credential_access": True,
        "acknowledged_no_network_call": True,
        "acknowledged_semantic_match_not_authority": True,
    }
    value.update(changes)
    return value


def _packet(*, source=None, decision=None, semantic_match=False):
    source = source or operator_packet(semantic_match=semantic_match)
    return build_live_adapter_dry_run_bind_pre_dispatch_review_packet(
        source, decision or _decision(), RECORDED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_bind_pre_dispatch_review_hash"] = digest
    raw["live_adapter_dry_run_bind_pre_dispatch_review_id"] = (
        f"ladrbpr:v1:sha256:{digest}"
    )


def test_builder_creates_verified_packet_and_reverifies_source(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_bind_pre_dispatch_review as module

    actual = module.verify_live_adapter_dry_run_operator_dispatch_review_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_live_adapter_dry_run_operator_dispatch_review_packet",
        recording,
    )
    packet = module.build_live_adapter_dry_run_bind_pre_dispatch_review_packet(
        operator_packet(), _decision(), RECORDED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(
        packet
    ) == packet
    assert len(calls) == 3
    assert not packet.fail_closed
    assert packet.bind_state == "NOT_BOUND"
    assert not any(getattr(packet, field) for field in (
        "bind_invoked", "bind_receipt_created", "trustlog_written",
        "request_dispatched", "endpoint_resolved", "credential_material_accessed",
        "authorization_header_constructed", "network_used",
        "live_adapter_instantiated", "webhook_called",
    ))


@pytest.mark.parametrize("field", [
    "reviewer_id", "reviewer_role", "reviewer_attestation", "review_reason",
])
def test_required_reviewer_text_and_closed_schema(field) -> None:
    with pytest.raises(LiveAdapterDryRunBindPreDispatchReviewError):
        _packet(decision=_decision(**{field: ""}))
    with pytest.raises(LiveAdapterDryRunBindPreDispatchReviewError):
        _packet(decision=_decision(unexpected=True))


@pytest.mark.parametrize("field", [
    "acknowledged_not_bind_authorization", "acknowledged_no_bind_invocation",
    "acknowledged_no_bind_receipt", "acknowledged_no_trustlog_write",
    "acknowledged_no_dispatch", "acknowledged_no_credential_access",
    "acknowledged_no_network_call",
    "acknowledged_semantic_match_not_authority",
])
def test_every_acknowledgement_is_required(field) -> None:
    with pytest.raises(LiveAdapterDryRunBindPreDispatchReviewError):
        _packet(decision=_decision(**{field: False}))


def test_rejection_is_recorded_fail_closed() -> None:
    packet = _packet(decision=_decision(
        "REJECTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW"
    ))
    assert packet.fail_closed
    assert not (
        packet.bind_pre_dispatch_review_result
        .accepted_for_future_bind_dispatch_gate_review
    )


def test_source_fields_lineage_and_semantics_are_preserved() -> None:
    source = operator_packet(semantic_match=True)
    packet = _packet(source=source)
    raw = source.model_dump(mode="json")
    for field in (
        "request_descriptor", "execution_intent", "execution_intent_id",
        "execution_intent_hash", "adapter_contract_descriptor",
        "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
        "endpoint_candidate", "endpoint_identity_binding", "credential_reference",
        "credential_scope_binding", "operator_review_decision",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity",
        "candidate_identity", "evidence_lineage", "replay_summary",
    ):
        actual = getattr(packet, field)
        if hasattr(actual, "model_dump"):
            actual = actual.model_dump(mode="json")
        assert actual == raw[field]
    assert packet.replay_summary["semantic_match"] is True
    assert not packet.bind_pre_dispatch_review_result.semantic_match_used
    assert not packet.bind_pre_dispatch_review_result.creates_authority_evidence


def test_checks_preconditions_and_requirements_are_exact_and_deterministic() -> None:
    packet = _packet()
    assert tuple(check.name for check in packet.bind_pre_dispatch_review_checks) == (
        CHECK_NAMES
    )
    assert all(
        check.ordinal == ordinal
        and check.passed
        and not any(getattr(check, field) for field in EFFECT_FIELDS)
        for ordinal, check in enumerate(packet.bind_pre_dispatch_review_checks, 1)
    )
    assert tuple(
        requirement.name
        for requirement in packet.future_bind_invocation_requirements
    ) == FUTURE_REQUIREMENT_NAMES
    assert all(
        requirement.separate_future_artifact_required
        and not requirement.satisfied_by_this_packet
        for requirement in packet.future_bind_invocation_requirements
    )
    assert not packet.bind_boundary_preconditions["satisfied_by_this_packet"]
    assert packet.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("field", [
    "source_operator_dispatch_review_packet", "bind_pre_dispatch_review_decision",
    "bind_pre_dispatch_review_result", "bind_boundary_preconditions",
    "bind_pre_dispatch_review_checks", "future_bind_invocation_requirements",
    "fail_closed", "scope_limitations",
])
def test_mutation_is_rejected_even_after_outer_rehash(field) -> None:
    raw = _packet().model_dump(mode="json")
    if field == "source_operator_dispatch_review_packet":
        raw[field]["operator_review_decision"]["reviewer_id"] = "forged"
    elif field == "bind_pre_dispatch_review_decision":
        raw[field]["review_reason"] = "forged"
    elif field == "bind_pre_dispatch_review_result":
        raw[field]["accepted_for_future_bind_dispatch_gate_review"] = False
    elif field == "bind_boundary_preconditions":
        raw[field]["source_verified"] = False
    elif field == "bind_pre_dispatch_review_checks":
        raw[field][0]["evidence_ref"] = "forged"
    elif field == "future_bind_invocation_requirements":
        raw[field][0]["satisfied_by_this_packet"] = True
    elif field == "fail_closed":
        raw[field] = True
    else:
        raw[field].reverse()
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunBindPreDispatchReviewError):
        verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(raw)


@pytest.mark.parametrize("field", [
    "live_adapter_dry_run_bind_pre_dispatch_review_id",
    "live_adapter_dry_run_bind_pre_dispatch_review_hash",
])
def test_forged_content_address_is_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = "forged"
    with pytest.raises(LiveAdapterDryRunBindPreDispatchReviewError):
        verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(raw)


def test_digests_and_content_address_change_with_content() -> None:
    first = _packet()
    second = _packet(decision=_decision(review_reason="Different reason."))
    assert first.live_adapter_dry_run_bind_pre_dispatch_review_hash != (
        second.live_adapter_dry_run_bind_pre_dispatch_review_hash
    )
    for domain, field in (
        ("veritas.live-adapter-dry-run-bind-pre-dispatch-review.checks/v1",
         "bind_pre_dispatch_review_checks"),
        ("veritas.live-adapter-dry-run-bind-pre-dispatch-review.preconditions/v1",
         "bind_boundary_preconditions"),
        ("veritas.live-adapter-dry-run-bind-pre-dispatch-review."
         "future-bind-invocation-requirements/v1",
         "future_bind_invocation_requirements"),
    ):
        value = first.model_dump(mode="json")[field]
        old = _digest(domain, value)
        if isinstance(value, list):
            value[0]["ordinal"] = 2
        else:
            value["source_verified"] = False
        assert old != _digest(domain, value)


def test_schema_accepts_packet_and_rejects_mutations() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    for field, value in (("unexpected", True), ("network_used", True)):
        mutated = deepcopy(raw)
        mutated[field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(mutated)


def test_module_has_no_prohibited_imports_or_effect_calls() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports & {
        "requests", "httpx", "urllib", "socket", "dns", "subprocess", "os",
        "pathlib",
    }
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {
        "open", "apply", "verify_postconditions", "revert", "WebhookBindAdapter",
        "Bind", "BindReceipt", "TrustLog",
    }
    assert "os.environ" not in source
