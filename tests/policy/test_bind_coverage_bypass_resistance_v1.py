"""Adversarial tests for BIND_COVERAGE_BYPASS_RESISTANCE_V1."""

from __future__ import annotations

import copy
import asyncio
import pickle
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib

import pytest

from scripts.quality import check_bind_coverage_bypass_resistance_v1 as inventory
from scripts.quality.check_bind_coverage_bypass_resistance_v1 import (
    EXPECTED_SINKS,
    discover,
)

from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    FinalOutcome,
    hash_execution_intent,
)
from veritas_os.policy.bind_core import execute_bind_adjudication
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
    _mint_consumed_authorization_lineage,
    _bound_execution_permit_identity,
    _authority_object_counts,
    _mint_bind_core_compensation_transition,
    _mint_grant_from_consumed_action,
    ImmutableFinalDispatch,
    PermitBinding,
    _mint_bound_execution_permit,
    _transport_consumed_authorization_lineage,
    canonical_headers,
    consume_bound_execution_permit,
    consume_compensation_eligibility_grant,
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
    _UrllibWebhookTransport,
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


def _request() -> SandboxDispatchRequest:
    return SandboxDispatchRequest(
        endpoint_url=ENDPOINT,
        payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT),
        idempotency_key="key",
        attempt_id="attempt",
    )


def test_fake_permit_is_rejected() -> None:
    dispatch, binding, _ = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(object(), binding, dispatch)


def test_reconstructed_permit_is_rejected() -> None:
    dispatch, binding, _ = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    reconstructed = object.__new__(BoundExecutionPermit)
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(reconstructed, binding, dispatch)


def test_serialized_permit_is_rejected() -> None:
    permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )[2]
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(BindExecutionCapabilityError):
            operation(permit)


def test_fake_compensation_grant_is_rejected() -> None:
    _, binding = _active_grant()
    with pytest.raises(BindExecutionCapabilityError):
        consume_compensation_eligibility_grant(object(), binding)


def test_reconstructed_compensation_grant_is_rejected() -> None:
    _, binding = _active_grant()
    reconstructed = object.__new__(CompensationEligibilityGrant)
    with pytest.raises(BindExecutionCapabilityError):
        consume_compensation_eligibility_grant(reconstructed, binding)


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


def test_permit_replay_is_rejected() -> None:
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    consume_bound_execution_permit(permit, binding, dispatch)
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(permit, binding, dispatch)


def test_leaked_consumed_permit_reference_is_rejected() -> None:
    dispatch, binding, leaked = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    consume_bound_execution_permit(leaked, binding, dispatch)
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(leaked, binding, dispatch)


def _active_grant() -> tuple[object, CompensationGrantBinding]:
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    consumption_identity = consume_bound_execution_permit(
        permit, binding, dispatch
    )
    grant_binding = CompensationGrantBinding(
        parent_permit_identity=_bound_execution_permit_identity(permit),
        parent_permit_consumption_identity=consumption_identity,
        authorization_consumption_id=binding.authorization_consumption_id,
        execution_intent_hash=binding.execution_intent_hash,
        operation_id=binding.operation_id,
        action_class=binding.action_class,
        compensation_reason="POSTCONDITION_FAILED",
        effect_boundary_id="registered-webhook-compensation",
        endpoint_identity="https://hooks.example.test/compensate",
        request_body_digest=hashlib.sha256(b"{}").hexdigest(),
        runtime_implementation_identity=(
            "veritas_os.policy.webhook_bind_adapter._UrllibWebhookTransport"
        ),
    )
    transition = _mint_bind_core_compensation_transition(
        execution_intent_hash=binding.execution_intent_hash,
        operation_id=binding.operation_id,
        reason=grant_binding.compensation_reason,
    )
    grant = _mint_grant_from_consumed_action(
        permit, grant_binding, transition
    )
    return grant, grant_binding


def test_grant_replay_is_rejected() -> None:
    grant, binding = _active_grant()
    consume_compensation_eligibility_grant(grant, binding)
    with pytest.raises(BindExecutionCapabilityError):
        consume_compensation_eligibility_grant(grant, binding)


def test_concurrent_grant_consumption_has_exactly_one_winner() -> None:
    grant, binding = _active_grant()

    def consume() -> bool:
        try:
            consume_compensation_eligibility_grant(grant, binding)
        except BindExecutionCapabilityError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(lambda _: consume(), range(32))) == 1


def test_cross_action_grant_reuse_is_rejected() -> None:
    grant, binding = _active_grant()
    with pytest.raises(BindExecutionCapabilityError):
        consume_compensation_eligibility_grant(
            grant, replace(binding, operation_id="another-action")
        )


def test_action_permit_cannot_authorize_compensation() -> None:
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    compensation = replace(dispatch, dispatch_kind="COMPENSATION")
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(permit, binding, compensation)


