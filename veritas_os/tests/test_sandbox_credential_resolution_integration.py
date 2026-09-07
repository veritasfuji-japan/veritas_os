"""Owning native call is mandatory; no accepting verifier mocks or real secrets."""

import asyncio
from dataclasses import replace
import json
import traceback

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_credential_resolution as module
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_pre_effect import (
    issued as issued_fixture, prepared_inputs as prepared_inputs_fixture, _args,
)
from veritas_os.tests.test_native_bind_authorization_consumption import _Revocation
from veritas_os.tests.test_sandbox_credential_resolution import TOKEN, metadata

pytestmark = pytest.mark.slow
issued = issued_fixture
prepared_inputs = prepared_inputs_fixture


class Provider:
    """Synthetic trusted adapter with controlled failures, no network or env reads."""

    def __init__(self, fixture, args, mode="valid"):
        self.clock = fixture[4]
        self.args = args
        config = args["deployment"]
        self.metadata = metadata(self.clock.now, **{
            name: getattr(config, name) for name in (
                "credential_reference_id", "credential_provider_type", "credential_version",
                "credential_scope", "credential_environment",
            )
        })
        self.calls = []
        self.mode = mode

    async def describe(self, request):
        self.calls.append(("describe", request))
        assert await self.args["effect_store"].get(request.attempt_id) is not None
        if self.mode == "bad_metadata":
            return self.metadata.model_copy(update={"credential_scope": "admin"})
        if self.mode == "missing_metadata":
            return None
        if self.mode == "invalid_metadata_shape":
            return self.metadata.model_copy(update={"revoked": TOKEN.decode()})
        if self.mode == "read_error":
            raise RuntimeError(TOKEN.decode())
        if self.mode == "lost_owner_before_resolve":
            self.args["effect_store"]._records.clear()
        return self.metadata

    async def resolve(self, request, *, expected_metadata_digest):
        self.calls.append(("resolve", request))
        assert expected_metadata_digest == sha256_of_canonical_json(self.metadata.model_dump(mode="json"))
        if self.mode == "resolve_error":
            raise RuntimeError(TOKEN.decode())
        if self.mode == "cancel":
            raise asyncio.CancelledError(TOKEN.decode())
        if self.mode == "lost_owner_after_resolve":
            self.args["effect_store"]._records.clear()
        actual = self.metadata
        if self.mode == "substitution":
            actual = actual.model_copy(update={"credential_version": "2"})
        if self.mode == "revoked_during_resolve":
            actual = actual.model_copy(update={"revoked": True})
        if self.mode == "expired_during_resolve":
            actual = actual.model_copy(update={"valid_until": self.clock.now.isoformat()})
        token = TOKEN
        if self.mode == "bad_material":
            token = b"header\r\ninjection"
        if self.mode == "empty_material":
            token = b""
        if self.mode == "oversize_material":
            token = b"x" + b"=" * 4096
        return module.SandboxProviderCredential(metadata=actual, material=SecretBytes(token))


async def resolve(artifact, args, provider):
    return await module.prepare_and_resolve_sandbox_credential(
        artifact, json.dumps(PAYLOAD), provider=provider, **args,
    )


