"""Owning metadata-only re-entry evaluation after sandbox recovery.

This boundary composes the TASK-031 trust-state gate with real current
governance inputs and a read-only credential metadata source.

It deliberately cannot:
- reuse the historical authorization;
- resolve credential material;
- issue a new authorization;
- send an external request; or
- turn EFFECT_UNKNOWN into retry authority.

A successful result only says that the caller may start a separate, fresh
authorization flow under current trust.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict

from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _requires_human_approval,
    _validate_governance_for_verified_context,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    _verified_source,
)
from veritas_os.policy.post_compromise_trust_continuity import (
    ApprovalState,
    AuthorityState,
    CredentialState,
    RecoveryTrustState,
    TrustContinuityObservation,
    TrustContinuityResult,
    evaluate_post_compromise_trust,
)
from veritas_os.policy.sandbox_action_binding import (
    SandboxDeployment,
    build_sandbox_action_binding,
    verify_sandbox_action_binding,
)
from veritas_os.policy.sandbox_credential_resolution import (
    SandboxCredentialMetadata,
)
from veritas_os.policy.sandbox_pre_effect import (
    SandboxClockReading,
    SandboxCurrentInputs,
    _clock,
)
from veritas_os.policy.sandbox_recovery import SandboxRecoveryResult
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.security.hash import sha256_of_canonical_json


class SandboxReentryError(ValueError):
    """Sanitized fail-closed error; never implies that execution is safe."""


@dataclass(frozen=True)
class SandboxCredentialTrustRequest:
    """Read-only current credential metadata lookup.

    There is intentionally no authorization_id, attempt_id, or secret-returning
    operation in this request.
    """

    credential_reference_id: str
    credential_provider_type: str
    credential_version: str
    credential_scope: str
    credential_environment: str
    audience: str


class SandboxCredentialMetadataReader(Protocol):
    """Deployment-owned read-only current credential metadata source."""

    async def describe_current(
        self,
        request: SandboxCredentialTrustRequest,
    ) -> SandboxCredentialMetadata:
        ...


class TrustGenerationReader(Protocol):
    """Deployment-owned monotonic trust-generation source outside rollback state."""

    def read_current_generation(self) -> int:
        ...


class SandboxReentryResult(BaseModel):
    """Hash-verifiable re-entry evaluation; never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: str = "sandbox-post-compromise-reentry/v1"
    snapshot_id: str
    recovery_operation_id: str
    historical_authorization_id: str
    current_governance_digest: str | None
    credential_metadata_digest: str | None
    trust_result: TrustContinuityResult
    historical_authorization_reusable: bool = False
    credential_material_accessed: bool = False
    external_effect_retry_permitted: bool = False


def _read_generation(reader: TrustGenerationReader) -> int:
    try:
        value = reader.read_current_generation()
    except Exception:
        raise SandboxReentryError("SRE_TRUST_GENERATION_UNAVAILABLE") from None
    if type(value) is not int or value < 0:
        raise SandboxReentryError("SRE_TRUST_GENERATION_INVALID")
    return value


def _effect_state(recovery: SandboxRecoveryResult) -> str:
    value = recovery.state.value
    if value not in {
        "EFFECT_UNKNOWN",
        "CONFIRMED_EFFECT",
        "CONFIRMED_NO_EFFECT",
    }:
        raise SandboxReentryError("SRE_RECOVERY_STATE_UNSUPPORTED")
    return value


def _credential_request(
    deployment: SandboxDeployment,
) -> SandboxCredentialTrustRequest:
    return SandboxCredentialTrustRequest(
        credential_reference_id=deployment.credential_reference_id,
        credential_provider_type=deployment.credential_provider_type,
        credential_version=deployment.credential_version,
        credential_scope=deployment.credential_scope,
        credential_environment=deployment.credential_environment,
        audience=deployment.endpoint_url.removesuffix("/v1/events"),
    )


