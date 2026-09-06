"""Native issuance with actual Ed25519 verification and genuine API lineage.

All keys, authority and approval artifacts are explicitly synthetic fixtures.
Production verifiers are never replaced with accepting mocks.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest

from veritas_os.policy import native_bind_authorization as module
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _digest,
    native_bind_authorization_signature_payload,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    CanonicalLiveAdapterBindAuthorizationArtifact,
)
from veritas_os.policy.promotion_requirement_runtime_risk import (
    build_promotion_requirement_runtime_risk_packet,
)
from veritas_os.tests import test_live_adapter_bind_authorization as crypto
from veritas_os.tests.test_promotion_requirement_runtime_risk import (
    api_risk_source as api_fixture,
    _risk_chain,
)
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import (
    _contract,
)

pytestmark = pytest.mark.slow
api_risk_source = api_fixture


def _setup(source, contract, now):
    final, risk, anchors = _risk_chain(source, contract, now)
    source_inputs = module.NativeAuthorizationSourceInputs(
        final_recheck=final,
        **{
            k: v
            for k, v in anchors.items()
            if k not in {"expected_source", "expected_contract", "verification_now"}
        },
    )
    # These fixture helpers sign synthetic artifacts. Only their fixture input
    # globals are adapted; all production source/crypto verifiers run unchanged.
    placeholder = RealBindAuthorizationGovernanceInputs(
        contract,
        {},
        None,
        None,
        None,
        None,
        None,
        anchors["verification_now"],
        expected_source=source,
    )
    _, _, context = module._verified_source(risk, source_inputs, placeholder)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(crypto, "source_packet", lambda: context)
        patch.setattr(crypto, "SOURCE_RECORDED_AT", now)
        patch.setattr(crypto, "AUTHORIZED_AT", anchors["verification_now"])
        patch.setattr(crypto, "VERIFICATION_NOW", anchors["verification_now"])
        patch.setattr(crypto, "_bind_context_hash", lambda _: final.bind_context_hash)
        authority = crypto._authority_bundle(contract)
        human = (
            crypto._signed_human_approval(contract)
            if risk.required_human_approval
            else (None,) * 4
        )
        governance = replace(
            placeholder,
            signed_authority_evidence_artifact=authority[0],
            authority_signature_verifier=authority[1],
            authority_signer_policy=authority[2],
            authority_verifier_policy=authority[3],
            authority_revocation_checker=authority[4],
            authority_revocation_policy=authority[5],
            signed_human_approval_artifact=human[0],
            human_approval_signature_verifier=human[1],
            human_approval_signer_policy=human[2],
            human_approval_verifier_policy=human[3],
        )
        key, trust, signer = crypto._bind_signature_setup()
        issuer_verifier = replace(
            trust.authorization_issuer_signature_verifier,
            authorization_artifact_version="v2",
        )
        approved = trust.authorization_issuer_verifier_policy.approved_verifiers[0]
        policy = replace(
            trust.authorization_issuer_verifier_policy,
            approved_verifiers=[
                replace(approved, verifier_policy_hash=issuer_verifier.policy_hash())
            ],
        )
        trust = replace(
            trust,
            authorization_issuer_signature_verifier=issuer_verifier,
            authorization_issuer_verifier_policy=policy,
        )
        start = anchors["verification_now"]
        end = now + timedelta(seconds=20)
        decision = crypto._signed_decision(
            key, source=context, valid_from=start, valid_until=end
        )
    inputs = dict(
        source_inputs=source_inputs, governance_inputs=governance, trust_inputs=trust
    )
    artifact = module.issue_native_bind_authorization(
        risk,
        decision,
        start,
        end,
        **inputs,
        authorization_issuer_signer=signer,
    )
    return artifact, inputs, signer, risk, decision, start, end


@pytest.fixture(scope="module")
def issued(api_risk_source):
    source, now, required, captured = api_risk_source
    assert captured["pipeline_ok"] is True
    contract = _contract(source.execution_intent["intended_action"], required)
    contract.irreversibility["boundary"] = "future-bind-consumption"
    return _setup(source, contract, now)


def _resign(raw, signer):
    body = {
        k: v
        for k, v in raw.items()
        if k
        not in {"authorization_id", "authorization_hash", "authorization_signature"}
    }
    digest = _digest(module.DOMAIN, body)
    raw = {
        **body,
        "authorization_hash": digest,
        "authorization_id": "laba:v2:sha256:" + digest,
    }
    raw["authorization_signature"] = base64.urlsafe_b64encode(
        signer.sign(native_bind_authorization_signature_payload(raw).encode())
    ).decode()
    return raw


def test_real_api_native_issuance_and_reverification(issued):
    artifact, inputs, _, risk, *_ = issued
    verified = module.verify_native_bind_authorization(artifact, **inputs)
    assert verified == artifact and verified is not artifact
    assert (
        verified.execution_intent
        == inputs["source_inputs"].final_recheck.execution_intent
    )
    assert verified.source_runtime_risk_packet == risk.model_dump(mode="json")
    assert verified.human_approval_requirement_status == (
        "VERIFIED" if risk.required_human_approval else "NOT_REQUIRED"
    )
    assert (
        verified.signed_human_approval_artifact is not None
    ) == risk.required_human_approval
    assert verified.authorization_consumption_state == "NOT_CONSUMED"
    assert verified.authorization_consumption_required
    assert not verified.duplicate_absence_verified
    for field in (
        "execution_authority_created",
        "human_approval_created",
        "bind_invoked",
        "bind_receipt_created",
        "credential_material_accessed",
        "network_used",
        "external_effect_occurred",
        "authorization_header_constructed",
    ):
        assert getattr(verified, field) is False


def test_v1_schema_and_verifier_reject_v2(issued):
    artifact, inputs, *_ = issued
    with pytest.raises(ValueError):
        CanonicalLiveAdapterBindAuthorizationArtifact.model_validate(
            artifact.model_dump()
        )
    v2 = inputs["trust_inputs"].authorization_issuer_signature_verifier
    v1 = replace(v2, authorization_artifact_version="v1")
    assert not v1.verify(artifact.model_dump(mode="json")).verified
    assert v1.policy_hash() != v2.policy_hash()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_gate_hash", "0" * 64),
        ("source_final_recheck_hash", "0" * 64),
        ("bind_context_hash", "0" * 64),
        ("action_contract_digest", "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("authority_verification_proof_digest", "0" * 64),
        ("runtime_authority_result_digest", "0" * 64),
        ("human_approval_requirement_status", "NOT_REQUIRED"),
        ("idempotency_key", "laba-idem:v2:sha256:" + "0" * 64),
    ],
)
def test_rehashed_and_resigned_false_claims_rejected(issued, field, value):
    artifact, inputs, signer, *_ = issued
    raw = artifact.model_dump(mode="json")
    if raw[field] == value:
        value = "VERIFIED"
    raw[field] = value
    with pytest.raises(ValueError, match="NABA_RECONSTRUCTION_MISMATCH"):
        module.verify_native_bind_authorization(_resign(raw, signer), **inputs)


@pytest.mark.parametrize(
    "change",
    [
        "contract_rules",
        "contract_required",
        "clock",
        "endpoint",
        "credential",
        "missing_source",
    ],
)
def test_independent_anchors_cannot_be_replaced(issued, change):
    artifact, original, *_ = issued
    inputs = dict(original)
    governance = inputs["governance_inputs"]
    source = inputs["source_inputs"]
    if change.startswith("contract"):
        contract = deepcopy(governance.action_contract)
        contract.human_approval_rules["minimum_approvals"] = 2
        if change == "contract_required":
            contract.human_approval_rules[
                "required"
            ] = not contract.human_approval_rules["required"]
        inputs["governance_inputs"] = replace(governance, action_contract=contract)
    elif change == "clock":
        inputs["governance_inputs"] = replace(
            governance,
            verification_now=governance.verification_now + timedelta(seconds=30),
        )
    elif change == "missing_source":
        inputs["governance_inputs"] = replace(governance, expected_source=None)
    else:
        field = (
            "current_endpoint"
            if change == "endpoint"
            else "current_credential_reference"
        )
        inputs["source_inputs"] = replace(source, **{field: {}})
    with pytest.raises(ValueError):
        module.verify_native_bind_authorization(artifact, **inputs)


@pytest.mark.parametrize("signal", [False, None])
def test_block_or_indeterminate_cannot_issue_or_call_signer(issued, signal):
    _, inputs, _, _, decision, start, end = issued
    src = inputs["source_inputs"]
    gov = inputs["governance_inputs"]
    risk_decision = {**src.expected_risk_decision, "runtime_risk_signal": signal}
    risk = build_promotion_requirement_runtime_risk_packet(
        src.final_recheck,
        risk_decision,
        src.expected_recorded_at,
        expected_source=gov.expected_source,
        expected_contract=gov.action_contract,
        expected_verified_at=src.expected_verified_at,
        expected_rechecked_at=src.expected_rechecked_at,
        current_endpoint=src.current_endpoint,
        current_credential_reference=src.current_credential_reference,
        required_credential_scope=src.required_credential_scope,
    )
    changed = {
        **inputs,
        "source_inputs": replace(src, expected_risk_decision=risk_decision),
    }

    class ForbiddenSigner:
        key_id = "bind-authorization-issuer-key"
        algorithm = "Ed25519"
        identity = "service:bind-authorization-issuer"
        role = "bind-authorization-issuer"

        def sign(self, payload):
            pytest.fail("rejected risk must not reach signing")

    with pytest.raises(ValueError, match="PRRR_RISK_NOT_ACCEPTABLE"):
        module.issue_native_bind_authorization(
            risk,
            decision,
            start,
            end,
            **changed,
            authorization_issuer_signer=ForbiddenSigner(),
        )


def test_missing_or_unexpected_human_receipt_rejected(issued):
    artifact, inputs, *_ = issued
    gov = inputs["governance_inputs"]
    human = (
        None if gov.signed_human_approval_artifact is not None else {"synthetic": True}
    )
    with pytest.raises(ValueError, match="LABA_HUMAN_APPROVAL_(REQUIRED|UNEXPECTED)"):
        module.verify_native_bind_authorization(
            artifact,
            **{
                **inputs,
                "governance_inputs": replace(gov, signed_human_approval_artifact=human),
            },
        )


def test_revoked_authority_rejected(issued):
    artifact, inputs, *_ = issued

    class Revoked(crypto._FreshRevocationChecker):
        def check(self, authority_evidence_id, *, now):
            return replace(super().check(authority_evidence_id, now=now), revoked=True)

    gov = replace(inputs["governance_inputs"], authority_revocation_checker=Revoked())
    with pytest.raises(ValueError, match="LABA_AUTHORITY_VERIFICATION_FAILED"):
        module.verify_native_bind_authorization(
            artifact, **{**inputs, "governance_inputs": gov}
        )


def test_corrupt_issuer_signature_rejected(issued):
    artifact, inputs, *_ = issued
    raw = artifact.model_dump(mode="json")
    raw["authorization_signature"] = "A" * 88
    with pytest.raises(ValueError, match="LABA_SIGNATURE_INVALID"):
        module.verify_native_bind_authorization(raw, **inputs)
