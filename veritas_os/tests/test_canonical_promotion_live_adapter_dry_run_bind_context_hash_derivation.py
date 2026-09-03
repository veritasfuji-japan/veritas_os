"""Fail-closed tests for promotion-native Bind context hash derivation."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta

import pytest

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation as context_module
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation import (
    AUTHORIZATION_REQUIREMENTS,
    CHECK_MODE,
    DOMAINS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS,
    CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError,
    build_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet,
    verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate import (
    VERIFIED_AT as SOURCE_AT,
    _packet as source_packet,
)

DERIVED_AT = SOURCE_AT + timedelta(seconds=1)


def _packet(*, source=None, derived_at=DERIVED_AT):
    return build_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
        source or source_packet(), derived_at
    )


def _tamper_source(path: tuple[str, ...], value):
    raw = source_packet().model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return raw


def test_valid_source_round_trips_and_preserves_exact_typed_fields():
    source = source_packet()
    packet = _packet(source=source)
    verified = verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
        json.loads(packet.model_dump_json())
    )

    assert verified == packet
    for name in PRESERVED_FIELDS:
        assert getattr(packet, name) == getattr(source, name), name
        assert (
            type(packet).model_fields[name].annotation
            == type(source).model_fields[name].annotation
        )
    assert packet.source_fresh_verified_source_gate_packet == source.model_dump(
        mode="json"
    )


def test_requirement_transition_consumes_only_context_hash_derivation():
    source = source_packet()
    packet = _packet(source=source)
    source_authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    output_authorization = tuple(
        item.name for item in packet.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in packet.future_bind_invocation_requirements)

    assert source_authorization[0] == "exact_bind_context_hash_derivation"
    assert output_authorization == source_authorization[1:]
    assert output_authorization == AUTHORIZATION_REQUIREMENTS
    assert output_authorization[0] == "final_endpoint_identity_recheck"
    assert invocation == INVOCATION_REQUIREMENTS
    assert all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *packet.future_bind_authorization_requirements,
            *packet.future_bind_invocation_requirements,
        )
    )


def test_output_routes_only_to_endpoint_recheck_without_authority_or_effect():
    packet = _packet()

    assert packet.ready_for_promotion_native_final_endpoint_identity_recheck
    assert packet.fresh_verified_source_gate_still_required is False
    assert packet.bind_context_hash_derivation_still_required is False
    assert packet.bind_context_hash_derived is True
    assert packet.final_endpoint_identity_recheck_still_required is True
    assert packet.bind_authorization_state == "NOT_AUTHORIZED"
    assert packet.authority_state == "NOT_AUTHORIZED"
    assert packet.human_approval_state == "NOT_APPROVED"
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)
    result = packet.bind_context_hash_derivation_result
    assert result.external_policy_freshness_verified is False
    assert result.endpoint_rechecked is False
    assert result.credential_scope_rechecked is False
    assert result.revocation_verified is False


def test_hash_is_canonical_digest_of_closed_exact_context():
    packet = _packet()
    context = packet.exact_bind_context.model_dump(mode="json")

    assert packet.bind_context_hash == context_module._digest(
        DOMAINS["bind-context"], context
    )
    assert (
        packet.bind_context_hash_derivation_result.bind_context_hash
        == packet.bind_context_hash
    )
    assert (
        packet.bind_context_hash_derivation_context["bind_context_hash"]
        == packet.bind_context_hash
    )
    assert "bind_context_derived_at" not in context


def test_context_explicitly_binds_critical_governance_lineage():
    source = source_packet()
    context = _packet(source=source).exact_bind_context
    expected = {
        "source_fresh_verified_source_gate_hash": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        ),
        "source_bind_authorization_gate_review_hash": (
            source.source_bind_authorization_gate_review_hash
        ),
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_identity_binding_digest": (source.endpoint_identity_binding_digest),
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_boundary_precondition_digest": (source.bind_boundary_precondition_digest),
        "authority_evidence_linkage_context_digest": (
            source.authority_evidence_linkage_context_digest
        ),
        "human_approval_linkage_context_digest": (
            source.human_approval_linkage_context_digest
        ),
        "final_readiness_context_digest": source.final_readiness_context_digest,
        "bind_authorization_gate_review_context_digest": (
            source.bind_authorization_gate_review_context_digest
        ),
        "source_promotion_hash": source.source_promotion_hash,
        "policy_snapshot_lineage": source.policy_snapshot_lineage,
        "approval_context": source.approval_context,
        "policy_lineage": source.policy_lineage,
    }
    for name, value in expected.items():
        assert getattr(context, name) == value, name


def test_derived_timestamp_changes_packet_but_not_exact_bind_context_hash():
    first = _packet()
    later = _packet(derived_at=DERIVED_AT + timedelta(seconds=1))

    assert first.exact_bind_context == later.exact_bind_context
    assert first.bind_context_hash == later.bind_context_hash
    assert (
        first.bind_context_hash_derivation_context_digest
        != later.bind_context_hash_derivation_context_digest
    )
    assert (
        first.promotion_live_adapter_dry_run_bind_context_hash_derivation_hash
        != later.promotion_live_adapter_dry_run_bind_context_hash_derivation_hash
    )


def test_fresh_source_identity_changes_exact_bind_context_hash():
    first = _packet()
    later_source = source_packet(verified_at=SOURCE_AT + timedelta(microseconds=1))
    later = _packet(source=later_source)

    assert first.bind_context_hash != later.bind_context_hash
    assert (
        first.exact_bind_context.source_fresh_verified_source_gate_hash
        != later.exact_bind_context.source_fresh_verified_source_gate_hash
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fresh_verified_source_gate_status",), "tampered"),
        (("fresh_verified_source_gate_state",), "tampered"),
        (("ready_for_promotion_native_bind_context_derivation",), False),
        (("fail_closed",), True),
        (("fresh_verified_source_gate_still_required",), True),
        (("bind_context_hash_derivation_still_required",), False),
        (("bind_context_hash_derived",), True),
        (
            ("promotion_live_adapter_dry_run_fresh_verified_source_gate_hash",),
            "0" * 64,
        ),
        (("fresh_verified_source_gate_context_digest",), "0" * 64),
        (("execution_intent_hash",), "0" * 64),
        (("adapter_contract_hash",), "0" * 64),
        (("endpoint_identity_binding_digest",), "0" * 64),
        (("credential_scope_binding_digest",), "0" * 64),
        (("operator_review_binding_digest",), "0" * 64),
        (("bind_boundary_precondition_digest",), "0" * 64),
        (("authority_evidence_linkage_context_digest",), "0" * 64),
        (("human_approval_linkage_context_digest",), "0" * 64),
        (("final_readiness_context_digest",), "0" * 64),
        (("bind_authorization_gate_review_context_digest",), "0" * 64),
        (("source_promotion_hash",), "0" * 64),
        (("policy_lineage",), {"tampered": True}),
        (("approval_context",), {"tampered": True}),
        (("fresh_verification_result", "endpoint_rechecked"), True),
    ],
)
def test_source_tamper_fails_closed(path, value):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        _packet(source=_tamper_source(path, value))


@pytest.mark.parametrize("field", EFFECT_FIELDS)
def test_any_source_effect_or_authority_capability_fails_closed(field):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        _packet(source=_tamper_source((field,), True))


def test_source_requirement_and_invocation_order_drift_fail_closed():
    for field in (
        "future_bind_authorization_requirements",
        "future_bind_invocation_requirements",
    ):
        raw = source_packet().model_dump(mode="json")
        raw[field][0], raw[field][1] = raw[field][1], raw[field][0]
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
        ):
            _packet(source=raw)


@pytest.mark.parametrize(
    "derived_at",
    [SOURCE_AT - timedelta(microseconds=1), datetime(2030, 1, 1)],
)
def test_invalid_or_naive_derivation_timestamp_fails_closed(derived_at):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        _packet(derived_at=derived_at)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bind_context_hash", "0" * 64),
        ("bind_context_hash_derivation_result_digest", "0" * 64),
        ("bind_context_hash_derivation_context_digest", "0" * 64),
        ("bind_context_hash_derivation_check_digest", "0" * 64),
        ("bind_context_hash_derived", False),
        ("final_endpoint_identity_recheck_still_required", False),
        ("execution_authorized", True),
        ("bind_authorization_issued", True),
        ("network_used", True),
        ("request_dispatched", True),
    ],
)
def test_packet_tamper_fails_reconstruction(field, value):
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
            raw
        )


def test_nested_context_or_result_tamper_fails_reconstruction():
    raw = _packet().model_dump(mode="json")
    raw["exact_bind_context"]["policy_lineage"] = {"tampered": True}
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
            raw
        )

    raw = _packet().model_dump(mode="json")
    raw["bind_context_hash_derivation_result"]["endpoint_rechecked"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
    ):
        verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
            raw
        )


def test_json_accepts_finite_float_and_rejects_non_finite_values():
    assert context_module._json(1.25) == 1.25
    assert context_module._json({"nested": [0.5, -2.75]}) == {"nested": [0.5, -2.75]}
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError
        ):
            context_module._json(value)


def test_builder_accepts_only_verified_source_and_explicit_timestamp():
    parameters = inspect.signature(
        build_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet
    ).parameters
    assert tuple(parameters) == (
        "source_fresh_verified_source_gate_packet",
        "bind_context_derived_at",
    )


def test_production_imports_have_no_test_legacy_or_effect_dependencies():
    tree = ast.parse(inspect.getsource(context_module))
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
    assert not any(name.split(".")[0] in forbidden for name in imported)
    assert CHECK_MODE in inspect.getsource(context_module)
