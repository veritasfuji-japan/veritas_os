"""Causal risk observations do not relax signed UTC validity boundaries.

All artifacts/providers are synthetic. Production source, signature and policy
verifiers run unchanged; observation wrappers never supply accepting results.
"""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from veritas_os.policy import sandbox_pre_effect as module
from veritas_os.policy.native_bind_authorization import _verified_source
from veritas_os.tests import test_live_adapter_bind_authorization as crypto
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh
from veritas_os.tests.test_sandbox_pre_effect import (
    _args,
    _prepare,
    issued as issued_fixture,
    prepared_inputs as prepared_inputs_fixture,
)
from veritas_os.tests.test_sandbox_credential_resolution_integration import (
    Provider,
    resolve,
)

pytestmark = pytest.mark.slow
issued = issued_fixture
prepared_inputs = prepared_inputs_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,offset,accepted",
    [
        ("signed_at", 0.0, True),
        ("signed_at", 0.000001, False),
        ("signed_at", 0.05, False),
        ("expiry", -0.000001, False),
        ("expiry", 0.0, False),
        ("expiry", 0.000001, True),
    ],
)
async def test_real_signed_authority_must_cover_lower_and_upper_bounds(
    prepared_inputs,
    mode,
    offset,
    accepted,
    monkeypatch,
):
    """A fresh risk observation cannot make a future/expired signed grant valid."""
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    current = prepared_inputs[3]
    _, _, context = _verified_source(
        current.runtime_risk_packet,
        current.source,
        replace(current.governance, verification_now=clock.now),
    )
    lower = clock.now - timedelta(seconds=clock.uncertainty_seconds)
    upper = clock.now + timedelta(seconds=2)
    monkeypatch.setattr(crypto, "source_packet", lambda: context)
    monkeypatch.setattr(
        crypto,
        "VERIFICATION_NOW",
        lower + timedelta(seconds=offset) if mode == "signed_at" else lower,
    )
    # The existing helper generates and signs an explicitly synthetic grant.
    monkeypatch.setattr(
        crypto,
        "SOURCE_RECORDED_AT",
        upper + timedelta(seconds=offset) - timedelta(days=1)
        if mode == "expiry"
        else clock.now,
    )
    bundle = crypto._authority_bundle(current.governance.action_contract)
    governance = replace(
        current.governance,
        **dict(
            zip(
                [
                    "signed_authority_evidence_artifact",
                    "authority_signature_verifier",
                    "authority_signer_policy",
                    "authority_verifier_policy",
                    "authority_revocation_checker",
                    "authority_revocation_policy",
                ],
                bundle,
                strict=True,
            )
        ),
    )
    args["load_current_inputs"] = lambda now: replace(current, governance=governance)
    if accepted:
        await _prepare(artifact, args)
    else:
        with pytest.raises(
            module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"
        ) as caught:
            await _prepare(artifact, args)
        assert "AUTHORITY" in str(caught.value.__context__)
    await _assert_retained(artifact, args, prepared_inputs)


async def _uncertain_args(fixture, uncertainty=0.05):
    artifact, args = await _args(fixture)
    clock = replace(fixture[4], uncertainty_seconds=uncertainty)
    args["trusted_clock"] = lambda: clock
    return artifact, args, clock


async def _assert_retained(artifact, args, fixture):
    record = fixture[2]
    assert await args["consumption_store"].get(artifact.authorization_id) == record
    attempt = await args["effect_store"].get(record.consumption_id)
    assert (
        attempt is not None and attempt.state == module.EffectExecutionState.IN_FLIGHT
    )
    with pytest.raises(module.SandboxPreEffectError, match="ATTEMPT_ALREADY_EXISTS"):
        await _prepare(artifact, args)


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertainty", [0.0, 0.000001, 0.05, 1.0])
async def test_causal_risk_accepts_without_backdating_or_relaxing_governance(
    prepared_inputs,
    uncertainty,
    monkeypatch,
):
    artifact, args, clock = await _uncertain_args(prepared_inputs, uncertainty)
    current = prepared_inputs[3]
    before = current.runtime_risk_packet.model_dump(mode="json")
    times = []
    original = module._validate_governance_for_verified_context

    def observe(context, governance, **kwargs):
        times.append(governance.verification_now)
        return original(context, governance, **kwargs)

    monkeypatch.setattr(module, "_validate_governance_for_verified_context", observe)
    result = await _prepare(artifact, args)
    assert times == [
        clock.now - timedelta(seconds=uncertainty),
        clock.now + timedelta(seconds=2),
    ]
    assert result.runtime_risk_hash == current.runtime_risk_packet.packet_hash
    assert current.runtime_risk_packet.model_dump(mode="json") == before
    assert datetime.fromisoformat(before["recorded_at"]) == clock.now
    assert datetime.fromisoformat(before["risk_decision"]["reviewed_at"]) == clock.now
    await _assert_retained(artifact, args, prepared_inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-0.05, -0.000001, 0.000001, 0.05])
