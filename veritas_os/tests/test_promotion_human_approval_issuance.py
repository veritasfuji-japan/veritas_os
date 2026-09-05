"""Promotion approval issuance preserves signed exact-context boundaries."""

import base64
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import veritas_os.tests.test_promotion_idempotency_replay_review as replay_tests
from veritas_os.governance.human_approval_receipt_signing import (
    TrustedEd25519HumanApprovalVerifier,
    human_approval_signature_payload,
)
from veritas_os.policy.gate_bound_human_approval_issuance import (
    GateBoundHumanApprovalIssuanceError,
    HumanApprovalEvent,
    issue_promotion_gate_bound_human_approval_artifact,
)
from veritas_os.tests.test_gate_bound_human_approval_issuance import (
    _contract,
    _Ed25519Signer,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_runtime_risk_review import (
    RECORDED_AT,
    VALID_UNTIL,
)

pytestmark = pytest.mark.slow
NOW = RECORDED_AT + timedelta(seconds=1)


@pytest.fixture(scope="module")
def inputs():
    source = replay_tests.source_packet.__wrapped__()
    projection = replay_tests.projection.__wrapped__(source)
    risk = replay_tests.valid_packet.__wrapped__(source, projection)
    review = replay_tests.review.__wrapped__(risk, source)
    return source, projection, risk, review


def _args(inputs):
    source, projection, risk, review = inputs
    contract = replace(_contract(projection), allowed_scope=["bind-request"])
    human = projection.human_approval_reference_bundle["human_approval_references"][0]
    signer = _Ed25519Signer(
        key_id="test-promotion-key",
        identity=human["approver_id"],
        role=human["approver_role"],
        private_key=Ed25519PrivateKey.generate(),
    )
    event = HumanApprovalEvent(
        approval_result="approved",
        approval_basis_refs=["review:" + review.review_hash],
        approved_at=NOW.isoformat(),
        signed_at=NOW.isoformat(),
        expires_at=VALID_UNTIL.isoformat(),
        metadata={"ticket": "test-only"},
    )
    return dict(action_contract=contract, event=event, signer=signer, now=NOW)


def _issue(inputs, **changes):
    source, _, risk, review = inputs
    args = _args(inputs)
    args.update(changes)
    return issue_promotion_gate_bound_human_approval_artifact(
        review, risk, source, **args
    )


def test_signed_context_and_lineage(inputs):
    source, projection, risk, review = inputs
    args = _args(inputs)
    artifact = _issue(inputs, **args)
    receipt = artifact["receipt"]
    assert receipt["bind_context_hash"] == projection.bind_context_hash
    assert receipt["execution_intent_id"] == projection.execution_intent_id
    assert receipt["signature_verified"] is False
    binding = receipt["metadata"]["promotion_approval_binding"]
    assert binding["idempotency_replay_review_hash"] == review.review_hash
    assert (
        binding["final_endpoint_identity_binding_digest"]
        == projection.final_endpoint_identity_binding_digest
    )
    assert (
        binding["final_credential_scope_binding_digest"]
        == projection.final_credential_scope_binding_digest
    )
    assert binding["human_approval_receipt_verification_required"]
    assert not binding["execution_authorized"]
    assert args["event"].metadata == {"ticket": "test-only"}
    public = args["signer"].private_key.public_key()
    signature = base64.urlsafe_b64decode(artifact["signature"])
    public.verify(signature, human_approval_signature_payload(artifact).encode())
    signer = args["signer"]
    verifier = TrustedEd25519HumanApprovalVerifier(
        trusted_public_keys={signer.key_id: public.public_bytes_raw()},
        trusted_signer_identities={signer.key_id: signer.identity},
        trusted_signer_roles={signer.key_id: signer.role},
        verifier_id="test-promotion-human-verifier",
    )
    assert verifier.verify(artifact).verified
    changed = deepcopy(artifact)
    changed["receipt"]["metadata"]["promotion_approval_binding"][
        "bind_context_hash"
    ] = "a" * 64
    with pytest.raises(InvalidSignature):
        public.verify(signature, human_approval_signature_payload(changed).encode())
    assert not verifier.verify(changed).verified


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved_at", (RECORDED_AT - timedelta(seconds=1)).isoformat()),
        ("signed_at", (NOW + timedelta(seconds=1)).isoformat()),
        ("expires_at", NOW.isoformat()),
        ("expires_at", (VALID_UNTIL + timedelta(seconds=1)).isoformat()),
        ("approved_at", NOW.replace(tzinfo=None).isoformat()),
        ("signed_at", "bad"),
        ("approval_result", "unexpected"),
        ("metadata", {"promotion_approval_binding": {}}),
        ("metadata", []),
    ],
)
def test_invalid_event_never_signs(inputs, field, value):
    args = _args(inputs)
    signer = Mock(wraps=args["signer"])
    event = replace(args["event"], **{field: value})
    with pytest.raises(GateBoundHumanApprovalIssuanceError):
        _issue(inputs, event=event, signer=signer)
    signer.sign.assert_not_called()


@pytest.mark.parametrize("part", ["review", "risk", "source", "clock"])
def test_invalid_source_never_signs(inputs, part):
    source, _, risk, review = inputs
    args = _args(inputs)
    signer = Mock(wraps=args["signer"])
    args["signer"] = signer
    if part == "clock":
        args["now"] = VALID_UNTIL
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="SOURCE_INVALID"):
        issue_promotion_gate_bound_human_approval_artifact(
            {} if part == "review" else review,
            {} if part == "risk" else risk,
            {} if part == "source" else source,
            **args,
        )
    signer.sign.assert_not_called()


def test_wrong_identity_and_action(inputs):
    args = _args(inputs)
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="IDENTITY_MISMATCH"):
        _issue(inputs, signer=replace(args["signer"], identity="other"))
    with pytest.raises(GateBoundHumanApprovalIssuanceError, match="CONTRACT_MISMATCH"):
        _issue(inputs, action_contract=replace(args["action_contract"], id="other"))


@pytest.mark.parametrize("result", ["denied", "expired", "indeterminate"])
def test_nonapproval_is_never_promoted(inputs, result):
    args = _args(inputs)
    artifact = _issue(inputs, event=replace(args["event"], approval_result=result))
    assert artifact["receipt"]["approval_result"] == result
    assert not artifact["receipt"]["signature_verified"]
