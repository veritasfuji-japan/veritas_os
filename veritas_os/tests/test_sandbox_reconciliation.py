"""Real native verification with synthetic read-only provider and TLS streams."""

import asyncio
from dataclasses import asdict, replace
from datetime import timedelta
import json
from pathlib import Path
import ssl

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_reconciliation as module
from veritas_os.policy.sandbox_credential_resolution import SandboxProviderCredential
from veritas_os.policy.trusted_https_reconciliation import ApprovedReconciliationVerifier
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_pre_effect import (
    issued as issued_fixture, prepared_inputs as prepared_fixture, _args,
)
from veritas_os.tests.test_sandbox_credential_resolution import metadata
from veritas_os.tests.test_sandbox_https_transport import Writer, TOKEN

pytestmark = pytest.mark.slow
issued = issued_fixture
prepared_inputs = prepared_fixture


def test_reader_sample_roundtrip_and_policy_binding():
    from veritas_os.tests.test_sandbox_action_binding import deployment
    values = json.loads((Path(__file__).parent / "fixtures" / "sandbox_reader_policy.json").read_text())
    policy = module.SandboxReaderPolicy(**values)
    assert asdict(policy) == values
    original = module.sandbox_reconciliation_policy_hash(deployment(), policy)
    for field in values:
        assert module.sandbox_reconciliation_policy_hash(deployment(), replace(policy, **{field: "changed"})) != original


class ReaderProvider:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.changes = {}

    async def describe(self, request):
        self.calls.append(request)
        fields = asdict(request)
        fields.pop("authorization_id")
        fields.pop("attempt_id")
        self.metadata = metadata(self.clock.now, **(fields | self.changes))
        return self.metadata

    async def resolve(self, request, *, expected_metadata_digest):
        self.calls.append(request)
        assert expected_metadata_digest == module.sha256_of_canonical_json(self.metadata.model_dump(mode="json"))
        return SandboxProviderCredential(metadata=self.metadata, material=SecretBytes(TOKEN))


async def setup_case(prepared_inputs, monkeypatch, status=200, changes=None):
    artifact, args = await _args(prepared_inputs)
    args["historical_governance_inputs"] = args.pop("governance_inputs")
    args.pop("load_current_inputs")
    current = module._build_record(
        consumption=prepared_inputs[2], state=module.EffectExecutionState.EFFECT_UNKNOWN,
        revision=2, updated_at=module._timestamp(prepared_inputs[4].now),
        reason_code="SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
    )
    args["effect_store"]._records[current.operation_id] = current
    reader = module.SandboxReaderPolicy("separate-reader", "reader-v1", "synthetic", "sandbox")
    args["reader_policy"] = reader
    args["verifier_policy"] = module.ReconciliationVerifierPolicy((ApprovedReconciliationVerifier(
        module.VERIFIER_ID, module.sandbox_reconciliation_policy_hash(args["deployment"], reader),
    ),))
    args["provider"] = ReaderProvider(prepared_inputs[4])
    writer, calls = Writer(), []
    operation = dict(
        operation_id="22222222-2222-4222-8222-222222222222",
        event_id=PAYLOAD["event_id"], payload_digest=module.sha256_of_canonical_json(PAYLOAD),
        idempotency_key=artifact.idempotency_key, state="PERSISTED",
    )
    operation.update(changes or {})

    async def connect(host, port, **kwargs):
        calls.append((host, port, kwargs))
        body = json.dumps(operation).encode()
        stream = asyncio.StreamReader(limit=8192)
        stream.feed_data((f"HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\n"
                          f"Content-Length: {len(body)}\r\n\r\n").encode() + body)
        stream.feed_eof()
        return stream, writer

    monkeypatch.setattr(module.asyncio, "open_connection", connect)
    return artifact, args, current, writer, calls


async def reconcile(artifact, args):
    return await module.reconcile_sandbox_effect(artifact, json.dumps(PAYLOAD), **args)


