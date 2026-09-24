"""Adversarial tests for BIND_COVERAGE_BYPASS_RESISTANCE_V1."""

from __future__ import annotations

import copy
import pickle
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.bind_coverage_registry import (
    load_bind_coverage_registry,
    match_frozen_runtime_boundary,
    validate_bind_coverage_registry,
)
from veritas_os.policy.bind_execution_capability import (
    BindExecutionCapabilityError,
    BoundExecutionPermit,
    CompensationEligibilityGrant,
    ConsumedAuthorizationLineage,
    ImmutableFinalDispatch,
    PermitBinding,
    _mint_bound_execution_permit,
    _transport_consumed_authorization_lineage,
    canonical_headers,
    consume_bound_execution_permit,
    runtime_implementation_identity,
)
from veritas_os.policy.sandbox_bind_execution import SandboxDispatchRequest
from veritas_os.policy.sandbox_https_transport import (
    SandboxHTTPSTransport,
    SandboxHTTPTransportError,
)
from veritas_os.policy.webhook_bind_adapter import (
    WebhookBindAdapter,
    WebhookResponse,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


ENDPOINT = "https://sandbox.example.test/v1/events"
EVENT = {"event_id": "11111111-1111-4111-8111-111111111111", "message": "p1"}


def _sandbox_capability(
    transport: SandboxHTTPSTransport,
    request: SandboxDispatchRequest,
) -> tuple[ImmutableFinalDispatch, PermitBinding, object]:
    body = request.payload_json.encode()
    runtime = runtime_implementation_identity(transport)
    identity = hashlib.sha256(body + request.endpoint_url.encode()).hexdigest()
    dispatch = ImmutableFinalDispatch(
        effect_boundary_id="native-v2-sandbox-action",
        dispatch_kind="ACTION",
        method="POST",
        canonical_endpoint=request.endpoint_url,
        canonical_bound_headers=canonical_headers({
            "content-type": "application/json",
            "idempotency-key": request.idempotency_key,
        }),
        body_bytes=body,
        body_digest=request.payload_digest,
        request_identity=identity,
        idempotency_identity=request.idempotency_key,
        credential_reference_digest="credential-reference",
        credential_scope_digest="credential-scope",
        authorization_consumption_id="consumption",
        runtime_implementation_identity=runtime,
    )
    binding = PermitBinding(
        coverage_entry_id="bcb-v1-native-v2-sandbox-action",
        operation_id="operation",
        action_class="sandbox.event.register.v1",
        dispatch_kind="ACTION",
        execution_intent_hash="intent-hash",
        authorization_id="authorization",
        authorization_hash="authorization-hash",
        authorization_consumption_id="consumption",
        target_identity=ENDPOINT,
        runtime_implementation_identity=runtime,
        effect_boundary_id=dispatch.effect_boundary_id,
        endpoint_identity=dispatch.canonical_endpoint,
        credential_reference_digest=dispatch.credential_reference_digest,
        credential_scope_digest=dispatch.credential_scope_digest,
        request_body_digest=dispatch.body_digest,
        request_identity=dispatch.request_identity,
        idempotency_identity=dispatch.idempotency_identity,
    )
    return dispatch, binding, _mint_bound_execution_permit(binding)


def test_permit_cannot_be_faked_copied_or_serialized() -> None:
    with pytest.raises(BindExecutionCapabilityError):
        BoundExecutionPermit()
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    permit = _sandbox_capability(SandboxHTTPSTransport(endpoint_url=ENDPOINT), request)[2]
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(BindExecutionCapabilityError):
            operation(permit)
    with pytest.raises(BindExecutionCapabilityError):
        CompensationEligibilityGrant()


def test_permit_atomic_consumption_has_exactly_one_winner() -> None:
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), request
    )

    def consume() -> bool:
        try:
            consume_bound_execution_permit(permit, binding, dispatch)
        except BindExecutionCapabilityError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(lambda _: consume(), range(32))) == 1


@pytest.mark.asyncio
async def test_direct_sandbox_transport_has_zero_effect(monkeypatch) -> None:
    calls: list[object] = []

    async def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("open_connection must not be reached")

    monkeypatch.setattr("asyncio.open_connection", forbidden)
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    with pytest.raises(SandboxHTTPTransportError):
        await SandboxHTTPSTransport(endpoint_url=ENDPOINT).send_once(
            request, take_material=lambda: None
        )
    assert calls == []


