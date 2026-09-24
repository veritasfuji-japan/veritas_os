"""Fail-closed post-compromise trust-state continuity gate.

This module does not restore credentials, issue authorization, perform recovery
transport, or assert external outcome. It classifies whether current trust has
been freshly revalidated after an operational rollback and whether the caller
may proceed to a *new* authorization flow.

Historical snapshot state is lineage only. It is never current execution
authority.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.security.hash import sha256_of_canonical_json


class RecoveryTrustState(StrEnum):
    """Trust validity after operational recovery."""

    TRUST_NOT_REVALIDATED = "TRUST_NOT_REVALIDATED"
    TRUST_REVALIDATING = "TRUST_REVALIDATING"
    TRUST_REVALIDATED = "TRUST_REVALIDATED"
    TRUST_INVALID = "TRUST_INVALID"


AuthorityState = Literal["VALID", "REVOKED", "UNAVAILABLE", "AMBIGUOUS"]
CredentialState = Literal["VALID", "REVOKED", "UNAVAILABLE", "AMBIGUOUS"]
CredentialMaterialSource = Literal[
    "CURRENT_PROVIDER",
    "HISTORICAL_SNAPSHOT",
    "UNAVAILABLE",
]
PolicyState = Literal["ADMISSIBLE", "DENIED", "UNAVAILABLE", "AMBIGUOUS"]
ApprovalState = Literal[
    "VERIFIED",
    "NOT_REQUIRED",
    "INVALID",
    "EXPIRED",
    "UNAVAILABLE",
    "AMBIGUOUS",
]
ActionBindingState = Literal["CURRENT", "DRIFTED", "UNAVAILABLE", "AMBIGUOUS"]
ExternalEffectState = Literal[
    "NONE",
    "EFFECT_UNKNOWN",
    "CONFIRMED_EFFECT",
    "CONFIRMED_NO_EFFECT",
]


class TrustContinuityObservation(BaseModel):
    """Trusted current-state observations for one recovered operation.

    The caller is responsible for obtaining these values from deployment-owned
    current trust sources. They must not be copied from the historical snapshot
    merely to satisfy this gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal["post-compromise-trust-observation/v1"] = (
        "post-compromise-trust-observation/v1"
    )
    snapshot_id: str = Field(min_length=1, max_length=256)
    historical_trust_generation: int = Field(ge=0)
    current_trust_generation: int = Field(ge=0)
    observation_generation: int = Field(ge=0)

    authority_state: AuthorityState
    credential_state: CredentialState
    credential_material_source: CredentialMaterialSource
    policy_state: PolicyState
    human_approval_required: bool
    human_approval_state: ApprovalState
    action_binding_state: ActionBindingState
    external_effect_state: ExternalEffectState

    historical_authorization_present: bool = False
    historical_authorization_consumed: bool | None = None


class TrustContinuityResult(BaseModel):
    """Deterministic recovery classification; never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal["post-compromise-trust-result/v1"] = (
        "post-compromise-trust-result/v1"
    )
    snapshot_id: str
    historical_trust_generation: int
    current_trust_generation: int
    state: RecoveryTrustState
    reason_code: str
    new_authorization_eligible: bool
    historical_authorization_reusable: Literal[False] = False
    external_effect_retry_permitted: Literal[False] = False
    observation_hash: str
    result_hash: str


def _result(
    observation: TrustContinuityObservation,
    *,
    state: RecoveryTrustState,
    reason_code: str,
    eligible: bool,
) -> TrustContinuityResult:
    observation_payload = observation.model_dump(mode="json")
    observation_hash = sha256_of_canonical_json(observation_payload)
    payload = {
        "format_version": "post-compromise-trust-result/v1",
        "snapshot_id": observation.snapshot_id,
        "historical_trust_generation": observation.historical_trust_generation,
        "current_trust_generation": observation.current_trust_generation,
        "state": state.value,
        "reason_code": reason_code,
        "new_authorization_eligible": eligible,
        "historical_authorization_reusable": False,
        "external_effect_retry_permitted": False,
        "observation_hash": observation_hash,
    }
    return TrustContinuityResult(
        **payload,
        result_hash=sha256_of_canonical_json(payload),
    )


def evaluate_post_compromise_trust(
    observation: TrustContinuityObservation,
) -> TrustContinuityResult:
    """Fail closed unless current trust is freshly and completely revalidated.

    A successful result only permits entry into a new authorization flow. It
    never revives or reuses historical authorization, approval, credential
    material, or execution permission.
    """

    if not isinstance(observation, TrustContinuityObservation):
        raise TypeError("PTC_OBSERVATION_REQUIRED")

    if observation.current_trust_generation < observation.historical_trust_generation:
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_TRUST_GENERATION_ROLLBACK",
            eligible=False,
        )

    if observation.observation_generation != observation.current_trust_generation:
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_NOT_REVALIDATED,
            reason_code="PTC_OBSERVATION_GENERATION_STALE",
            eligible=False,
        )

    if observation.authority_state != "VALID":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_AUTHORITY_NOT_CURRENT",
            eligible=False,
        )

    if observation.credential_state != "VALID":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_CREDENTIAL_NOT_CURRENT",
            eligible=False,
        )

    if observation.credential_material_source != "CURRENT_PROVIDER":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_CREDENTIAL_SOURCE_NOT_CURRENT",
            eligible=False,
        )

    if observation.policy_state != "ADMISSIBLE":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_POLICY_NOT_CURRENT",
            eligible=False,
        )

    if observation.human_approval_required:
        if observation.human_approval_state != "VERIFIED":
            return _result(
                observation,
                state=RecoveryTrustState.TRUST_INVALID,
                reason_code="PTC_APPROVAL_NOT_CURRENT",
                eligible=False,
            )
    elif observation.human_approval_state != "NOT_REQUIRED":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_APPROVAL_REQUIREMENT_MISMATCH",
            eligible=False,
        )

    if observation.action_binding_state != "CURRENT":
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_INVALID,
            reason_code="PTC_ACTION_BINDING_NOT_CURRENT",
            eligible=False,
        )

    if observation.external_effect_state in {"EFFECT_UNKNOWN", "CONFIRMED_EFFECT"}:
        return _result(
            observation,
            state=RecoveryTrustState.TRUST_NOT_REVALIDATED,
            reason_code="PTC_EXTERNAL_EFFECT_NOT_CLEAR_FOR_NEW_EXECUTION",
            eligible=False,
        )

    return _result(
        observation,
        state=RecoveryTrustState.TRUST_REVALIDATED,
        reason_code="PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        eligible=True,
    )


__all__ = [
    "RecoveryTrustState",
    "TrustContinuityObservation",
    "TrustContinuityResult",
    "evaluate_post_compromise_trust",
]
