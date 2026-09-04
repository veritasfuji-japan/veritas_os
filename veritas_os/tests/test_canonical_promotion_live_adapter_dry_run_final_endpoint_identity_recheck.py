"""Fail-closed tests for promotion-native final endpoint identity recheck."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta

import pytest

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck as endpoint_module
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    CHECK_MODE,
    DOMAINS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS,
    CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError,
    build_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet,
    verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation import (
    DERIVED_AT as SOURCE_AT,
    _packet as source_packet,
)

RECHECKED_AT = SOURCE_AT + timedelta(seconds=1)
pytestmark = pytest.mark.slow


def _candidate(source, **changes):
    value = dict(source.endpoint_candidate)
    value.update(changes)
    return value


def _packet(*, source, candidate=None, rechecked_at=RECHECKED_AT):
    candidate = candidate if candidate is not None else _candidate(source)
    return build_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
        source, candidate, rechecked_at
    )


def _tamper_source(source, path: tuple[str, ...], value):
    raw = source.model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return raw


@pytest.fixture(scope="module")
def source():
    """Build the deeply verified upstream packet only in the slow-test lane."""

    return source_packet()


@pytest.fixture(scope="module")
def valid_packet(source):
    """Build one fully verified packet for reconstruction-focused tests."""

    return _packet(source=source)


def test_valid_source_round_trips_and_preserves_exact_typed_fields(
    source, valid_packet
):
    packet = valid_packet
    verified = verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
        json.loads(packet.model_dump_json())
    )

    assert verified == packet
    for name in PRESERVED_FIELDS:
        assert getattr(packet, name) == getattr(source, name), name
        assert (
            type(packet).model_fields[name].annotation
            == type(source).model_fields[name].annotation
        )
    assert packet.source_bind_context_hash_derivation_packet == source.model_dump(
        mode="json"
    )


def test_requirement_transition_consumes_only_endpoint_identity_recheck(
    source, valid_packet
):
    packet = valid_packet
    source_authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    output_authorization = tuple(
        item.name for item in packet.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in packet.future_bind_invocation_requirements)

    assert source_authorization[0] == "final_endpoint_identity_recheck"
    assert output_authorization == source_authorization[1:]
    assert output_authorization == AUTHORIZATION_REQUIREMENTS
    assert output_authorization[0] == "final_credential_scope_recheck"
    assert invocation == INVOCATION_REQUIREMENTS
    assert all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *packet.future_bind_authorization_requirements,
            *packet.future_bind_invocation_requirements,
        )
    )


def test_output_routes_only_to_credential_recheck_without_authority_or_effect(
    valid_packet,
):
    packet = valid_packet

    assert packet.ready_for_promotion_native_final_credential_scope_recheck
    assert packet.fresh_verified_source_gate_still_required is False
    assert packet.bind_context_hash_derivation_still_required is False
    assert packet.bind_context_hash_derived is True
    assert packet.final_endpoint_identity_recheck_still_required is False
    assert packet.final_endpoint_identity_rechecked is True
    assert packet.final_credential_scope_recheck_still_required is True
    assert packet.bind_authorization_state == "NOT_AUTHORIZED"
    assert packet.authority_state == "NOT_AUTHORIZED"
    assert packet.human_approval_state == "NOT_APPROVED"
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)


def test_result_truthfully_limits_recheck_to_local_metadata(valid_packet):
    result = valid_packet.final_endpoint_identity_recheck_result

    assert result.endpoint_rechecked is True
    assert result.local_endpoint_metadata_rechecked is True
    assert result.trusted_clock_verified is False
    assert result.endpoint_resolution_performed is False
    assert result.external_endpoint_identity_verified is False
    assert result.dns_identity_verified is False
    assert result.tls_peer_identity_verified is False
    assert result.endpoint_liveness_verified is False
    assert result.network_path_verified is False
    assert result.external_policy_freshness_verified is False
    assert result.credential_scope_rechecked is False
    assert result.revocation_verified is False


def test_recheck_binds_exact_candidate_identity_to_exact_bind_context(
    source, valid_packet
):
    packet = valid_packet
    binding = packet.final_endpoint_identity_binding

    assert (
        packet.rechecked_endpoint_candidate.model_dump(mode="json")
        == source.endpoint_candidate
    )
    assert packet.rechecked_endpoint_candidate_digest == source.endpoint_candidate_digest
    assert binding["bind_context_hash"] == source.bind_context_hash
    assert (
        binding["endpoint_candidate_id"]
        == source.endpoint_candidate["endpoint_candidate_id"]
    )
    assert binding["endpoint_candidate_digest"] == source.endpoint_candidate_digest
    assert (
        binding["endpoint_identity_binding_digest"]
        == source.endpoint_identity_binding_digest
    )
    assert packet.final_endpoint_identity_binding_digest == endpoint_module._digest(
        DOMAINS["binding"], binding
    )
    assert (
        packet.final_endpoint_identity_recheck_result.final_endpoint_identity_binding_digest
        == packet.final_endpoint_identity_binding_digest
    )


def test_recheck_timestamp_changes_packet_not_frozen_bind_or_endpoint_identity(
    source, valid_packet
):
    first = valid_packet
    later = endpoint_module._assemble(
        source,
        endpoint_module._candidate(_candidate(source)),
        endpoint_module._timestamp(RECHECKED_AT + timedelta(seconds=1)),
    )

    assert first.bind_context_hash == later["bind_context_hash"]
    assert (
        first.rechecked_endpoint_candidate_digest
        == later["rechecked_endpoint_candidate_digest"]
    )
    assert (
        first.final_endpoint_identity_binding_digest
        == later["final_endpoint_identity_binding_digest"]
    )
    assert (
        first.final_endpoint_identity_recheck_context_digest
        != later["final_endpoint_identity_recheck_context_digest"]
    )
    assert (
        first.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash
        != later[
            "promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash"
        ]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint_candidate_id", "endpoint:other:v1"),
        ("endpoint_kind", "HTTPS_WEBHOOK"),
        ("endpoint_scheme", "http"),
        ("endpoint_host", "other.example.invalid"),
        ("endpoint_port", 8443),
        ("endpoint_path_prefix", "/other"),
        ("endpoint_environment", "production"),
        ("endpoint_purpose", "other-purpose"),
        ("adapter_contract_id", "adapter:other:v1"),
        ("target_system", "other-system"),
        ("target_resource_scope", "other-resource"),
        ("declared_by", "operator:other"),
        ("declared_at", (RECHECKED_AT + timedelta(seconds=1)).isoformat()),
    ],
)
def test_any_endpoint_identity_change_fails_closed(source, field, value):
    candidate = endpoint_module._candidate(
        _candidate(source, **{field: value})
    )
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        endpoint_module._validate_candidate(source, candidate)


def test_public_builder_rejects_mismatched_endpoint(source):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        _packet(
            source=source,
            candidate=_candidate(source, endpoint_host="other.example.invalid"),
        )


def test_sensitive_or_open_endpoint_input_fails_closed(source):
    candidate = _candidate(source)
    candidate["token"] = "must-not-be-accepted"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        endpoint_module._candidate(candidate)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("bind_context_hash_derivation_status",), "tampered"),
        (("ready_for_promotion_native_final_endpoint_identity_recheck",), False),
        (("bind_context_hash",), "0" * 64),
        (("bind_context_hash_derivation_result", "endpoint_rechecked"), True),
    ],
)
def test_source_tamper_fails_closed(source, path, value):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        _packet(
            source=_tamper_source(source, path, value),
            candidate=_candidate(source),
        )


@pytest.mark.parametrize(
    "field",
    (
        "execution_authorized",
        "bind_authorization_issued",
        "credential_material_accessed",
        "endpoint_contacted",
        "network_used",
        "request_dispatched",
        "external_effect_used",
        "ready_for_real_bind",
    ),
)
def test_representative_source_effect_or_authority_claim_fails_closed(source, field):
    tampered = source.model_copy(update={field: True})
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        endpoint_module._validate_source(tampered)


def test_source_requirement_and_invocation_order_drift_fail_closed(source):
    for field in (
        "future_bind_authorization_requirements",
        "future_bind_invocation_requirements",
    ):
        requirements = list(getattr(source, field))
        requirements[0], requirements[1] = requirements[1], requirements[0]
        tampered = source.model_copy(update={field: tuple(requirements)})
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
        ):
            endpoint_module._validate_source(tampered)


def test_recheck_timestamp_before_source_fails_closed(source):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        _packet(
            source=source,
            rechecked_at=SOURCE_AT - timedelta(microseconds=1),
        )


@pytest.mark.parametrize("value", [datetime(2030, 1, 1), "not-a-timestamp"])
def test_naive_or_invalid_timestamp_fails_closed(value):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        endpoint_module._timestamp(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("final_endpoint_identity_recheck_context_digest", "0" * 64),
        ("execution_authorized", True),
    ],
)
def test_packet_tamper_fails_reconstruction(valid_packet, field, value):
    raw = valid_packet.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
            raw
        )


def test_nested_binding_or_result_tamper_fails_reconstruction(valid_packet):
    raw = valid_packet.model_dump(mode="json")
    raw["final_endpoint_identity_binding"]["bind_context_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
            raw
        )

    raw = valid_packet.model_dump(mode="json")
    raw["final_endpoint_identity_recheck_result"]["credential_scope_rechecked"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
            raw
        )


def test_builder_accepts_only_verified_source_candidate_and_explicit_timestamp():
    parameters = inspect.signature(
        build_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet
    ).parameters
    assert tuple(parameters) == (
        "source_bind_context_hash_derivation_packet",
        "endpoint_candidate",
        "endpoint_identity_rechecked_at",
    )


def test_production_imports_have_no_test_legacy_or_effect_dependencies():
    tree = ast.parse(inspect.getsource(endpoint_module))
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
    assert CHECK_MODE in inspect.getsource(endpoint_module)
