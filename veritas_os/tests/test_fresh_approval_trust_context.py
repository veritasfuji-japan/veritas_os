"""Non-effecting v0.3 composition preserves independent policy anchors."""

from dataclasses import replace

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.fresh_bind_source_chain import (
    build_fresh_bind_source_chain,
    fresh_bind_proof_report,
)
from veritas_os.policy.real_bind_context import derive_verified_real_bind_context_hash
from veritas_os.tests.test_fresh_bind_source_chain import _inputs, RECORDED_AT

pytestmark = pytest.mark.slow


def _policy(intent, inputs, required):
    return ActionClassContract(
        id=intent.intended_action,
        version="1",
        domain="test",
        action_class="test_action",
        description="Independent test policy",
        declared_intent="Review action",
        allowed_scope=list(inputs.authority_evidence_reference_bundle["bundle_scope"]),
        prohibited_scope=[],
        authority_sources=["test-authority"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"level": "low"},
        human_approval_rules={"required": required, "minimum_approvals": int(required)},
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="deny",
        metadata={},
    )


@pytest.fixture(scope="module", params=[True, False])
def chain(request):
    intent, inputs = _inputs()
    contract = _policy(intent, inputs, request.param)
    if not request.param:
        inputs = replace(inputs, human_approval_reference_bundle=None)
    result = build_fresh_bind_source_chain(
        intent, inputs, built_at=RECORDED_AT, expected_contract=contract
    )
    return contract, result


def test_fresh_v03_to_context_preserves_anchors_without_effects(chain):
    contract, result = chain
    gate = result.verified_gate_review_packet
    digest = derive_verified_real_bind_context_hash(
        gate,
        expected_source=result.authority_linkage_packet,
        expected_contract=contract,
    )
    assert len(digest) == 64
    assert (
        result.human_approval_linkage_packet.required_human_approval
        is (contract.human_approval_rules["required"])
    )
    report = fresh_bind_proof_report(result)
    assert not report["real_bind_authorization_issued"]
    assert not report["external_effect_performed"]
    assert not report["human_approval_proven"]
    assert not gate.bind_receipt_created and not gate.network_used


@pytest.mark.parametrize("missing", ["source", "contract", "both"])
def test_context_never_falls_back_to_embedded_anchors(chain, missing):
    contract, result = chain
    with pytest.raises(ValueError):
        derive_verified_real_bind_context_hash(
            result.verified_gate_review_packet,
            expected_source=None
            if missing != "contract"
            else result.authority_linkage_packet,
            expected_contract=None if missing != "source" else contract,
        )


def test_fully_rebuilt_policy_downgrade_rejected_at_context_boundary():
    intent, inputs = _inputs()
    trusted = _policy(intent, inputs, True)
    substituted = replace(
        trusted, human_approval_rules={"required": False, "minimum_approvals": 0}
    )
    forged = build_fresh_bind_source_chain(
        intent,
        replace(inputs, human_approval_reference_bundle=None),
        built_at=RECORDED_AT,
        expected_contract=substituted,
    )
    assert substituted.id == trusted.id and substituted.version == trusted.version
    with pytest.raises(ValueError):
        derive_verified_real_bind_context_hash(
            forged.verified_gate_review_packet,
            expected_source=forged.authority_linkage_packet,
            expected_contract=trusted,
        )


def test_required_policy_cannot_infer_missing_human_reference():
    intent, inputs = _inputs()
    with pytest.raises(ValueError):
        build_fresh_bind_source_chain(
            intent,
            replace(inputs, human_approval_reference_bundle=None),
            built_at=RECORDED_AT,
            expected_contract=_policy(intent, inputs, True),
        )