@pytest.mark.asyncio
async def test_only_owning_call_resolves_once_without_receipts_or_dispatch(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    result = await resolve(artifact, args, provider)
    assert [x[0] for x in provider.calls] == ["describe", "resolve"]
    request = provider.calls[0][1]
    assert request == provider.calls[1][1]
    assert request.authorization_id == artifact.authorization_id
    assert request.credential_reference_id == args["deployment"].credential_reference_id
    assert result.material.get_secret_value() == TOKEN
    assert result.preparation.binding.idempotency_key == artifact.idempotency_key
    assert result.preparation.attempt == await args["effect_store"].get(request.attempt_id)
    with pytest.raises(ValueError):
        await resolve(artifact, args, provider)
    assert len(provider.calls) == 2
    result.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected_calls", [
    ("bad_metadata", 1), ("missing_metadata", 1), ("invalid_metadata_shape", 1), ("read_error", 1),
    ("resolve_error", 2), ("substitution", 2), ("revoked_during_resolve", 2),
    ("expired_during_resolve", 2), ("bad_material", 2),
    ("empty_material", 2), ("oversize_material", 2),
])
async def test_failures_never_return_material_or_release_attempt(prepared_inputs, mode, expected_calls, caplog, recwarn):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args, mode)
    with pytest.raises(module.SandboxCredentialResolutionError) as caught:
        await resolve(artifact, args, provider)
    assert len(provider.calls) == expected_calls
    assert caught.value.__context__ is None
    assert TOKEN.decode() not in "".join(traceback.format_exception(caught.value)) + caplog.text
    assert TOKEN.decode() not in "".join(str(w.message) for w in recwarn)
    assert await args["effect_store"].get(prepared_inputs[2].consumption_id) is not None
    assert await args["consumption_store"].get(artifact.authorization_id) == prepared_inputs[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected_calls", [
    ("lost_owner_before_resolve", 1), ("lost_owner_after_resolve", 2),
])
async def test_ownership_is_read_before_and_after_material_resolution(prepared_inputs, mode, expected_calls):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args, mode)
    with pytest.raises(ValueError):
        await resolve(artifact, args, provider)
    assert len(provider.calls) == expected_calls


@pytest.mark.asyncio
async def test_cancelled_provider_leaves_attempt_and_does_not_leak_message(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args, "cancel")
    with pytest.raises(asyncio.CancelledError) as caught:
        await resolve(artifact, args, provider)
    assert not caught.value.args and caught.value.__context__ is None
    assert await args["effect_store"].get(prepared_inputs[2].consumption_id) is not None


@pytest.mark.asyncio
async def test_preexisting_audit_preparation_does_not_allow_secret_access(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    await module.prepare_sandbox_attempt(artifact, json.dumps(PAYLOAD), **args)
    provider = Provider(prepared_inputs, args)
    with pytest.raises(ValueError):
        await resolve(artifact, args, provider)
    assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("after", ["describe", "resolve"])
async def test_current_revocation_is_rechecked_around_material_access(prepared_inputs, after):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    original = args["load_current_inputs"]

    def load(now):
        current = original(now)
        if after in [call[0] for call in provider.calls]:
            current = replace(current, governance=replace(current.governance,
                authority_revocation_checker=_Revocation(current.governance, "revoked")))
        return current

    args["load_current_inputs"] = load
    with pytest.raises(ValueError):
        await resolve(artifact, args, provider)
    assert len(provider.calls) == (1 if after == "describe" else 2)


@pytest.mark.asyncio
async def test_missing_provider_fails_before_claim(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    with pytest.raises(ValueError):
        await resolve(artifact, args, None)
    assert not args["effect_store"]._records


@pytest.mark.asyncio
async def test_provider_timeout_never_retries(prepared_inputs, monkeypatch):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    describe = provider.describe

    async def stalled(request):
        await describe(request)
        await asyncio.Event().wait()

    provider.describe = stalled
    monkeypatch.setattr(module, "PROVIDER_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ValueError):
        await resolve(artifact, args, provider)
    assert len(provider.calls) == 1
    assert args["effect_store"]._records


@pytest.mark.asyncio
async def test_competing_resolvers_read_material_only_once(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    results = await asyncio.gather(
        resolve(artifact, args, provider), resolve(artifact, args, provider),
        return_exceptions=True,
    )
    assert sum(isinstance(x, module.SandboxResolvedCredential) for x in results) == 1
    assert sum(isinstance(x, module.SandboxCredentialResolutionError) for x in results) == 1
    assert [x[0] for x in provider.calls] == ["describe", "resolve"]
    for result in results:
        if isinstance(result, module.SandboxResolvedCredential):
            result.close()
