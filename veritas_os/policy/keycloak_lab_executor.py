"""Own one governed role grant in a disposable, loopback-only Keycloak lab."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import re
import ssl
from typing import Any, Awaitable, Callable, Literal
from urllib.parse import urlsplit

from pydantic import SecretBytes

from veritas_os.policy.bind_coverage_registry import (
    KEYCLOAK_LAB_SCOPE,
    match_frozen_runtime_boundary,
)
from veritas_os.policy.bind_execution_capability import (
    ImmutableFinalDispatch,
    PermitBinding,
    _mint_bound_execution_permit,
    canonical_headers,
    consume_bound_execution_permit,
    runtime_implementation_identity,
)
from veritas_os.policy.keycloak_dispatch_reservation import (
    _verify_keycloak_dispatch,
    reserve_and_commit_keycloak_dispatch,
)
from veritas_os.policy.keycloak_role_grant_binding import ACTION, KeycloakLabDeployment
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import NativeAuthorizationSourceInputs
from veritas_os.policy.native_bind_authorization_consumption import (
    _recheck_native_consumption_inputs,
    consume_native_bind_authorization,
)
from veritas_os.policy.sandbox_pre_effect import (
    SandboxClockReading,
    SandboxCurrentInputs,
    _window,
)
from veritas_os.security.hash import sha256_of_canonical_json

_BOUNDARY = "native-v2-keycloak-loopback-lab"
_REQUEST_TIMEOUT = 5


class KeycloakLabExecutionError(ValueError):
    """Sanitized pre-dispatch error. Consumption is never released."""


@dataclass(frozen=True)
class KeycloakLabWriterCredential:
    """Short-lived material returned by the lab's trusted writer resolver."""

    material: SecretBytes
    reference_digest: str
    scope_digest: str
    expires_at: datetime


@dataclass(frozen=True)
class KeycloakLabDispatchObservation:
    """Local transport observation; the effect evidence remains read-only."""

    operation_id: str
    observation: Literal["HTTP_204_UNVERIFIED", "TRANSPORT_UNKNOWN"]


