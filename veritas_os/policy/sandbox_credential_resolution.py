"""Resolve one pinned sandbox bearer credential inside the owning attempt.

The provider is trusted executor configuration, not request data. Its adapter
must authenticate the provider and bind the returned material to metadata. No
concrete provider, environment fallback, header, Bind or dispatch is installed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import re
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    InMemoryAtomicEffectStateStore, PostgresAtomicEffectStateStore,
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
from veritas_os.policy.sandbox_pre_effect import (
    SandboxClockReading, SandboxCurrentInputs, SandboxPreparedAttempt,
    _clock, _recheck_sandbox_current, _window, prepare_sandbox_attempt,
)
from veritas_os.security.hash import sha256_of_canonical_json

PROVIDER_TIMEOUT_SECONDS = 5


class SandboxCredentialResolutionError(ValueError):
    """Sanitized failure; the existing attempt is never released for retry."""


@dataclass(frozen=True)
class SandboxCredentialRequest:
    """Exact provider lookup derived only from the verified deployment binding."""

    authorization_id: str
    attempt_id: str
    credential_reference_id: str
    credential_provider_type: str
    credential_version: str
    credential_scope: str
    credential_environment: str
    audience: str


class SandboxCredentialMetadata(BaseModel):
    """Provider-authenticated metadata, never a self-asserted authentication flag.

    Authenticity is the configured provider adapter's responsibility. This model
    validates shape only; the continuation checks every policy/time binding.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    credential_reference_id: str = Field(min_length=1)
    credential_provider_type: str = Field(min_length=1)
    credential_version: str = Field(min_length=1)
    credential_scope: str = Field(min_length=1)
    credential_environment: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    credential_kind: Literal["bearer"]
    valid_from: str = Field(min_length=1)
    valid_until: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)
    revoked: bool


class SandboxProviderCredential(BaseModel):
    """Provider response with material redacted by repr and JSON serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    metadata: SandboxCredentialMetadata
    material: SecretBytes = Field(repr=False)


class SandboxCredentialProvider(Protocol):
    """Trusted, deployment-injected adapter; no caller-selected provider lookup.

    describe must not return secret material. resolve must atomically enforce
    expected_metadata_digest and current revocation/version before reading that
    exact credential. Both operations must authenticate the provider. Client
    validation cannot prove a dishonest provider's metadata matches its token.
    """

    async def describe(self, request: SandboxCredentialRequest) -> SandboxCredentialMetadata:
        ...

    async def resolve(
        self, request: SandboxCredentialRequest, *, expected_metadata_digest: str,
    ) -> SandboxProviderCredential:
        ...


class SandboxResolvedCredential:
    """Ephemeral material plus audit data; never an execution capability.

    Only material.get_secret_value() explicitly exposes bytes to trusted code.
    Generic repr/JSON/dataclass/pickle paths cannot expose the token. close drops
    our reference; Python memory erasure or a provider's own logging is not claimed.
    A future sender must recheck ownership/governance after this function returns.
    """

    __slots__ = ("preparation", "metadata_digest", "_material", "_metadata", "_descriptor_started", "_request")

    def __init__(
        self, preparation: SandboxPreparedAttempt, metadata_digest: str, material: SecretBytes,
        *, metadata: SandboxCredentialMetadata | None = None,
        descriptor_started: SandboxClockReading | None = None,
        request: SandboxCredentialRequest | None = None,
    ) -> None:
        self.preparation = preparation
        self.metadata_digest = metadata_digest
        self._material: SecretBytes | None = material
        self._metadata = metadata
        self._descriptor_started = descriptor_started
        self._request = request

    def __repr__(self) -> str:
        return "SandboxResolvedCredential(material=<redacted>)"

    def __reduce_ex__(self, protocol: int) -> Any:
        raise TypeError("SandboxResolvedCredential cannot be serialized")

    @property
    def material(self) -> SecretBytes:
        """Return a redacted wrapper for explicit, scoped use by trusted code."""
        if self._material is None:
            raise SandboxCredentialResolutionError("SCR_CREDENTIAL_CLOSED")
        return self._material

    def close(self) -> None:
        """Drop this object's material reference without claiming memory erasure."""
        self._material = None
        self._metadata = self._descriptor_started = self._request = None


def _validate_metadata(
    value: Any, request: SandboxCredentialRequest,
    started: SandboxClockReading, finished: SandboxClockReading,
) -> SandboxCredentialMetadata:
    # Revalidate even a model constructed with model_construct/model_copy.
    if type(value) is not SandboxCredentialMetadata:
        raise SandboxCredentialResolutionError("SCR_METADATA_REQUIRED")
    # Serializer warnings can echo invalid provider values before we reject them.
    metadata = SandboxCredentialMetadata.model_validate(
        value.model_dump(mode="python", warnings=False),
    )
    for name in (
        "credential_reference_id", "credential_provider_type", "credential_version",
        "credential_scope", "credential_environment", "audience",
    ):
        if getattr(metadata, name) != getattr(request, name):
            raise SandboxCredentialResolutionError("SCR_METADATA_BINDING_MISMATCH")
    start, end = _clock(started), _clock(finished)
    lower = min(
        start - timedelta(seconds=started.uncertainty_seconds),
        end - timedelta(seconds=finished.uncertainty_seconds),
    )
    upper = end + timedelta(seconds=finished.uncertainty_seconds)
    observed = datetime.fromisoformat(_timestamp(metadata.observed_at))
    if (
        metadata.revoked
        or not datetime.fromisoformat(_timestamp(metadata.valid_from)) <= lower
        or not upper < datetime.fromisoformat(_timestamp(metadata.valid_until))
        or not lower <= observed <= upper
        or not 0 <= (end - start).total_seconds() <= PROVIDER_TIMEOUT_SECONDS
        or not 0 <= finished.monotonic_seconds - started.monotonic_seconds <= PROVIDER_TIMEOUT_SECONDS
    ):
        raise SandboxCredentialResolutionError("SCR_METADATA_STALE_REVOKED_OR_EXPIRED")
    return metadata


