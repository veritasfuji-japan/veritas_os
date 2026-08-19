"""Fail-closed contract tests for canonical Bind Authorization v1."""

from __future__ import annotations

import ast
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from veritas_os.policy.live_adapter_bind_authorization import (
    ACKNOWLEDGEMENTS,
    ARCHITECTURE_GAPS,
    BindAuthorizationDecision,
    LiveAdapterBindAuthorizationError,
    _timestamp,
    build_live_adapter_bind_authorization_artifact,
)
from veritas_os.tests.test_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _decision as gate_decision,
    _packet as source_packet,
)

AUTHORIZED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
VALID_UNTIL = AUTHORIZED_AT + timedelta(minutes=5)
MODULE = Path("veritas_os/policy/live_adapter_bind_authorization.py")
SCHEMA = Path("schemas/live-adapter-bind-authorization-v1.schema.json")


def _decision(**changes):
    value = {
        "authorizer_id": "operator:bob",
        "authorizer_role": "bind-authorizer",
        "authorizer_attestation": "I authorize only this exact future Bind attempt.",
        "authorized_at": AUTHORIZED_AT.isoformat(),
        "authorization_reason": "verified governance chain and explicit operator GO",
        "explicit_go_no_go_confirmation": "GO_AUTHORIZED",
        **{field: True for field in ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _build(source=None, decision=None):
    return build_live_adapter_bind_authorization_artifact(
        source or source_packet(),
        decision or _decision(),
        AUTHORIZED_AT,
        VALID_UNTIL,
    )


def test_passed_gate_review_still_fails_closed_at_real_proof_gap():
    """Declared linkage metadata must never be promoted to real authority."""
    with pytest.raises(
        LiveAdapterBindAuthorizationError,
        match="LABA_ARCHITECTURE_GAP_UNVERIFIED_REAL_GOVERNANCE_ARTIFACTS",
    ):
        _build()
    assert ARCHITECTURE_GAPS == (
        "real_authority_evidence_is_only_a_declared_reference_bundle",
        "real_human_approval_is_only_a_declared_reference_bundle",
        "runtime_authority_validator_inputs_are_not_embedded_in_the_source_chain",
    )


def test_failed_gate_review_cannot_be_upgraded_to_authorization():
    failed = source_packet(decision=gate_decision(passed=False))
    with pytest.raises(
        LiveAdapterBindAuthorizationError, match="LABA_SOURCE_NOT_AUTHORIZABLE"
    ):
        _build(source=failed)


@pytest.mark.parametrize(
    "field",
    ["authorizer_id", "authorizer_role", "authorizer_attestation", "authorization_reason"],
)
def test_authorizer_identity_role_attestation_and_reason_are_required(field):
    with pytest.raises(ValidationError):
        BindAuthorizationDecision.model_validate(_decision(**{field: ""}))


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_every_authorization_boundary_acknowledgement_is_required(field):
    with pytest.raises(ValidationError):
        BindAuthorizationDecision.model_validate(_decision(**{field: False}))


def test_no_go_semantic_promotion_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        BindAuthorizationDecision.model_validate(
            _decision(explicit_go_no_go_confirmation="NO_GO")
        )
    with pytest.raises(ValidationError):
        BindAuthorizationDecision.model_validate(
            _decision(semantic_match_authorized=True)
        )


def test_timestamp_normalization_requires_timezone_awareness():
    assert _timestamp(AUTHORIZED_AT).endswith("+00:00")
    with pytest.raises(LiveAdapterBindAuthorizationError, match="LABA_TIMESTAMP_NAIVE"):
        _timestamp("2031-01-01T00:00:00")
    with pytest.raises(LiveAdapterBindAuthorizationError, match="LABA_TIMESTAMP_INVALID"):
        _timestamp("malformed")


def test_schema_is_closed_and_constrains_identity_states_and_effects():
    schema = json.loads(SCHEMA.read_text())
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties["live_adapter_bind_authorization_id"]["pattern"] == (
        "^laba:v1:sha256:[0-9a-f]{64}$"
    )
    assert properties["bind_authorization_state"]["const"] == "AUTHORIZED"
    assert properties["authorization_consumption_state"]["const"] == "NOT_CONSUMED"
    for field in (
        "bind_invoked", "bind_receipt_created", "trustlog_written",
        "request_dispatched", "endpoint_resolved", "credential_material_accessed",
        "authorization_header_constructed", "network_used", "dns_used",
        "webhook_called", "live_adapter_instantiated", "live_adapter_method_called",
        "filesystem_used", "database_used", "provider_used", "subprocess_used",
        "operation_committed",
    ):
        assert properties[field]["const"] is False


def test_module_has_no_runtime_effect_imports_or_calls():
    text = MODULE.read_text()
    tree = ast.parse(text)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection(
        {"requests", "httpx", "socket", "urllib", "subprocess", "os"}
    )
    for prohibited in (
        "execute_bind_adjudication", "execute_bind_boundary", "WebhookBindAdapter",
        "ReferenceBindAdapter", "BindReceipt", "TrustLog", "resolve_credentials",
        "secret_manager", "construct_authorization_header(", "open(",
        "write_text", "os.environ",
    ):
        assert prohibited not in text
