"""Fail-closed tests for promotion-native final Bind readiness evidence."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness import (
    ACKNOWLEDGEMENTS,
    COPY_FIELDS,
    EFFECT_FIELDS,
    FUTURE_REQUIREMENTS,
    OUTCOMES,
    CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError,
    build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet,
    verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _packet as source_packet,
)

RECORDED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
MODULE = Path(
    "veritas_os/policy/"
    "canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness.py"
)


def _decision(*, accepted: bool = True, **changes) -> dict:
    value = {
        "final_bind_authorization_readiness_review_decision_id": "review:final:1",
        "reviewer_id": "operator:alice",
        "reviewer_role": "bind-readiness-reviewer",
        "reviewer_attestation": "I reviewed readiness evidence only.",
        "reviewed_at": RECORDED_AT.isoformat(),
        "review_outcome": OUTCOMES[0] if accepted else OUTCOMES[1],
        "review_reason": "promotion-native chain reviewed",
        **{field: True for field in ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _packet(*, accepted: bool = True):
    return build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        source_packet(), _decision(accepted=accepted), RECORDED_AT
    )


def _set(raw: dict, path: tuple, value) -> None:
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def test_accepted_independently_verifies_without_authority_or_effects() -> None:
    packet = _packet()
    assert (
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            packet
        )
        == packet
    )
    assert packet.ready_for_promotion_native_bind_authorization_gate_review
    assert packet.fail_closed is False
    assert packet.request_dispatch_state == "NOT_DISPATCHED"
    assert packet.bind_state == "NOT_BOUND"
    assert packet.authority_state == "NOT_AUTHORIZED"
    assert packet.human_approval_state == "NOT_APPROVED"
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)


def test_rejected_independently_verifies_and_fails_closed() -> None:
    packet = _packet(accepted=False)
    assert (
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            packet
        )
        == packet
    )
    assert not packet.ready_for_promotion_native_bind_authorization_gate_review
    assert packet.fail_closed


def test_complete_upstream_preservation_surface_is_exact() -> None:
    source = source_packet()
    packet = build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        source, _decision(), RECORDED_AT
    )
    source_json = source.model_dump(mode="json")
    packet_json = packet.model_dump(mode="json")
    for field in COPY_FIELDS:
        assert getattr(packet, field) == getattr(source, field), field
        assert packet_json[field] == source_json[field], field
    assert type(packet.human_approval_reference_bundle) is type(
        source.human_approval_reference_bundle
    )
    assert type(packet.human_approval_binding_matrix[0]) is type(
        source.human_approval_binding_matrix[0]
    )
    assert type(packet.human_approval_linkage_result) is type(
        source.human_approval_linkage_result
    )


def test_json_round_trip_preserves_derived_structures_and_hashes() -> None:
    packet = _packet()
    raw = packet.model_dump(mode="json")
    parsed = type(packet).model_validate(raw)
    verified = verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        parsed
    )
    assert verified == packet
    assert verified.final_readiness_context == packet.final_readiness_context
    assert (
        verified.promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash
        == packet.promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("execution_intent_hash",), "tampered"),
        (("adapter_contract_hash",), "tampered"),
        (("endpoint_identity_binding_digest",), "tampered"),
        (("credential_scope_binding_digest",), "tampered"),
        (("operator_review_binding_digest",), "tampered"),
        (("bind_boundary_precondition_digest",), "tampered"),
        (("authority_evidence_linkage_context_digest",), "tampered"),
        (("human_approval_linkage_context_digest",), "tampered"),
        (("final_bind_authorization_readiness_review_decision_digest",), "tampered"),
        (("final_bind_authorization_readiness_result_digest",), "tampered"),
        (("final_readiness_context_digest",), "tampered"),
        (("final_bind_authorization_readiness_check_digest",), "tampered"),
        (("future_requirement_digest",), "tampered"),
        (("network_used",), True),
        (("request_dispatched",), True),
        (("bind_invoked",), True),
        (("external_effect_used",), True),
    ],
)
def test_verifier_rejects_chain_digest_and_effect_tamper(path, value) -> None:
    raw = _packet().model_dump(mode="json")
    _set(raw, path, value)
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            raw
        )


@pytest.mark.parametrize("field", ("reviewer_id", "reviewer_role", "reviewer_attestation"))
def test_empty_reviewer_metadata_is_rejected(field: str) -> None:
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source_packet(), _decision(**{field: ""}), RECORDED_AT
        )


@pytest.mark.parametrize("field", ACKNOWLEDGEMENTS)
def test_false_acknowledgement_is_rejected(field: str) -> None:
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source_packet(), _decision(**{field: False}), RECORDED_AT
        )


def test_unknown_authorization_shortcut_is_rejected() -> None:
    raw = _packet().model_dump(mode="json")
    raw["safe_to_bind"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            raw
        )


def test_naive_and_invalid_timestamp_ordering_are_rejected() -> None:
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source_packet(), _decision(reviewed_at="2026-01-01T00:00:00"), RECORDED_AT
        )
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError
    ):
        build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            source_packet(), _decision(), RECORDED_AT - timedelta(seconds=2)
        )


def test_all_future_requirements_remain_unsatisfied() -> None:
    packet = _packet()
    assert tuple(item.name for item in packet.future_requirements) == FUTURE_REQUIREMENTS
    assert all(
        item.separate_future_artifact_required
        and not item.satisfied_by_this_packet
        for item in packet.future_requirements
    )


def test_production_module_has_no_test_or_capability_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any(name.startswith(("veritas_os.tests", "tests")) for name in imports)
    assert not any(
        name.split(".")[0]
        in {"socket", "subprocess", "requests", "httpx", "urllib", "pathlib"}
        for name in imports
    )
