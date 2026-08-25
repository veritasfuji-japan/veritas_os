"""Tests for fresh, fail-closed Real Bind prerequisite composition."""

from __future__ import annotations

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.fresh_bind_source_chain import (
    FreshBindSourceChainError,
    FreshBindSourceChainInputs,
    build_fresh_bind_source_chain,
    fresh_bind_proof_report,
)
from veritas_os.tests.test_live_adapter_dry_run_authority_evidence_linkage import (
    _bundle as authority_bundle,
)
from veritas_os.tests.test_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT,
    _decision as gate_decision,
)
from veritas_os.tests.test_live_adapter_dry_run_bind_pre_dispatch_review import (
    _decision as pre_dispatch_decision,
)
from veritas_os.tests.test_live_adapter_dry_run_credential_authorization import (
    _reference as credential_reference,
    _snapshot as credential_snapshot,
)
from veritas_os.tests.test_live_adapter_dry_run_endpoint_allowlist import (
    _candidate as endpoint_candidate,
    _snapshot as endpoint_snapshot,
)
from veritas_os.tests.test_live_adapter_dry_run_final_bind_authorization_readiness import (
    _decision as final_decision,
)
from veritas_os.tests.test_live_adapter_dry_run_human_approval_linkage import (
    _bundle as human_bundle,
)
from veritas_os.tests.test_live_adapter_dry_run_operator_dispatch_review import (
    _decision as operator_decision,
)
from veritas_os.tests.test_reference_adapter_rehearsal import (
    _packet as rehearsal_packet,
)


def _inputs() -> tuple[ExecutionIntent, FreshBindSourceChainInputs]:
    rehearsal = rehearsal_packet(semantic_match=False)
    intent = ExecutionIntent(**rehearsal.execution_intent)
    endpoint = endpoint_candidate()
    credential = credential_reference()
    return intent, FreshBindSourceChainInputs(
        reference_rehearsal_packet=rehearsal,
        endpoint_candidate=endpoint,
        endpoint_allowlist_snapshot=endpoint_snapshot(endpoint),
        credential_reference=credential,
        credential_policy_snapshot=credential_snapshot(credential),
        operator_review_decision=operator_decision(),
        bind_pre_dispatch_review_decision=pre_dispatch_decision(),
        authority_evidence_reference_bundle=authority_bundle(),
        human_approval_reference_bundle=human_bundle(),
        final_readiness_review_decision=final_decision(),
        gate_review_decision=gate_decision(),
    )


def test_fresh_chain_preserves_exact_intent_and_independently_verifies() -> None:
    intent, inputs = _inputs()
    packet = build_fresh_bind_source_chain(intent, inputs, built_at=RECORDED_AT)
    assert packet.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == intent.execution_intent_id
    assert packet.request_dispatch_state == "NOT_DISPATCHED"
    assert packet.bind_state == "NOT_BOUND"


@pytest.mark.parametrize("mutation", ["object", "id", "hash", "digest"])
def test_fresh_chain_rejects_intent_or_source_tampering(mutation: str) -> None:
    intent, inputs = _inputs()
    raw = inputs.reference_rehearsal_packet.model_dump(mode="json")
    if mutation == "object":
        raw["execution_intent"]["target_system"] = "foreign"
    elif mutation == "id":
        raw["execution_intent_id"] = "foreign"
    elif mutation == "hash":
        raw["execution_intent_hash"] = "0" * 64
    else:
        raw["reference_rehearsal_hash"] = "0" * 64
    changed = FreshBindSourceChainInputs(
        **{**inputs.__dict__, "reference_rehearsal_packet": raw}
    )
    with pytest.raises((FreshBindSourceChainError, ValueError)):
        build_fresh_bind_source_chain(intent, changed, built_at=RECORDED_AT)


def test_report_never_claims_an_external_effect() -> None:
    report = fresh_bind_proof_report(authorization_issued=True)
    assert report["authorization_source_chain_proven"] is True
    assert report["real_bind_authorization_issued"] is True
    assert report["external_effect_performed"] is False
    assert report["real_decision_to_effect_e2e"] is False
