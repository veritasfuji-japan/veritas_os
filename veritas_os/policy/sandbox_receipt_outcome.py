"""Publish deterministic BindReceipt/Outcome pairs from durable sandbox evidence.

This is retrospective, narrowly scoped evidence of sandbox event persistence.
It never reruns Bind, fabricates live check results, renews execution authority,
or appends a TrustLog entry. Publication is an atomic, write-once database pair.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from veritas_os.governance.outcome_receipt import build_outcome_receipt, validate_outcome_receipt
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome, hash_bind_receipt
from veritas_os.policy.bind_core.normalizers import normalize_execution_intent
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState, InMemoryAtomicEffectStateStore, PostgresAtomicEffectStateStore, _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore, PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs, RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs, _verified_source, verify_native_bind_authorization,
)
from veritas_os.policy.sandbox_action_binding import SandboxDeployment, verify_sandbox_action_binding
from veritas_os.policy.sandbox_event_store import parse_event
from veritas_os.policy.sandbox_reconciliation import (
    SandboxReaderPolicy, VERIFIER_ID, sandbox_reconciliation_policy_hash,
)
from veritas_os.policy.sandbox_reconciliation_archive import validate_archive
from veritas_os.policy.sandbox_receipt_store import _persist_receipts
from veritas_os.policy.trusted_https_reconciliation import ReconciliationVerifierPolicy
from veritas_os.security.hash import sha256_of_canonical_json


class SandboxReceiptError(ValueError):
    """Sanitized failure: no publication success or external-effect retry implied."""


class SandboxReceiptBundle(BaseModel):
    """Detached serialized existing artifact schemas, persisted as one pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["sandbox-receipt-bundle/v1"] = "sandbox-receipt-bundle/v1"
    bind_receipt: dict[str, Any]
    outcome_receipt: dict[str, Any]
    bundle_hash: str


