"""Integrity-checked sandbox reconciliation archive; never execution authority.

Hashes detect inconsistent storage, not a malicious database operator rewriting
all records. The original HTTPS verifier remains the observation trust boundary.
No credential material, HTTP headers or event message is archived.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState, EffectStateRecord, ReconciliationClaim,
    VerifiedReconciliationEvidence, _record_hash_payload,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.sandbox_event_store import SandboxOperation, validate_uuid, validate_key
from veritas_os.policy.trusted_https_reconciliation import reconciliation_observation_digest
from veritas_os.security.hash import sha256_of_canonical_json


class SandboxReconciliationArchive(BaseModel):
    """Full verified evidence and inputs needed to recompute its proof hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["sandbox-reconciliation-archive/v1"] = "sandbox-reconciliation-archive/v1"
    original_record: EffectStateRecord
    operation: SandboxOperation
    reader_metadata_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof: VerifiedReconciliationEvidence

    @field_validator("operation", mode="before")
    @classmethod
    def explicit_operation(cls, value: object) -> object:
        """Stored observations cannot infer a missing PERSISTED field."""
        fields = {"operation_id", "event_id", "idempotency_key", "payload_digest", "state"}
        if isinstance(value, SandboxOperation):
            if value.model_fields_set != fields:
                raise ValueError("operation fields")
        elif type(value) is not dict or set(value) != fields:
            raise ValueError("operation fields")
        return value


def validate_archive(record: EffectStateRecord, archive: SandboxReconciliationArchive) -> SandboxReconciliationArchive:
    """Revalidate stored schemas, canonical hashes and exact terminal lineage.

    Integrity verification only: no new HTTPS observation, policy approval,
    authorization or outcome receipt is created by reading stored evidence.
    """
    archive = SandboxReconciliationArchive.model_validate(archive.model_dump(mode="python", warnings=False))
    record = EffectStateRecord.model_validate(record.model_dump(mode="python", warnings=False))
    original, operation, proof = archive.original_record, archive.operation, archive.proof
    evidence = proof.evidence
    for item in (original, record):
        if item.format_version != "bind-effect-state/v1" or item.record_hash != sha256_of_canonical_json(
            _record_hash_payload(item.model_dump(mode="json"))
        ):
            raise ValueError("record hash")
    if (original.state != EffectExecutionState.EFFECT_UNKNOWN or original.revision != 2
            or original.reason_code != "SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED"
            or original.reconciliation_evidence_hash is not None
            or record.state != EffectExecutionState.CONFIRMED_EFFECT or record.revision != 3
            or record.reason_code != "SANDBOX_READONLY_LOOKUP_CONFIRMED"):
        raise ValueError("state")
    for field in ("operation_id", "authorization_id", "authorization_hash", "consumption_id",
                  "consumption_hash", "execution_intent_id", "idempotency_key"):
        if getattr(original, field) != getattr(record, field):
            raise ValueError("lineage")
    if original.operation_id != original.consumption_id:
        raise ValueError("operation lineage")
    for field in ("operation_id", "authorization_id", "consumption_id"):
        if getattr(evidence, field) != getattr(original, field):
            raise ValueError("evidence lineage")
    validate_uuid(operation.operation_id)
    validate_uuid(operation.event_id)
    validate_key(operation.idempotency_key)
    if (operation.state != "PERSISTED" or operation.idempotency_key != original.idempotency_key
            or evidence.format_version != "bind-effect-reconciliation-evidence/v1"
            or evidence.claim != ReconciliationClaim.CONFIRMED_EFFECT
            or evidence.source_type != "sandbox-readonly-https"
            or proof.verifier_id != "sandbox-readonly-reconciliation/v1"
            or evidence.external_operation_reference != operation.operation_id
            or evidence.external_ack_digest != sha256_of_canonical_json(operation.model_dump(mode="json"))
            or evidence.observation_digest != reconciliation_observation_digest(evidence)
            or record.reconciliation_evidence_hash != proof.deterministic_digest()
            or record.updated_at != proof.verified_at or proof.verified_at != evidence.observed_at
            or datetime.fromisoformat(_timestamp(original.updated_at)) > datetime.fromisoformat(_timestamp(record.updated_at))):
        raise ValueError("observation")
    if proof.verification_proof_hash != sha256_of_canonical_json({
        "observation": evidence.model_dump(mode="json"), "policy_hash": proof.verifier_policy_hash,
        "original_record_hash": original.record_hash,
        "reader_metadata_digest": archive.reader_metadata_digest,
    }):
        raise ValueError("proof")
    return archive
