"""Consume native v2 once after fresh governance, without executing an action.

Only the configured consumption database may be written. No credentials,
headers, adapter, BindReceipt, or external-action dispatch enter this API.
The returned record is audit evidence, not a reusable execution capability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    NativeBindAuthorizationArtifact,
    verify_native_bind_authorization,
    _verified_source,
    _supported_approval_rules,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _validate_governance_for_verified_context,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AuthorizationConsumptionRecord,
    InMemoryAtomicAuthorizationConsumptionStore,
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)


class NativeAuthorizationConsumptionError(ValueError):
    """Fail-closed native consumption error; never includes backend secrets."""


@dataclass(frozen=True)
class NativeAuthorizationConsumptionResult:
    """Consumed audit lineage, not permission to execute or retry an action."""

    authorization: NativeBindAuthorizationArtifact
    consumption_record: AuthorizationConsumptionRecord
    current_runtime_risk_hash: str
    current_authority_proof_digest: str
    current_human_approval_proof_digest: str | None
    current_runtime_authority_digest: str
    durable_store_used: bool
    authorization_consumed: Literal[True] = True
    execution_authority_created: Literal[False] = False
    credential_material_accessed: Literal[False] = False
    bind_invoked: Literal[False] = False
    bind_receipt_created: Literal[False] = False
    external_action_executed: Literal[False] = False


async def consume_native_bind_authorization(
    artifact: Any,
    *,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    current_source_inputs: NativeAuthorizationSourceInputs,
    current_runtime_risk_packet: Any,
    now: datetime,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore
    | InMemoryAtomicAuthorizationConsumptionStore,
    allow_in_memory_for_testing: bool = False,
) -> NativeAuthorizationConsumptionResult:
    """Reverify historical and current evidence, then atomically consume once.

    Callers supply the trusted consumption clock and fresh risk evidence:
    both risk reviewed_at and recorded_at must equal now. Source/contract trust
    anchors are deployment inputs, never extracted from candidate snapshots.
    Historical signed proof hashes are not rewritten with current proof hashes.

    PostgreSQL is required by default. Explicit process-local testing is not
    durable and cannot establish cross-process replay protection. Unrecognized
    store implementations, even with production_safe=True, are rejected.

    Failure after an attempted write never releases or reuses an authorization.
    A database commit with a lost acknowledgement must be treated as consumed
    or unknown, not automatically retried as an executable action. A future
    execution boundary still needs fresh policy/risk checks and durable lineage.
    """
    durable = type(consumption_store) is PostgresAtomicAuthorizationConsumptionStore
    if not durable and not (
        allow_in_memory_for_testing is True
        and type(consumption_store) is InMemoryAtomicAuthorizationConsumptionStore
    ):
        raise NativeAuthorizationConsumptionError("NABC_DURABLE_STORE_REQUIRED")
    if not isinstance(governance_inputs, RealBindAuthorizationGovernanceInputs):
        raise NativeAuthorizationConsumptionError("NABC_GOVERNANCE_INPUTS_REQUIRED")
    current = datetime.fromisoformat(_timestamp(now))
    issued_at = datetime.fromisoformat(_timestamp(governance_inputs.verification_now))
    if current < issued_at:
        raise NativeAuthorizationConsumptionError("NABC_CLOCK_BEFORE_ISSUANCE")

    authorization = verify_native_bind_authorization(
        artifact,
        source_inputs=issuance_source_inputs,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    if not (
        datetime.fromisoformat(authorization.valid_from)
        <= current
        < datetime.fromisoformat(authorization.valid_until)
    ):
        raise NativeAuthorizationConsumptionError("NABC_AUTHORIZATION_EXPIRED")
    current_governance = replace(governance_inputs, verification_now=current)
    risk, final, context = _verified_source(
        current_runtime_risk_packet,
        current_source_inputs,
        current_governance,
    )
    if (
        datetime.fromisoformat(risk.risk_decision.reviewed_at) != current
        or datetime.fromisoformat(risk.recorded_at) != current
    ):
        raise NativeAuthorizationConsumptionError("NABC_FRESH_RISK_REVIEW_REQUIRED")
    if (
        final.bind_context_hash != authorization.bind_context_hash
        or final.exact_bind_context.action_contract_digest
        != authorization.action_contract_digest
        or context.execution_intent != authorization.execution_intent
        or context.execution_intent_id != authorization.execution_intent_id
        or context.execution_intent_hash != authorization.execution_intent_hash
        or final.exact_bind_context.gate_packet_hash != authorization.source_gate_hash
    ):
        raise NativeAuthorizationConsumptionError("NABC_CURRENT_CONTEXT_MISMATCH")
    _supported_approval_rules(current_governance.action_contract.human_approval_rules)
    governance = _validate_governance_for_verified_context(
        context,
        current_governance,
        bind_context_hash=final.bind_context_hash,
    )
    if (
        governance.human_approval_status
        != authorization.human_approval_requirement_status
        or (governance.human_approval_status == "VERIFIED")
        != risk.required_human_approval
    ):
        raise NativeAuthorizationConsumptionError("NABC_CURRENT_APPROVAL_MISMATCH")
    record = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=authorization.authorization_id,
        live_adapter_bind_authorization_hash=authorization.authorization_hash,
        idempotency_key=authorization.idempotency_key,
        bind_context_hash=authorization.bind_context_hash,
        execution_intent_id=authorization.execution_intent_id,
        execution_intent_hash=authorization.execution_intent_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        consumed_at=current.isoformat(),
    )
    try:
        claimed = await consumption_store.consume_once(record)
    except Exception:
        # Storage exceptions can include connection strings. Never expose them.
        raise NativeAuthorizationConsumptionError(
            "NABC_STORE_FAILED_OR_UNKNOWN"
        ) from None
    if claimed is not True:
        raise NativeAuthorizationConsumptionError("NABC_ALREADY_CONSUMED")
    return NativeAuthorizationConsumptionResult(
        authorization=authorization,
        consumption_record=record,
        current_runtime_risk_hash=risk.packet_hash,
        current_authority_proof_digest=governance.authority_proof.verification_proof_hash,
        current_human_approval_proof_digest=(
            governance.human_approval_proof.verification_proof_hash
            if governance.human_approval_proof
            else None
        ),
        current_runtime_authority_digest=governance.runtime_result_digest,
        durable_store_used=durable,
    )
