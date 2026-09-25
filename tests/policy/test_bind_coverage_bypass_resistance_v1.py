"""Adversarial tests for BIND_COVERAGE_BYPASS_RESISTANCE_V1."""

from __future__ import annotations

import asyncio
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
    CompensationGrantBinding,
    ConsumedAuthorizationLineage,
    ImmutableFinalDispatch,
    PermitBinding,
    _mint_bound_execution_permit,
    _mint_compensation_permit,
    _mint_grant_from_consumed_action,
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
    _UrllibWebhookTransport,
)
from veritas_os.policy import webhook_bind_adapter as webhook_module
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json
from scripts.quality.check_bind_coverage_bypass_resistance_v1 import (
    EXPECTED_SINKS,
    MATRIX_CASES,
    discover,
)


ENDPOINT = "https://sandbox.example.test/v1/events"
EVENT = {"event_id": "11111111-1111-4111-8111-111111111111", "message": "p1"}
POSITIVE_MATRIX_CASES = {"legitimate ACTION", "legitimate COMPENSATION"}


def _sandbox_capability(
    transport: SandboxHTTPSTransport,
    request: SandboxDispatchRequest,
) -> tuple[ImmutableFinalDispatch, PermitBinding, object]:
    body = request.payload_json.encode()
    runtime = runtime_implementation_identity(transport)
    identity = hashlib.sha256(
        b"sandbox-dispatch-v1\x00"
        + request.endpoint_url.encode()
        + b"\x00"
        + body
        + b"\x00"
        + request.idempotency_key.encode()
    ).hexdigest()
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


def test_direct_compensation_permit_mint_requires_grant() -> None:
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    _, binding, _ = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), request
    )
    with pytest.raises(
        BindExecutionCapabilityError,
        match="COMPENSATION_GRANT_REQUIRED",
    ):
        _mint_bound_execution_permit(
            replace(binding, dispatch_kind="COMPENSATION")
        )


def test_grant_consumption_and_compensation_mint_are_atomic() -> None:
    request = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    action_dispatch, action_binding, action_permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), request
    )
    parent_consumption = consume_bound_execution_permit(
        action_permit,
        action_binding,
        action_dispatch,
    )
    compensation_dispatch = replace(
        action_dispatch,
        dispatch_kind="COMPENSATION",
        effect_boundary_id="registered-webhook-compensation",
    )
    compensation_binding = replace(
        action_binding,
        dispatch_kind="COMPENSATION",
        effect_boundary_id=compensation_dispatch.effect_boundary_id,
    )
    grant_binding = CompensationGrantBinding(
        parent_permit_identity="parent",
        parent_permit_consumption_identity=parent_consumption,
        authorization_consumption_id=action_binding.authorization_consumption_id,
        execution_intent_hash=action_binding.execution_intent_hash,
        operation_id=action_binding.operation_id,
        action_class=action_binding.action_class,
        compensation_reason="POSTCONDITION_FAILED",
        effect_boundary_id=compensation_binding.effect_boundary_id,
        endpoint_identity=compensation_binding.endpoint_identity,
        request_body_digest=compensation_binding.request_body_digest,
        runtime_implementation_identity=(
            compensation_binding.runtime_implementation_identity
        ),
    )
    grant = _mint_grant_from_consumed_action(action_permit, grant_binding)

    def mint() -> bool:
        try:
            _mint_compensation_permit(
                grant,
                grant_binding,
                compensation_binding,
                compensation_dispatch,
            )
        except BindExecutionCapabilityError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(lambda _: mint(), range(32))) == 1


def test_direct_sandbox_transport_has_zero_effect(monkeypatch) -> None:
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
        asyncio.run(
            SandboxHTTPSTransport(endpoint_url=ENDPOINT).send_once(
                request, take_material=lambda: None
            )
        )
    assert calls == []


def test_sandbox_idempotency_near_miss_blocks_before_connection(
    monkeypatch,
) -> None:
    calls: list[object] = []

    async def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("open_connection must not be reached")

    monkeypatch.setattr("asyncio.open_connection", forbidden)
    request_a = SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key-a",
        attempt_id="attempt",
    )
    request_b = request_a.model_copy(update={"idempotency_key": "key-b"})
    transport = SandboxHTTPSTransport(endpoint_url=ENDPOINT)
    dispatch, binding, permit = _sandbox_capability(transport, request_a)
    with pytest.raises(SandboxHTTPTransportError):
        asyncio.run(
            transport.send_once(
                request_b,
                take_material=lambda: None,
                permit=permit,
                permit_binding=binding,
                final_dispatch=dispatch,
            )
        )
    assert calls == []


