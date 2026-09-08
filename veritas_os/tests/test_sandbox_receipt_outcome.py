"""Native verification and archived-result binding, without live external access."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json

import pytest

from veritas_os.policy import sandbox_receipt_outcome as module
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome, hash_bind_receipt
from veritas_os.governance.outcome_receipt import OutcomeReceipt, validate_outcome_receipt
from veritas_os.tests.test_sandbox_reconciliation import (
    issued as issued_fixture, prepared_inputs as prepared_fixture, setup_case, reconcile,
)
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_https_transport import TOKEN

pytestmark = pytest.mark.slow
issued = issued_fixture
prepared_inputs = prepared_fixture


async def ready(prepared_inputs, monkeypatch):
    artifact, args, original, writer, calls = await setup_case(prepared_inputs, monkeypatch)
    result = await reconcile(artifact, args)
    args.pop("provider")
    args.pop("trusted_clock")
    return artifact, args, result, writer, calls


async def publish(artifact, args):
    return await module.publish_sandbox_receipts(artifact, json.dumps(PAYLOAD), **args)


@pytest.mark.asyncio
async def test_publish_existing_artifacts_once_and_bind_full_lineage(prepared_inputs, monkeypatch):
    artifact, args, result, writer, calls = await ready(prepared_inputs, monkeypatch)
    first = await publish(artifact, args)
    repeat = await publish(artifact, args)
    assert first == repeat
    bind_data = dict(first.bind_receipt)
    bind_data["final_outcome"] = FinalOutcome(bind_data["final_outcome"])
    receipt = BindReceipt(**bind_data)
    outcome = OutcomeReceipt(**first.outcome_receipt)
    assert hash_bind_receipt(receipt) == receipt.bind_receipt_hash
    assert outcome.deterministic_digest() == outcome.outcome_hash
    assert validate_outcome_receipt(outcome).is_valid
    assert outcome.committed and outcome.postcondition_status == "passed"
    assert outcome.bind_receipt_id == receipt.bind_receipt_id
    assert outcome.metadata["bind_receipt_hash"] == receipt.bind_receipt_hash
    assert receipt.governance_identity["authorization_id"] == artifact.authorization_id
    assert receipt.governance_identity["reconciliation_evidence_hash"] == result.record.reconciliation_evidence_hash
    assert not receipt.trustlog_hash
    assert receipt.risk_check_result == {"status": "LIVE_RESULTS_NOT_ARCHIVED"}
    assert receipt.admissibility_result["status"] == "RETROSPECTIVE_RECORD_NOT_EXECUTION_PERMISSION"
    store = args["effect_store"]
    assert len(store._sandbox_receipts) == 1
    assert await store.get(result.record.operation_id) == result.record
    assert len(calls) == len(writer.writes) == 1
    assert TOKEN.decode() not in first.model_dump_json()
    # Returned mutable dictionaries must not mutate durable contents.
    first.bind_receipt["final_outcome"] = "BLOCKED"
    assert await publish(artifact, args) == repeat


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["archive", "record", "consumption", "policy", "reader", "source", "durability", "payload", "stored_pair"])
async def test_missing_or_substituted_lineage_never_publishes(prepared_inputs, monkeypatch, mode):
    artifact, args, result, writer, calls = await ready(prepared_inputs, monkeypatch)
    store = args["effect_store"]
    operation_id = result.record.operation_id
    if mode == "archive":
        del store._archives[operation_id]
    elif mode == "record":
        store._records[operation_id] = store._archives[operation_id].original_record
    elif mode == "consumption":
        original_get = args["consumption_store"].get
        async def get(key):
            row = await original_get(key)
            return row.model_copy(update={"credential_scope_binding_digest": "changed"})
        monkeypatch.setattr(args["consumption_store"], "get", get)
    elif mode == "policy":
        args["verifier_policy"] = module.ReconciliationVerifierPolicy(())
    elif mode == "reader":
        args["reader_policy"] = replace(args["reader_policy"], credential_version="changed")
    elif mode == "source":
        args["issuance_source_inputs"] = replace(args["issuance_source_inputs"], current_endpoint={})
    elif mode == "durability":
        args["allow_in_memory_for_testing"] = False
    elif mode == "stored_pair":
        store._sandbox_receipts[operation_id] = '{"forged":true}'
    if mode == "payload":
        call = module.publish_sandbox_receipts(artifact, json.dumps(PAYLOAD | {"message": "changed"}), **args)
    else:
        call = publish(artifact, args)
    with pytest.raises(module.SandboxReceiptError) as caught:
        await call
    assert caught.value.__context__ is None
    assert len(calls) == 1
    if mode != "stored_pair":
        assert not store._sandbox_receipts
    else:
        assert store._sandbox_receipts[operation_id] == '{"forged":true}'


@pytest.mark.asyncio
async def test_concurrent_publishers_return_identical_pair(prepared_inputs, monkeypatch):
    artifact, args, _, _, calls = await ready(prepared_inputs, monkeypatch)
    results = await asyncio.gather(*(publish(artifact, args) for _ in range(3)))
    assert all(result == results[0] for result in results)
    assert len(args["effect_store"]._sandbox_receipts) == 1 and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["before", "lost_ack", "cancel"])
async def test_publication_failure_and_safe_repeat(prepared_inputs, monkeypatch, mode):
    artifact, args, _, _, calls = await ready(prepared_inputs, monkeypatch)
    real_persist = module._persist_receipts
    async def fail(*positional, **kwargs):
        if mode == "lost_ack":
            await real_persist(*positional, **kwargs)
        if mode == "cancel":
            raise asyncio.CancelledError(TOKEN.decode())
        raise RuntimeError(TOKEN.decode())
    monkeypatch.setattr(module, "_persist_receipts", fail)
    with pytest.raises(asyncio.CancelledError if mode == "cancel" else module.SandboxReceiptError) as caught:
        await publish(artifact, args)
    assert TOKEN.decode() not in str(caught.value) and caught.value.__context__ is None
    assert bool(args["effect_store"]._sandbox_receipts) == (mode == "lost_ack")
    saved = dict(args["effect_store"]._sandbox_receipts)
    monkeypatch.setattr(module, "_persist_receipts", real_persist)
    assert await publish(artifact, args)
    if mode == "lost_ack":
        assert saved == args["effect_store"]._sandbox_receipts
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("event_id", "44444444-4444-4444-8444-444444444444"), ("payload_digest", "f" * 64)])
async def test_self_consistent_archive_for_different_action_rejected(prepared_inputs, monkeypatch, field, value):
    from veritas_os.policy.trusted_https_reconciliation import reconciliation_observation_digest
    artifact, args, result, _, _ = await ready(prepared_inputs, monkeypatch)
    store = args["effect_store"]
    archive = store._archives[result.record.operation_id]
    operation = archive.operation.model_copy(update={field: value})
    observation = archive.proof.evidence.model_copy(update={
        "external_ack_digest": module.sha256_of_canonical_json(operation.model_dump(mode="json")),
    })
    observation = observation.model_copy(update={"observation_digest": reconciliation_observation_digest(observation)})
    proof = archive.proof.model_copy(update={
        "evidence": observation,
        "verification_proof_hash": module.sha256_of_canonical_json({
            "observation": observation.model_dump(mode="json"), "policy_hash": archive.proof.verifier_policy_hash,
            "original_record_hash": archive.original_record.record_hash,
            "reader_metadata_digest": archive.reader_metadata_digest,
        }),
    })
    archive = archive.model_copy(update={"operation": operation, "proof": proof})
    record = module._build_record(
        consumption=prepared_inputs[2], state=module.EffectExecutionState.CONFIRMED_EFFECT,
        revision=3, updated_at=proof.verified_at, reason_code="SANDBOX_READONLY_LOOKUP_CONFIRMED",
        reconciliation_evidence_hash=proof.deterministic_digest(),
    )
    module.validate_archive(record, archive)
    store._records[record.operation_id], store._archives[record.operation_id] = record, archive
    with pytest.raises(module.SandboxReceiptError):
        await publish(artifact, args)
    assert not store._sandbox_receipts
