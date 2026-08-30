"""Fail-closed tests for promotion-native Authority Evidence linkage."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    BINDINGS,
    CHECK_MODE,
    EFFECT_FIELDS,
    CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError,
    build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review import (
    EVALUATED_AT,
    _packet as bind_review,
)


RECORDED_AT = EVALUATED_AT + timedelta(seconds=5)


def _expected(source) -> dict[str, str]:
    return {
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": source.endpoint_candidate["endpoint_candidate_id"],
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": source.credential_reference[
            "credential_reference_id"
        ],
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": source.credential_reference["target_resource_scope"],
        "purpose": source.credential_reference["credential_purpose"],
        "bind_pre_dispatch_review_id": (
            source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id
        ),
        "bind_pre_dispatch_review_hash": (
            source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash
        ),
    }


def _bundle(source=None) -> dict:
    source = source or bind_review()
    expected = _expected(source)
    reference = {
        "authority_evidence_reference_id": "authority-ref:promotion:1",
        "authority_evidence_kind": "signed-policy-decision",
        "authority_source_type": "upstream-authority-service",
        "authority_source_id": "authority:local-reference-only",
        "authority_policy_id": "authority-policy:1",
        "authority_policy_version": "1",
        "authority_scope": "bind-request",
        "authority_subject": "operator:alice",
        "authority_issuer": "issuer:example",
        "authority_issued_at": (RECORDED_AT - timedelta(minutes=1)).isoformat(),
        "authority_expires_at": (RECORDED_AT + timedelta(minutes=5)).isoformat(),
        "authority_evidence_hash": "sha256:" + "a" * 64,
        "authority_evidence_format": "authority-evidence/v1",
        "declared_verification_state": "DECLARED_VERIFIED_BY_UPSTREAM_ARTIFACT",
        **{attribute: expected[name] for name, attribute in BINDINGS},
    }
    claims = [
        {
            "binding_claim_id": f"pladrael-claim:v1:authority-ref:promotion:1:{name}",
            "authority_evidence_reference_id": "authority-ref:promotion:1",
            "claim_type": name,
            "expected_value": expected[name],
            "actual_value": expected[name],
            "matched": True,
            "comparison_mode": CHECK_MODE,
        }
        for name, _ in BINDINGS
    ]
    return {
        "authority_evidence_reference_bundle_id": "authority-bundle:promotion:1",
        "bundle_declared_by": "operator:alice",
        "bundle_declared_at": RECORDED_AT.isoformat(),
        "bundle_scope": ["bind-request"],
        "authority_evidence_references": [reference],
        "authority_evidence_binding_claims": claims,
        "bundle_limitations": [
            "metadata-only",
            "not-cryptographically-verified-by-this-boundary",
        ],
    }


def _packet():
    source = bind_review()
    return build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
        source, _bundle(source), RECORDED_AT
    )


def test_full_chain_preserves_exact_evidence_without_authority_or_effects() -> None:
    source = bind_review()
    packet = verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
        build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            source, _bundle(source), RECORDED_AT
        )
    )
    for field in (
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_id",
        "adapter_contract_hash",
        "endpoint_candidate_digest",
        "endpoint_identity_binding_digest",
        "credential_reference_digest",
        "credential_scope_binding_digest",
        "operator_review_binding_digest",
        "bind_boundary_precondition_digest",
    ):
        assert getattr(packet, field) == getattr(source, field)
    assert len(packet.authority_evidence_reference_digests) == 1
    assert len(packet.authority_evidence_binding_matrix) == len(BINDINGS)
    assert packet.authority_evidence_linkage_result.all_binding_claims_matched
    assert packet.ready_for_promotion_native_human_approval_reference_linkage_review
    assert packet.authority_evidence_proven is False
    assert packet.authority_evidence_externally_verified is False
    assert packet.human_approval_proven is False
    assert packet.execution_authorized is False
    assert all(getattr(packet, field) is False for field in EFFECT_FIELDS)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_bind_pre_dispatch_review_hash", "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("endpoint_identity_binding_digest", "0" * 64),
        ("credential_scope_binding_digest", "0" * 64),
        ("operator_review_binding_digest", "0" * 64),
        ("bind_boundary_precondition_digest", "0" * 64),
        ("authority_evidence_reference_digests.authority-ref:promotion:1", "0" * 64),
        ("authority_evidence_reference_bundle_digest", "0" * 64),
        ("authority_evidence_binding_matrix.0.actual_value", "tampered"),
        ("authority_evidence_binding_matrix_digest", "0" * 64),
        ("authority_evidence_linkage_result.all_binding_claims_matched", False),
        ("authority_evidence_linkage_context.approval_context", {}),
        ("authority_evidence_linkage_context_digest", "0" * 64),
        ("authority_evidence_linkage_checks.0.name", "network_not_used"),
        ("future_requirements.0.name", "network_dispatch"),
        ("authority_evidence_proven", True),
        ("authority_evidence_externally_verified", True),
        ("human_approval_proven", True),
        ("execution_authorized", True),
        ("bind_authorization_issued", True),
        ("network_used", True),
        ("credential_material_accessed", True),
        ("request_dispatched", True),
        ("bind_invoked", True),
        ("bind_receipt_created", True),
        ("trustlog_written", True),
        (
            "promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash",
            "0" * 64,
        ),
    ],
)
def test_packet_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    target[parts[-1]] = value
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError
    ):
        verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            raw
        )


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("state", "DECLARED_PENDING_EXTERNAL_VERIFICATION"),
        ("state", "DECLARED_REJECTED_BY_UPSTREAM_ARTIFACT"),
        ("expires", RECORDED_AT.isoformat()),
        ("issued", (RECORDED_AT + timedelta(seconds=1)).isoformat()),
        ("declared", (RECORDED_AT + timedelta(seconds=1)).isoformat()),
        ("linked", "tampered"),
    ],
)
def test_invalid_reference_metadata_fails_closed(mutation: str, value: str) -> None:
    source = bind_review()
    bundle = _bundle(source)
    reference = bundle["authority_evidence_references"][0]
    if mutation == "state":
        reference["declared_verification_state"] = value
    elif mutation == "expires":
        reference["authority_expires_at"] = value
    elif mutation == "issued":
        reference["authority_issued_at"] = value
    elif mutation == "declared":
        bundle["bundle_declared_at"] = value
    else:
        reference["linked_execution_intent_hash"] = value
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError
    ):
        build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            source, bundle, RECORDED_AT
        )


def test_missing_duplicate_extra_and_incomplete_claims_fail_closed() -> None:
    source = bind_review()
    variants = []
    missing = _bundle(source)
    missing["authority_evidence_references"] = []
    variants.append(missing)
    duplicate = _bundle(source)
    duplicate["authority_evidence_references"].append(
        deepcopy(duplicate["authority_evidence_references"][0])
    )
    variants.append(duplicate)
    omitted_claim = _bundle(source)
    omitted_claim["authority_evidence_binding_claims"].pop()
    variants.append(omitted_claim)
    unknown = _bundle(source)
    unknown["safe"] = True
    variants.append(unknown)
    for bundle in variants:
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError
        ):
            build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
                source, bundle, RECORDED_AT
            )


def test_rejected_source_and_unknown_packet_shortcut_fail_closed() -> None:
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError
    ):
        source = bind_review("REJECTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW")
        build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            source, _bundle(source), RECORDED_AT
        )
    raw = _packet().model_dump(mode="json")
    raw["authorized"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError
    ):
        verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            raw
        )
