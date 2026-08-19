"""Integrity and non-effect tests for final Bind readiness packet v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_REQUIREMENTS,
    CHECK_NAMES,
    INVOCATION_REQUIREMENTS,
    OUTCOMES,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunFinalBindAuthorizationReadinessError,
    _packet_hash,
    build_live_adapter_dry_run_final_bind_authorization_readiness_packet,
    verify_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_human_approval_linkage import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _packet as source_packet,
)

RECORDED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
MODULE = Path("veritas_os/policy/live_adapter_dry_run_final_bind_authorization_readiness.py")
SCHEMA = Path("schemas/live-adapter-dry-run-final-bind-authorization-readiness-v1.schema.json")


def _decision(*, accepted=True, **changes):
    value = {
        "final_bind_authorization_readiness_review_decision_id": "final-review:billing:v1",
        "reviewer_id": "operator:alice", "reviewer_role": "bind-readiness-reviewer",
        "reviewer_attestation": "I reviewed local readiness only.",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_outcome": OUTCOMES[0] if accepted else OUTCOMES[1],
        "review_reason": "local linkage artifacts reviewed",
        **{field: True for field in ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _packet(*, source=None, decision=None, semantic_match=False):
    source = source or source_packet(semantic_match=semantic_match)
    return build_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        source, decision or _decision(), RECORDED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_final_bind_authorization_readiness_hash"] = digest
    raw["live_adapter_dry_run_final_bind_authorization_readiness_id"] = (
        f"ladfbar:v1:sha256:{digest}"
    )


def test_builder_creates_and_verifies_ready_packet(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness as module

    actual = module.verify_live_adapter_dry_run_human_approval_linkage_review_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_live_adapter_dry_run_human_approval_linkage_review_packet", recording
    )
    packet = module.build_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        source_packet(), _decision(), RECORDED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_final_bind_authorization_readiness_packet(packet) == packet
    assert len(calls) == 3
    assert not packet.fail_closed
    assert packet.final_readiness_state == "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    assert not packet.bind_authorization_created


def test_rejected_review_records_fail_closed_not_ready() -> None:
    packet = _packet(decision=_decision(accepted=False))
    assert packet.fail_closed
    assert packet.final_readiness_state == "NOT_READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    assert not packet.final_bind_authorization_readiness_result.accepted_for_future_bind_authorization_gate_review


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_every_acknowledgement_is_required(field) -> None:
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        _packet(decision=_decision(**{field: False}))


@pytest.mark.parametrize("field", [
    "reviewer_id", "reviewer_role", "reviewer_attestation",
    "final_bind_authorization_readiness_review_decision_id", "review_reason",
])
def test_review_identity_and_attestation_are_required(field) -> None:
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        _packet(decision=_decision(**{field: ""}))


def test_review_decision_is_closed() -> None:
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        _packet(decision=_decision(unexpected=True))


@pytest.mark.parametrize("field", [
    "request_descriptor", "execution_intent", "execution_intent_id", "execution_intent_hash",
    "adapter_contract_descriptor", "adapter_contract_id", "adapter_contract_hash",
    "adapter_contract_version", "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "authority_evidence_linkage_result", "human_approval_linkage_result",
    "source_bind_pre_dispatch_review_hash", "source_operator_dispatch_review_hash",
    "source_credential_authorization_hash", "source_endpoint_allowlist_evaluation_hash",
    "source_dispatch_readiness_hash", "source_live_adapter_dry_run_request_hash",
])
def test_source_content_and_lineage_are_preserved(field) -> None:
    packet = _packet()
    source = packet.source_human_approval_linkage_review_packet
    assert getattr(packet, field) == source[field]


def test_checks_and_future_requirements_are_exact_and_ordered() -> None:
    packet = _packet()
    assert tuple(check.name for check in packet.final_bind_authorization_readiness_checks) == CHECK_NAMES
    assert tuple(item.name for item in packet.future_bind_authorization_gate_requirements) == AUTHORIZATION_REQUIREMENTS
    assert tuple(item.name for item in packet.future_bind_invocation_requirements) == INVOCATION_REQUIREMENTS
    assert all(not getattr(check, field) for check in packet.final_bind_authorization_readiness_checks
               for field in ("bind_authorization_created", "network_used", "operation_committed"))


@pytest.mark.parametrize("field", [
    "final_bind_authorization_readiness_review_decision",
    "final_bind_authorization_readiness_result", "final_bind_authorization_readiness_checks",
    "future_bind_authorization_gate_requirements", "future_bind_invocation_requirements",
    "scope_limitations",
])
def test_mutated_derived_content_is_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    if field == "final_bind_authorization_readiness_review_decision":
        raw[field]["review_reason"] = "forged"
    elif field == "final_bind_authorization_readiness_result":
        raw[field]["all_required_local_linkage_artifacts_verified"] = False
    elif field == "final_bind_authorization_readiness_checks":
        raw[field][0]["evidence_ref"] = "forged"
    elif field.startswith("future_"):
        raw[field][0]["name"] = "forged"
    else:
        raw[field].reverse()
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        verify_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)


@pytest.mark.parametrize("field", [
    "authority_evidence_created", "human_approval_created", "execution_authority_created",
    "bind_authorization_created", "bind_invoked", "bind_receipt_created", "trustlog_written",
    "request_dispatched", "endpoint_resolved", "credential_material_accessed",
    "authorization_header_constructed", "network_used", "live_adapter_instantiated",
    "webhook_called",
])
def test_effect_mutations_are_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = True
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        verify_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)


@pytest.mark.parametrize("field", [
    "live_adapter_dry_run_final_bind_authorization_readiness_id",
    "live_adapter_dry_run_final_bind_authorization_readiness_hash",
])
def test_forged_content_address_is_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = "forged"
    with pytest.raises(LiveAdapterDryRunFinalBindAuthorizationReadinessError):
        verify_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)


def test_semantic_match_is_never_promoted() -> None:
    for semantic_match in (False, True):
        packet = _packet(semantic_match=semantic_match)
        assert not packet.final_bind_authorization_readiness_result.semantic_match_used
        assert not packet.human_approval_created
        assert not packet.authority_evidence_created
        assert not packet.execution_authority_created
        assert not packet.bind_authorization_created


def test_schema_validates_packet_and_rejects_effect_mutation() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    raw["bind_authorization_created"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)


def test_module_has_no_prohibited_imports_or_calls() -> None:
    tree = ast.parse(MODULE.read_text())
    imports = {alias.name.split(".")[0] for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not imports.intersection({
        "requests", "httpx", "urllib", "socket", "dns", "subprocess", "os", "pathlib",
    })
    text = MODULE.read_text()
    for prohibited in (
        "WebhookBindAdapter", "BindReceipt", "TrustLog", "open(", "os.environ",
        "read_text", "write_text", "credential_store", "verify_postconditions",
        "revert(", "apply(",
    ):
        assert prohibited not in text


def test_packet_hash_changes_with_content() -> None:
    raw = _packet().model_dump(mode="json")
    changed = deepcopy(raw)
    changed["final_bind_authorization_readiness_recorded_at"] = (
        RECORDED_AT + timedelta(seconds=1)
    ).isoformat()
    assert _packet_hash(changed) != _packet_hash(raw)


def test_scope_limitations_are_exact() -> None:
    assert _packet().scope_limitations == SCOPE_LIMITATIONS
