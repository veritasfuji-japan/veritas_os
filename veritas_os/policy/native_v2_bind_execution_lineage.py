"""Bridge one consumed native-v2 authorization into BCBR lineage.

This module does not consume an authorization and does not create execution
authority.  It accepts only the concrete result returned by the native-v2
atomic consumer and projects its exact, already-consumed identity into the
process-local lineage type owned by bind_execution_capability.

The returned context manager is intentionally one-shot in scope: callers must
enter it only around the current Bind invocation.  The lineage remains audit
provenance, not a reusable effect capability; effect authority is still minted
and consumed at the registered ACTION sink.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from veritas_os.policy.bind_execution_capability import (
    ConsumedAuthorizationLineage,
    _mint_consumed_authorization_lineage,
    _transport_consumed_authorization_lineage,
)
from veritas_os.policy.native_bind_authorization_consumption import (
    NativeAuthorizationConsumptionResult,
)


class NativeV2BindExecutionLineageError(ValueError):
    """Fail-closed error for invalid native-v2 consumption provenance."""


@contextmanager
def transport_consumed_native_v2_authorization_lineage(
    result: NativeAuthorizationConsumptionResult,
) -> Iterator[ConsumedAuthorizationLineage]:
    """Transport exact native-v2 consumption provenance around one Bind call.

    No caller-supplied authorization, consumption, intent, credential or target
    identifiers are accepted.  Every field is projected from the typed result
    returned by consume_native_bind_authorization().
    """
    if type(result) is not NativeAuthorizationConsumptionResult:
        raise NativeV2BindExecutionLineageError(
            "NVBEL_NATIVE_CONSUMPTION_RESULT_REQUIRED"
        )
    if (
        result.authorization_consumed is not True
        or result.execution_authority_created is not False
        or result.credential_material_accessed is not False
        or result.bind_invoked is not False
        or result.bind_receipt_created is not False
        or result.external_action_executed is not False
    ):
        raise NativeV2BindExecutionLineageError(
            "NVBEL_NATIVE_CONSUMPTION_STATE_INVALID"
        )

    authorization = result.authorization
    record = result.consumption_record
    if (
        record.live_adapter_bind_authorization_id != authorization.authorization_id
        or record.live_adapter_bind_authorization_hash
        != authorization.authorization_hash
        or record.execution_intent_id != authorization.execution_intent_id
        or record.execution_intent_hash != authorization.execution_intent_hash
        or record.bind_context_hash != authorization.bind_context_hash
        or record.idempotency_key != authorization.idempotency_key
    ):
        raise NativeV2BindExecutionLineageError(
            "NVBEL_NATIVE_CONSUMPTION_BINDING_MISMATCH"
        )

    intent = authorization.execution_intent
    action_class = intent.get("intended_action")
    target_identity = intent.get("target_resource")
    if (
        not isinstance(action_class, str)
        or not action_class.strip()
        or not isinstance(target_identity, str)
        or not target_identity.strip()
        or not record.consumption_id
        or not record.credential_reference_digest
        or not record.credential_scope_binding_digest
    ):
        raise NativeV2BindExecutionLineageError(
            "NVBEL_NATIVE_LINEAGE_FIELDS_INVALID"
        )

    lineage = _mint_consumed_authorization_lineage(
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.authorization_hash,
        consumption_id=record.consumption_id,
        execution_intent_hash=authorization.execution_intent_hash,
        operation_id=record.consumption_id,
        action_class=action_class,
        target_identity=target_identity,
        credential_reference_digest=record.credential_reference_digest,
        credential_scope_digest=record.credential_scope_binding_digest,
    )
    with _transport_consumed_authorization_lineage(lineage):
        yield lineage
