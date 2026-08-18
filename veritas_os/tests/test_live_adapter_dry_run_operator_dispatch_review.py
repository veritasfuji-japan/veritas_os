"""Integrity and non-effect tests for operator dispatch review v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_operator_dispatch_review import (
    CHECK_NAMES,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENT_NAMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunOperatorDispatchReviewError,
    _digest,
    _packet_hash,
    build_live_adapter_dry_run_operator_dispatch_review_packet,
    verify_live_adapter_dry_run_operator_dispatch_review_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_credential_authorization import (
    EVALUATED_AT,
    _packet as credential_packet,
)

RECORDED_AT = EVALUATED_AT + timedelta(seconds=1)
MODULE = Path(
    "veritas_os/policy/live_adapter_dry_run_operator_dispatch_review.py"
)
SCHEMA = Path(
    "schemas/live-adapter-dry-run-operator-dispatch-review-v1.schema.json"
)


def _decision(source=None, review_decision="APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW",
              **changes):
    source = source or credential_packet()
    value = {
        "operator_review_id": "operator-review:billing:v1",
        "reviewer_id": "reviewer:alice",
        "reviewer_role": "dispatch-reviewer",
        "reviewer_organization": "veritas-local",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_decision": review_decision,
        "review_reason": "Evidence reviewed; advance only to separate Bind review.",
        "reviewed_endpoint_candidate_id": (
            source.endpoint_candidate["endpoint_candidate_id"]
        ),
        "reviewed_credential_reference_id": (
            source.credential_reference.credential_reference_id
        ),
        "reviewed_adapter_contract_id": source.adapter_contract_id,
        "reviewed_target_system": source.credential_reference.target_system,
        "reviewed_target_resource_scope": (
            source.credential_reference.target_resource_scope
        ),
        "acknowledged_scope_limitations": True,
        "acknowledged_non_effect_guarantees": True,
        "acknowledged_future_bind_pre_dispatch_review_required": True,
        "acknowledged_no_dispatch": True,
        "acknowledged_no_credential_access": True,
        "acknowledged_no_network": True,
        "acknowledged_no_bind": True,
        "acknowledged_no_bind_receipt": True,
        "acknowledged_no_trustlog_write": True,
    }
    value.update(changes)
    return value


def _packet(*, source=None, decision=None, semantic_match=False):
    source = source or credential_packet(semantic_match=semantic_match)
    return build_live_adapter_dry_run_operator_dispatch_review_packet(
        source, decision or _decision(source), RECORDED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_operator_dispatch_review_hash"] = digest
    raw["live_adapter_dry_run_operator_dispatch_review_id"] = (
        f"ladror:v1:sha256:{digest}"
    )


def test_builder_creates_verified_approved_packet_and_reverifies_source(
    monkeypatch,
) -> None:
    import veritas_os.policy.live_adapter_dry_run_operator_dispatch_review as module

    actual = module.verify_live_adapter_dry_run_credential_authorization_evaluation_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module,
        "verify_live_adapter_dry_run_credential_authorization_evaluation_packet",
        recording,
    )
    packet = module.build_live_adapter_dry_run_operator_dispatch_review_packet(
        credential_packet(), _decision(), RECORDED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_operator_dispatch_review_packet(
        packet
    ) == packet
    assert len(calls) == 3
    assert not packet.fail_closed
    assert packet.request_dispatch_state == "NOT_DISPATCHED"
    assert not any(getattr(packet, field) for field in (
        "credential_resolved", "credential_material_accessed",
        "credential_material_embedded", "authorization_header_constructed",
        "token_embedded", "secret_embedded", "endpoint_resolved",
        "network_used", "live_adapter_instantiated", "webhook_called",
        "bind_invoked", "bind_receipt_created", "trustlog_written",
        "request_dispatched",
    ))


@pytest.mark.parametrize("decision", ["REJECT", "HOLD_FOR_MORE_EVIDENCE"])
def test_non_approval_decisions_remain_fail_closed(decision) -> None:
    assert _packet(decision=_decision(review_decision=decision)).fail_closed


@pytest.mark.parametrize("field", [
    "reviewer_id", "reviewer_role", "reviewer_organization", "review_reason",
])
def test_required_operator_text_must_be_present(field) -> None:
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        _packet(decision=_decision(**{field: ""}))


def test_decision_is_closed_and_allowed() -> None:
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        _packet(decision=_decision(unexpected=True))
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        _packet(decision=_decision(review_decision="EXECUTE"))


@pytest.mark.parametrize("field", [
    "reviewed_endpoint_candidate_id", "reviewed_credential_reference_id",
    "reviewed_adapter_contract_id", "reviewed_target_system",
    "reviewed_target_resource_scope",
])
def test_reviewed_source_identities_must_match_exactly(field) -> None:
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        _packet(decision=_decision(**{field: "forged"}))


@pytest.mark.parametrize("field", [
    "acknowledged_scope_limitations",
    "acknowledged_non_effect_guarantees",
    "acknowledged_future_bind_pre_dispatch_review_required",
    "acknowledged_no_dispatch", "acknowledged_no_credential_access",
    "acknowledged_no_network", "acknowledged_no_bind",
    "acknowledged_no_bind_receipt", "acknowledged_no_trustlog_write",
])
def test_all_acknowledgements_are_mandatory(field) -> None:
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        _packet(decision=_decision(**{field: False}))


def test_source_fields_and_lineage_are_preserved_exactly() -> None:
    source = credential_packet()
    packet = _packet(source=source)
    raw = source.model_dump(mode="json")
    for field in (
        "request_descriptor", "execution_intent", "adapter_contract_descriptor",
        "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
        "endpoint_candidate", "endpoint_identity_binding", "credential_reference",
        "credential_scope_binding", "source_to_execution_intent_mapping",
        "field_mapping_proof", "required_field_presence",
        "source_decision_identity", "candidate_identity", "evidence_lineage",
        "replay_summary",
    ):
        actual = getattr(packet, field)
        if hasattr(actual, "model_dump"):
            actual = actual.model_dump(mode="json")
        assert actual == raw[field]
    assert packet.source_endpoint_allowlist_evaluation_hash == (
        source.source_endpoint_allowlist_evaluation_hash
    )
    assert packet.source_dispatch_readiness_hash == source.source_dispatch_readiness_hash
    assert packet.source_live_adapter_dry_run_request_hash == (
        source.source_live_adapter_dry_run_request_hash
    )


def test_checks_and_future_requirements_are_exact_ordered_non_effect_evidence() -> None:
    packet = _packet()
    assert tuple(check.name for check in packet.operator_dispatch_review_checks) == (
        CHECK_NAMES
    )
    for ordinal, check in enumerate(packet.operator_dispatch_review_checks, 1):
        assert check.ordinal == ordinal and check.passed
        assert not any(getattr(check, field) for field in EFFECT_FIELDS)
    assert tuple(
        item.name for item in packet.future_bind_pre_dispatch_review_requirements
    ) == FUTURE_REQUIREMENT_NAMES
    assert all(
        item.separate_future_artifact_required
        and not item.satisfied_by_this_packet
        for item in packet.future_bind_pre_dispatch_review_requirements
    )
    assert packet.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("field", [
    "operator_dispatch_review_checks",
    "future_bind_pre_dispatch_review_requirements",
    "scope_limitations", "operator_review_decision", "fail_closed",
])
def test_mutations_are_rejected_even_if_outer_packet_is_rehashed(field) -> None:
    raw = _packet().model_dump(mode="json")
    if field == "operator_dispatch_review_checks":
        raw[field][0]["evidence_ref"] = "forged"
    elif field == "future_bind_pre_dispatch_review_requirements":
        raw[field][0]["satisfied_by_this_packet"] = True
    elif field == "scope_limitations":
        raw[field].reverse()
    elif field == "operator_review_decision":
        raw[field]["reviewer_id"] = "forged"
    else:
        raw[field] = True
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        verify_live_adapter_dry_run_operator_dispatch_review_packet(raw)


@pytest.mark.parametrize("field", [
    "live_adapter_dry_run_operator_dispatch_review_id",
    "live_adapter_dry_run_operator_dispatch_review_hash",
])
def test_forged_content_address_is_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = "forged"
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        verify_live_adapter_dry_run_operator_dispatch_review_packet(raw)


def test_digest_and_content_address_change_with_content() -> None:
    first = _packet()
    second = _packet(decision=_decision(review_reason="Different local reason."))
    assert first.operator_review_decision_digest != second.operator_review_decision_digest
    assert first.live_adapter_dry_run_operator_dispatch_review_hash != (
        second.live_adapter_dry_run_operator_dispatch_review_hash
    )
    checks = first.model_dump(mode="json")["operator_dispatch_review_checks"]
    old_digest = _digest(
        "veritas.live-adapter-dry-run-operator-dispatch-review.checks/v1", checks
    )
    checks[0]["evidence_ref"] = "changed"
    assert old_digest != _digest(
        "veritas.live-adapter-dry-run-operator-dispatch-review.checks/v1", checks
    )


@pytest.mark.parametrize("semantic_match", [True, False])
def test_semantic_match_is_preserved_without_authority(semantic_match) -> None:
    packet = _packet(semantic_match=semantic_match)
    assert packet.replay_summary["semantic_match"] is semantic_match
    serialized = json.dumps(packet.model_dump(mode="json"))
    assert "authority_evidence_recheck" in serialized
    assert all(
        not requirement.satisfied_by_this_packet
        for requirement in packet.future_bind_pre_dispatch_review_requirements
    )


def test_source_mutation_is_rejected_by_reverification() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_credential_authorization_evaluation_packet"][
        "credential_authorization_result"
    ]["authorized"] = False
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunOperatorDispatchReviewError):
        verify_live_adapter_dry_run_operator_dispatch_review_packet(raw)


def test_schema_accepts_packet_and_rejects_mutations() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    extra = deepcopy(raw)
    extra["unexpected"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(extra)
    effect = deepcopy(raw)
    effect["network_used"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(effect)


def test_module_has_no_prohibited_imports_or_effect_calls() -> None:
    tree = ast.parse(MODULE.read_text())
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
    source = MODULE.read_text()
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {
        "open", "apply", "verify_postconditions", "revert",
        "WebhookBindAdapter", "Bind", "BindReceipt", "TrustLog",
    }
    assert "os.environ" not in source
