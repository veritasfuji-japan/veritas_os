"""Reconstructed children are local results, never caller trust shortcuts."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from veritas_os.policy import native_bind_authorization as native
from veritas_os.policy import promotion_requirement_runtime_risk as risk
from veritas_os.tests.test_native_bind_authorization import (
    issued as issued_fixture,
    api_risk_source as source_fixture,
)
from veritas_os.tests.test_human_approval_requirement_resolution_integration import (
    chain as legacy_fixture,
)

pytestmark = pytest.mark.slow
issued = issued_fixture
api_risk_source = source_fixture
legacy_chain = legacy_fixture


def test_valid_legacy_source_cannot_enter_native_satisfaction(legacy_chain):
    from veritas_os.policy.promotion_human_approval_requirement_satisfaction import (
        build_promotion_human_approval_requirement_satisfaction_packet,
    )

    source, contract, resolution = legacy_chain
    with pytest.raises(ValueError, match="PHARS_NATIVE_SOURCE_REQUIRED"):
        build_promotion_human_approval_requirement_satisfaction_packet(
            source,
            resolution,
            contract,
            None,
            datetime.fromisoformat(resolution.resolved_at),
        )


def test_native_projects_one_fresh_reconstruction_per_call(issued, monkeypatch):
    artifact, inputs, *_ = issued
    source, governance = inputs["source_inputs"], inputs["governance_inputs"]
    before = source.final_recheck.model_dump(mode="json")
    original = risk.verify_rechecks
    calls = []

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return result

    monkeypatch.setattr(risk, "verify_rechecks", observe)
    _, final, context = native._verified_source(
        artifact.source_runtime_risk_packet,
        source,
        governance,
    )
    assert calls == [final] and calls[0] is final
    assert final is not source.final_recheck
    assert context.execution_intent == before["execution_intent"]
    final.execution_intent["target_resource"] = "attacker"
    assert source.final_recheck.model_dump(mode="json") == before
    _, second, _ = native._verified_source(
        artifact.source_runtime_risk_packet,
        source,
        governance,
    )
    assert len(calls) == 2 and second is not final
    assert second.model_dump(mode="json") == before


@pytest.mark.parametrize(
    "change", ["contract", "source", "endpoint", "credential", "clock"]
)
def test_previous_success_never_skips_changed_external_inputs(issued, change):
    artifact, inputs, *_ = issued
    source, governance = inputs["source_inputs"], inputs["governance_inputs"]
    native._verified_source(artifact.source_runtime_risk_packet, source, governance)
    if change == "contract":
        contract = deepcopy(governance.action_contract)
        contract.human_approval_rules["required"] = not contract.human_approval_rules[
            "required"
        ]
        governance = replace(governance, action_contract=contract)
    elif change == "source":
        governance = replace(governance, expected_source=None)
    elif change == "clock":
        governance = replace(
            governance,
            verification_now=governance.verification_now + timedelta(minutes=1),
        )
    else:
        field = (
            "current_endpoint"
            if change == "endpoint"
            else "current_credential_reference"
        )
        source = replace(source, **{field: {}})
    with pytest.raises(ValueError):
        native._verified_source(artifact.source_runtime_risk_packet, source, governance)