def _validate_current_credential_metadata(
    value: Any,
    request: SandboxCredentialTrustRequest,
    started: SandboxClockReading,
    finished: SandboxClockReading,
) -> tuple[CredentialState, str | None]:
    try:
        if type(value) is not SandboxCredentialMetadata:
            return "UNAVAILABLE", None
        metadata = SandboxCredentialMetadata.model_validate(
            value.model_dump(mode="python", warnings=False)
        )
        for name in (
            "credential_reference_id",
            "credential_provider_type",
            "credential_version",
            "credential_scope",
            "credential_environment",
            "audience",
        ):
            if getattr(metadata, name) != getattr(request, name):
                return "AMBIGUOUS", None

        start = _clock(started)
        end = _clock(finished)
        lower = min(
            start - timedelta(seconds=started.uncertainty_seconds),
            end - timedelta(seconds=finished.uncertainty_seconds),
        )
        upper = end + timedelta(seconds=finished.uncertainty_seconds)
        observed = datetime.fromisoformat(metadata.observed_at)
        valid_from = datetime.fromisoformat(metadata.valid_from)
        valid_until = datetime.fromisoformat(metadata.valid_until)

        if metadata.revoked:
            return "REVOKED", sha256_of_canonical_json(
                metadata.model_dump(mode="json")
            )
        if not (
            valid_from <= lower
            and upper < valid_until
            and lower <= observed <= upper
            and 0 <= (end - start).total_seconds() <= 5
            and 0
            <= finished.monotonic_seconds - started.monotonic_seconds
            <= 5
        ):
            return "AMBIGUOUS", sha256_of_canonical_json(
                metadata.model_dump(mode="json")
            )
        return "VALID", sha256_of_canonical_json(
            metadata.model_dump(mode="json")
        )
    except Exception:
        return "AMBIGUOUS", None


def _classify_governance_failure(
    exc: Exception,
    *,
    human_required: bool,
) -> tuple[AuthorityState, str, ApprovalState]:
    code = str(exc)
    lowered = code.lower()

    authority: AuthorityState = "AMBIGUOUS"
    policy = "AMBIGUOUS"
    approval: ApprovalState = "AMBIGUOUS" if human_required else "NOT_REQUIRED"

    if "LABA_AUTHORITY_VERIFICATION_FAILED" in code:
        authority = "REVOKED" if "revok" in lowered else "AMBIGUOUS"
    if (
        "LABA_ACTION_CONTRACT_" in code
        or "LABA_RUNTIME_AUTHORITY_NOT_COMMIT" in code
        or "LABA_REQUIRED_EVIDENCE_PROOF_UNAVAILABLE" in code
    ):
        policy = "DENIED"
    if "LABA_HUMAN_APPROVAL" in code:
        if "expir" in lowered:
            approval = "EXPIRED"
        elif "required" in lowered:
            approval = "UNAVAILABLE"
        else:
            approval = "INVALID"

    return authority, policy, approval