def test_direct_compensation_permit_mint_is_rejected() -> None:
    _, binding, _ = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    with pytest.raises(BindExecutionCapabilityError):
        _mint_bound_execution_permit(
            replace(binding, dispatch_kind="COMPENSATION")
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_id", "wrong-operation"),
        ("target_identity", "wrong-resource"),
        ("credential_reference_digest", "wrong-credential"),
    ],
    ids=["wrong-operation", "wrong-resource", "changed-credential-identity"],
)
def test_exact_binding_mutation_is_rejected(field: str, value: str) -> None:
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    changed = replace(binding, **{field: value})
    with pytest.raises(BindExecutionCapabilityError):
        consume_bound_execution_permit(permit, changed, dispatch)


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
        transport=_UrllibWebhookTransport(transport),
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


def test_direct_webhook_adapter_invocation_has_zero_external_post() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    with pytest.raises(RuntimeError):
        adapter.apply(_intent(), {})
    assert transport.posts == []


def test_direct_webhook_helper_invocation_has_zero_external_post() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    with pytest.raises(RuntimeError):
        adapter._post_json_object(
            adapter.action_url, adapter.action_payload, _intent(), "failure"
        )
    assert transport.posts == []


def test_direct_webhook_transport_invocation_has_zero_external_post() -> None:
    transport = _RecordingWebhookTransport()
    guarded = _UrllibWebhookTransport(transport)
    with pytest.raises(RuntimeError):
        guarded.request(
            "POST",
            "https://hooks.example.test/action",
            body_bytes=b"{}",
            timeout=1,
        )
    assert transport.posts == []


def test_legitimate_webhook_action_sends_exact_frozen_bytes() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = _mint_consumed_authorization_lineage(
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


def test_direct_compensation_authorization_without_core_transition_is_rejected() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = _mint_consumed_authorization_lineage(
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
        before_counts = _authority_object_counts()
        with pytest.raises(BindExecutionCapabilityError):
            adapter._authorize_compensation_dispatch(
                intent, "POSTCONDITION_FAILED"
            )
        assert _authority_object_counts() == before_counts
    assert transport.posts == [canonical_json_dumps({"change": "p1"}).encode()]


def test_bind_core_transition_mints_exactly_one_compensation() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    object.__setattr__(adapter, "expected_postcondition", {"missing": True})
    intent = replace(
        _intent(),
        expected_state_fingerprint=sha256_of_canonical_json(
            {"ok": True, "compensated": True}
        ),
    )
    lineage = _mint_consumed_authorization_lineage(
        authorization_id="authorization",
        authorization_hash="a" * 64,
        consumption_id="consumption-core",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation-core",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        receipt = execute_bind_adjudication(
            execution_intent=intent,
            adapter=adapter,
            append_trustlog=False,
        )
    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert transport.posts == [
        canonical_json_dumps({"change": "p1"}).encode(),
        canonical_json_dumps({"undo": "p1"}).encode(),
    ]


def _consume_webhook_action(
    adapter: WebhookBindAdapter,
    intent: ExecutionIntent,
) -> None:
    token = adapter._authorize_action_dispatch(intent)
    try:
        adapter.apply(intent, {})
    finally:
        adapter._clear_authorized_dispatch(token)


def test_compensation_endpoint_mutation_is_rejected() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = _mint_consumed_authorization_lineage(
        authorization_id="authorization-endpoint",
        authorization_hash="b" * 64,
        consumption_id="consumption-endpoint",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation-endpoint",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        _consume_webhook_action(adapter, intent)
        object.__setattr__(
            adapter,
            "compensation_url",
            "https://hooks.example.test/other-compensation",
        )
        transition = _mint_bind_core_compensation_transition(
            execution_intent_hash=hash_execution_intent(intent),
            operation_id=lineage.operation_id,
            reason="POSTCONDITION_FAILED",
        )
        with pytest.raises(RuntimeError):
            adapter._authorize_compensation_dispatch(
                intent, "POSTCONDITION_FAILED", transition
            )
    assert len(transport.posts) == 1


def test_compensation_payload_mutation_is_rejected() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = _mint_consumed_authorization_lineage(
        authorization_id="authorization-payload",
        authorization_hash="c" * 64,
        consumption_id="consumption-payload",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation-payload",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        _consume_webhook_action(adapter, intent)
        assert adapter.compensation_payload is not None
        adapter.compensation_payload["undo"] = "valid-but-different-p2"
        transition = _mint_bind_core_compensation_transition(
            execution_intent_hash=hash_execution_intent(intent),
            operation_id=lineage.operation_id,
            reason="POSTCONDITION_FAILED",
        )
        with pytest.raises(RuntimeError):
            adapter._authorize_compensation_dispatch(
                intent, "POSTCONDITION_FAILED", transition
            )
    assert len(transport.posts) == 1


def test_post_validation_toctou_dispatches_frozen_p1() -> None:
    transport = _RecordingWebhookTransport()
    adapter = _webhook(transport)
    intent = _intent()
    lineage = _mint_consumed_authorization_lineage(
        authorization_id="authorization-toctou",
        authorization_hash="d" * 64,
        consumption_id="consumption-toctou",
        execution_intent_hash=hash_execution_intent(intent),
        operation_id="operation-toctou",
        action_class="registered_webhook",
        target_identity=intent.target_resource,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
    )
    with _transport_consumed_authorization_lineage(lineage):
        token = adapter._authorize_action_dispatch(intent)
        adapter.action_payload["change"] = "independently-valid-p2"
        try:
            adapter.apply(intent, {})
        finally:
            adapter._clear_authorized_dispatch(token)
    assert transport.posts == [canonical_json_dumps({"change": "p1"}).encode()]


def test_unregistered_subclass_is_rejected() -> None:
    class Alternate(SandboxHTTPSTransport):
        pass

    alternate = Alternate(endpoint_url=ENDPOINT)
    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            alternate,
            effect_boundary_id="native-v2-sandbox-action",
            dispatch_kind="ACTION",
        )


def test_duplicate_coverage_is_rejected() -> None:
    entries = load_bind_coverage_registry()
    duplicate = next(entry for entry in entries if entry.proof_scope)
    result = validate_bind_coverage_registry(entries + [duplicate])
    assert result.valid is False
    assert any("exact boundary" in error or "coverage_entry_id" in error for error in result.errors)


def test_registry_runtime_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            object(),
            effect_boundary_id="native-v2-sandbox-action",
            dispatch_kind="ACTION",
        )


def test_alternate_adapter_is_rejected() -> None:
    class AlternateAdapter:
        pass

    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            AlternateAdapter(),
            effect_boundary_id="registered-webhook-action",
            dispatch_kind="ACTION",
        )


def test_wrapper_proxy_is_rejected() -> None:
    class Proxy:
        def __init__(self) -> None:
            self.delegate = SandboxHTTPSTransport(endpoint_url=ENDPOINT)

    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            Proxy(),
            effect_boundary_id="native-v2-sandbox-action",
            dispatch_kind="ACTION",
        )


