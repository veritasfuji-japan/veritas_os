"""TASK-031 integration: current trust is wired into sandbox re-entry."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from veritas_os.policy import sandbox_reentry as module
from veritas_os.policy.bind_effect_reconciliation import EffectExecutionState
from veritas_os.policy.sandbox_credential_resolution import SandboxCredentialMetadata
from veritas_os.policy.sandbox_recovery import SandboxRecoveryResult
from veritas_os.tests.test_native_bind_authorization_consumption import _Revocation
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_pre_effect import (
    issued as issued_fixture,
    prepared_inputs as prepared_fixture,
)

issued = issued_fixture
prepared_inputs = prepared_fixture


class GenerationReader:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def read_current_generation(self):
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


class MetadataReader:
    def __init__(self, now, *, revoked=False, fail=False, version=None):
        self.now = now
        self.revoked = revoked
        self.fail = fail
        self.version = version
        self.calls = 0

    async def describe_current(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider detail must not escape")
        return SandboxCredentialMetadata(
            credential_reference_id=request.credential_reference_id,
            credential_provider_type=request.credential_provider_type,
            credential_version=self.version or request.credential_version,
            credential_scope=request.credential_scope,
            credential_environment=request.credential_environment,
            audience=request.audience,
            credential_kind="bearer",
            valid_from=(self.now - timedelta(minutes=5)).isoformat(),
            valid_until=(self.now + timedelta(minutes=5)).isoformat(),
            observed_at=self.now.isoformat(),
            revoked=self.revoked,
        )


def recovery_result(artifact, record, *, state=EffectExecutionState.CONFIRMED_NO_EFFECT):
    status = {
        EffectExecutionState.CONFIRMED_NO_EFFECT: "CONFIRMED_NO_EFFECT",
        EffectExecutionState.EFFECT_UNKNOWN: "STILL_UNKNOWN",
        EffectExecutionState.CONFIRMED_EFFECT: "CONFIRMED_EFFECT",
    }[state]
    return SandboxRecoveryResult(
        operation_id=record.consumption_id,
        authorization_id=artifact.authorization_id,
        state=state,
        recovery_status=status,
        reason_code="TASK031_SYNTHETIC_RECOVERY_LINEAGE",
    )


async def evaluate(prepared_inputs, *, reader=None, generations=(41, 41), recovery_state=None, current=None):
    artifact, inputs, record, default_current, clock = prepared_inputs
    reader = reader or MetadataReader(clock.now)
    current = current or default_current
    result = await module.evaluate_sandbox_reentry_after_recovery(
        artifact,
        json.dumps(PAYLOAD),
        snapshot_id="snapshot:task031:integration",
        historical_trust_generation=41,
        recovery_result=recovery_result(
            artifact,
            record,
            state=recovery_state or EffectExecutionState.CONFIRMED_NO_EFFECT,
        ),
        deployment=__import__(
            "veritas_os.tests.test_sandbox_action_binding",
            fromlist=["deployment"],
        ).deployment(),
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        trusted_clock=lambda: clock,
        load_current_inputs=lambda _now: current,
        credential_metadata_reader=reader,
        trust_generation_reader=GenerationReader(*generations),
    )
    return result, reader


@pytest.mark.asyncio
async def test_current_governance_and_metadata_only_provider_allow_fresh_authorization_flow(prepared_inputs):
    result, reader = await evaluate(prepared_inputs)
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_REVALIDATED
    assert result.trust_result.new_authorization_eligible is True
    assert result.historical_authorization_reusable is False
    assert result.credential_material_accessed is False
    assert result.external_effect_retry_permitted is False
    assert result.current_governance_digest is not None
    assert result.credential_metadata_digest is not None
    assert reader.calls == 1


@pytest.mark.asyncio
async def test_revoked_current_credential_fails_closed_without_material_resolution(prepared_inputs):
    clock = prepared_inputs[4]
    result, reader = await evaluate(
        prepared_inputs,
        reader=MetadataReader(clock.now, revoked=True),
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.reason_code == "PTC_CREDENTIAL_NOT_CURRENT"
    assert result.trust_result.new_authorization_eligible is False
    assert result.credential_material_accessed is False
    assert reader.calls == 1


@pytest.mark.asyncio
async def test_provider_unavailable_fails_closed(prepared_inputs):
    clock = prepared_inputs[4]
    result, _ = await evaluate(
        prepared_inputs,
        reader=MetadataReader(clock.now, fail=True),
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.reason_code == "PTC_CREDENTIAL_NOT_CURRENT"
    assert result.trust_result.new_authorization_eligible is False


@pytest.mark.asyncio
async def test_credential_version_drift_is_not_current_trust(prepared_inputs):
    clock = prepared_inputs[4]
    result, _ = await evaluate(
        prepared_inputs,
        reader=MetadataReader(clock.now, version="restored-old-version"),
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.reason_code == "PTC_CREDENTIAL_NOT_CURRENT"


@pytest.mark.asyncio
async def test_current_authority_revocation_blocks_before_credential_metadata_access(prepared_inputs):
    current = prepared_inputs[3]
    revoked = replace(
        current,
        governance=replace(
            current.governance,
            authority_revocation_checker=_Revocation(
                current.governance,
                "revoked",
            ),
        ),
    )
    reader = MetadataReader(prepared_inputs[4].now)
    result, reader = await evaluate(
        prepared_inputs,
        reader=reader,
        current=revoked,
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.new_authorization_eligible is False
    assert reader.calls == 0


@pytest.mark.asyncio
async def test_trust_generation_change_during_observation_is_not_revalidated(prepared_inputs):
    result, _ = await evaluate(
        prepared_inputs,
        generations=(41, 42),
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_NOT_REVALIDATED
    assert result.trust_result.reason_code == "PTC_OBSERVATION_GENERATION_STALE"
    assert result.trust_result.new_authorization_eligible is False


@pytest.mark.asyncio
async def test_trust_generation_rollback_fails_closed(prepared_inputs):
    result, _ = await evaluate(
        prepared_inputs,
        generations=(40, 40),
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.reason_code == "PTC_TRUST_GENERATION_ROLLBACK"


@pytest.mark.asyncio
async def test_policy_action_binding_drift_fails_closed_without_credential_read(prepared_inputs):
    current = prepared_inputs[3]
    changed_contract = replace(
        current.governance.action_contract,
        human_approval_rules={"required": False},
    )
    changed = replace(
        current,
        governance=replace(
            current.governance,
            action_contract=changed_contract,
        ),
    )
    reader = MetadataReader(prepared_inputs[4].now)
    result, reader = await evaluate(
        prepared_inputs,
        reader=reader,
        current=changed,
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_INVALID
    assert result.trust_result.new_authorization_eligible is False
    assert reader.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        EffectExecutionState.EFFECT_UNKNOWN,
        EffectExecutionState.CONFIRMED_EFFECT,
    ],
)
async def test_unresolved_or_confirmed_prior_effect_never_becomes_retry_authority(prepared_inputs, state):
    result, _ = await evaluate(
        prepared_inputs,
        recovery_state=state,
    )
    assert result.trust_result.state == module.RecoveryTrustState.TRUST_NOT_REVALIDATED
    assert result.trust_result.reason_code == "PTC_EXTERNAL_EFFECT_NOT_CLEAR_FOR_NEW_EXECUTION"
    assert result.trust_result.new_authorization_eligible is False
    assert result.external_effect_retry_permitted is False
    assert result.historical_authorization_reusable is False


@pytest.mark.asyncio
async def test_recovery_result_must_match_historical_authorization(prepared_inputs):
    artifact, inputs, record, current, clock = prepared_inputs
    bad = SandboxRecoveryResult(
        operation_id=record.consumption_id,
        authorization_id="different-authorization",
        state=EffectExecutionState.CONFIRMED_NO_EFFECT,
        recovery_status="CONFIRMED_NO_EFFECT",
        reason_code="TASK031_SYNTHETIC_RECOVERY_LINEAGE",
    )
    with pytest.raises(module.SandboxReentryError, match="AUTHORIZATION_MISMATCH"):
        await module.evaluate_sandbox_reentry_after_recovery(
            artifact,
            json.dumps(PAYLOAD),
            snapshot_id="snapshot:task031:integration",
            historical_trust_generation=41,
            recovery_result=bad,
            deployment=__import__(
                "veritas_os.tests.test_sandbox_action_binding",
                fromlist=["deployment"],
            ).deployment(),
            issuance_source_inputs=inputs["source_inputs"],
            historical_governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            trusted_clock=lambda: clock,
            load_current_inputs=lambda _now: current,
            credential_metadata_reader=MetadataReader(clock.now),
            trust_generation_reader=GenerationReader(41, 41),
        )
