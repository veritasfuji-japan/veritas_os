"""Exclusive, no-effect sandbox preparation using independent trusted inputs.

An IN_FLIGHT row is a permanent attempt claim, not permission to dispatch. This
module never consumes, resolves credentials, invokes Bind or creates receipts.
Failures after claim leave the row intact; recovery cannot acquire it again.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
import math
from typing import Any, Callable

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState, EffectStateRecord, InMemoryAtomicEffectStateStore,
    PostgresAtomicEffectStateStore, _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs, RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _validate_governance_for_verified_context,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs, NativeBindAuthorizationArtifact,
    _VerifiedContext, _supported_approval_rules, _verified_source,
    verify_native_bind_authorization,
)
from veritas_os.policy.sandbox_action_binding import (
    ACTION, SandboxDeployment, VerifiedSandboxActionBinding,
    build_sandbox_action_binding, verify_sandbox_action_binding,
)
from veritas_os.security.hash import sha256_of_canonical_json


class SandboxPreEffectError(ValueError):
    """Sanitized preparation error; never a retry authorization."""


def _sandbox_business_event_key(
    canonical_payload_json: str, deployment: SandboxDeployment,
) -> str:
    """Scope one immutable business-event identity to the exact sandbox target.

    The message and authorization/idempotency identifiers are deliberately not
    part of this key. A replacement authorization for the same event UUID cannot
    escape the durable claim by changing payload text or authorization identity.
    """
    try:
        payload = json.loads(canonical_payload_json)
        event_id = payload["event_id"]
        if type(event_id) is not str:
            raise ValueError("event id")
    except Exception:
        raise SandboxPreEffectError("SPE_BUSINESS_EVENT_IDENTITY_INVALID") from None
    return "sandbox-business-event:v1:sha256:" + sha256_of_canonical_json({
        "domain": "veritas.sandbox-business-event/v1",
        "action": ACTION,
        "target_system": deployment.target_system,
        "endpoint_url": deployment.endpoint_url,
        "event_id": event_id,
    })


@dataclass(frozen=True)
class SandboxClockReading:
    """Executor clock and health-provider inputs, never request timestamps.

    Authenticity of the host/health provider is a deployment trust assumption.
    Monotonic seconds measure elapsed time; they do not establish UTC truth.
    """

    now: datetime
    monotonic_seconds: float
    health_checked_at: datetime
    uncertainty_seconds: float


@dataclass(frozen=True)
class SandboxCurrentInputs:
    """Fresh independent registry/policy/risk inputs obtained after claiming."""

    source: NativeAuthorizationSourceInputs
    governance: RealBindAuthorizationGovernanceInputs
    runtime_risk_packet: Any


@dataclass(frozen=True)
class SandboxPreparedAttempt:
    """Audit-only result; must not be serialized and reused as a capability."""

    binding: VerifiedSandboxActionBinding
    attempt: EffectStateRecord
    runtime_risk_hash: str
    checked_at: str
    durable_store_used: bool
    authorization: NativeBindAuthorizationArtifact = field(repr=False)
    issued_context: _VerifiedContext = field(repr=False)
    clock: SandboxClockReading = field(repr=False)


def _clock(reading: SandboxClockReading) -> datetime:
    if type(reading) is not SandboxClockReading or any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in (reading.monotonic_seconds, reading.uncertainty_seconds)
    ):
        raise SandboxPreEffectError("SPE_CLOCK_INVALID")
    now = datetime.fromisoformat(_timestamp(reading.now))
    health = datetime.fromisoformat(_timestamp(reading.health_checked_at))
    if not 0 <= (now - health).total_seconds() <= 30 or reading.uncertainty_seconds > 1:
        raise SandboxPreEffectError("SPE_CLOCK_UNHEALTHY")
    return now


def _window(reading: SandboxClockReading, authorization: Any) -> tuple[datetime, datetime]:
    now = _clock(reading)
    delta = timedelta(seconds=reading.uncertainty_seconds)
    lower, upper = now - delta, now + delta
    if not (
        datetime.fromisoformat(authorization.valid_from) <= lower
        and upper < datetime.fromisoformat(authorization.valid_until)
    ):
        raise SandboxPreEffectError("SPE_AUTHORIZATION_OUTSIDE_TIME_WINDOW")
    return lower, upper


async def prepare_sandbox_attempt(
    authorization: Any,
    payload_json: str,
    *,
    deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
    allow_in_memory_for_testing: bool = False,
) -> SandboxPreparedAttempt:
    """Read consumption, permanently claim once, then recheck current governance.

    PostgreSQL is mandatory except explicitly opted-in process-local tests.
    Callbacks are executor-configured trust roots, not supplied by a request.
    The current-input callback is invoked only after the claim commits. Even a
    lost commit acknowledgement stops preparation without releasing the claim.
    No lease, automatic retry, consumption rollback or effect classification is
    provided. A future executor must repeat checks after credential resolution,
    persist dispatch intent and enforce the same ownership at the send boundary.
    """
    durable = (
        type(consumption_store) is PostgresAtomicAuthorizationConsumptionStore
        and type(effect_store) is PostgresAtomicEffectStateStore
    )
    if not durable and not (
        allow_in_memory_for_testing is True
        and type(consumption_store) is InMemoryAtomicAuthorizationConsumptionStore
        and type(effect_store) is InMemoryAtomicEffectStateStore
    ):
        raise SandboxPreEffectError("SPE_DURABLE_STORES_REQUIRED")
    binding = verify_sandbox_action_binding(
        authorization, payload_json, deployment=deployment,
        source_inputs=issuance_source_inputs, governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    business_event_key = _sandbox_business_event_key(
        binding.binding.payload_json, deployment,
    )
    verified = verify_native_bind_authorization(
        authorization, source_inputs=issuance_source_inputs,
        governance_inputs=governance_inputs, trust_inputs=trust_inputs,
    )
    _, _, issued_context = _verified_source(
        verified.source_runtime_risk_packet, issuance_source_inputs, governance_inputs,
    )
    try:
        started = trusted_clock()
        _window(started, verified)
        stored = await consumption_store.get(verified.authorization_id)
    except Exception:
        raise SandboxPreEffectError("SPE_CONSUMPTION_READ_OR_CLOCK_FAILED") from None
    if stored is None:
        raise SandboxPreEffectError("SPE_DURABLE_CONSUMPTION_REQUIRED")
    expected = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=verified.authorization_id,
        live_adapter_bind_authorization_hash=verified.authorization_hash,
        idempotency_key=verified.idempotency_key,
        bind_context_hash=verified.bind_context_hash,
        execution_intent_id=verified.execution_intent_id,
        execution_intent_hash=verified.execution_intent_hash,
        endpoint_identity_binding_digest=issued_context.endpoint_identity_binding_digest,
        credential_reference_digest=issued_context.credential_reference_digest,
        credential_scope_binding_digest=issued_context.credential_scope_binding_digest,
        consumed_at=stored.consumed_at,
    )
    consumed_at = datetime.fromisoformat(_timestamp(stored.consumed_at))
    if stored != expected or not (
        datetime.fromisoformat(verified.valid_from) <= consumed_at <= _clock(started)
        and consumed_at < datetime.fromisoformat(verified.valid_until)
    ):
        raise SandboxPreEffectError("SPE_CONSUMPTION_LINEAGE_MISMATCH")
    attempt = _build_record(
        consumption=expected, state=EffectExecutionState.IN_FLIGHT,
        revision=1, updated_at=_timestamp(started.now),
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    try:
        claimed = await effect_store.create_in_flight(
            attempt, business_event_key=business_event_key,
        )
    except Exception:
        raise SandboxPreEffectError("SPE_CLAIM_FAILED_OR_UNKNOWN") from None
    if claimed is not True:
        # Distinguish replay of the same consumed authorization from a new
        # authorization colliding on the same business event. The unique store
        # claim remains the race arbiter; this read is classification only.
        try:
            existing_attempt = await effect_store.get(attempt.operation_id)
        except Exception:
            raise SandboxPreEffectError("SPE_CLAIM_FAILED_OR_UNKNOWN") from None
        if existing_attempt is not None:
            raise SandboxPreEffectError("SPE_ATTEMPT_ALREADY_EXISTS")
        raise SandboxPreEffectError("SPE_BUSINESS_EVENT_ALREADY_CLAIMED")
    risk_hash, finished = _recheck_sandbox_current(
        verified=verified, binding=binding, issued_context=issued_context,
        payload_json=payload_json, deployment=deployment, started=started,
        trusted_clock=trusted_clock, load_current_inputs=load_current_inputs,
    )
    return SandboxPreparedAttempt(
        binding, attempt, risk_hash, _timestamp(finished.now), durable,
        verified, issued_context, finished,
    )


def _recheck_sandbox_current(
    *,
    verified: NativeBindAuthorizationArtifact,
    binding: VerifiedSandboxActionBinding,
    issued_context: _VerifiedContext,
    payload_json: str,
    deployment: SandboxDeployment,
    started: SandboxClockReading,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
) -> tuple[str, SandboxClockReading]:
    """Repeat the same checks inside an owning call, never from request claims.

    Shared by preparation and its credential continuation. This private helper
    grants no ownership; the continuation must itself create the unique attempt.

    Fresh risk timestamps are causal observation markers from this synchronous
    loader invocation, not independent UTC not-before grants. Reconstruct risk at
    the exact executor sample and require both timestamps to equal that sample.
    Authorization and signed governance still cover the lower uncertainty bound;
    risk and governance must also survive the conservative completion horizon.
    No artifact is backdated and no general verifier accepts clock tolerance.
    """
    try:
        checked = trusted_clock()
        lower, _ = _window(checked, verified)
        if checked.now < started.now or checked.monotonic_seconds < started.monotonic_seconds:
            raise SandboxPreEffectError("SPE_CLOCK_ROLLBACK")
        current = load_current_inputs(checked.now)
        if type(current) is not SandboxCurrentInputs:
            raise SandboxPreEffectError("SPE_CURRENT_INPUTS_REQUIRED")
        gov = replace(current.governance, verification_now=lower)
        if build_sandbox_action_binding(
            payload_json, deployment=deployment, expected_contract=gov.action_contract,
        ) != binding.binding:
            raise SandboxPreEffectError("SPE_ACTION_CHANGED")
        risk, final, context = _verified_source(
            current.runtime_risk_packet, current.source,
            replace(gov, verification_now=checked.now),
        )
        if (
            final.bind_context_hash != verified.bind_context_hash
            or final.exact_bind_context.action_contract_digest != verified.action_contract_digest
            or context != issued_context
            or final.exact_bind_context.gate_packet_hash != verified.source_gate_hash
        ):
            raise SandboxPreEffectError("SPE_CURRENT_CONTEXT_MISMATCH")
        if (
            datetime.fromisoformat(risk.risk_decision.reviewed_at) != checked.now
            or datetime.fromisoformat(risk.recorded_at) != checked.now
        ):
            raise SandboxPreEffectError("SPE_FRESH_RISK_REQUIRED")
        _supported_approval_rules(gov.action_contract.human_approval_rules)
        proof = _validate_governance_for_verified_context(
            context, gov, bind_context_hash=final.bind_context_hash,
        )
        if (
            proof.human_approval_status != verified.human_approval_requirement_status
            or (proof.human_approval_status == "VERIFIED") != risk.required_human_approval
        ):
            raise SandboxPreEffectError("SPE_CURRENT_APPROVAL_MISMATCH")
        # Conservative end horizon covers one second of work plus the maximum
        # permitted one-second clock uncertainty. Check before sampling completion.
        upper = checked.now + timedelta(seconds=2)
        if upper >= datetime.fromisoformat(verified.valid_until):
            raise SandboxPreEffectError("SPE_AUTHORIZATION_OUTSIDE_TIME_WINDOW")
        _verified_source(current.runtime_risk_packet, current.source, replace(gov, verification_now=upper))
        _validate_governance_for_verified_context(
            context, replace(gov, verification_now=upper), bind_context_hash=final.bind_context_hash,
        )
        finished = trusted_clock()
        _window(finished, verified)
        if not (
            0 <= (finished.now - checked.now).total_seconds() <= 1
            and 0 <= finished.monotonic_seconds - checked.monotonic_seconds <= 1
        ):
            raise SandboxPreEffectError("SPE_RECHECK_DELAY_OR_ROLLBACK")
    except Exception:
        # Provider errors can contain private registry/connection details.
        raise SandboxPreEffectError("SPE_RECHECK_FAILED_ATTEMPT_RETAINED") from None
    return risk.packet_hash, finished
