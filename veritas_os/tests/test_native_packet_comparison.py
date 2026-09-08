"""Full packet comparisons retain normalization and independent reconstruction."""

from copy import deepcopy
from datetime import datetime
from functools import partial

import pytest

from veritas_os.policy import (
    promotion_human_approval_requirement_satisfaction as satisfaction,
)
from veritas_os.policy import promotion_requirement_bind_readiness as readiness
from veritas_os.policy import promotion_requirement_final_rechecks as rechecks
from veritas_os.policy.human_approval_requirement_resolution import _json
from veritas_os.tests.test_native_bind_authorization import (
    issued as issued_fixture,
    api_risk_source as source_fixture,
)

pytestmark = pytest.mark.slow
issued = issued_fixture
api_risk_source = source_fixture


@pytest.fixture(params=["satisfaction", "readiness", "gate", "fresh", "final"])
def stage(issued, request):
    """Use genuine API lineage and both human-approval requirement states."""
    _, inputs, *_ = issued
    src, gov = inputs["source_inputs"], inputs["governance_inputs"]
    anchors = dict(
        expected_source=gov.expected_source, expected_contract=gov.action_contract
    )
    final_inputs = dict(
        **anchors,
        expected_verified_at=src.expected_verified_at,
        expected_rechecked_at=src.expected_rechecked_at,
        current_endpoint=src.current_endpoint,
        current_credential_reference=src.current_credential_reference,
        required_credential_scope=src.required_credential_scope,
    )
    final = src.final_recheck
    fresh = final.source_packet
    gate = fresh["source_packet"]
    ready = gate["source_packet"]
    satisfied = ready["source_packet"]
    cases = {
        "satisfaction": (
            satisfaction,
            satisfied,
            partial(
                satisfaction.verify_promotion_human_approval_requirement_satisfaction_packet,
                **anchors,
            ),
            satisfaction.PromotionHumanApprovalRequirementSatisfactionPacket,
        ),
        "readiness": (
            readiness,
            ready,
            partial(
                readiness.verify_promotion_requirement_final_readiness_packet, **anchors
            ),
            readiness.PromotionRequirementFinalReadinessPacket,
        ),
        "gate": (
            readiness,
            gate,
            partial(readiness.verify_promotion_requirement_bind_gate_packet, **anchors),
            readiness.PromotionRequirementBindGatePacket,
        ),
        "fresh": (
            rechecks,
            fresh,
            partial(
                rechecks.verify_promotion_requirement_fresh_source_packet,
                **anchors,
                expected_verified_at=src.expected_verified_at,
            ),
            rechecks.PromotionRequirementFreshSourcePacket,
        ),
        "final": (
            rechecks,
            final.model_dump(mode="python"),
            partial(
                rechecks.verify_promotion_requirement_final_recheck_packet,
                **final_inputs,
            ),
            rechecks.PromotionRequirementFinalRecheckPacket,
        ),
    }
    return cases[request.param]


def test_complete_comparison_preserves_hashes_and_fresh_return(stage, monkeypatch):
    module, raw, verify, model = stage
    candidate = model.model_validate(deepcopy(raw))
    before = _json(candidate)
    normalized_models = []
    original = module._json

    def observe(value):
        if type(value) is model:
            normalized_models.append(value)
        return original(value)

    monkeypatch.setattr(module, "_json", observe)
    rebuilt = verify(candidate)
    assert rebuilt is not candidate
    assert rebuilt.model_dump(mode="python") == _json(rebuilt) == before
    assert candidate.model_dump(mode="python") == before
    # The typed input is still normalized, but the two comparison operands
    # must not trigger another recursive normalization of the complete tree.
    assert normalized_models == [candidate]


@pytest.mark.parametrize(
    "invalid", [float("nan"), float("inf"), b"bytes", {1: "key"}, datetime(2026, 9, 8)]
)
@pytest.mark.parametrize("typed", [False, True])
def test_malformed_nested_input_is_rejected_before_comparison(stage, invalid, typed):
    _, raw, verify, model = stage
    changed = deepcopy(raw)
    # model_copy can bypass schema validation; the public verifier must not.
    field = "execution_intent"
    changed[field] = {**changed[field], "malformed_nested_input": [invalid]}
    candidate = (
        model.model_validate(raw).model_copy(update={field: changed[field]})
        if typed
        else changed
    )
    with pytest.raises(ValueError):
        verify(candidate)


def test_rehashing_a_changed_field_does_not_replace_reconstruction(stage):
    module, raw, verify, _ = stage
    changed = deepcopy(raw)
    changed["required_human_approval"] = not changed["required_human_approval"]
    digest = module._packet_hash(changed)
    changed["packet_hash"] = digest
    changed["packet_id"] = changed["packet_id"].rsplit(":", 1)[0] + ":" + digest
    with pytest.raises(ValueError, match="RECONSTRUCTION_MISMATCH"):
        verify(changed)
