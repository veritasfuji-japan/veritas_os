"""Storage integrity tests with synthetic evidence, not external-effect proof."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError, EffectExecutionState, InMemoryAtomicEffectStateStore,
    ReconciliationClaim, ReconciliationEvidence, VerifiedReconciliationEvidence, _build_record,
)
from veritas_os.policy.sandbox_event_store import SandboxOperation
from veritas_os.policy.sandbox_reconciliation_archive import SandboxReconciliationArchive, validate_archive
from veritas_os.policy.trusted_https_reconciliation import reconciliation_observation_digest
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_pg_bind_effect_state_contention import _consumption


def archive_case(token="archive-test"):
    consumed = _consumption(token)
    original = _build_record(
        consumption=consumed, state=EffectExecutionState.EFFECT_UNKNOWN, revision=2,
        updated_at="2026-08-24T00:00:01+00:00",
        reason_code="SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
    )
    operation = SandboxOperation(
        operation_id="22222222-2222-4222-8222-222222222222",
        event_id="33333333-3333-4333-8333-333333333333",
        idempotency_key=original.idempotency_key, payload_digest="a" * 64, state="PERSISTED",
    )
    observation = ReconciliationEvidence(
        operation_id=original.operation_id, authorization_id=original.authorization_id,
        consumption_id=original.consumption_id, claim=ReconciliationClaim.CONFIRMED_EFFECT,
        source_type="sandbox-readonly-https", source_identity="https://sandbox.test",
        observed_at="2026-08-24T00:00:02+00:00", external_operation_reference=operation.operation_id,
        external_ack_digest=sha256_of_canonical_json(operation.model_dump(mode="json")),
        observation_digest="0" * 64,
    )
    observation = observation.model_copy(update={"observation_digest": reconciliation_observation_digest(observation)})
    metadata_digest = "b" * 64
    policy_hash = "c" * 64
    proof = VerifiedReconciliationEvidence(
        evidence=observation, verifier_id="sandbox-readonly-reconciliation/v1",
        verifier_policy_hash=policy_hash, verified_at=observation.observed_at,
        verification_proof_hash=sha256_of_canonical_json({
            "observation": observation.model_dump(mode="json"), "policy_hash": policy_hash,
            "original_record_hash": original.record_hash, "reader_metadata_digest": metadata_digest,
        }),
    )
    record = _build_record(
        consumption=consumed, state=EffectExecutionState.CONFIRMED_EFFECT, revision=3,
        updated_at=proof.verified_at, reason_code="SANDBOX_READONLY_LOOKUP_CONFIRMED",
        reconciliation_evidence_hash=proof.deterministic_digest(),
    )
    archive = SandboxReconciliationArchive(
        original_record=original, operation=operation, reader_metadata_digest=metadata_digest, proof=proof,
    )
    return original, record, archive


def test_archive_roundtrip_recomputes_all_proof_inputs():
    _, record, archive = archive_case()
    restored = SandboxReconciliationArchive.model_validate_json(archive.model_dump_json())
    assert validate_archive(record, restored) == archive


@pytest.mark.parametrize("path,value", [
    (("reader_metadata_digest",), "f" * 64),
    (("operation", "event_id"), "44444444-4444-4444-8444-444444444444"),
    (("operation", "state"), "SUCCESS"),
    (("operation", "payload_digest"), "f" * 64),
    (("operation", "operation_id"), "44444444-4444-4444-8444-444444444444"),
    (("original_record", "record_hash"), "f" * 64),
    (("proof", "verification_proof_hash"), "f" * 64),
    (("proof", "verifier_policy_hash"), "f" * 64),
    (("proof", "evidence", "observation_digest"), "f" * 64),
    (("proof", "evidence", "authorization_id"), "other"),
    (("proof", "verified_at"), "2026-08-24T00:00:03+00:00"),
])
def test_archive_substitution_is_rejected(path, value):
    _, record, archive = archive_case()
    data = deepcopy(archive.model_dump(mode="json"))
    node = data
    for field in path[:-1]:
        node = node[field]
    node[path[-1]] = value
    with pytest.raises(ValueError):
        validate_archive(record, SandboxReconciliationArchive.model_validate(data))


def test_missing_operation_state_and_unknown_fields_rejected():
    _, _, archive = archive_case()
    for key in archive.operation.model_dump():
        data = archive.model_dump(mode="json")
        del data["operation"][key]
        with pytest.raises(ValueError):
            SandboxReconciliationArchive.model_validate(data)
    with pytest.raises(ValueError):
        SandboxReconciliationArchive.model_validate(archive.model_dump() | {"token": "unwanted"})


@pytest.mark.asyncio
async def test_atomic_archive_has_one_winner_and_cannot_be_rewritten():
    original, record, archive = archive_case()
    store = InMemoryAtomicEffectStateStore()
    assert await store.create_in_flight(original)
    outcomes = await asyncio.gather(*(store.confirm_reconciliation(
        expected=original, record=record, archive=archive,
    ) for _ in range(16)))
    assert outcomes.count(True) == 1
    assert await store.get_reconciliation(record.operation_id) == archive
    assert not await store.transition(
        operation_id=record.operation_id, expected_state=record.state,
        record=record.model_copy(update={"revision": 4}),
    )
    assert await store.get(record.operation_id) == record


@pytest.mark.asyncio
async def test_missing_mismatched_and_tampered_archives_fail_closed():
    original, record, archive = archive_case()
    store = InMemoryAtomicEffectStateStore()
    assert await store.get_reconciliation(original.operation_id) is None
    await store.create_in_flight(original)
    with pytest.raises(BindEffectStateError):
        await store.get_reconciliation(original.operation_id)
    with pytest.raises(BindEffectStateError):
        await store.confirm_reconciliation(expected=record, record=record, archive=archive)
    assert await store.confirm_reconciliation(expected=original, record=record, archive=archive)
    store._records[record.operation_id] = original
    with pytest.raises(ValueError):
        await store.get_reconciliation(record.operation_id)


@pytest.mark.asyncio
async def test_stale_expected_record_cannot_publish_evidence():
    original, record, archive = archive_case()
    store = InMemoryAtomicEffectStateStore()
    await store.create_in_flight(original.model_copy(update={"record_hash": "f" * 64}))
    assert not await store.confirm_reconciliation(expected=original, record=record, archive=archive)
    assert not store._archives