def test_valid_p2_cannot_replace_frozen_p1() -> None:
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), request
    )
    p2 = {**EVENT, "message": "independently-valid-p2"}
    p2_bytes = canonical_json_dumps(p2).encode()
    assert sha256_of_canonical_json(p2) != dispatch.body_digest
    changed = replace(
        dispatch,
        body_bytes=p2_bytes,
        body_digest=hashlib.sha256(p2_bytes).hexdigest(),
    )
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(permit, binding, changed)
    assert dispatch.body_bytes == canonical_json_dumps(EVENT).encode()


class _RecordingWebhookTransport:
    def __init__(self) -> None:
        self.posts: list[bytes] = []

    def request(self, method, url, **kwargs):
        if method == "POST":
            self.posts.append(kwargs["body_bytes"])
        return WebhookResponse(200, {"ok": True, "compensated": True})


def _webhook(transport: _RecordingWebhookTransport) -> WebhookBindAdapter:
    return WebhookBindAdapter(
        snapshot_url="https://hooks.example.test/snapshot",
        action_url="https://hooks.example.test/action",
        postcondition_url="https://hooks.example.test/status",
        compensation_url="https://hooks.example.test/compensate",
        action_payload={"change": "p1"},
        compensation_payload={"undo": "p1"},
        expected_postcondition={"ok": True},
        allowed_hosts={"hooks.example.test"},
        hmac_secret=b"test-only-secret",
        transport=transport,
        dns_resolver=lambda _: ["8.8.8.8"],
    )


def _intent() -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="intent",
        decision_id="decision",
        target_system="webhook",
        target_resource="https://hooks.example.test/action",
        intended_action="registered_webhook",
        approval_context={"external_webhook_action_approved": True},
    )


def test_direct_webhook_paths_have_zero_external_post() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    for invoke in (
        lambda: adapter.apply(_intent(), {}),
        lambda: adapter._post_json_object(
            adapter.action_url, adapter.action_payload, _intent(), "failure"
        ),
        lambda: adapter._request(
            "POST", adapter.action_url, headers={}, json_body=adapter.action_payload
        ),
    ):
        with pytest.raises(RuntimeError):
            invoke()
    assert transport.posts == []


def test_legitimate_webhook_action_sends_exact_frozen_bytes() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = ConsumedAuthorizationLineage(
        authorization_id="authorization",
        authorization_hash="a" * 64,
        consumption_id="consumption",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        token = adapter._authorize_action_dispatch(intent)
        try:
            assert adapter.apply(intent, {}) is True
        finally:
            adapter._clear_authorized_dispatch(token)
    assert transport.posts == [canonical_json_dumps({"change": "p1"}).encode()]


def test_legitimate_compensation_requires_consumed_parent_action() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = ConsumedAuthorizationLineage(
        authorization_id="authorization",
        authorization_hash="a" * 64,
        consumption_id="consumption",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        action_token = adapter._authorize_action_dispatch(intent)
        try:
            adapter.apply(intent, {})
        finally:
            adapter._clear_authorized_dispatch(action_token)
        compensation_token = adapter._authorize_compensation_dispatch(
            intent, "POSTCONDITION_FAILED"
        )
        try:
            assert adapter.revert(intent, {}) is True
        finally:
            adapter._clear_authorized_dispatch(compensation_token)
        with pytest.raises(BindExecutionCapabilityError):
            adapter._authorize_compensation_dispatch(intent, "REPLAY")
    assert transport.posts == [
        canonical_json_dumps({"change": "p1"}).encode(),
        canonical_json_dumps({"undo": "p1"}).encode(),
    ]


def test_exact_registry_rejects_subclass_duplicate_and_ambiguity() -> None:
    class Alternate(SandboxHTTPSTransport):
        pass

    alternate = Alternate(endpoint_url=ENDPOINT)
    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            alternate,
            effect_boundary_id="native-v2-sandbox-action",
            dispatch_kind="ACTION",
        )
    entries = load_bind_coverage_registry()
    duplicate = next(entry for entry in entries if entry.proof_scope)
    result = validate_bind_coverage_registry(entries + [duplicate])
    assert result.valid is False
    assert any("exact boundary" in error or "coverage_entry_id" in error for error in result.errors)
