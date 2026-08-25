"""Tests for fresh, fail-closed Real Bind prerequisite composition."""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.fresh_bind_source_chain import (
    FreshBindSourceChainError,
    FreshBindSourceChainInputs,
    build_fresh_bind_source_chain,
    fresh_bind_proof_report,
)
from veritas_os.tests.test_adapter_dry_run_fixture_result import _fixtures
from veritas_os.tests.test_bind_adapter_contract_selection import (
    _packet as selection_packet,
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


def _inputs() -> tuple[ExecutionIntent, FreshBindSourceChainInputs]:
    selection = selection_packet(semantic_match=False)
    intent = ExecutionIntent(**selection.execution_intent)
    endpoint = endpoint_candidate()
    credential = credential_reference()
    return intent, FreshBindSourceChainInputs(
        adapter_contract_selection_packet=selection,
        fixture_step_results=_fixtures(),
        reference_rehearsal_fixture={"scenario": "deterministic-reference-v1"},
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


def test_fresh_chain_constructs_new_root_and_preserves_exact_intent() -> None:
    intent, inputs = _inputs()
    result = build_fresh_bind_source_chain(intent, inputs, built_at=RECORDED_AT)
    root = result.root_rehearsal_packet
    gate = result.verified_gate_review_packet
    assert root is not inputs.adapter_contract_selection_packet
    assert root.execution_intent == intent.to_dict()
    assert gate.execution_intent == intent.to_dict()
    assert gate.execution_intent_id == intent.execution_intent_id
    assert gate.request_dispatch_state == "NOT_DISPATCHED"
    assert gate.bind_state == "NOT_BOUND"


@pytest.mark.parametrize("mutation", ["object", "id", "hash", "digest"])
def test_fresh_chain_rejects_selection_intent_or_digest_tampering(
    mutation: str,
) -> None:
    intent, inputs = _inputs()
    raw = inputs.adapter_contract_selection_packet.model_dump(mode="json")
    if mutation == "object":
        raw["execution_intent"]["target_system"] = "foreign"
    elif mutation == "id":
        raw["execution_intent_id"] = "foreign"
    elif mutation == "hash":
        raw["execution_intent_hash"] = "0" * 64
    else:
        raw["adapter_contract_selection_hash"] = "0" * 64
    with pytest.raises((FreshBindSourceChainError, ValueError)):
        build_fresh_bind_source_chain(
            intent,
            replace(inputs, adapter_contract_selection_packet=raw),
            built_at=RECORDED_AT,
        )


def test_endpoint_and_credential_mismatches_fail_closed() -> None:
    intent, inputs = _inputs()
    endpoint = dict(inputs.endpoint_candidate)
    endpoint["endpoint_host"] = "foreign.invalid"
    with pytest.raises(ValueError):
        build_fresh_bind_source_chain(
            intent, replace(inputs, endpoint_candidate=endpoint), built_at=RECORDED_AT
        )

    credential = dict(inputs.credential_reference)
    credential["adapter_contract_id"] = "foreign-contract"
    with pytest.raises(ValueError):
        build_fresh_bind_source_chain(
            intent,
            replace(inputs, credential_reference=credential),
            built_at=RECORDED_AT,
        )


def test_public_builder_has_no_root_or_lineage_override() -> None:
    parameters = inspect.signature(build_fresh_bind_source_chain).parameters
    assert "reference_rehearsal_packet" not in parameters
    assert {
        "execution_intent_id",
        "execution_intent_hash",
        "decision_id",
        "decision_hash",
    }.isdisjoint(parameters)
    assert (
        "reference_rehearsal_packet" not in FreshBindSourceChainInputs.__annotations__
    )


def test_report_derives_independent_claims_and_does_not_claim_issuance() -> None:
    intent, inputs = _inputs()
    result = build_fresh_bind_source_chain(intent, inputs, built_at=RECORDED_AT)
    report = fresh_bind_proof_report(result)
    assert report["decision_lineage_proven"] is True
    assert report["execution_intent_lineage_proven"] is True
    assert report["endpoint_binding_proven"] is True
    assert report["credential_scope_binding_proven"] is True
    assert report["authorization_source_chain_proven"] is True
    assert report["authority_evidence_proven"] is False
    assert report["revocation_checked"] is False
    assert report["human_approval_proven"] is False
    assert report["real_bind_authorization_issued"] is False
    assert report["external_effect_performed"] is False
    assert report["real_decision_to_effect_e2e"] is False


@pytest.mark.parametrize(
    "field",
    [
        "endpoint_allowlist",
        "credential_scope",
        "authority_linkage",
        "human_approval",
        "adapter_contract",
    ],
)
def test_declared_prerequisite_mismatches_fail_closed(field: str) -> None:
    intent, inputs = _inputs()
    if field == "endpoint_allowlist":
        snapshot = dict(inputs.endpoint_allowlist_snapshot)
        snapshot["allowlist_entries"] = []
        changed = replace(inputs, endpoint_allowlist_snapshot=snapshot)
    elif field == "credential_scope":
        reference = dict(inputs.credential_reference)
        reference["credential_scope"] = ["foreign:scope"]
        changed = replace(inputs, credential_reference=reference)
    elif field == "authority_linkage":
        bundle = dict(inputs.authority_evidence_reference_bundle)
        references = [dict(bundle["authority_evidence_references"][0])]
        references[0]["linked_execution_intent_id"] = "foreign"
        bundle["authority_evidence_references"] = references
        changed = replace(inputs, authority_evidence_reference_bundle=bundle)
    elif field == "human_approval":
        bundle = dict(inputs.human_approval_reference_bundle)
        bundle["human_approval_references"] = []
        changed = replace(inputs, human_approval_reference_bundle=bundle)
    else:
        selection = inputs.adapter_contract_selection_packet.model_dump(mode="json")
        selection["adapter_contract_descriptor"]["target_system"] = "foreign"
        changed = replace(inputs, adapter_contract_selection_packet=selection)
    with pytest.raises(ValueError):
        build_fresh_bind_source_chain(intent, changed, built_at=RECORDED_AT)
