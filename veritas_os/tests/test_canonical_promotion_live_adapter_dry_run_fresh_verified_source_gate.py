"""Fail-closed tests for the promotion-native fresh verified source gate."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta

import pytest

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate as fresh_module
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate import (
    AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS,
    CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError,
    build_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet,
    verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review import (
    RECORDED_AT as SOURCE_AT,
    _packet as source_packet,
)

VERIFIED_AT = SOURCE_AT + timedelta(seconds=1)


def _packet(*, source=None, verified_at=VERIFIED_AT):
    return build_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
        source or source_packet(), verified_at
    )


def _tamper_source(path: tuple[str, ...], value):
    raw = source_packet().model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return raw


def test_valid_pass_source_round_trips_and_preserves_exact_typed_fields():
    source = source_packet()
    packet = _packet(source=source)
    verified = verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
        json.loads(packet.model_dump_json())
    )

    assert verified == packet
    for name in PRESERVED_FIELDS:
        assert getattr(packet, name) == getattr(source, name), name
        assert (
            packet.model_fields[name].annotation == source.model_fields[name].annotation
        )
    assert packet.source_bind_authorization_gate_review_packet == source.model_dump(
        mode="json"
    )


def test_json_accepts_finite_float_and_rejects_non_finite_values():
    assert fresh_module._json(1.25) == 1.25
    assert fresh_module._json({"nested": [0.5, -2.75]}) == {
        "nested": [0.5, -2.75]
    }
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError
        ):
            fresh_module._json(value)


def test_requirement_transition_consumes_only_fresh_source_gate():
    source = source_packet()
    packet = _packet(source=source)
    source_names = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    output_names = tuple(
        item.name for item in packet.future_bind_authorization_requirements
    )
    invocation_names = tuple(
        item.name for item in packet.future_bind_invocation_requirements
    )

    assert source_names[0] == "fresh_verified_source_gate"
    assert output_names == source_names[1:] == AUTHORIZATION_REQUIREMENTS
    assert output_names[0] == "exact_bind_context_hash_derivation"
    assert invocation_names == INVOCATION_REQUIREMENTS
    assert all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *packet.future_bind_authorization_requirements,
            *packet.future_bind_invocation_requirements,
        )
    )


def test_output_routes_only_to_bind_context_derivation_without_authority():
    packet = _packet()
    assert packet.ready_for_promotion_native_bind_context_derivation is True
    assert packet.fresh_verified_source_gate_still_required is False
    assert packet.bind_context_hash_derivation_still_required is True
    assert packet.bind_context_hash_derived is False
    assert not hasattr(packet, "bind_context_hash")
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)
    assert packet.fresh_verification_result.external_policy_freshness_verified is False
    assert packet.fresh_verification_result.endpoint_rechecked is False
    assert packet.fresh_verification_result.credential_scope_rechecked is False
    assert packet.fresh_verification_result.revocation_verified is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("gate_review_state",),
            "FAILED_FOR_FUTURE_PROMOTION_NATIVE_FRESH_VERIFIED_SOURCE_GATE",
        ),
        (("ready_for_promotion_native_fresh_verified_source_gate",), False),
        (("fail_closed",), True),
        (("fresh_verified_source_gate_still_required",), False),
        (
            ("promotion_live_adapter_dry_run_bind_authorization_gate_review_id",),
            "tampered",
        ),
        (
            ("promotion_live_adapter_dry_run_bind_authorization_gate_review_hash",),
            "0" * 64,
        ),
        (("bind_authorization_gate_review_context_digest",), "0" * 64),
        (("execution_intent_id",), "tampered"),
        (("execution_intent_hash",), "0" * 64),
        (("adapter_contract_id",), "tampered"),
        (("adapter_contract_hash",), "0" * 64),
        (("endpoint_identity_binding_digest",), "0" * 64),
        (("credential_scope_binding_digest",), "0" * 64),
        (("operator_review_binding_digest",), "0" * 64),
        (("authority_evidence_linkage_context_digest",), "0" * 64),
        (("human_approval_linkage_context_digest",), "0" * 64),
        (("final_readiness_context_digest",), "0" * 64),
        (("source_promotion_hash",), "0" * 64),
        (("approval_context", "required_human_approval"), False),
    ],
)
def test_source_tamper_fails_closed(path, value):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        _packet(source=_tamper_source(path, value))


@pytest.mark.parametrize("field", EFFECT_FIELDS)
def test_any_source_effect_or_authority_capability_fails_closed(field):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        _packet(source=_tamper_source((field,), True))


def test_failed_gate_review_source_is_rejected():
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        _packet(source=source_packet(passed=False))


@pytest.mark.parametrize(
    "verified_at",
    [SOURCE_AT - timedelta(microseconds=1), datetime(2030, 1, 1)],
)
def test_invalid_or_naive_fresh_timestamp_fails_closed(verified_at):
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        _packet(verified_at=verified_at)


def test_timestamp_must_not_precede_reviewed_at_even_if_recorded_at_allows_it():
    source = source_packet()
    raw = source.model_dump(mode="json")
    reviewed_at = datetime.fromisoformat(
        raw["bind_authorization_gate_review_decision"]["reviewed_at"]
    )
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        _packet(source=raw, verified_at=reviewed_at - timedelta(microseconds=1))


def test_source_requirement_and_invocation_order_drift_fail_closed():
    for field in (
        "future_bind_authorization_requirements",
        "future_bind_invocation_requirements",
    ):
        raw = source_packet().model_dump(mode="json")
        raw[field][0], raw[field][1] = raw[field][1], raw[field][0]
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError
        ):
            _packet(source=raw)


def test_hashes_bind_fresh_timestamp_and_exact_source():
    first = _packet()
    later = _packet(verified_at=VERIFIED_AT + timedelta(seconds=1))
    assert (
        first.fresh_verification_result_digest != later.fresh_verification_result_digest
    )
    assert (
        first.fresh_verified_source_gate_context_digest
        != later.fresh_verified_source_gate_context_digest
    )
    assert (
        first.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        != later.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
    )

    alternate = source_packet(
        decision={
            **source_packet().bind_authorization_gate_review_decision.model_dump(
                mode="json"
            ),
            "bind_authorization_gate_review_decision_id": "gate-review:alternate",
        }
    )
    changed = _packet(source=alternate)
    assert (
        first.fresh_verified_source_gate_context_digest
        != changed.fresh_verified_source_gate_context_digest
    )
    assert (
        first.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        != changed.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
    )


def test_packet_tamper_fails_reconstruction():
    raw = _packet().model_dump(mode="json")
    raw["fresh_verified_source_gate_context_digest"] = "0" * 64
    with pytest.raises(CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError):
        verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
            raw
        )


def test_production_imports_have_no_test_legacy_or_effect_dependencies():
    tree = ast.parse(inspect.getsource(fresh_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    forbidden = {"requests", "httpx", "urllib", "socket", "subprocess"}
    assert not any(name.startswith("veritas_os.tests") for name in imported)
    assert not any("fresh_bind_source_chain" in name for name in imported)
    assert not any(name.split(".")[0] in forbidden for name in imported)