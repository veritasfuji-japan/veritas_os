"""Exclusive, no-effect sandbox preparation using independent trusted inputs.

An IN_FLIGHT row is a permanent attempt claim, not permission to dispatch. This
module never consumes, resolves credentials, invokes Bind or creates receipts.
Failures after claim leave the row intact; recovery cannot acquire it again.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import json
import math
import secrets
import threading
from typing import Any, Callable

from veritas_os.policy.bind_effect_reconciliation import (
    EffectStateRecord, InMemoryAtomicEffectStateStore,
    PostgresAtomicEffectStateStore, _SANDBOX_ORIGIN_CAPABILITY, _build_record,
    _immutable_effect_lineage_digest,
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


_OWNERSHIP_DOMAIN = b"veritas.sandbox-execution-ownership/v1\x00"


def _ownership_digest(secret: bytes) -> str:
    if type(secret) is not bytes or len(secret) != 32:
        raise SandboxPreEffectError("SEO_HANDLE_INVALID")
    return hashlib.sha256(_OWNERSHIP_DOMAIN + secret).hexdigest()


class _SandboxExecutionOwnershipHandle:
    """Process-local linear authority; DB state cannot reconstruct this object."""

    __slots__ = (
        "operation_id", "origin_record_hash", "immutable_lineage_digest",
        "_secret", "_state", "_lock",
    )

    def __init__(self, attempt: EffectStateRecord, secret: bytes) -> None:
        self.operation_id = attempt.operation_id
        self.origin_record_hash = attempt.record_hash
        self.immutable_lineage_digest = _immutable_effect_lineage_digest(attempt)
        self._secret = secret
        self._state = "UNUSED"
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _spend(self) -> bytes:
        with self._lock:
            if self._state != "UNUSED":
                raise SandboxPreEffectError("SEO_HANDLE_ALREADY_SPENT")
            self._state = "SPENT"
            return self._secret

    def __copy__(self):
        raise TypeError("Sandbox execution ownership handle cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Sandbox execution ownership handle cannot be copied")

    def __reduce__(self):
        raise TypeError("Sandbox execution ownership handle cannot be serialized")

    def __reduce_ex__(self, protocol):
        raise TypeError("Sandbox execution ownership handle cannot be serialized")


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
    """Prepared origin plus a private one-shot live execution ownership handle.

    The handle is process-local, non-copyable and non-serializable. Durable
    readback reconstructs audit state only and can never recreate this authority.
    """

    binding: VerifiedSandboxActionBinding
    attempt: EffectStateRecord
    runtime_risk_hash: str
    checked_at: str
    durable_store_used: bool
    authorization: NativeBindAuthorizationArtifact = field(repr=False)
    issued_context: _VerifiedContext = field(repr=False)
    clock: SandboxClockReading = field(repr=False)
    ownership_handle: _SandboxExecutionOwnershipHandle = field(repr=False, compare=False)


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
    ownership_secret = secrets.token_bytes(32)
    ownership_digest = _ownership_digest(ownership_secret)
    try:
        attempt = await effect_store.create_sandbox_pre_dispatch_attempt(
            consumption=expected,
            updated_at=_timestamp(started.now),
            business_event_key=business_event_key,
            ownership_digest=ownership_digest,
            origin_authority=_SANDBOX_ORIGIN_CAPABILITY,
        )
    except Exception:
        # A commit may have succeeded before the acknowledgement was lost.
        # Never reconstruct execution ownership from durable readback.
        raise SandboxPreEffectError("SPE_CLAIM_FAILED_OR_UNKNOWN") from None
    if attempt is None:
        # Existing durable state is classification only and never ownership.
        try:
            existing_attempt = await effect_store.get(expected.consumption_id)
        except Exception:
            raise SandboxPreEffectError("SPE_CLAIM_FAILED_OR_UNKNOWN") from None
        if existing_attempt is not None:
            raise SandboxPreEffectError("SPE_ATTEMPT_ALREADY_EXISTS")
        raise SandboxPreEffectError("SPE_BUSINESS_EVENT_ALREADY_CLAIMED")
    ownership_handle = _SandboxExecutionOwnershipHandle(attempt, ownership_secret)
    risk_hash, finished = _recheck_sandbox_current(
        verified=verified, binding=binding, issued_context=issued_context,
        payload_json=payload_json, deployment=deployment, started=started,
        trusted_clock=trusted_clock, load_current_inputs=load_current_inputs,
    )
    return SandboxPreparedAttempt(
        binding, attempt, risk_hash, _timestamp(finished.now), durable,
        verified, issued_context, finished, ownership_handle,
    )


async def consume_sandbox_ownership(
    prepared: SandboxPreparedAttempt,
    *,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    updated_at: str | None = None,
) -> SandboxPreparedAttempt:
    """Consume the unique live continuation authority exactly once.

    Local spending is irreversible and occurs before the first await. The
    durable CAS races pre-dispatch NO_EFFECT recovery on the same exact origin
    predicate. An ambiguous CAS result never restores the local handle.
    """
    if type(prepared) is not SandboxPreparedAttempt:
        raise SandboxPreEffectError("SEO_HANDLE_REQUIRED")
    handle = prepared.ownership_handle
    if (
        handle.operation_id != prepared.attempt.operation_id
        or handle.origin_record_hash != prepared.attempt.record_hash
        or handle.immutable_lineage_digest
        != _immutable_effect_lineage_digest(prepared.attempt)
    ):
        raise SandboxPreEffectError("SEO_HANDLE_BINDING_MISMATCH")
    secret = handle._spend()
    digest = _ownership_digest(secret)
    try:
        consumed = await effect_store.consume_sandbox_ownership(
            expected=prepared.attempt,
            ownership_digest=digest,
            immutable_lineage_digest=handle.immutable_lineage_digest,
            updated_at=updated_at or prepared.checked_at,
        )
    except Exception:
        raise SandboxPreEffectError("SEO_OWNERSHIP_COMMIT_FAILED_OR_UNKNOWN") from None
    if consumed is not True:
        raise SandboxPreEffectError("SEO_PRE_DISPATCH_ARBITRATION_LOST")
    return prepared


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