def test_alternate_factory_implementation_is_rejected() -> None:
    class AlternateFactoryTransport:
        pass

    produced = AlternateFactoryTransport()
    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            produced,
            effect_boundary_id="registered-webhook-action",
            dispatch_kind="ACTION",
        )


def test_ambiguous_coverage_is_rejected() -> None:
    entries = load_bind_coverage_registry()
    sandbox = next(
        entry
        for entry in entries
        if entry.effect_boundary_id == "native-v2-sandbox-action"
    )
    with pytest.raises(ValueError):
        match_frozen_runtime_boundary(
            SandboxHTTPSTransport(endpoint_url=ENDPOINT),
            effect_boundary_id="native-v2-sandbox-action",
            dispatch_kind="ACTION",
            entries=entries + [replace(sandbox, coverage_entry_id="ambiguous-copy")],
        )


def test_parent_action_permit_identity_is_authority_validated() -> None:
    dispatch, binding, permit = _sandbox_capability(
        SandboxHTTPSTransport(endpoint_url=ENDPOINT), _request()
    )
    consumption_identity = consume_bound_execution_permit(
        permit, binding, dispatch
    )
    grant_binding = CompensationGrantBinding(
        parent_permit_identity="caller-forged-parent-identity",
        parent_permit_consumption_identity=consumption_identity,
        authorization_consumption_id=binding.authorization_consumption_id,
        execution_intent_hash=binding.execution_intent_hash,
        operation_id=binding.operation_id,
        action_class=binding.action_class,
        compensation_reason="POSTCONDITION_FAILED",
        effect_boundary_id="registered-webhook-compensation",
        endpoint_identity="https://hooks.example.test/compensate",
        request_body_digest=hashlib.sha256(b"{}").hexdigest(),
        runtime_implementation_identity=(
            "veritas_os.policy.webhook_bind_adapter._UrllibWebhookTransport"
        ),
    )
    transition = _mint_bind_core_compensation_transition(
        execution_intent_hash=binding.execution_intent_hash,
        operation_id=binding.operation_id,
        reason=grant_binding.compensation_reason,
    )
    with pytest.raises(BindExecutionCapabilityError):
        _mint_grant_from_consumed_action(
            permit, grant_binding, transition
        )


def test_undeclared_effect_sink_breaks_exact_inventory_equality(
    tmp_path, monkeypatch
) -> None:
    sink = tmp_path / "new_runtime.py"
    sink.write_text("client.send(b'effect')\n", encoding="utf-8")
    monkeypatch.setattr(inventory, "SOURCES", (str(sink),))
    discovered = {
        (str(row["path"]), str(row["primitive"]))
        for row in inventory.discover()
    }
    assert discovered == {(str(sink), "client.send")}
    assert discovered != EXPECTED_SINKS