async def evaluate_sandbox_reentry_after_recovery(
    historical_authorization: Any,
    payload_json: str,
    *,
    snapshot_id: str,
    historical_trust_generation: int,
    recovery_result: SandboxRecoveryResult,
    deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    historical_governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    trusted_clock: Callable[[], SandboxClockReading],
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs],
    credential_metadata_reader: SandboxCredentialMetadataReader,
    trust_generation_reader: TrustGenerationReader,
) -> SandboxReentryResult:
    """Evaluate current trust after recovery without creating execution authority.

    Historical authorization is accepted only to prove lineage and the original
    action binding. Current admissibility comes from freshly loaded governance,
    current trust generation, and a metadata-only credential-provider read.
    """

    if type(snapshot_id) is not str or not snapshot_id.strip():
        raise SandboxReentryError("SRE_SNAPSHOT_ID_REQUIRED")
    if type(historical_trust_generation) is not int or historical_trust_generation < 0:
        raise SandboxReentryError("SRE_HISTORICAL_TRUST_GENERATION_INVALID")
    if type(recovery_result) is not SandboxRecoveryResult:
        raise SandboxReentryError("SRE_RECOVERY_RESULT_REQUIRED")

    try:
        historical_binding = verify_sandbox_action_binding(
            historical_authorization,
            payload_json,
            deployment=deployment,
            source_inputs=issuance_source_inputs,
            governance_inputs=historical_governance_inputs,
            trust_inputs=trust_inputs,
        )
    except Exception:
        raise SandboxReentryError("SRE_HISTORICAL_LINEAGE_INVALID") from None

    if recovery_result.authorization_id != historical_binding.authorization_id:
        raise SandboxReentryError("SRE_RECOVERY_AUTHORIZATION_MISMATCH")

    effect_state = _effect_state(recovery_result)
    generation_before = _read_generation(trust_generation_reader)

    authority_state: AuthorityState = "AMBIGUOUS"
    policy_state = "AMBIGUOUS"
    approval_state: ApprovalState = "AMBIGUOUS"
    human_required = True
    action_binding_state = "UNAVAILABLE"
    current_governance_digest: str | None = None
    credential_state: CredentialState = "UNAVAILABLE"
    credential_metadata_digest: str | None = None

    reading = trusted_clock()
    now = _clock(reading)

    current: SandboxCurrentInputs | None = None
    try:
        loaded = load_current_inputs(now)
        if type(loaded) is not SandboxCurrentInputs:
            raise TypeError("current inputs")
        current = loaded
        human_required = _requires_human_approval(
            current.governance.action_contract
        )

        try:
            current_binding = build_sandbox_action_binding(
                payload_json,
                deployment=deployment,
                expected_contract=current.governance.action_contract,
            )
            action_binding_state = (
                "CURRENT"
                if current_binding == historical_binding.binding
                else "DRIFTED"
            )
        except Exception:
            action_binding_state = "DRIFTED"

        gov = replace(current.governance, verification_now=now)
        try:
            _, final, context = _verified_source(
                current.runtime_risk_packet,
                current.source,
                gov,
            )
            proof = _validate_governance_for_verified_context(
                context,
                gov,
                bind_context_hash=final.bind_context_hash,
            )
            authority_state = "VALID"
            policy_state = "ADMISSIBLE"
            approval_state = proof.human_approval_status
            current_governance_digest = proof.runtime_result_digest
        except Exception as exc:
            (
                authority_state,
                policy_state,
                approval_state,
            ) = _classify_governance_failure(
                exc,
                human_required=human_required,
            )
    except Exception:
        current = None

    if (
        current is not None
        and authority_state == "VALID"
        and policy_state == "ADMISSIBLE"
        and action_binding_state == "CURRENT"
    ):
        request = _credential_request(deployment)
        started = trusted_clock()
        try:
            metadata = await credential_metadata_reader.describe_current(request)
        except Exception:
            metadata = None
        finished = trusted_clock()
        credential_state, credential_metadata_digest = (
            _validate_current_credential_metadata(
                metadata,
                request,
                started,
                finished,
            )
        )

    generation_after = _read_generation(trust_generation_reader)

    observation = TrustContinuityObservation(
        snapshot_id=snapshot_id,
        historical_trust_generation=historical_trust_generation,
        current_trust_generation=generation_before,
        observation_generation=generation_after,
        authority_state=authority_state,
        credential_state=credential_state,
        credential_material_source=(
            "CURRENT_PROVIDER"
            if credential_state in {"VALID", "REVOKED", "AMBIGUOUS"}
            and credential_metadata_digest is not None
            else "UNAVAILABLE"
        ),
        policy_state=policy_state,
        human_approval_required=human_required,
        human_approval_state=approval_state,
        action_binding_state=action_binding_state,
        external_effect_state=effect_state,
        historical_authorization_present=True,
        historical_authorization_consumed=True,
        historical_authorization_reuse_attempted=False,
    )
    trust_result = evaluate_post_compromise_trust(observation)

    return SandboxReentryResult(
        snapshot_id=snapshot_id,
        recovery_operation_id=recovery_result.operation_id,
        historical_authorization_id=historical_binding.authorization_id,
        current_governance_digest=current_governance_digest,
        credential_metadata_digest=credential_metadata_digest,
        trust_result=trust_result,
        historical_authorization_reusable=False,
        credential_material_accessed=False,
        external_effect_retry_permitted=False,
    )


__all__ = [
    "SandboxCredentialMetadataReader",
    "SandboxCredentialTrustRequest",
    "SandboxReentryError",
    "SandboxReentryResult",
    "TrustGenerationReader",
    "evaluate_sandbox_reentry_after_recovery",
]
