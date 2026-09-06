"""Cross-boundary attacks against native v2 issuance, with real verifiers."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from veritas_os.policy import native_bind_authorization as module
from veritas_os.tests.test_native_bind_authorization import (
    issued as issued_fixture,
    api_risk_source as source_fixture,
    _setup,
)

pytestmark = pytest.mark.slow
issued = issued_fixture
api_risk_source = source_fixture


def test_schema_matches_native_model(issued):
    artifact, *_ = issued
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "schemas/native-live-adapter-bind-authorization-v2.schema.json"
        ).read_text()
    )
    expected = module.NativeBindAuthorizationArtifact.model_json_schema()
    assert {k: v for k, v in schema.items() if k != "$schema"} == expected
    Draft202012Validator(schema).validate(artifact.model_dump(mode="json"))


def test_complete_rebuilt_not_required_attack_against_original_contract(issued):
    _, original_inputs, _, risk, *_ = issued
    if not risk.required_human_approval:
        pytest.skip("downgrade requires the REQUIRED baseline")
    original = original_inputs["governance_inputs"]
    forged_contract = replace(
        original.action_contract,
        human_approval_rules={"required": False, "minimum_approvals": 0},
    )
    assert forged_contract.id == original.action_contract.id
    assert forged_contract.version == original.action_contract.version
    attacker_artifact, attacker_inputs, *_ = _setup(
        original.expected_source,
        forged_contract,
        original_inputs["source_inputs"].expected_verified_at,
    )
    assert attacker_artifact.human_approval_requirement_status == "NOT_REQUIRED"
    # Even an authenticated issuer cannot turn its embedded, completely rebuilt
    # HARR/satisfaction/final/risk/authorization into the external policy anchor.
    with pytest.raises(ValueError):
        module.verify_native_bind_authorization(
            attacker_artifact,
            **{
                **attacker_inputs,
                "governance_inputs": replace(
                    attacker_inputs["governance_inputs"],
                    action_contract=original.action_contract,
                    expected_source=original.expected_source,
                ),
            },
        )


@pytest.mark.parametrize("target", ["authority", "human", "go"])
def test_corrupt_upstream_signature_cannot_issue(issued, target):
    _, inputs, signer, risk, decision, start, end = issued
    changed = dict(inputs)
    if target == "go":
        decision = deepcopy(decision)
        decision["signature"] = "A" * 88
    else:
        gov = inputs["governance_inputs"]
        field = (
            "signed_authority_evidence_artifact"
            if target == "authority"
            else "signed_human_approval_artifact"
        )
        artifact = deepcopy(getattr(gov, field))
        if artifact is None:
            artifact = {"signature": "A" * 88}
        else:
            artifact["signature"] = "A" * 88
        changed["governance_inputs"] = replace(gov, **{field: artifact})
    with pytest.raises(ValueError):
        module.issue_native_bind_authorization(
            risk, decision, start, end, **changed, authorization_issuer_signer=signer
        )


def test_expired_authorization_before_risk_deadline_rejected(issued):
    artifact, inputs, *_ = issued
    gov = inputs["governance_inputs"]
    # Risk remains valid until +30; authorization expires at +20.
    now = inputs["source_inputs"].expected_verified_at + timedelta(seconds=21)
    with pytest.raises(ValueError, match="NABA_VALIDITY_OUTSIDE_CURRENT_RISK"):
        module.verify_native_bind_authorization(
            artifact,
            **{
                **inputs,
                "governance_inputs": replace(gov, verification_now=now),
            },
        )


def test_absent_issuance_boundary_in_contract_fails_closed(issued):
    _, inputs, *_ = issued
    contract = deepcopy(inputs["governance_inputs"].action_contract)
    del contract.irreversibility["boundary"]
    with pytest.raises(ValueError, match="LABA_RUNTIME_AUTHORITY_NOT_COMMIT"):
        _setup(
            inputs["governance_inputs"].expected_source,
            contract,
            inputs["source_inputs"].expected_verified_at,
        )


@pytest.mark.parametrize(
    "rules",
    [
        {"minimum_approvals": 2},
        {"minimum_approvals": -1},
        {"minimum_approvals": True},
        {"minimum_approvals": "1"},
        {"required": "false"},
        {"required": 1},
        {"required": True, "approver_role": "security-officer"},
    ],
)
def test_unimplemented_or_ambiguous_approval_rules_rejected(rules):
    with pytest.raises(ValueError, match="NABA_UNSUPPORTED_HUMAN_RULES"):
        module._supported_approval_rules(rules)


def test_quorum_contract_cannot_reach_authorization(issued):
    _, inputs, *_ = issued
    contract = replace(
        inputs["governance_inputs"].action_contract,
        human_approval_rules={"required": True, "minimum_approvals": 2},
    )
    # A no-approval source refuses linkage before issuance; a REQUIRED source
    # reaches the v2 rule guard, which refuses a single receipt for quorum.
    expected = (
        "NABA_UNSUPPORTED_HUMAN_RULES"
        if inputs["governance_inputs"].action_contract.human_approval_rules["required"]
        else "PLADHAL_HUMAN_APPROVAL_NOT_REQUIRED"
    )
    with pytest.raises(ValueError, match=expected):
        _setup(
            inputs["governance_inputs"].expected_source,
            contract,
            inputs["source_inputs"].expected_verified_at,
        )
