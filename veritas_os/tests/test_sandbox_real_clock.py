"""Opt-in host timing gate with real UTC/monotonic samples and real verifiers.

Run without coverage/profiling: VERITAS_RUN_SANDBOX_TIMING=1 python -m pytest
veritas_os/tests/test_sandbox_real_clock.py -q -s --no-cov
Synthetic provider/health declarations and in-memory stores do not establish
deployment clock authenticity, provider truth, or PostgreSQL latency.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import time

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_credential_resolution as credential
from veritas_os.policy import sandbox_pre_effect as preparation
from veritas_os.policy.native_bind_authorization_consumption import (
    consume_native_bind_authorization,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_native_bind_authorization import _setup
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD, deployment
from veritas_os.tests.test_sandbox_action_binding_integration import (
    issued as issued_fixture,
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("VERITAS_RUN_SANDBOX_TIMING") != "1",
        reason="Host performance gate: explicitly opt in without coverage/profiling",
    ),
]
TOKEN = b"synthetic.real.clock.test.only"
issued = issued_fixture


class _Clock:
    """Sample actual host clocks; health and uncertainty are fixture inputs."""

    def __init__(self, uncertainty=0.0):
        self.readings = []
        self.uncertainty = uncertainty

    def __call__(self):
        now = datetime.now(timezone.utc)
        reading = preparation.SandboxClockReading(
            now, time.monotonic(), now, self.uncertainty
        )
        self.readings.append(reading)
        return reading


class _Provider:
    """Synthetic material only; no network or credential backend is involved."""

    def __init__(self, artifact, mode):
        self.artifact = artifact
        self.mode = mode
        self.calls = []

    async def describe(self, request):
        self.calls.append("describe")
        if self.mode == "slow_describe":
            await asyncio.sleep(5.05)
        self.metadata = credential.SandboxCredentialMetadata(
            **{
                name: getattr(request, name)
                for name in (
                    "credential_reference_id",
                    "credential_provider_type",
                    "credential_version",
                    "credential_scope",
                    "credential_environment",
                    "audience",
                )
            },
            credential_kind="bearer",
            valid_from=self.artifact.valid_from,
            valid_until=self.artifact.valid_until,
            observed_at=datetime.now(timezone.utc).isoformat(),
            revoked=False,
        )
        return self.metadata

    async def resolve(self, request, *, expected_metadata_digest):
        self.calls.append("resolve")
        assert expected_metadata_digest == sha256_of_canonical_json(
            self.metadata.model_dump(mode="json"),
        )
        if self.mode == "slow_resolve":
            await asyncio.sleep(5.05)
        return credential.SandboxProviderCredential(
            metadata=self.metadata,
            material=SecretBytes(TOKEN),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("valid", id="valid-1"),
        pytest.param("valid", id="valid-2"),
        pytest.param("valid", id="valid-3"),
        "slow_source",
        "slow_describe",
        "slow_resolve",
        "uncertain_clock",
        "maximum_uncertainty",
    ],
)
async def test_real_clock_budget_and_fail_closed(
    issued, mode, monkeypatch, record_property
):
    """Measure the complete owning continuation, including fresh risk creation."""
    _, seed = issued
    # Fresh signed fixtures for each run; do not edit timestamps inside artifacts.
    now = datetime.now(timezone.utc)
    artifact, inputs, *_ = _setup(
        seed["governance_inputs"].expected_source,
        seed["governance_inputs"].action_contract,
        now,
    )
    # Existing synthetic issuance places its declared start three seconds ahead.
    # Wait for real UTC to reach it; the verification clock is never frozen/shifted.
    delay = (
        datetime.fromisoformat(artifact.valid_from) - datetime.now(timezone.utc)
    ).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay + 0.01)
    consumed_at = datetime.now(timezone.utc)
    risk, source = _fresh(inputs, consumed_at)
    consumption = preparation.InMemoryAtomicAuthorizationConsumptionStore()
    result = await consume_native_bind_authorization(
        artifact,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        current_source_inputs=source,
        current_runtime_risk_packet=risk,
        now=consumed_at,
        consumption_store=consumption,
        allow_in_memory_for_testing=True,
    )
    clock = _Clock({"uncertain_clock": 0.05, "maximum_uncertainty": 1.0}.get(mode, 0.0))
    effects = preparation.InMemoryAtomicEffectStateStore()
    provider = _Provider(artifact, mode)
    recheck_seconds = []
    load_seconds = []
    completed_clocks = []
    recheck_failures = []
    original = preparation._recheck_sandbox_current

    def measured(**kwargs):
        start = time.perf_counter()
        try:
            result = original(**kwargs)
            completed_clocks.append(result[1])
            return result
        except preparation.SandboxPreEffectError as exc:
            # Record only allowlisted fixed codes, never a provider's message.
            cause = str(exc.__context__)
            recheck_failures.append(
                cause
                if cause
                in {
                    "SPE_RECHECK_DELAY_OR_ROLLBACK",
                    "SPE_FRESH_RISK_REQUIRED",
                    "SPE_AUTHORIZATION_OUTSIDE_TIME_WINDOW",
                    "PRRR_REVIEW_NOT_CURRENT",
                }
                else type(exc.__context__).__name__
            )
            raise
        finally:
            recheck_seconds.append(time.perf_counter() - start)

    def load(checked_at):
        start = time.perf_counter()
        if mode == "slow_source":
            time.sleep(1.05)
        risk, source = _fresh(inputs, checked_at)
        load_seconds.append(time.perf_counter() - start)
        return preparation.SandboxCurrentInputs(
            source, inputs["governance_inputs"], risk
        )

    # Observation wrappers always call the real verifier; no accepting mock.
    monkeypatch.setattr(preparation, "_recheck_sandbox_current", measured)
    monkeypatch.setattr(credential, "_recheck_sandbox_current", measured)
    start = time.perf_counter()
    resolved = None
    error = None
    try:
        resolved = await credential.prepare_and_resolve_sandbox_credential(
            artifact,
            json.dumps(PAYLOAD),
            deployment=deployment(),
            issuance_source_inputs=inputs["source_inputs"],
            governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            consumption_store=consumption,
            effect_store=effects,
            trusted_clock=clock,
            load_current_inputs=load,
            provider=provider,
            allow_in_memory_for_testing=True,
        )
    except credential.SandboxCredentialResolutionError as exc:
        error = exc
    elapsed = time.perf_counter() - start
    measurement = {
        "case": mode,
        "outcome": "resolved" if resolved else "rejected",
        "continuation_seconds": round(elapsed, 6),
        "recheck_seconds": [round(x, 6) for x in recheck_seconds],
        "recheck_failures": recheck_failures,
        "source_load_seconds": [round(x, 6) for x in load_seconds],
        "provider_calls": provider.calls,
        "declared_uncertainty_seconds": clock.uncertainty,
    }
    if resolved is not None:
        descriptor_age = (
            completed_clocks[-1].monotonic_seconds
            - completed_clocks[0].monotonic_seconds
        )
        measurement["descriptor_age_seconds"] = round(descriptor_age, 6)
    record_property("sandbox_timing", json.dumps(measurement))
    try:
        assert (
            await consumption.get(artifact.authorization_id)
            == result.consumption_record
        )
        assert await effects.get(result.consumption_record.consumption_id) is not None
        assert all(
            b.now > a.now and b.monotonic_seconds > a.monotonic_seconds
            for a, b in zip(clock.readings, clock.readings[1:], strict=False)
        )
        if mode in ("valid", "uncertain_clock", "maximum_uncertainty"):
            assert error is None and resolved is not None, measurement
            assert resolved.material.get_secret_value() == TOKEN
            assert len(recheck_seconds) == 3 and max(recheck_seconds) <= 1
            assert 0 < descriptor_age <= 5
            assert provider.calls == ["describe", "resolve"]
        else:
            assert resolved is None and error is not None, measurement
            assert error.__context__ is None
            expected = {
                "slow_source": [],
                "slow_describe": ["describe"],
                "slow_resolve": ["describe", "resolve"],
            }
            assert provider.calls == expected[mode]
            assert elapsed >= (1 if mode == "slow_source" else 5)
    finally:
        if resolved is not None:
            resolved.close()