async def _recheck_owned(
    prepared: SandboxPreparedAttempt, *, payload_json: str, deployment: SandboxDeployment,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
) -> SandboxPreparedAttempt:
    stored = await effect_store.get(prepared.attempt.operation_id)
    if stored != prepared.attempt:
        raise SandboxCredentialResolutionError("SCR_ATTEMPT_OWNERSHIP_LOST")
    risk_hash, clock = _recheck_sandbox_current(
        verified=prepared.authorization, binding=prepared.binding,
        issued_context=prepared.issued_context, payload_json=payload_json,
        deployment=deployment, started=prepared.clock, trusted_clock=trusted_clock,
        load_current_inputs=load_current_inputs,
    )
    return replace(prepared, runtime_risk_hash=risk_hash, checked_at=_timestamp(clock.now), clock=clock)


async def prepare_and_resolve_sandbox_credential(
    authorization: Any, payload_json: str, *, deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
    provider: SandboxCredentialProvider,
    allow_in_memory_for_testing: bool = False,
) -> SandboxResolvedCredential:
    """Claim, inspect metadata, recheck, resolve once and recheck before returning.

    No caller-supplied prepared object/consumed flag is accepted. A pre-existing
    attempt, including an earlier no-effect preparation, cannot enter this path.
    Provider calls are bounded and never retried. Failures retain consumption and
    the attempt; acquired material is not returned on failed post-resolution checks.
    """
    response = None
    description = metadata = actual = None
    cancelled = False
    try:
        if provider is None:
            raise SandboxCredentialResolutionError("SCR_PROVIDER_REQUIRED")
        prepared = await prepare_sandbox_attempt(
            authorization, payload_json, deployment=deployment,
            issuance_source_inputs=issuance_source_inputs, governance_inputs=governance_inputs,
            trust_inputs=trust_inputs, consumption_store=consumption_store,
            effect_store=effect_store, trusted_clock=trusted_clock,
            load_current_inputs=load_current_inputs,
            allow_in_memory_for_testing=allow_in_memory_for_testing,
        )
        request = SandboxCredentialRequest(
            prepared.binding.authorization_id, prepared.attempt.operation_id,
            deployment.credential_reference_id, deployment.credential_provider_type,
            deployment.credential_version, deployment.credential_scope,
            deployment.credential_environment, deployment.endpoint_url.removesuffix("/v1/events"),
        )
        descriptor_started = prepared.clock
        async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
            description = await provider.describe(request)
        observed = trusted_clock()
        _window(observed, prepared.authorization)
        metadata = _validate_metadata(description, request, descriptor_started, observed)
        digest = sha256_of_canonical_json(metadata.model_dump(mode="json"))
        prepared = await _recheck_owned(
            prepared, payload_json=payload_json, deployment=deployment, effect_store=effect_store,
            trusted_clock=trusted_clock, load_current_inputs=load_current_inputs,
        )
        # Do not resolve on a descriptor which expired while governance was checked.
        _validate_metadata(metadata, request, descriptor_started, prepared.clock)
        async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
            response = await provider.resolve(request, expected_metadata_digest=digest)
        if type(response) is not SandboxProviderCredential:
            raise SandboxCredentialResolutionError("SCR_PROVIDER_RESPONSE_INVALID")
        finished = trusted_clock()
        _window(finished, prepared.authorization)
        actual = _validate_metadata(response.metadata, request, descriptor_started, finished)
        if actual != metadata or type(response.material) is not SecretBytes:
            raise SandboxCredentialResolutionError("SCR_PROVIDER_RESPONSE_SUBSTITUTED")
        # Bearer token grammar only; do not construct a header or hash the secret.
        if not 1 <= len(response.material.get_secret_value()) <= 4096 or not re.fullmatch(
            rb"[A-Za-z0-9._~+/-]+=*", response.material.get_secret_value(),
        ):
            raise SandboxCredentialResolutionError("SCR_MATERIAL_INVALID")
        prepared = await _recheck_owned(
            prepared, payload_json=payload_json, deployment=deployment, effect_store=effect_store,
            trusted_clock=trusted_clock, load_current_inputs=load_current_inputs,
        )
        _validate_metadata(actual, request, descriptor_started, prepared.clock)
        return SandboxResolvedCredential(
            prepared, digest, response.material, metadata=actual,
            descriptor_started=descriptor_started, request=request,
        )
    except asyncio.CancelledError:
        cancelled = True
    except Exception:
        # Raise outside the handler so the public exception does not retain the
        # provider exception in __context__, even when chaining is suppressed.
        pass
    finally:
        # Also runs on cancellation. Do not log provider objects or their errors.
        response = None
        description = metadata = actual = None
    if cancelled:
        raise asyncio.CancelledError()
    raise SandboxCredentialResolutionError("SCR_FAILED_ATTEMPT_NOT_RELEASED")
