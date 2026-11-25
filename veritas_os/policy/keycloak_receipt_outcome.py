"""Publish a retrospective receipt pair for a verified Keycloak grant."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from veritas_os.governance.outcome_receipt import OutcomeReceipt, build_outcome_receipt, validate_outcome_receipt
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome, hash_bind_receipt
from veritas_os.policy.bind_core.normalizers import normalize_execution_intent
from veritas_os.policy.keycloak_reconciliation import (
    KeycloakConfirmedReconciliation,
    read_verified_keycloak_confirmation,
)
from veritas_os.policy.keycloak_role_grant_binding import ACTION, REFERENCE_PREFIX
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    _verified_source,
    verify_native_bind_authorization,
)
from veritas_os.security.hash import sha256_of_canonical_json


class KeycloakReceiptError(ValueError):
    """A receipt pair could not be published or verified."""


class KeycloakReceiptBundle(BaseModel):
    """The existing receipt schemas stored together under one content hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["keycloak-receipt-bundle/v1"] = "keycloak-receipt-bundle/v1"
    bind_receipt: dict[str, Any]
    outcome_receipt: dict[str, Any]
    bundle_hash: str


def _stored_receipt_lineage(confirmation: KeycloakConfirmedReconciliation) -> dict[str, Any]:
    record, dispatch, observation = confirmation.record, confirmation.intent, confirmation.observation
    return {
        "recording_basis": "RETROSPECTIVE_KEYCLOAK_RECONCILIATION",
        "bind_timestamp_basis": "AUTHORIZATION_CONSUMED_AT",
        "authorization_id": record.authorization_id,
        "authorization_hash": record.authorization_hash,
        "consumption_id": record.consumption_id,
        "consumption_hash": record.consumption_hash,
        "dispatch_reservation_hash": observation.reservation_record_hash,
        "effect_record_hash": record.record_hash,
        "reconciliation_evidence_hash": record.reconciliation_evidence_hash,
        "archive_hash": sha256_of_canonical_json(observation.model_dump(mode="json")),
        "approved_reference": dispatch.approved_reference,
        "deployment_policy_digest": dispatch.deployment_policy_digest,
        "payload_digest": dispatch.body_digest,
        "external_operation_reference": str(observation.audit_event_id),
        "external_effect_claim": "KEYCLOAK_ACCEPTED_GRANT_AND_DIRECT_MAPPING_OBSERVED",
        "trustlog_publication": "NOT_PUBLISHED",
    }


def _observed_role_effect(confirmation: KeycloakConfirmedReconciliation) -> dict[str, Any]:
    return {
        "kind": "keycloak_direct_role_mapping_observed",
        "audit_event_id": str(confirmation.observation.audit_event_id),
        "role_id": confirmation.intent.target.role_id,
        "mapping_observed_at": confirmation.observation.mapping_observed_at.isoformat(),
        "reverified_at": confirmation.record.updated_at,
    }


async def read_verified_keycloak_receipts(operation_id: str) -> KeycloakReceiptBundle | None:
    """Verify a published pair from stored evidence without publishing or querying Keycloak."""
    from veritas_os.storage.db import get_pool

    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT receipt_bundle FROM bind_keycloak_dispatch_intents WHERE operation_id=%s",
                (operation_id,),
            )
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        bundle = KeycloakReceiptBundle.model_validate(row[0])
        confirmation = await read_verified_keycloak_confirmation(operation_id)
        if confirmation is None:
            raise ValueError("missing confirmed effect")
        record, dispatch = confirmation.record, confirmation.intent
        consumption = await PostgresAtomicAuthorizationConsumptionStore().get(record.authorization_id)
        receipt = BindReceipt(**bundle.bind_receipt)
        outcome = OutcomeReceipt(**bundle.outcome_receipt)
        if (
            bundle.bundle_hash != sha256_of_canonical_json(bundle.model_dump(mode="json", exclude={"bundle_hash"}))
            or receipt.to_dict() != bundle.bind_receipt
            or hash_bind_receipt(receipt) != receipt.bind_receipt_hash
            or outcome.to_dict() != bundle.outcome_receipt
            or outcome.deterministic_digest() != outcome.outcome_hash
            or not validate_outcome_receipt(outcome).is_valid
        ):
            raise ValueError("receipt integrity")

        lineage = receipt.governance_identity
        expected_lineage = _stored_receipt_lineage(confirmation)
        if (
            not isinstance(lineage, dict)
            or any(lineage.get(key) != value for key, value in expected_lineage.items())
            or outcome.metadata != {
                **lineage, "bind_receipt_hash": receipt.bind_receipt_hash,
                "idempotency_key": record.idempotency_key,
            }
            or consumption is None
            or consumption.consumption_id != record.consumption_id
            or consumption.consumption_hash != record.consumption_hash
            or receipt.bind_ts != consumption.consumed_at
            or receipt.idempotency_key != record.idempotency_key
            or receipt.bind_receipt_id != "keycloak-bind-" + record.consumption_id
            or receipt.execution_intent_id != record.execution_intent_id
            or receipt.execution_intent_hash != dispatch.execution_intent_hash
            or receipt.target_path != dispatch.endpoint_url
            or receipt.final_outcome != FinalOutcome.COMMITTED.value
            or outcome.operation_id != operation_id
            or outcome.outcome_receipt_id != f"outcome-{operation_id}"
            or outcome.bind_receipt_id != receipt.bind_receipt_id
            or outcome.execution_intent_id != receipt.execution_intent_id
            or outcome.decision_id != receipt.decision_id
            or outcome.target_resource != dispatch.endpoint_url
            or outcome.action_class != ACTION or outcome.intended_action != ACTION
            or outcome.final_outcome != "COMMITTED" or outcome.committed is not True
            or outcome.blocked is not False or outcome.escalated is not False
            or outcome.rolled_back is not False or outcome.rollback_status is not None
            or outcome.postcondition_status != "passed" or outcome.evaluated_at != record.updated_at
            or outcome.observed_effects != [_observed_role_effect(confirmation)]
        ):
            raise ValueError("receipt lineage")
    except Exception:
        raise KeycloakReceiptError("KGR_RECEIPT_READ_INTEGRITY_FAILED") from None
    return bundle


