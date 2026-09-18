"""Consume native v2 once after fresh governance, without executing an action.

Only the configured consumption database may be written. No credentials,
headers, adapter, BindReceipt, or external-action dispatch enter this API.
The returned record is audit evidence, not a reusable execution capability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from veritas_os.governance.reconciliation_capability_evidence import (
    ReconciliationCapabilityEvidence,
    ReconciliationCapabilityVerifierTrustPolicy,
    VerifiedReconciliationCapabilityEvidence,
    validate_verified_reconciliation_capability_evidence,
)

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


@dataclass(frozen=True)
class ReconciliationCapabilityExecutionPolicy:
    """Deployment-controlled policy for pre-consumption reconciliation gating.

    This object is not request data and does not itself create execution
    permission. When require_authoritative_reconciliation is false, the
    existing consumption contract remains unchanged.
    """

    policy_id: str
    require_authoritative_reconciliation: bool
    current_target_configuration_digest: str | None = None
    expected_verifier_id: str | None = None
    expected_verifier_policy_id: str | None = None
    expected_verifier_policy_hash: str | None = None
    expected_evidence_digest: str | None = None
    expected_trust_policy_id: str | None = None
    expected_trust_policy_hash: str | None = None


def _is_sha256(value: str | None) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _validate_reconciliation_capability_execution_policy(
    policy: ReconciliationCapabilityExecutionPolicy,
) -> None:
    """Fail closed on ambiguous or incompletely anchored gate policy."""
    if type(policy) is not ReconciliationCapabilityExecutionPolicy:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
        )
    if not policy.policy_id.strip() or type(
        policy.require_authoritative_reconciliation
    ) is not bool:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
        )

    anchor_values = (
        policy.current_target_configuration_digest,
        policy.expected_verifier_id,
        policy.expected_verifier_policy_id,
        policy.expected_verifier_policy_hash,
        policy.expected_evidence_digest,
        policy.expected_trust_policy_id,
        policy.expected_trust_policy_hash,
    )

    if not policy.require_authoritative_reconciliation:
        if any(value is not None for value in anchor_values):
            raise NativeAuthorizationConsumptionError(
                "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
            )
        return

    if not all(isinstance(value, str) and value.strip() for value in anchor_values):
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
        )
    if not (
        _is_sha256(policy.current_target_configuration_digest)
        and _is_sha256(policy.expected_verifier_policy_hash)
        and _is_sha256(policy.expected_evidence_digest)
        and _is_sha256(policy.expected_trust_policy_hash)
    ):
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
        )


def _enforce_reconciliation_capability_before_consumption(
    *,
    policy: ReconciliationCapabilityExecutionPolicy | None,
    proof: VerifiedReconciliationCapabilityEvidence | None,
    trust_policy: ReconciliationCapabilityVerifierTrustPolicy | None,
    raw_evidence: ReconciliationCapabilityEvidence | None,
    current_endpoint_identity_binding_digest: str,
    verification_time: datetime,
) -> tuple[str | None, str | None, str | None, bool]:
    """Apply the policy-selected verified capability gate before consumption."""
    if policy is None:
        if proof is not None or trust_policy is not None or raw_evidence is not None:
            raise NativeAuthorizationConsumptionError(
                "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
            )
        return None, None, None, False

    _validate_reconciliation_capability_execution_policy(policy)
    if not policy.require_authoritative_reconciliation:
        if proof is not None or trust_policy is not None or raw_evidence is not None:
            raise NativeAuthorizationConsumptionError(
                "NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID"
            )
        return policy.policy_id, None, None, False

    if type(proof) is not VerifiedReconciliationCapabilityEvidence:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_VERIFIED_PROOF_REQUIRED"
        )
    if type(trust_policy) is not ReconciliationCapabilityVerifierTrustPolicy:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_TRUST_POLICY_REQUIRED"
        )
    if raw_evidence is not None:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_RAW_EVIDENCE_NOT_ACCEPTED"
        )

    if (
        trust_policy.policy_id != policy.expected_trust_policy_id
        or trust_policy.deterministic_hash() != policy.expected_trust_policy_hash
    ):
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_TRUST_POLICY_MISMATCH"
        )

    if (
        proof.verifier_id,
        proof.verifier_policy_id,
        proof.verifier_policy_hash,
    ) != (
        policy.expected_verifier_id,
        policy.expected_verifier_policy_id,
        policy.expected_verifier_policy_hash,
    ):
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_REJECTED"
        )

    try:
        failures = validate_verified_reconciliation_capability_evidence(
            proof,
            trust_policy=trust_policy,
            current_endpoint_identity_binding_digest=(
                current_endpoint_identity_binding_digest
            ),
            current_target_configuration_digest=str(
                policy.current_target_configuration_digest
            ),
            verification_time=verification_time,
            require_authoritative=True,
            expected_evidence_digest=policy.expected_evidence_digest,
        )
    except ValueError:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_REJECTED"
        ) from None

    if failures:
        raise NativeAuthorizationConsumptionError(
            "NABC_RECONCILIATION_CAPABILITY_REJECTED"
        )

    return (
        policy.policy_id,
        proof.evidence_digest,
        proof.verification_proof_hash,
        True,
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
    reconciliation_capability_policy_id: str | None = None
    reconciliation_capability_evidence_digest: str | None = None
    reconciliation_capability_verification_proof_hash: str | None = None
    reconciliation_capability_required: bool = False
    reconciliation_capability_satisfied: bool = False
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
    reconciliation_capability_policy: ReconciliationCapabilityExecutionPolicy
    | None = None,
    reconciliation_capability_proof: VerifiedReconciliationCapabilityEvidence
    | None = None,
    reconciliation_capability_trust_policy:
        ReconciliationCapabilityVerifierTrustPolicy | None = None,
    reconciliation_capability_evidence: ReconciliationCapabilityEvidence
    | None = None,
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
    or unknown, not automatically retried as an executable action.

    When a deployment-controlled reconciliation capability policy requires an
    authoritative downstream resolution path, a deployment-controlled verifier
    must first seal the raw capability artifact into a verified proof. The proof
    seal, verifier trust policy, current endpoint/configuration, and independently
    supplied policy anchors are all rechecked before the consumption write.
    Missing, raw-only, stale, drifted, heuristic, unsealed, or untrusted evidence
    fails closed while leaving the authorization unconsumed. If the policy does
    not require the gate, the existing consumption contract remains unchanged.
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

    (
        reconciliation_policy_id,
        reconciliation_evidence_digest,
        reconciliation_verification_proof_hash,
        reconciliation_capability_satisfied,
    ) = _enforce_reconciliation_capability_before_consumption(
        policy=reconciliation_capability_policy,
        proof=reconciliation_capability_proof,
        trust_policy=reconciliation_capability_trust_policy,
        raw_evidence=reconciliation_capability_evidence,
        current_endpoint_identity_binding_digest=(
            context.endpoint_identity_binding_digest
        ),
        verification_time=current,
    )

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
        reconciliation_capability_policy_id=reconciliation_policy_id,
        reconciliation_capability_evidence_digest=reconciliation_evidence_digest,
        reconciliation_capability_verification_proof_hash=(
            reconciliation_verification_proof_hash
        ),
        reconciliation_capability_required=(
            reconciliation_capability_policy is not None
            and reconciliation_capability_policy.require_authoritative_reconciliation
        ),
        reconciliation_capability_satisfied=reconciliation_capability_satisfied,
    )