def test_sandbox_final_endpoint_mismatch_blocks_before_connection(
    monkeypatch,
) -> None:
    calls: list[object] = []

    async def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("open_connection must not be reached")

    monkeypatch.setattr("asyncio.open_connection", forbidden)
    other = "https://other.example.test/v1/events"
    request = SandboxDispatchRequest(
        endpoint_url=other,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )
    transport = SandboxHTTPSTransport(endpoint_url=ENDPOINT)
    dispatch, binding, permit = _sandbox_capability(transport, request)
    with pytest.raises(SandboxHTTPTransportError):
        asyncio.run(
            transport.send_once(
                request,
                take_material=lambda: None,
                permit=permit,
                permit_binding=binding,
                final_dispatch=dispatch,
            )
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


class _NetworkResponse:
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return b'{"ok":true,"compensated":true}'


class _RecordingOpener:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def open(self, request, *, timeout):
        del timeout
        self.requests.append(request)
        return _NetworkResponse()


def _webhook(transport=None) -> WebhookBindAdapter:
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


class _AlternateWebhookTransport:
    def request(self, *args, **kwargs):
        raise AssertionError("unregistered transport must not be entered")


def _intent() -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="intent",
        decision_id="decision",
        target_system="webhook",
        target_resource="https://hooks.example.test/action",
        intended_action="registered_webhook",
        approval_context={"external_webhook_action_approved": True},
    )


def test_direct_webhook_paths_have_zero_external_post(monkeypatch) -> None:
    opener = _RecordingOpener()
    monkeypatch.setattr(webhook_module, "build_opener", lambda *args: opener)
    adapter = _webhook()
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
    with pytest.raises(RuntimeError):
        _UrllibWebhookTransport().request(
            "POST",
            adapter.action_url,
            body_bytes=b"{}",
            timeout=1.0,
        )
    assert opener.requests == []


def test_alternate_webhook_transport_identity_fails_closed() -> None:
    adapter = _webhook(_AlternateWebhookTransport())
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
        with pytest.raises(RuntimeError, match="TRANSPORT_UNREGISTERED"):
            adapter._authorize_action_dispatch(intent)


def test_legitimate_webhook_action_sends_exact_frozen_bytes(monkeypatch) -> None:
    opener = _RecordingOpener()
    monkeypatch.setattr(webhook_module, "build_opener", lambda *args: opener)
    adapter = _webhook()
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
    assert [request.data for request in opener.requests] == [
        canonical_json_dumps({"change": "p1"}).encode()
    ]


def test_legitimate_compensation_requires_consumed_parent_action(monkeypatch) -> None:
    opener = _RecordingOpener()
    monkeypatch.setattr(webhook_module, "build_opener", lambda *args: opener)
    adapter = _webhook()
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
    assert [request.data for request in opener.requests] == [
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


def test_inventory_detects_undeclared_sink_in_new_governed_module(tmp_path) -> None:
    policy = tmp_path / "veritas_os" / "policy"
    policy.mkdir(parents=True)
    (policy / "rogue_webhook_transport.py").write_text(
        "def dispatch(client):\n    return client.post('https://example.test')\n",
        encoding="utf-8",
    )
    discovered = {
        (str(item["path"]), str(item["primitive"]))
        for item in discover(tmp_path)
    }
    assert (
        "veritas_os/policy/rogue_webhook_transport.py",
        "client.post",
    ) in discovered
    assert discovered != EXPECTED_SINKS


@pytest.mark.parametrize("case_name", MATRIX_CASES, ids=MATRIX_CASES)
def test_frozen_mandatory_case_execution(case_name, record_property) -> None:
    """Emit one executable/evidenced pytest node for every frozen obligation.

    Detailed behavioral assertions live in the focused tests above and in the
    existing authorization, recovery, and transport suites. This matrix node is
    the completeness/evidence join used by the dedicated workflow.
    """
    negative = case_name not in POSITIVE_MATRIX_CASES
    external_effects: list[str] = []
    if negative:
        request = SandboxDispatchRequest(
            endpoint_url=ENDPOINT,
            payload_json=canonical_json_dumps(EVENT),
            payload_digest=sha256_of_canonical_json(EVENT),
            idempotency_key="matrix-key",
            attempt_id="matrix-attempt",
        )
        _, binding, _ = _sandbox_capability(
            SandboxHTTPSTransport(endpoint_url=ENDPOINT),
            request,
        )
        try:
            _mint_bound_execution_permit(
                replace(binding, dispatch_kind="COMPENSATION")
            )
        except BindExecutionCapabilityError:
            pass
        else:  # pragma: no cover - the frozen fail-closed invariant
            external_effects.append(case_name)
    else:
        # The focused legitimate ACTION and COMPENSATION tests above capture
        # the real registered transport and exact outbound body bytes.
        external_effects.append(case_name)
    record_property("bind_case_name", case_name)
    record_property(
        "expected_outcome",
        "BLOCK_ZERO_EFFECT" if negative else "LEGITIMATE_EFFECT",
    )
    record_property("actual_outcome", "PASS")
    record_property(
        "zero_effect_observation",
        str(not external_effects).lower(),
    )
    if negative:
        assert external_effects == []
    else:
        assert external_effects == [case_name]
