"""J3 timing counterexample: synthetic only, no DNS, TLS or provider effect.

This test deliberately demonstrates a limitation of the current native sandbox
transport. It does NOT establish Strict RC1 conformance or a kernel-level race.
The controlled clock advances synchronously after the final take_material()
check and before the concrete transport's writer.write() call.
"""

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_bind_execution as execution
from veritas_os.policy import sandbox_https_transport as https
from veritas_os.tests.test_sandbox_bind_execution import (
    Provider,
    _args,
    prepared_inputs as prepared_inputs_fixture,
    run,
)
from veritas_os.tests.test_sandbox_https_transport import Writer, TOKEN as HTTP_TOKEN

pytestmark = pytest.mark.slow
prepared_inputs = prepared_inputs_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_ms", [1000, 1001, 2000, 2001])
async def test_j3_post_check_clock_advance_is_not_rechecked_at_write(
    prepared_inputs, monkeypatch, delay_ms
):
    """Observe late write after a valid final check, without claiming a real send."""
    artifact, args = await _args(prepared_inputs)
    cell = [prepared_inputs[4]]
    args["trusted_clock"] = lambda: cell[0]

    provider = Provider(prepared_inputs, args)
    original_resolve = provider.resolve

    async def resolve(request, **kwargs):
        credential = await original_resolve(request, **kwargs)
        return credential.model_copy(update={"material": SecretBytes(HTTP_TOKEN)})

    provider.resolve = resolve

    writer = Writer()
    writes_at = []
    original_write = writer.write

    def record_write(wire):
        writes_at.append(cell[0])
        original_write(wire)

    writer.write = record_write

    connected = False

    async def fake_connect(*_args, **_kwargs):
        nonlocal connected
        connected = True
        reader = asyncio.StreamReader()
        reader.feed_eof()
        return reader, writer

    monkeypatch.setattr(https.asyncio, "open_connection", fake_connect)

    original_get_secret_value = SecretBytes.get_secret_value
    injected = 0
    before_advance = []

    def advance_clock_after_take_material(self):
        nonlocal injected
        raw = original_get_secret_value(self)
        # The concrete HTTPS transport calls this after take_material(), which
        # has already checked the clock, but before writer.write(wire).
        if connected and raw == HTTP_TOKEN and injected == 0:
            injected += 1
            reading = cell[0]
            before_advance.append(reading)
            cell[0] = replace(
                reading,
                now=reading.now + timedelta(milliseconds=delay_ms),
                monotonic_seconds=reading.monotonic_seconds + delay_ms / 1000,
            )
        return raw

    monkeypatch.setattr(
        SecretBytes, "get_secret_value", advance_clock_after_take_material
    )

    transport = https.SandboxHTTPSTransport(
        endpoint_url=args["deployment"].endpoint_url
    )
    observation = await run(artifact, args, provider, transport)

    assert injected == 1, "test must reach the post-check/pre-write seam"
    assert len(before_advance) == 1
    assert len(writes_at) == 1, "current implementation does not recheck at write"
    assert len(writer.writes) == 1
    assert writes_at[0] == cell[0]
    elapsed_ms = (
        writes_at[0].monotonic_seconds - before_advance[0].monotonic_seconds
    ) * 1000
    assert elapsed_ms == pytest.approx(delay_ms, abs=0.001)
    assert observation.state == "UNKNOWN"
    assert observation.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
    stored = await args["effect_store"].get(observation.attempt_id)
    assert stored.state == execution.EffectExecutionState.EFFECT_UNKNOWN

    # Even after a synthetic write, no second execution is authorized.
    with pytest.raises(execution.SandboxBindExecutionError):
        await run(artifact, args, provider, transport)
    assert len(writer.writes) == 1
