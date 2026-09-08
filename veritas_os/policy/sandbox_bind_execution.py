"""Owning native v2 dispatch seam; no concrete network adapter is installed.

Only executor-configured transports may implement this contract. They must use
TLS, the exact request, no redirects/retries and call take_material immediately
before their sole send. Tests are inert; this module does not certify a transport
or enable a deployment. Durable uncertainty precedes possible external effect.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState, EffectStateRecord, InMemoryAtomicEffectStateStore,
    PostgresAtomicEffectStateStore,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs, RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import NativeAuthorizationSourceInputs
from veritas_os.policy.sandbox_action_binding import SandboxDeployment
from veritas_os.policy.sandbox_credential_resolution import (
    SandboxCredentialProvider, _recheck_owned, _validate_metadata,
    prepare_and_resolve_sandbox_credential,
)
from veritas_os.policy.sandbox_pre_effect import (
    SandboxClockReading, SandboxCurrentInputs, _clock, _window,
)
from veritas_os.security.hash import sha256_of_canonical_json

REQUEST_TIMEOUT_SECONDS = 5


class SandboxBindExecutionError(ValueError):
    """Sanitized failure; consumption and attempt are never released."""


class SandboxDispatchRequest(BaseModel):
    """Exact non-secret request, reconstructed inside the owning call."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    method: Literal["POST"] = "POST"
    endpoint_url: str
    payload_json: str
    payload_digest: str
    idempotency_key: str
    attempt_id: str


class SandboxDispatchTransport(Protocol):
    """Trusted executor seam, not a caller-selectable generic adapter.

The implementation must authenticate the pinned TLS identity, disable redirects,
proxies and retries, bound response size, and never log secrets or exceptions.
It must call take_material once, immediately before sending the exact request,
and stop on callback failure/cancellation. It must not keep the returned material.
Its return is deliberately ignored: acknowledgement is NOT confirmed effect.
A concrete implementation and its timing/TLS tests are a deployment prerequisite.
"""

    async def send_once(
        self, request: SandboxDispatchRequest, *, take_material: Callable[[], SecretBytes],
    ) -> None:
        ...


class SandboxDispatchObservation(BaseModel):
    """Non-secret local observation, not a BindReceipt or consequence proof."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    attempt_id: str
    authorization_id: str
    consumption_id: str
    dispatch_intent_hash: str
    payload_digest: str
    idempotency_key: str
    state: Literal["UNKNOWN"] = "UNKNOWN"
    reason_code: Literal["TRANSPORT_RETURNED_UNVERIFIED", "TRANSPORT_FAILED_OR_UNKNOWN"]


async def execute_sandbox_bind(
    authorization: Any, payload_json: str, *, deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
    provider: SandboxCredentialProvider,
    transport: SandboxDispatchTransport,
    allow_in_memory_for_testing: bool = False,
) -> SandboxDispatchObservation:
    """Own preparation/resolution, persist possible dispatch, then send at most once.

Never accept a caller's resolved credential, prepared result or verified flag.
The existing permanent claim rejects all repeat calls, including after crashes.
CAS acknowledgement loss prevents transport entry; durable EFFECT_UNKNOWN is
never upgraded from an HTTP response. Reconciliation/receipts remain separate.
"""
    resolved = None
    cancelled = False
    try:
        if transport is None:
            raise SandboxBindExecutionError("SBE_TRANSPORT_REQUIRED")
        resolved = await prepare_and_resolve_sandbox_credential(
            authorization, payload_json, deployment=deployment,
            issuance_source_inputs=issuance_source_inputs,
            governance_inputs=governance_inputs, trust_inputs=trust_inputs,
            consumption_store=consumption_store, effect_store=effect_store,
            trusted_clock=trusted_clock, load_current_inputs=load_current_inputs,
            provider=provider, allow_in_memory_for_testing=allow_in_memory_for_testing,
        )
        # Capture before the ownership read and final reconstruction. Storage,
        # reconstruction, CAS and transport setup all share this one-second cap.
        started = trusted_clock()
        _clock(started)
        prepared = await _recheck_owned(
            resolved.preparation, payload_json=payload_json, deployment=deployment,
            effect_store=effect_store, trusted_clock=trusted_clock,
            load_current_inputs=load_current_inputs,
        )
        request = SandboxDispatchRequest(
            endpoint_url=deployment.endpoint_url,
            payload_json=prepared.binding.binding.payload_json,
            payload_digest=prepared.binding.binding.payload_digest,
            idempotency_key=prepared.binding.idempotency_key,
            attempt_id=prepared.attempt.operation_id,
        )

        def check_send_window() -> None:
            now = trusted_clock()
            _window(now, prepared.authorization)
            if not (
                0 <= (now.now - started.now).total_seconds() <= 1
                and 0 <= now.monotonic_seconds - started.monotonic_seconds <= 1
                and now.now >= prepared.clock.now
                and now.monotonic_seconds >= prepared.clock.monotonic_seconds
            ):
                raise SandboxBindExecutionError("SBE_SEND_WINDOW_EXCEEDED")
            _validate_metadata(
                resolved._metadata, resolved._request, resolved._descriptor_started, now,
            )

        check_send_window()
        values = prepared.attempt.model_dump(mode="json")
        values.update(
            state=EffectExecutionState.EFFECT_UNKNOWN.value,
            revision=prepared.attempt.revision + 1,
            updated_at=_timestamp(prepared.clock.now),
            reason_code="SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
        )
        values.pop("record_hash")
        intent = EffectStateRecord(**values, record_hash=sha256_of_canonical_json(values))
        committed = await effect_store.transition(
            operation_id=intent.operation_id,
            expected_state=EffectExecutionState.IN_FLIGHT, record=intent,
        )
        if committed is not True or await effect_store.get(intent.operation_id) != intent:
            raise SandboxBindExecutionError("SBE_DISPATCH_INTENT_NOT_CONFIRMED")
        check_send_window()
        taken = False

        def take_material() -> SecretBytes:
            nonlocal taken
            if taken:
                raise SandboxBindExecutionError("SBE_MATERIAL_ALREADY_TAKEN")
            # A failing first callback cannot be retried after time/state changes.
            taken = True
            check_send_window()
            return resolved.material

        reason = "TRANSPORT_FAILED_OR_UNKNOWN"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                await transport.send_once(request, take_material=take_material)
            if taken:
                reason = "TRANSPORT_RETURNED_UNVERIFIED"
        except asyncio.CancelledError:
            raise
        except Exception:
            # No remote body, header or exception is returned or persisted.
            pass
        return SandboxDispatchObservation(
            attempt_id=intent.operation_id, authorization_id=intent.authorization_id,
            consumption_id=intent.consumption_id, dispatch_intent_hash=intent.record_hash,
            payload_digest=request.payload_digest, idempotency_key=intent.idempotency_key,
            reason_code=reason,
        )
    except asyncio.CancelledError:
        cancelled = True
    except Exception:
        pass
    finally:
        if resolved is not None:
            resolved.close()
    if cancelled:
        raise asyncio.CancelledError()
    raise SandboxBindExecutionError("SBE_FAILED_ATTEMPT_NOT_RELEASED")