async def test_rebuilt_risk_within_uncertainty_is_not_a_fresh_observation(
    prepared_inputs,
    offset,
):
    """Even fully rebuilt/rehashed packets must match this exact invocation."""
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    risk, source = _fresh(prepared_inputs[1], clock.now + timedelta(seconds=offset))
    args["load_current_inputs"] = lambda now: replace(
        prepared_inputs[3],
        runtime_risk_packet=risk,
        source=source,
    )
    with pytest.raises(
        module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"
    ):
        await _prepare(artifact, args)
    await _assert_retained(artifact, args, prepared_inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining", [0.01, 1.0, 2.0, 2.000001])
async def test_fresh_risk_must_survive_full_completion_horizon(
    prepared_inputs, remaining
):
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    risk, source = _fresh(
        prepared_inputs[1],
        clock.now,
        valid_until=(clock.now + timedelta(seconds=remaining)).isoformat(),
    )
    args["load_current_inputs"] = lambda now: replace(
        prepared_inputs[3],
        runtime_risk_packet=risk,
        source=source,
    )
    if remaining > 2:
        result = await _prepare(artifact, args)
        assert result.runtime_risk_hash == risk.packet_hash
    else:
        with pytest.raises(
            module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"
        ):
            await _prepare(artifact, args)
    await _assert_retained(artifact, args, prepared_inputs)


def test_general_verifier_still_rejects_future_risk_at_lower_bound(prepared_inputs):
    """No global tolerance or caller-supplied already-verified bypass is added."""
    current, clock = prepared_inputs[3:5]
    with pytest.raises(ValueError, match="PRRR_REVIEW_NOT_CURRENT"):
        _verified_source(
            current.runtime_risk_packet,
            current.source,
            replace(
                current.governance,
                verification_now=clock.now - timedelta(microseconds=1),
            ),
        )


@pytest.mark.asyncio
async def test_current_recording_does_not_refresh_an_older_review(prepared_inputs):
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    risk, source = _fresh(
        prepared_inputs[1],
        clock.now,
        reviewed_at=(clock.now - timedelta(microseconds=1)).isoformat(),
    )
    args["load_current_inputs"] = lambda now: replace(
        prepared_inputs[3],
        runtime_risk_packet=risk,
        source=source,
    )
    with pytest.raises(
        module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"
    ) as caught:
        await _prepare(artifact, args)
    assert str(caught.value.__context__) == "SPE_FRESH_RISK_REQUIRED"
    await _assert_retained(artifact, args, prepared_inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["utc_rollback", "monotonic_rollback", "utc_delay", "monotonic_delay", "unhealthy"],
)
async def test_nonzero_uncertainty_does_not_hide_clock_failures(prepared_inputs, mode):
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    changes = {
        "utc_rollback": dict(
            now=clock.now - timedelta(microseconds=1),
            health_checked_at=clock.now - timedelta(microseconds=1),
        ),
        "monotonic_rollback": dict(
            monotonic_seconds=clock.monotonic_seconds - 0.000001
        ),
        "utc_delay": dict(now=clock.now + timedelta(seconds=1.000001)),
        "monotonic_delay": dict(monotonic_seconds=clock.monotonic_seconds + 1.000001),
        "unhealthy": dict(uncertainty_seconds=1.000001),
    }
    readings = iter([clock, clock, replace(clock, **changes[mode])])
    args["trusted_clock"] = lambda: next(readings)
    with pytest.raises(
        module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"
    ):
        await _prepare(artifact, args)
    args["trusted_clock"] = lambda: clock
    await _assert_retained(artifact, args, prepared_inputs)


@pytest.mark.parametrize(
    "edge,offset,accepted",
    [
        ("valid_from", -0.05, True),
        ("valid_from", -0.049999, False),
        ("valid_until", 0.05, False),
        ("valid_until", 0.050001, True),
    ],
)
def test_authorization_interval_edges_are_not_clock_tolerances(
    prepared_inputs,
    edge,
    offset,
    accepted,
):
    artifact = prepared_inputs[0]
    clock = replace(prepared_inputs[4], uncertainty_seconds=0.05)
    # Exercise the interval predicate, not signature admission of this copy.
    boundary = artifact.model_copy(
        update={edge: (clock.now + timedelta(seconds=offset)).isoformat()}
    )
    if accepted:
        module._window(clock, boundary)
    else:
        with pytest.raises(module.SandboxPreEffectError, match="OUTSIDE_TIME_WINDOW"):
            module._window(clock, boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertainty", [0.05, 1.0])
async def test_owning_credential_chain_supports_nonzero_uncertainty(
    prepared_inputs, uncertainty
):
    artifact, args, _ = await _uncertain_args(prepared_inputs, uncertainty)
    provider = Provider(prepared_inputs, args)
    result = await resolve(artifact, args, provider)
    try:
        assert [call[0] for call in provider.calls] == ["describe", "resolve"]
        assert result.preparation.clock.uncertainty_seconds == uncertainty
        await _assert_retained(artifact, args, prepared_inputs)
    finally:
        result.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("after", ["describe", "resolve"])
async def test_later_recheck_rejects_rehashed_risk_with_wrong_observation_time(
    prepared_inputs, after
):
    artifact, args, clock = await _uncertain_args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    risk, source = _fresh(prepared_inputs[1], clock.now - timedelta(microseconds=1))

    def load(now):
        current = prepared_inputs[3]
        if after in [call[0] for call in provider.calls]:
            return replace(current, runtime_risk_packet=risk, source=source)
        return current

    args["load_current_inputs"] = load
    with pytest.raises(ValueError, match="SCR_FAILED_ATTEMPT_NOT_RELEASED"):
        await resolve(artifact, args, provider)
    assert len(provider.calls) == (1 if after == "describe" else 2)
    await _assert_retained(artifact, args, prepared_inputs)