class KeycloakLabExecutor:
    """One fixed TLS peer and role assignment, with no request-selected transport."""

    def __init__(
        self,
        deployment: KeycloakLabDeployment,
        *,
        trusted_clock: Callable[[], SandboxClockReading],
        load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
        resolve_writer: Callable[[], Awaitable[KeycloakLabWriterCredential]],
    ) -> None:
        if type(deployment) is not KeycloakLabDeployment:
            raise KeycloakLabExecutionError("KGR_LAB_DEPLOYMENT_REQUIRED")
        self._deployment = deployment
        self._clock = trusted_clock
        self._load_current_inputs = load_current_inputs
        self._resolve_writer = resolve_writer
        # Reviewed lab roots only. The socket is loopback, but server identity
        # still has to match the signed HTTPS hostname.
        self._tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._tls.load_verify_locations(cadata=deployment.ca_pem)
        self._tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self._tls.set_alpn_protocols(["http/1.1"])

    async def execute(
        self,
        authorization: Any,
        *,
        event_id: str,
        attempt_id: str,
        issuance_source_inputs: NativeAuthorizationSourceInputs,
        governance_inputs: RealBindAuthorizationGovernanceInputs,
        trust_inputs: BindAuthorizationTrustInputs,
    ) -> KeycloakLabDispatchObservation | None:
        """Consume, commit, recheck, then attempt the fixed POST once.

        Returning None means no commit acknowledgement was obtained. Any
        post-commit transport result leaves reconciliation to an independent
        reader. This method never accepts an existing reservation or credential.
        """
        try:
            return await self._execute(
                authorization,
                event_id=event_id,
                attempt_id=attempt_id,
                issuance_source_inputs=issuance_source_inputs,
                governance_inputs=governance_inputs,
                trust_inputs=trust_inputs,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            raise KeycloakLabExecutionError("KGR_LAB_EXECUTION_STOPPED") from None

    async def _execute(
        self,
        authorization: Any,
        *,
        event_id: str,
        attempt_id: str,
        issuance_source_inputs: NativeAuthorizationSourceInputs,
        governance_inputs: RealBindAuthorizationGovernanceInputs,
        trust_inputs: BindAuthorizationTrustInputs,
    ) -> KeycloakLabDispatchObservation | None:
        entry = match_frozen_runtime_boundary(
            self,
            effect_boundary_id=_BOUNDARY,
            dispatch_kind="ACTION",
            proof_scope=KEYCLOAK_LAB_SCOPE,
        )
        deployment = self._deployment
        request = dict(
            target=deployment.target,
            event_id=event_id,
            attempt_id=attempt_id,
            deployment_policy_digest=deployment.digest(),
            authorization=authorization,
            source_inputs=issuance_source_inputs,
            governance_inputs=governance_inputs,
            trust_inputs=trust_inputs,
        )
        verified, binding = _verify_keycloak_dispatch(**request)
        initial = self._clock()
        _window(initial, verified)
        current = self._load_current_inputs(initial.now)
        if type(current) is not SandboxCurrentInputs:
            raise KeycloakLabExecutionError("KGR_LAB_CURRENT_INPUTS_REQUIRED")
        if verified.human_approval_requirement_status != "VERIFIED":
            raise KeycloakLabExecutionError("KGR_LAB_HUMAN_APPROVAL_REQUIRED")
        _, context, _ = _recheck_native_consumption_inputs(
            verified,
            governance_inputs=current.governance,
            current_source_inputs=current.source,
            current_runtime_risk_packet=current.runtime_risk_packet,
            current=initial.now,
        )
        if (
            current.source.current_credential_reference.get("credential_reference_id")
            != deployment.writer_reference_id
            or current.source.required_credential_scope != deployment.writer_scope
        ):
            raise KeycloakLabExecutionError("KGR_LAB_CREDENTIAL_SCOPE_MISMATCH")
        consumed = await consume_native_bind_authorization(
            authorization,
            issuance_source_inputs=issuance_source_inputs,
            governance_inputs=governance_inputs,
            trust_inputs=trust_inputs,
            current_source_inputs=current.source,
            current_runtime_risk_packet=current.runtime_risk_packet,
            now=initial.now,
            consumption_store=PostgresAtomicAuthorizationConsumptionStore(),
        )
        async with asyncio.timeout(_REQUEST_TIMEOUT):
            credential = await self._resolve_writer()
        if (
            type(credential) is not KeycloakLabWriterCredential
            or type(credential.material) is not SecretBytes
            or credential.reference_digest != context.credential_reference_digest
            or credential.scope_digest != context.credential_scope_binding_digest
            or credential.expires_at.utcoffset() is None
        ):
            raise KeycloakLabExecutionError("KGR_LAB_CREDENTIAL_INVALID")

        def recheck() -> None:
            started = self._clock()
            _window(started, verified)
            fresh = self._load_current_inputs(started.now)
            if type(fresh) is not SandboxCurrentInputs:
                raise KeycloakLabExecutionError("KGR_LAB_CURRENT_INPUTS_REQUIRED")
            risk, _, _ = _recheck_native_consumption_inputs(
                verified,
                governance_inputs=fresh.governance,
                current_source_inputs=fresh.source,
                current_runtime_risk_packet=fresh.runtime_risk_packet,
                current=started.now,
            )
            finished = self._clock()
            _, latest = _window(finished, verified)
            if (
                started.now < initial.now
                or started.monotonic_seconds < initial.monotonic_seconds
                or not 0 <= (finished.now - started.now).total_seconds() <= 1
                or not 0 <= finished.monotonic_seconds - started.monotonic_seconds <= 1
                or latest >= datetime.fromisoformat(risk.risk_decision.valid_until)
                or credential.expires_at <= latest
            ):
                raise KeycloakLabExecutionError("KGR_LAB_SEND_WINDOW_INVALID")

        recheck()
        effect = await reserve_and_commit_keycloak_dispatch(
            **request,
            consumption=consumed.consumption_record,
        )
        if effect is None:
            return None

        runtime = runtime_implementation_identity(self)
        identity = sha256_of_canonical_json(
            {
                "endpoint": binding.endpoint_url,
                "body_digest": binding.body_digest,
                "business_event": binding.business_event_key,
                "method": "POST",
            }
        )
        dispatch = ImmutableFinalDispatch(
            effect_boundary_id=_BOUNDARY,
            dispatch_kind="ACTION",
            method="POST",
            canonical_endpoint=binding.endpoint_url,
            canonical_bound_headers=canonical_headers(
                {"content-type": "application/json"}
            ),
            body_bytes=binding.body,
            body_digest=binding.body_digest,
            request_identity=identity,
            idempotency_identity=binding.business_event_key,
            credential_reference_digest=context.credential_reference_digest,
            credential_scope_digest=context.credential_scope_binding_digest,
            authorization_consumption_id=effect.consumption_id,
            runtime_implementation_identity=runtime,
        )
        permit_binding = PermitBinding(
            coverage_entry_id=entry.coverage_entry_id,
            operation_id=effect.operation_id,
            action_class=ACTION,
            dispatch_kind="ACTION",
            execution_intent_hash=verified.execution_intent_hash,
            authorization_id=verified.authorization_id,
            authorization_hash=verified.authorization_hash,
            authorization_consumption_id=effect.consumption_id,
            target_identity=deployment.target.realm_id,
            runtime_implementation_identity=runtime,
            effect_boundary_id=_BOUNDARY,
            endpoint_identity=binding.endpoint_url,
            credential_reference_digest=context.credential_reference_digest,
            credential_scope_digest=context.credential_scope_binding_digest,
            request_body_digest=binding.body_digest,
            request_identity=identity,
            idempotency_identity=binding.business_event_key,
        )
        try:
            observation = await self._post_once(
                dispatch,
                permit_binding,
                _mint_bound_execution_permit(permit_binding),
                credential,
                recheck,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            observation = "TRANSPORT_UNKNOWN"
        return KeycloakLabDispatchObservation(effect.operation_id, observation)

    async def _post_once(
        self,
        dispatch: ImmutableFinalDispatch,
        binding: PermitBinding,
        permit: object,
        credential: KeycloakLabWriterCredential,
        recheck: Callable[[], None],
    ) -> Literal["HTTP_204_UNVERIFIED", "TRANSPORT_UNKNOWN"]:
        writer = None
        try:
            target = self._deployment.target
            expected = (
                f"{target.origin}/admin/realms/{target.realm_name}/users/{target.user_id}"
                f"/role-mappings/clients/{target.client_id}"
            )
            if (
                dispatch.canonical_endpoint != expected
                or dispatch.runtime_implementation_identity
                != runtime_implementation_identity(self)
            ):
                raise KeycloakLabExecutionError("KGR_LAB_ENDPOINT_MISMATCH")
            endpoint = urlsplit(expected)
            token = credential.material.get_secret_value()
            if not 32 <= len(token) <= 4096 or not re.fullmatch(
                rb"[A-Za-z0-9._~+/-]+=*", token
            ):
                raise KeycloakLabExecutionError("KGR_LAB_CREDENTIAL_INVALID")
            body = dispatch.body_bytes
            prefix = (
                f"POST {endpoint.path} HTTP/1.1\r\nHost: {endpoint.hostname}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                "Connection: close\r\nAuthorization: Bearer "
            ).encode("ascii")
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1",
                    self._deployment.tls_port,
                    ssl=self._tls,
                    server_hostname=endpoint.hostname,
                    limit=1024,
                    ssl_handshake_timeout=_REQUEST_TIMEOUT,
                )
                recheck()
                consume_bound_execution_permit(permit, binding, dispatch)
                writer.write(prefix + token + b"\r\n\r\n" + body)
                await writer.drain()
                status = await reader.readline()
                if re.fullmatch(rb"HTTP/1\.[01] 204(?: [^\r\n]*)?\r\n", status):
                    return "HTTP_204_UNVERIFIED"
        finally:
            if writer is not None:
                writer.transport.abort()
        return "TRANSPORT_UNKNOWN"