@pytest.mark.asyncio
async def test_independent_get_binds_original_key_and_confirms(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    result = await reconcile(artifact, args)
    assert result.record.state == module.EffectExecutionState.CONFIRMED_EFFECT
    assert result.record.reconciliation_evidence_hash == result.evidence.deterministic_digest()
    assert result.evidence.evidence.observation_digest == module.reconciliation_observation_digest(result.evidence.evidence)
    assert len(calls) == len(writer.writes) == 1
    assert writer.writes[0].startswith(f"GET /v1/operations?idempotency_key={artifact.idempotency_key} HTTP/1.1\r\n".encode())
    assert b"POST" not in writer.writes[0]
    assert writer.aborted
    assert calls[0][2]["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert calls[0][2]["ssl"].check_hostname
    assert args["provider"].calls[0].credential_scope == module.LOOKUP_SCOPE
    assert args["provider"].calls[0].credential_reference_id != args["deployment"].credential_reference_id
    assert TOKEN.decode() not in repr(result)
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    assert len(calls) == 1
    assert await args["consumption_store"].get(artifact.authorization_id) == prepared_inputs[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 503, 401, 302, 201])
async def test_non_200_keeps_unknown(prepared_inputs, monkeypatch, status):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch, status)
    result = await reconcile(artifact, args)
    assert result.record == current and result.evidence is None
    assert await args["effect_store"].get(current.operation_id) == current
    assert len(writer.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("event_id", "other"), ("payload_digest", "0" * 64), ("idempotency_key", "other"),
    ("operation_id", "not-uuid"), ("state", "SUCCESS"), ("secret", "injected"),
])
async def test_external_substitution_never_confirms(prepared_inputs, monkeypatch, field, value):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch, changes={field: value})
    with pytest.raises(module.SandboxReconciliationError) as caught:
        await reconcile(artifact, args)
    assert caught.value.__context__ is None
    assert await args["effect_store"].get(current.operation_id) == current


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["unapproved", "writer", "contract", "source", "lineage", "state", "hash", "durability"])
async def test_untrusted_configuration_or_lineage_prevents_lookup(prepared_inputs, monkeypatch, mode):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    if mode == "unapproved":
        args["verifier_policy"] = module.ReconciliationVerifierPolicy(())
    elif mode == "writer":
        args["reader_policy"] = replace(args["reader_policy"], credential_reference_id=args["deployment"].credential_reference_id)
    elif mode == "contract":
        gov = args["historical_governance_inputs"]
        args["historical_governance_inputs"] = replace(gov, action_contract=replace(gov.action_contract, human_approval_rules={"required": True}))
    elif mode == "source":
        args["issuance_source_inputs"] = replace(args["issuance_source_inputs"], current_endpoint={})
    elif mode == "durability":
        args["allow_in_memory_for_testing"] = False
    else:
        updates = {"lineage": {"authorization_id": "other"}, "state": {"state": module.EffectExecutionState.IN_FLIGHT}, "hash": {"record_hash": "0" * 64}}
        args["effect_store"]._records[current.operation_id] = current.model_copy(update=updates[mode])
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    assert not calls and not writer.writes and not args["provider"].calls


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"revoked": True}, {"credential_scope": "admin"}, {"audience": "https://other.test"}, {"credential_version": "changed"}])
async def test_reader_metadata_fail_closed(prepared_inputs, monkeypatch, changes):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    args["provider"].changes = changes
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    assert not calls and len(args["provider"].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["false", "lost_ack", "readback", "cancel", "tls"])
async def test_failure_never_returns_confirmed_result(prepared_inputs, monkeypatch, mode):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    store = args["effect_store"]
    original = store.confirm_reconciliation

    async def transition(**kwargs):
        if mode == "false":
            return False
        result = await original(**kwargs)
        if mode == "lost_ack":
            raise RuntimeError(TOKEN.decode())
        if mode == "readback":
            store._records[current.operation_id] = current
        return result

    monkeypatch.setattr(store, "confirm_reconciliation", transition)
    if mode in {"cancel", "tls"}:
        async def fail(*args, **kwargs):
            if mode == "cancel":
                raise asyncio.CancelledError(TOKEN.decode())
            raise ssl.SSLError(TOKEN.decode())
        monkeypatch.setattr(module.asyncio, "open_connection", fail)
    error = asyncio.CancelledError if mode == "cancel" else module.SandboxReconciliationError
    with pytest.raises(error) as caught:
        await reconcile(artifact, args)
    assert caught.value.__context__ is None and TOKEN.decode() not in str(caught.value)


