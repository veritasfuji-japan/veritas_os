"""External trust anchors survive both native review stages and full rehashing."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from veritas_os.policy import promotion_requirement_bind_readiness as module
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import (
    api_source as captured_api_source,
    native as native_source,
    _contract,
    _link,
    authority,
    resolve,
    satisfy,
    sources,
)

pytestmark = pytest.mark.slow
api_source = captured_api_source
native = native_source


def _decision(now, accepted=True):
    return {
        "review_id": "local-review:1",
        "reviewer_id": "reviewer:alice",
        "review_reason": "Review independently bound prerequisite evidence only.",
        "reviewed_at": now.isoformat(),
        "accepted": accepted,
        "acknowledged_no_authorization": True,
        "acknowledged_no_human_approval_proof": True,
        "acknowledged_no_authority_evidence_proof": True,
        "acknowledged_no_external_effect": True,
        "acknowledged_independent_policy_binding": True,
    }


def _chain(source, contract, now):
    resolution = resolve(source, contract, now)
    sat = satisfy(
        source, resolution, contract,
        _link(source, now) if resolution.required_human_approval else None, now,
    )
    anchors = {"expected_source": source, "expected_contract": contract}
    ready = module.build_promotion_requirement_final_readiness_packet(
        sat, _decision(now), now, **anchors
    )
    gate = module.build_promotion_requirement_bind_gate_packet(
        ready, _decision(now), now, **anchors
    )
    return ready, gate


STAGES = (
    (0, module.verify_promotion_requirement_final_readiness_packet),
    (1, module.verify_promotion_requirement_bind_gate_packet),
)


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("stage,verify", STAGES)
def test_both_states_preserve_complete_source_and_return_rebuilt(native, required, stage, verify):
    source, _, _, now = native
    contract = _contract(required=required)
    packet = _chain(source, contract, now)[stage]
    result = verify(packet, expected_source=source, expected_contract=contract)
    assert result == packet and result is not packet
    assert result.required_human_approval is required
    assert result.execution_intent == source.execution_intent
    assert result.fail_closed is False
    assert ("human_approval_receipt_verification" in result.future_authorization_requirements) is required
    assert "fresh_verified_source_gate" in result.future_authorization_requirements
    assert "single_use_consumption" in result.future_invocation_requirements
    sat = result.source_packet if stage == 0 else result.source_packet["source_packet"]
    assert sat["source_authority_evidence_linkage_review_packet"] == source.model_dump(mode="json")
    assert (sat["required_human_approval_linkage_packet"] is not None) is required
    for name in (
        "human_approval_created", "human_approval_proven", "authority_evidence_proven",
        "execution_authority_created", "bind_authorization_created", "bind_invoked",
        "bind_receipt_created", "credential_material_accessed", "network_used",
        "external_effect_occurred", "ready_for_real_bind",
    ):
        assert getattr(result, name) is False
    schema = Path(__file__).resolve().parents[2] / "schemas" / (result.format_version.replace("/", "-") + ".schema.json")
    Draft202012Validator(json.loads(schema.read_text())).validate(result.model_dump(mode="json"))


@pytest.mark.parametrize("rules", [
    {"required": False, "minimum_approvals": 0},
    {"required": True, "minimum_approvals": 2},
    {"required": True, "minimum_approvals": 1, "approver_role": "attacker"},
])
@pytest.mark.parametrize("stage,verify", STAGES)
def test_entire_chain_rebuilt_with_same_id_version_contract_is_rejected(native, rules, stage, verify):
    source, trusted, _, now = native
    attacker = replace(trusted, human_approval_rules=rules)
    assert (attacker.id, attacker.version) == (trusted.id, trusted.version)
    forged = _chain(source, attacker, now)[stage]
    with pytest.raises(ValueError):
        verify(forged, expected_source=source, expected_contract=trusted)


@pytest.mark.parametrize("stage,verify", STAGES)
def test_entire_chain_rebuilt_for_substituted_source_is_rejected(native, stage, verify):
    source, contract, _, now = native
    bundle = source.authority_evidence_reference_bundle.model_dump(mode="json")
    bundle["bundle_declared_by"] = "attacker"
    other = authority(source.source_bind_pre_dispatch_review_packet, bundle, sources.RECORDED_AT)
    forged = _chain(other, contract, now)[stage]
    with pytest.raises(ValueError):
        verify(forged, expected_source=source, expected_contract=contract)


@pytest.mark.parametrize("field", [
    "action_contract_digest", "source_authority_evidence_linkage_review_hash",
    "requirement_resolution_hash", "required_human_approval",
    "future_authorization_requirements", "execution_intent_hash", "fail_closed",
])
@pytest.mark.parametrize("stage,verify", STAGES)
def test_rehashed_derived_fields_are_rejected(native, stage, verify, field):
    source, contract, _, now = native
    raw = _chain(source, contract, now)[stage].model_dump(mode="json")
    raw[field] = not raw[field] if isinstance(raw[field], bool) else [] if isinstance(raw[field], list) else "0" * 64
    raw["packet_hash"] = module._packet_hash(raw)
    raw["packet_id"] = f"{raw['format_version']}:sha256:{raw['packet_hash']}"
    with pytest.raises(ValueError, match="PRBR_RECONSTRUCTION_MISMATCH"):
        verify(raw, expected_source=source, expected_contract=contract)


@pytest.mark.parametrize("stage,verify", STAGES)
@pytest.mark.parametrize("missing", ["expected_source", "expected_contract"])
def test_independent_anchors_are_mandatory(native, stage, verify, missing):
    source, contract, _, now = native
    packet = _chain(source, contract, now)[stage]
    anchors = {"expected_source": source, "expected_contract": contract}
    del anchors[missing]
    with pytest.raises(TypeError):
        verify(packet, **anchors)
    anchors[missing] = None
    with pytest.raises(ValueError):
        verify(packet, **anchors)


def test_rejected_readiness_cannot_reach_gate(native):
    source, contract, _, now = native
    ready, _ = _chain(source, contract, now)
    anchors = {"expected_source": source, "expected_contract": contract}
    rejected = module.build_promotion_requirement_final_readiness_packet(
        ready.source_packet, _decision(now, False), now, **anchors
    )
    assert module.verify_promotion_requirement_final_readiness_packet(rejected, **anchors).fail_closed
    with pytest.raises(ValueError, match="PRBR_READINESS_REJECTED"):
        module.build_promotion_requirement_bind_gate_packet(rejected, _decision(now), now, **anchors)
    gate = module.build_promotion_requirement_bind_gate_packet(ready, _decision(now, False), now, **anchors)
    assert module.verify_promotion_requirement_bind_gate_packet(gate, **anchors).fail_closed
    assert not gate.ready_for_fresh_verified_source_gate


@pytest.mark.parametrize("stage", [0, 1])
@pytest.mark.parametrize("error", ["before_source", "before_review", "naive", "acknowledgement"])
def test_invalid_review_or_timestamp_fails_closed(native, stage, error):
    source, contract, _, now = native
    ready, _ = _chain(source, contract, now)
    decision = _decision(now)
    recorded = now
    if error == "before_source":
        decision["reviewed_at"] = (now - timedelta(seconds=1)).isoformat()
    elif error == "before_review":
        recorded -= timedelta(seconds=1)
    elif error == "naive":
        decision["reviewed_at"] = now.replace(tzinfo=None).isoformat()
    else:
        decision["acknowledged_independent_policy_binding"] = False
    builder = (module.build_promotion_requirement_final_readiness_packet,
               module.build_promotion_requirement_bind_gate_packet)[stage]
    with pytest.raises(ValueError):
        builder(ready.source_packet if stage == 0 else ready, decision, recorded,
                expected_source=source, expected_contract=contract)


def test_real_authenticated_api_reaches_policy_bound_gate(api_source):
    source, now, required = api_source
    contract = _contract(action="post_synthetic_review", required=required)
    before = deepcopy(source.model_dump(mode="json"))
    _, gate = _chain(source, contract, now)
    result = module.verify_promotion_requirement_bind_gate_packet(
        gate, expected_source=source, expected_contract=contract
    )
    assert result.required_human_approval is required
    assert result.execution_intent == source.execution_intent
    assert result.ready_for_fresh_verified_source_gate
    assert not result.ready_for_real_bind
    assert source.model_dump(mode="json") == before