async def publish_sandbox_receipts(
    authorization: Any, payload_json: str, *, deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    historical_governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    reader_policy: SandboxReaderPolicy, verifier_policy: ReconciliationVerifierPolicy,
    allow_in_memory_for_testing: bool = False,
) -> SandboxReceiptBundle:
    """Rebuild native lineage and publish only an exact archived confirmed result.

    Caller-provided receipts, verified flags and dispatch acknowledgements are not
    accepted. Historical issuance and trusted storage are rechecked on every call.
    Time and IDs derive from the stored evidence, so repeats return the same pair.
    No current-time authority or bind-time live checks are asserted by this call.
    """
    cancelled = False
    try:
        durable = (type(consumption_store) is PostgresAtomicAuthorizationConsumptionStore
                   and type(effect_store) is PostgresAtomicEffectStateStore)
        if not durable and not (
            allow_in_memory_for_testing is True
            and type(consumption_store) is InMemoryAtomicAuthorizationConsumptionStore
            and type(effect_store) is InMemoryAtomicEffectStateStore
        ):
            raise ValueError("durable stores")
        if type(reader_policy) is not SandboxReaderPolicy or type(verifier_policy) is not ReconciliationVerifierPolicy:
            raise ValueError("policy")
        policy_hash = sandbox_reconciliation_policy_hash(deployment, reader_policy)
        if not verifier_policy.approves(VERIFIER_ID, policy_hash):
            raise ValueError("unapproved archive policy")
        binding = verify_sandbox_action_binding(
            authorization, payload_json, deployment=deployment, source_inputs=issuance_source_inputs,
            governance_inputs=historical_governance_inputs, trust_inputs=trust_inputs,
        )
        verified = verify_native_bind_authorization(
            authorization, source_inputs=issuance_source_inputs,
            governance_inputs=historical_governance_inputs, trust_inputs=trust_inputs,
        )
        _, _, context = _verified_source(
            verified.source_runtime_risk_packet, issuance_source_inputs, historical_governance_inputs,
        )
        consumption = await consumption_store.get(verified.authorization_id)
        if consumption is None:
            raise ValueError("missing consumption")
        expected = build_authorization_consumption_record(
            live_adapter_bind_authorization_id=verified.authorization_id,
            live_adapter_bind_authorization_hash=verified.authorization_hash,
            idempotency_key=verified.idempotency_key, bind_context_hash=verified.bind_context_hash,
            execution_intent_id=verified.execution_intent_id, execution_intent_hash=verified.execution_intent_hash,
            endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
            credential_reference_digest=context.credential_reference_digest,
            credential_scope_binding_digest=context.credential_scope_binding_digest,
            consumed_at=consumption.consumed_at,
        )
        consumed_at = datetime.fromisoformat(_timestamp(consumption.consumed_at))
        if consumption != expected or not datetime.fromisoformat(verified.valid_from) <= consumed_at < datetime.fromisoformat(verified.valid_until):
            raise ValueError("consumption lineage")
        record = await effect_store.get(consumption.consumption_id)
        archive = await effect_store.get_reconciliation(consumption.consumption_id)
        if record is None or archive is None:
            raise ValueError("missing archived result")
        validate_archive(record, archive)
        expected_record = _build_record(
            consumption=consumption, state=EffectExecutionState.CONFIRMED_EFFECT, revision=3,
            updated_at=archive.proof.verified_at, reason_code="SANDBOX_READONLY_LOOKUP_CONFIRMED",
            reconciliation_evidence_hash=archive.proof.deterministic_digest(),
        )
        event = parse_event(binding.binding.payload_json.encode("utf-8"))
        if (record != expected_record or archive.operation.event_id != event.event_id
                or archive.operation.payload_digest != binding.binding.payload_digest
                or archive.proof.verifier_policy_hash != policy_hash
                or archive.proof.evidence.source_identity != deployment.endpoint_url.removesuffix("/v1/events")
                or consumed_at > datetime.fromisoformat(_timestamp(archive.original_record.updated_at))):
            raise ValueError("archived action binding")
        intent = normalize_execution_intent(verified.execution_intent)
        scope = context.authority_evidence_reference_bundle.get("bundle_scope")
        if type(scope) is not list or not scope or any(type(x) is not str or not x.strip() for x in scope):
            raise ValueError("scope")
        lineage = {
            "recording_basis": "RETROSPECTIVE_SANDBOX_RECONCILIATION",
            "authorization_id": verified.authorization_id, "authorization_hash": verified.authorization_hash,
            "consumption_id": consumption.consumption_id, "consumption_hash": consumption.consumption_hash,
            "effect_record_hash": record.record_hash,
            "reconciliation_evidence_hash": archive.proof.deterministic_digest(),
            "archive_hash": sha256_of_canonical_json(archive.model_dump(mode="json")),
            "payload_digest": binding.binding.payload_digest,
            "external_operation_reference": archive.operation.operation_id,
            "human_approval_requirement_status": verified.human_approval_requirement_status,
            "human_approval_verification_proof_digest": verified.human_approval_verification_proof_digest,
            "external_effect_claim": "SANDBOX_EVENT_PERSISTENCE_ONLY",
            "trustlog_publication": "NOT_PUBLISHED",
        }
        receipt = BindReceipt(
            bind_receipt_id="sandbox-bind-" + consumption.consumption_id,
            execution_intent_id=intent.execution_intent_id, decision_id=intent.decision_id,
            bind_ts=archive.original_record.updated_at,
            execution_intent_hash=verified.execution_intent_hash, decision_hash=intent.decision_hash,
            policy_snapshot_id=intent.policy_snapshot_id, actor_identity=intent.actor_identity,
            authority_check_result={"status": "HISTORICAL_NATIVE_ISSUANCE_VERIFIED"},
            constraint_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
            drift_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
            risk_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
            admissibility_result={"status": "RETROSPECTIVE_RECORD_NOT_EXECUTION_PERMISSION"},
            final_outcome=FinalOutcome.COMMITTED,
            governance_identity=lineage,
            bind_reason_code="SANDBOX_PERSISTENCE_INDEPENDENTLY_RECONCILED",
            idempotency_key=consumption.idempotency_key, idempotency_status="CONSUMED",
            retry_safety="NO_EXTERNAL_EFFECT_RETRY", target_path=deployment.endpoint_url,
            target_type="sandbox-event", action_contract_id=historical_governance_inputs.action_contract.id,
            action_contract_version=historical_governance_inputs.action_contract.version,
            commit_boundary_result="RECONCILED_SANDBOX_PERSISTENCE",
        )
        receipt = replace(receipt, bind_receipt_hash=hash_bind_receipt(receipt))
        outcome = build_outcome_receipt(
            decision_id=intent.decision_id, execution_intent_id=intent.execution_intent_id,
            bind_receipt_id=receipt.bind_receipt_id, operation_id=consumption.consumption_id,
            action_class=historical_governance_inputs.action_contract.action_class,
            target_system=intent.target_system, target_resource=intent.target_resource,
            intended_action=intent.intended_action, requested_scope=scope,
            final_outcome="COMMITTED", postcondition_status="passed",
            observed_effects=[{"kind": "sandbox_event_persisted", "event_id": event.event_id,
                               "payload_digest": binding.binding.payload_digest,
                               "operation_id": archive.operation.operation_id}],
            evaluated_at=archive.proof.verified_at,
            metadata={**lineage, "bind_receipt_hash": receipt.bind_receipt_hash,
                      "idempotency_key": consumption.idempotency_key},
        )
        if not validate_outcome_receipt(outcome).is_valid or outcome.outcome_hash != outcome.deterministic_digest():
            raise ValueError("outcome validation")
        values = {"format_version": "sandbox-receipt-bundle/v1", "bind_receipt": receipt.to_dict(),
                  "outcome_receipt": outcome.to_dict()}
        bundle = SandboxReceiptBundle(**values, bundle_hash=sha256_of_canonical_json(values))
        await _persist_receipts(effect_store, record=record, archive=archive, bundle=bundle.model_dump(mode="json"))
        return bundle
    except asyncio.CancelledError:
        cancelled = True
    except Exception:
        pass
    if cancelled:
        raise asyncio.CancelledError()
    raise SandboxReceiptError("SRO_PUBLICATION_FAILED_NO_EFFECT_RETRY")
