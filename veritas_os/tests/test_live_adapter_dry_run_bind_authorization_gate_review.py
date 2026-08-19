"""Integrity and non-effect tests for Bind Authorization Gate Review v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_REQUIREMENTS,
    CHECK_NAMES,
    INVOCATION_REQUIREMENTS,
    OUTCOMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunBindAuthorizationGateReviewError,
    _packet_hash,
    build_live_adapter_dry_run_bind_authorization_gate_review_packet,
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_final_bind_authorization_readiness import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _packet as source_packet,
)

RECORDED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
MODULE = Path(
    "veritas_os/policy/live_adapter_dry_run_bind_authorization_gate_review.py"
)
SCHEMA = Path(
    "schemas/live-adapter-dry-run-bind-authorization-gate-review-v1.schema.json"
)


def _decision(*, passed=True, **changes):
    value = {
        "bind_authorization_gate_review_decision_id": "gate-review:billing:v1",
        "reviewer_id": "operator:alice",
        "reviewer_role": "bind-gate-reviewer",
        "reviewer_attestation": "I reviewed local gate evidence only.",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_outcome": OUTCOMES[0] if passed else OUTCOMES[1],
        "review_reason": "deterministic local gate review",
        **{field: True for field in ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _packet(*, source=None, decision=None, semantic_match=False):
    source = source or source_packet(semantic_match=semantic_match)
    return build_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source, decision or _decision(), RECORDED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_bind_authorization_gate_review_hash"] = digest
    raw["live_adapter_dry_run_bind_authorization_gate_review_id"] = (
        f"ladbagr:v1:sha256:{digest}"
    )


def test_builder_creates_valid_verified_packet_and_reverifies_source(monkeypatch):
    import veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review as module

    actual = (
        module.verify_live_adapter_dry_run_final_bind_authorization_readiness_packet
    )
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module,
        "verify_live_adapter_dry_run_final_bind_authorization_readiness_packet",
        recording,
    )
    packet = module.build_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source_packet(), _decision(), RECORDED_AT
    )
    assert len(calls) == 2
    assert (
        module.verify_live_adapter_dry_run_bind_authorization_gate_review_packet(packet)
        == packet
    )
    assert len(calls) == 3
    assert not packet.fail_closed
    assert packet.gate_review_state == OUTCOMES[0]


def test_failed_review_is_valid_fail_closed_evidence():
    packet = _packet(decision=_decision(passed=False))
    assert packet.fail_closed
    assert packet.gate_review_state == OUTCOMES[1]
    assert not packet.bind_authorization_gate_review_result.gate_review_passed


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_every_acknowledgement_is_required(field):
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: False}))


@pytest.mark.parametrize(
    "field",
    [
        "reviewer_id",
        "reviewer_role",
        "reviewer_attestation",
        "bind_authorization_gate_review_decision_id",
        "review_reason",
    ],
)
def test_review_identity_and_attestation_are_required(field):
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(**{field: ""}))


def test_decision_schema_is_closed():
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        _packet(decision=_decision(unexpected=True))


@pytest.mark.parametrize(
    "field",
    [
        "request_descriptor",
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        "endpoint_identity_binding",
        "endpoint_identity_binding_digest",
        "credential_scope_binding",
        "credential_scope_binding_digest",
        "authority_evidence_linkage_result",
        "human_approval_linkage_result",
        "final_bind_authorization_readiness_result",
        "source_human_approval_linkage_review_hash",
        "source_authority_evidence_linkage_review_hash",
        "source_bind_pre_dispatch_review_hash",
        "source_operator_dispatch_review_hash",
        "source_credential_authorization_hash",
        "source_endpoint_allowlist_evaluation_hash",
        "source_dispatch_readiness_hash",
        "source_live_adapter_dry_run_request_hash",
    ],
)
def test_source_content_and_lineage_are_preserved(field):
    packet = _packet()
    assert (
        getattr(packet, field)
        == packet.source_final_bind_authorization_readiness_packet[field]
    )


def test_source_human_approval_linkage_review_hash_mutation_is_rejected():
    raw = _packet().model_dump(mode="json")
    raw["source_human_approval_linkage_review_hash"] = "0" * 64
    _rehash(raw)

    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


def test_checks_requirements_and_scope_are_exact_ordered_and_non_effecting():
    packet = _packet()
    assert (
        tuple(check.name for check in packet.bind_authorization_gate_review_checks)
        == CHECK_NAMES
    )
    assert (
        tuple(
            item.name
            for item in packet.future_real_bind_authorization_artifact_requirements
        )
        == AUTHORIZATION_REQUIREMENTS
    )
    assert (
        tuple(item.name for item in packet.future_bind_invocation_requirements)
        == INVOCATION_REQUIREMENTS
    )
    assert packet.scope_limitations == SCOPE_LIMITATIONS
    assert all(
        not check.operation_committed and not check.network_used
        for check in packet.bind_authorization_gate_review_checks
    )


@pytest.mark.parametrize(
    "field",
    [
        "bind_authorization_gate_review_result",
        "bind_authorization_gate_review_checks",
        "future_real_bind_authorization_artifact_requirements",
        "future_bind_invocation_requirements",
        "scope_limitations",
        "fail_closed",
    ],
)
def test_derived_mutation_is_rejected(field):
    raw = _packet().model_dump(mode="json")
    if field == "bind_authorization_gate_review_result":
        raw[field]["gate_review_passed"] = False
    elif field == "bind_authorization_gate_review_checks":
        raw[field][0]["evidence_ref"] = "forged"
    elif field.startswith("future_"):
        raw[field][0]["name"] = "forged"
    elif field == "scope_limitations":
        raw[field].reverse()
    else:
        raw[field] = True
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


@pytest.mark.parametrize(
    "field",
    [
        "authority_evidence_created",
        "human_approval_created",
        "execution_authority_created",
        "bind_authorization_created",
        "bind_invoked",
        "bind_receipt_created",
        "trustlog_written",
        "request_dispatched",
        "endpoint_resolved",
        "credential_material_accessed",
        "authorization_header_constructed",
        "network_used",
        "live_adapter_instantiated",
        "webhook_called",
    ],
)
def test_effect_mutations_are_rejected(field):
    raw = _packet().model_dump(mode="json")
    raw[field] = True
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


@pytest.mark.parametrize(
    "field",
    [
        "live_adapter_dry_run_bind_authorization_gate_review_id",
        "live_adapter_dry_run_bind_authorization_gate_review_hash",
    ],
)
def test_forged_content_address_is_rejected(field):
    raw = _packet().model_dump(mode="json")
    raw[field] = "forged"
    with pytest.raises(LiveAdapterDryRunBindAuthorizationGateReviewError):
        verify_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


def test_semantic_match_is_preserved_only_in_source_and_never_promoted():
    for semantic_match in (False, True):
        packet = _packet(semantic_match=semantic_match)
        assert not packet.bind_authorization_gate_review_result.semantic_match_used
        assert not any(
            (
                packet.human_approval_created,
                packet.authority_evidence_created,
                packet.execution_authority_created,
                packet.bind_authorization_created,
            )
        )


def test_schema_validates_output_and_rejects_mutation():
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    raw["bind_authorization_created"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)


def test_module_has_no_prohibited_imports_or_calls():
    text = MODULE.read_text()
    tree = ast.parse(text)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection(
        {"requests", "httpx", "urllib", "socket", "dns", "subprocess", "os", "pathlib"}
    )
    for prohibited in (
        "WebhookBindAdapter",
        "BindReceipt",
        "TrustLog",
        "open(",
        "os.environ",
        "read_text",
        "write_text",
        "credential_store",
        "verify_postconditions",
        "revert(",
        "apply(",
    ):
        assert prohibited not in text
