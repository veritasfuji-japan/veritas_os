"""Real local signature verification for v0.3 issuance trust propagation."""

import base64
from dataclasses import replace

import pytest
from veritas_os.governance.human_approval_receipt import (
    ApprovedHumanApprovalVerifier,
    HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from veritas_os.governance.human_approval_receipt_signing import (
    human_approval_signature_payload,
)

from veritas_os.policy.human_approval_requirement_resolution import (
    build_human_approval_requirement_resolution_packet as resolve,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_linkage import (
    build_live_adapter_dry_run_human_approval_linkage_review_packet as link,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_requirement_satisfaction import (
    build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet as satisfy,
)
from veritas_os.policy.live_adapter_bind_authorization import (
    build_live_adapter_bind_authorization_artifact as issue,
    verify_live_adapter_bind_authorization_artifact as verify,
)
from veritas_os.policy.gate_bound_human_approval_issuance import (
    issue_gate_bound_human_approval_artifact as approve,
)
from veritas_os.policy.real_bind_context import derive_verified_real_bind_context_hash
from veritas_os.tests.test_live_adapter_dry_run_human_approval_requirement_satisfaction import (
    authority_source_packet,
    human_bundle,
    HUMAN_RECORDED_AT,
    SATISFACTION_RECORDED_AT,
    _build_gate,
)
from veritas_os.tests.test_live_adapter_bind_authorization import (
    _governance_inputs,
    _bind_signature_setup,
    _signed_decision,
    VALID_FROM,
    VALID_UNTIL,
)
from veritas_os.tests.test_gate_bound_human_approval_issuance import (
    _Ed25519Signer,
    _event,
    KEY_ID,
    IDENTITY,
    ROLE,
    _trusted_verifier,
)

pytestmark = pytest.mark.slow


def _gate(source, contract, required):
    resolution = resolve(source, contract, HUMAN_RECORDED_AT)
    child = link(source, human_bundle(source), HUMAN_RECORDED_AT) if required else None
    satisfaction = satisfy(
        source, resolution, contract, child, SATISFACTION_RECORDED_AT
    )
    return _build_gate(satisfaction, source, contract)[1]


@pytest.fixture(scope="module", params=[False, True])
def case(request):
    governance = _governance_inputs(human_required=request.param)
    source = authority_source_packet()
    gate = _gate(source, governance.action_contract, request.param)
    governance = replace(governance, expected_source=source)
    if request.param:
        key = Ed25519PrivateKey.generate()
        human_signer = _Ed25519Signer(KEY_ID, IDENTITY, ROLE, key)
        receipt = approve(
            gate,
            expected_source=source,
            action_contract=governance.action_contract,
            event=_event(),
            signer=human_signer,
        )
        human_verifier = _trusted_verifier(key)
        signer_policy = HumanApprovalSignerPolicy(
            policy_id="v03-test-signers",
            allowed_key_ids=[KEY_ID],
            allowed_algorithms=["Ed25519"],
            required_signer_identities=[IDENTITY],
            required_signer_roles=[ROLE],
            allowed_action_classes=[governance.action_contract.action_class],
            allowed_policy_snapshot_ids=[gate.execution_intent["policy_snapshot_id"]],
        )
        verifier_policy = HumanApprovalVerifierPolicy(
            [
                ApprovedHumanApprovalVerifier(
                    verifier_id=human_verifier.verifier_id,
                    trust_level="production",
                    verifier_key_id=KEY_ID,
                    policy_id=human_verifier.verifier_policy_id,
                    policy_hash=human_verifier.policy_hash(),
                )
            ]
        )
        governance = replace(
            governance,
            signed_human_approval_artifact=receipt,
            human_approval_signature_verifier=human_verifier,
            human_approval_signer_policy=signer_policy,
            human_approval_verifier_policy=verifier_policy,
        )
    private, trust, signer = _bind_signature_setup()
    decision = _signed_decision(private, source=gate)
    return gate, governance, decision, trust, signer


def _issue(case, governance=None):
    gate, original, decision, trust, signer = case
    return issue(
        gate,
        decision,
        VALID_FROM,
        VALID_UNTIL,
        governance_inputs=governance or original,
        trust_inputs=trust,
        authorization_issuer_signer=signer,
    )


def test_v03_authorization_reverifies_real_signatures_without_execution(
    case, monkeypatch
):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    artifact = _issue(case)
    _, governance, _, trust, _ = case
    assert (
        verify(artifact, governance_inputs=governance, trust_inputs=trust) == artifact
    )
    assert artifact.human_approval_requirement_status == (
        "VERIFIED" if governance.signed_human_approval_artifact else "NOT_REQUIRED"
    )
    assert artifact.bind_authorization_state == "AUTHORIZED"
    for field in (
        "bind_invoked",
        "bind_receipt_created",
        "credential_material_accessed",
        "network_used",
        "operation_committed",
        "request_dispatched",
    ):
        assert not getattr(artifact, field)
    with pytest.raises(ValueError):
        verify(
            artifact,
            governance_inputs=replace(governance, expected_source=None),
            trust_inputs=trust,
        )


@pytest.mark.parametrize(
    "mutation", ["missing_source", "contract", "authority_signature", "human_presence"]
)
def test_issuance_rejects_invalid_trust_before_signing(case, mutation, monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    gate, governance, decision, trust, signer = case
    if mutation == "missing_source":
        governance = replace(governance, expected_source=None)
    elif mutation == "contract":
        governance = replace(
            governance,
            action_contract=replace(
                governance.action_contract,
                human_approval_rules={"required": False, "minimum_approvals": 9},
            ),
        )
    elif mutation == "authority_signature":
        governance = replace(
            governance,
            signed_authority_evidence_artifact={
                **governance.signed_authority_evidence_artifact,
                "signature": "invalid",
            },
        )
    else:
        governance = replace(
            governance,
            signed_human_approval_artifact=(
                {} if governance.signed_human_approval_artifact is None else None
            ),
        )

    def forbidden_sign(self, payload):
        pytest.fail("issuer signing must not run after failed verification")

    monkeypatch.setattr(type(signer), "sign", forbidden_sign)
    with pytest.raises(ValueError):
        issue(
            gate,
            decision,
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=governance,
            trust_inputs=trust,
            authorization_issuer_signer=signer,
        )


def test_receipt_issuance_requires_independent_source_and_explicit_reference(case):
    gate, governance, _, _, _ = case
    signer = _Ed25519Signer(KEY_ID, IDENTITY, ROLE, Ed25519PrivateKey.generate())
    kwargs = dict(
        action_contract=governance.action_contract, event=_event(), signer=signer
    )
    with pytest.raises(ValueError):
        approve(gate, **kwargs)
    if governance.signed_human_approval_artifact is None:
        with pytest.raises(ValueError):
            approve(gate, expected_source=governance.expected_source, **kwargs)
    else:
        artifact = approve(gate, expected_source=governance.expected_source, **kwargs)
        signer.private_key.public_key().verify(
            base64.urlsafe_b64decode(artifact["signature"]),
            human_approval_signature_payload(artifact).encode("utf-8"),
        )
        assert artifact["receipt"][
            "bind_context_hash"
        ] == derive_verified_real_bind_context_hash(
            gate,
            expected_source=governance.expected_source,
            expected_contract=governance.action_contract,
        )


def test_fully_rebuilt_same_id_version_downgrade_cannot_reach_issuance(monkeypatch):
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    original = _governance_inputs(human_required=True)
    source = authority_source_packet()
    substituted = replace(
        original.action_contract,
        human_approval_rules={"required": False, "minimum_approvals": 0},
    )
    forged = _gate(source, substituted, False)
    private, trust, signer = _bind_signature_setup()
    decision = _signed_decision(private, source=forged)
    with pytest.raises(ValueError):
        issue(
            forged,
            decision,
            VALID_FROM,
            VALID_UNTIL,
            governance_inputs=replace(original, expected_source=source),
            trust_inputs=trust,
            authorization_issuer_signer=signer,
        )