@pytest.mark.asyncio
async def test_reconciliation_after_authorization_expiry_is_not_reauthorization(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    old = prepared_inputs[4]
    later = old.now + timedelta(days=1)
    clock = replace(old, now=later, health_checked_at=later, monotonic_seconds=old.monotonic_seconds + 86400)
    args["trusted_clock"] = lambda: clock
    args["provider"] = ReaderProvider(clock)
    result = await reconcile(artifact, args)
    assert result.record.state == module.EffectExecutionState.CONFIRMED_EFFECT
    assert len(writer.writes) == 1 and writer.writes[0].startswith(b"GET ")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["scope", "version", "late_tls", "rollback"])
async def test_post_resolution_and_tls_rechecks(prepared_inputs, monkeypatch, mode):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    if mode in {"scope", "version"}:
        original = args["provider"].resolve

        async def resolve(request, **kwargs):
            response = await original(request, **kwargs)
            field = "credential_scope" if mode == "scope" else "credential_version"
            return response.model_copy(update={"metadata": response.metadata.model_copy(update={field: "changed"})})

        args["provider"].resolve = resolve
    else:
        cell = [prepared_inputs[4]]
        args["trusted_clock"] = lambda: cell[0]
        original_connect = module.asyncio.open_connection

        async def connect(*positional, **kwargs):
            result = await original_connect(*positional, **kwargs)
            delta = 5.01 if mode == "late_tls" else -0.01
            cell[0] = replace(cell[0], now=cell[0].now + timedelta(seconds=delta),
                              monotonic_seconds=cell[0].monotonic_seconds + delta)
            return result

        monkeypatch.setattr(module.asyncio, "open_connection", connect)
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    assert not writer.writes
    assert await args["effect_store"].get(current.operation_id) == current


@pytest.mark.asyncio
async def test_competing_reconcilers_only_one_terminal_transition(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    results = await asyncio.gather(reconcile(artifact, args), reconcile(artifact, args), return_exceptions=True)
    assert sum(isinstance(r, module.SandboxReconciliationResult) for r in results) == 1
    assert sum(isinstance(r, module.SandboxReconciliationError) for r in results) == 1
    assert (await args["effect_store"].get(current.operation_id)).revision == 3


@pytest.mark.asyncio
async def test_real_native_dispatch_to_readonly_reconciliation(prepared_inputs, monkeypatch):
    from veritas_os.tests.test_sandbox_bind_execution import Transport, run
    from veritas_os.tests.test_sandbox_credential_resolution_integration import Provider
    artifact, dispatch_args = await _args(prepared_inputs)
    observation = await run(artifact, dispatch_args, Provider(prepared_inputs, dispatch_args), Transport(dispatch_args))
    assert observation.state == "UNKNOWN"
    _, args, _, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    args["consumption_store"] = dispatch_args["consumption_store"]
    args["effect_store"] = dispatch_args["effect_store"]
    result = await reconcile(artifact, args)
    assert result.record.state == module.EffectExecutionState.CONFIRMED_EFFECT
    assert result.record.consumption_id == observation.consumption_id
    assert len(writer.writes) == 1 and writer.writes[0].startswith(b"GET ")


@pytest.mark.asyncio
async def test_lookup_timeout_retains_unknown_without_resend(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)

    async def timeout(reader):
        raise TimeoutError(TOKEN.decode())

    monkeypatch.setattr(module, "_read_bounded_response", timeout)
    with pytest.raises(module.SandboxReconciliationError) as caught:
        await reconcile(artifact, args)
    assert TOKEN.decode() not in str(caught.value) and caught.value.__context__ is None
    assert len(calls) == len(writer.writes) == 1
    assert await args["effect_store"].get(current.operation_id) == current


@pytest.mark.asyncio
async def test_lost_commit_ack_retains_full_evidence_without_new_lookup(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    store = args["effect_store"]
    commit = store.confirm_reconciliation

    async def lost_ack(**kwargs):
        assert await commit(**kwargs)
        raise RuntimeError(TOKEN.decode())

    monkeypatch.setattr(store, "confirm_reconciliation", lost_ack)
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    archive = await store.get_reconciliation(current.operation_id)
    assert archive.original_record == current
    assert archive.proof.deterministic_digest() == (await store.get(current.operation_id)).reconciliation_evidence_hash
    assert TOKEN.decode() not in archive.model_dump_json()
    assert len(calls) == len(writer.writes) == 1
    with pytest.raises(module.SandboxReconciliationError):
        await reconcile(artifact, args)
    assert len(calls) == 1
