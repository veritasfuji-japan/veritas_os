"""Exact request binding tests; all deployment metadata is synthetic."""

from dataclasses import replace
import json

import pytest

from veritas_os.policy import sandbox_action_binding as binding
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import _contract


def contract():
    return replace(
        _contract(action=binding.ACTION, required=False),
        irreversibility={"level": "low", "boundary": "future-bind-consumption"},
    )


def deployment():
    return binding.SandboxDeployment(
        endpoint_url="https://sandbox.example.invalid/v1/events",
        target_system="synthetic-sandbox",
        action_contract_digest=contract().deterministic_digest(),
        credential_reference_id="credential-ref:promotion:billing:v1",
        credential_version="1",
        credential_provider_type="LOCAL_SECRET_STORE_REFERENCE",
        credential_scope="sandbox:events:register sandbox:operations:read",
        credential_environment="sandbox",
    )


PAYLOAD = {"event_id": "12345678-1234-4234-8234-123456789abc", "message": "synthetic"}


def build(value=None, config=None, policy=None):
    return binding.build_sandbox_action_binding(
        json.dumps(PAYLOAD) if value is None else value,
        deployment=deployment() if config is None else config,
        expected_contract=contract() if policy is None else policy,
    )


def test_stable_reference_canonicalizes_only_json_whitespace_and_key_order():
    first = build()
    second = build(json.dumps(dict(reversed(list(PAYLOAD.items()))), indent=2))
    assert first == second
    assert json.loads(first.payload_json) == PAYLOAD


@pytest.mark.parametrize("value", [
    "[]", "null", "true", "{}", "{", '{"event_id":"x","message":"x"}',
    json.dumps({**PAYLOAD, "message": ""}),
    json.dumps({**PAYLOAD, "message": "あ" * 86}),
    json.dumps({**PAYLOAD, "message": 1}),
    json.dumps({**PAYLOAD, "extra": True}),
    json.dumps({**PAYLOAD, "message": "\ud800"}),
    '{"event_id":"12345678-1234-4234-8234-123456789abc","message":"a","message":"b"}',
    " " * 4097, "[" * 1500,
])
def test_invalid_payload_fails_closed(value):
    with pytest.raises(binding.SandboxActionBindingError, match="SAB_PAYLOAD_INVALID"):
        build(value)


@pytest.mark.parametrize("url", [
    "http://sandbox.example.invalid/v1/events", "https://user@host.test/v1/events",
    "https://host.test/v1/events?x=1", "https://host.test/v1/events#x",
    "https://host.test/v1/events/", "https://host.test:443/v1/events",
    "https://HOST.test/v1/events", "https://host.test/v1/../events",
])
def test_non_exact_destination_rejected(url):
    with pytest.raises(binding.SandboxActionBindingError):
        build(config=replace(deployment(), endpoint_url=url))


@pytest.mark.parametrize("field", binding.SandboxDeployment.__dataclass_fields__)
def test_missing_deployment_field_rejected(field):
    with pytest.raises(binding.SandboxActionBindingError):
        build(config=replace(deployment(), **{field: ""}))


@pytest.mark.parametrize("field", [
    "credential_version", "credential_reference_id", "credential_scope",
    "credential_provider_type", "credential_environment", "target_system",
])
def test_changed_deployment_requires_different_preissuance_reference(field):
    assert build(config=replace(deployment(), **{field: "changed"})).reference != build().reference


def test_same_id_version_contract_downgrade_rejected():
    original = contract()
    changed = replace(original, human_approval_rules={"required": True})
    assert changed.id == original.id and changed.version == original.version
    with pytest.raises(binding.SandboxActionBindingError, match="CONTRACT_MISMATCH"):
        build(policy=changed)


@pytest.mark.parametrize("field,value", [
    ("message", "another synthetic event"),
    ("event_id", "12345678-1234-4234-8234-123456789abd"),
])
def test_payload_change_changes_preissuance_reference(field, value):
    assert build(json.dumps({**PAYLOAD, field: value})).reference != build().reference