async def publish_keycloak_receipts(
    operation_id: str,
    authorization: Any,
    *,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> KeycloakReceiptBundle:
    """Revalidate historical authority and durable evidence, then publish once."""
    try:
        bundle, confirmation = await _build_keycloak_receipts(
            operation_id, authorization, source_inputs=source_inputs,
            governance_inputs=governance_inputs, trust_inputs=trust_inputs,
        )
        await _persist_keycloak_receipts(confirmation, bundle)
    except Exception:
        raise KeycloakReceiptError("KGR_RECEIPT_PUBLICATION_FAILED") from None
    return bundle


async def _build_keycloak_receipts(
    operation_id: str,
    authorization: Any,
    *,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> tuple[KeycloakReceiptBundle, KeycloakConfirmedReconciliation]:
    confirmation = await read_verified_keycloak_confirmation(operation_id)
    if confirmation is None:
        raise ValueError("missing confirmed result")
    record, dispatch, observation = confirmation.record, confirmation.intent, confirmation.observation
    verified = verify_native_bind_authorization(
        authorization, source_inputs=source_inputs, governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    signed = verified.execution_intent
    refs = [ref for ref in signed["evidence_refs"] if isinstance(ref, str) and ref.startswith(REFERENCE_PREFIX)]
    intent = normalize_execution_intent(signed)
    if (
        verified.authorization_id != record.authorization_id
        or verified.authorization_hash != record.authorization_hash
        or verified.execution_intent_id != record.execution_intent_id
        or verified.execution_intent_hash != dispatch.execution_intent_hash
        or refs != [dispatch.approved_reference]
        or intent.intended_action != ACTION
        or intent.target_resource != dispatch.endpoint_url
        or governance_inputs.action_contract.action_class != ACTION
    ):
        raise ValueError("authorization lineage")

    consumption = await PostgresAtomicAuthorizationConsumptionStore().get(verified.authorization_id)
    if consumption is None:
        raise ValueError("missing consumption")
    _, _, context = _verified_source(verified.source_runtime_risk_packet, source_inputs, governance_inputs)
    expected = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=verified.authorization_id,
        live_adapter_bind_authorization_hash=verified.authorization_hash,
        idempotency_key=verified.idempotency_key,
        bind_context_hash=verified.bind_context_hash,
        execution_intent_id=verified.execution_intent_id,
        execution_intent_hash=verified.execution_intent_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        consumed_at=consumption.consumed_at,
    )
    consumed_at = datetime.fromisoformat(consumption.consumed_at)
    if (
        consumption != expected
        or consumption.consumption_id != record.consumption_id
        or consumption.consumption_hash != record.consumption_hash
        or consumption.idempotency_key != record.idempotency_key
        or not datetime.fromisoformat(verified.valid_from) <= consumed_at < datetime.fromisoformat(
            verified.valid_until,
        )
        or consumed_at > observation.mapping_observed_at
    ):
        raise ValueError("consumption lineage")
    scope = context.authority_evidence_reference_bundle.get("bundle_scope")
    if type(scope) is not list or not scope or any(type(item) is not str or not item.strip() for item in scope):
        raise ValueError("scope")

    lineage = {
        **_stored_receipt_lineage(confirmation),
        "human_approval_requirement_status": verified.human_approval_requirement_status,
        "human_approval_verification_proof_digest": verified.human_approval_verification_proof_digest,
    }
    contract = governance_inputs.action_contract
    receipt = BindReceipt(
        bind_receipt_id="keycloak-bind-" + consumption.consumption_id,
        execution_intent_id=intent.execution_intent_id, decision_id=intent.decision_id,
        bind_ts=consumption.consumed_at,
        execution_intent_hash=verified.execution_intent_hash, decision_hash=intent.decision_hash,
        policy_snapshot_id=intent.policy_snapshot_id, actor_identity=intent.actor_identity,
        authority_check_result={"status": "HISTORICAL_NATIVE_ISSUANCE_VERIFIED"},
        constraint_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
        drift_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
        risk_check_result={"status": "LIVE_RESULTS_NOT_ARCHIVED"},
        admissibility_result={"status": "RETROSPECTIVE_RECORD_NOT_EXECUTION_PERMISSION"},
        final_outcome=FinalOutcome.COMMITTED,
        governance_identity=lineage,
        bind_reason_code="KEYCLOAK_GRANT_INDEPENDENTLY_RECONCILED",
        idempotency_key=consumption.idempotency_key, idempotency_status="CONSUMED",
        retry_safety="NO_EXTERNAL_EFFECT_RETRY", target_path=dispatch.endpoint_url,
        target_type="keycloak-client-role-mapping", action_contract_id=contract.id,
        action_contract_version=contract.version, commit_boundary_result="RECONCILED_KEYCLOAK_GRANT",
    )
    receipt = replace(receipt, bind_receipt_hash=hash_bind_receipt(receipt))
    outcome = build_outcome_receipt(
        decision_id=intent.decision_id, execution_intent_id=intent.execution_intent_id,
        bind_receipt_id=receipt.bind_receipt_id, operation_id=operation_id,
        action_class=contract.action_class, target_system=intent.target_system,
        target_resource=intent.target_resource, intended_action=intent.intended_action,
        requested_scope=scope, final_outcome="COMMITTED", postcondition_status="passed",
        observed_effects=[_observed_role_effect(confirmation)],
        evaluated_at=record.updated_at,
        metadata={**lineage, "bind_receipt_hash": receipt.bind_receipt_hash,
                  "idempotency_key": consumption.idempotency_key},
    )
    if not validate_outcome_receipt(outcome).is_valid or outcome.outcome_hash != outcome.deterministic_digest():
        raise ValueError("outcome validation")
    values = {
        "format_version": "keycloak-receipt-bundle/v1",
        "bind_receipt": receipt.to_dict(),
        "outcome_receipt": outcome.to_dict(),
    }
    return KeycloakReceiptBundle(**values, bundle_hash=sha256_of_canonical_json(values)), confirmation


async def _persist_keycloak_receipts(
    confirmation: KeycloakConfirmedReconciliation, bundle: KeycloakReceiptBundle,
) -> None:
    from psycopg.types.json import Jsonb
    from veritas_os.storage.db import get_pool

    record = confirmation.record
    payload = bundle.model_dump(mode="json")
    lineage = (
        Jsonb(confirmation.intent.model_dump(mode="json")),
        Jsonb(confirmation.observation.model_dump(mode="json")),
    )
    read_query = (
        "SELECT k.receipt_bundle FROM bind_keycloak_dispatch_intents AS k "
        "JOIN bind_effect_states AS e USING (operation_id) "
        "WHERE e.operation_id=%s AND e.record_hash=%s AND e.record::jsonb=%s::jsonb "
        "AND k.intent::jsonb=%s::jsonb AND k.reconciliation_observation::jsonb=%s::jsonb"
    )
    effect = (record.operation_id, record.record_hash, Jsonb(record.model_dump(mode="json")))
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "WITH confirmed AS (SELECT operation_id FROM bind_effect_states "
            "WHERE operation_id=%s AND record_hash=%s AND record::jsonb=%s::jsonb FOR SHARE) "
            "UPDATE bind_keycloak_dispatch_intents AS k SET receipt_bundle=%s "
            "FROM confirmed WHERE k.operation_id=confirmed.operation_id "
            "AND k.intent::jsonb=%s::jsonb AND k.reconciliation_observation::jsonb=%s::jsonb "
            "AND k.receipt_bundle IS NULL",
            (*effect, Jsonb(payload), *lineage),
        )
        row = await (await conn.execute(read_query, (*effect, *lineage))).fetchone()
        if row != (payload,):
            raise ValueError("receipt conflict or changed lineage")
    async with pool.connection() as conn:
        row = await (await conn.execute(read_query, (*effect, *lineage))).fetchone()
        if row != (payload,):
            raise ValueError("committed receipt readback")
