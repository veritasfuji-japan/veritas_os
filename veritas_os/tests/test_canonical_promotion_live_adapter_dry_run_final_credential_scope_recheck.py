"""Fail-closed tests for promotion-native final credential scope recheck."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta

import pytest

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck as scope_module
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    CHECK_MODE,
    DOMAINS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS,
    SCOPE_MATCH_MODE,
    CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError,
    build_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet,
    verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    RECHECKED_AT as SOURCE_AT,
    _packet as endpoint_packet,
    source_packet as bind_context_packet,
)

RECHECKED_AT = SOURCE_AT + timedelta(seconds=1)
pytestmark = pytest.mark.slow


def _reference(source, **changes):
    value = dict(source.credential_reference)
    value.update(changes)
    return value


def _packet(
    *,
    source,
    reference=None,
    required_scope=None,
    rechecked_at=RECHECKED_AT,
):
    reference = reference if reference is not None else _reference(source)
    required_scope = (
        required_scope if required_scope is not None else reference["credential_scope"]
    )
    return build_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
        source,
        reference,
        required_scope,
        rechecked_at,
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
    """Build the deeply verified endpoint packet only in the slow lane."""

    return endpoint_packet(source=bind_context_packet())


@pytest.fixture(scope="module")
def valid_packet(source):
    """Build one verified packet for reconstruction-focused tests."""

    return _packet(source=source)


def test_valid_source_round_trips_and_preserves_exact_typed_fields(
    source, valid_packet
):
    packet = valid_packet
    verified = verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
        json.loads(packet.model_dump_json())
    )

    assert verified == packet
    for name in PRESERVED_FIELDS:
        assert getattr(packet, name) == getattr(source, name), name
        assert (
            type(packet).model_fields[name].annotation
            == type(source).model_fields[name].annotation
        )
    assert packet.source_final_endpoint_identity_recheck_packet == source.model_dump(
        mode="json"
    )


def test_requirement_transition_consumes_only_final_credential_scope_recheck(
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

    assert source_authorization[0] == "final_credential_scope_recheck"
    assert output_authorization == source_authorization[1:]
    assert output_authorization == AUTHORIZATION_REQUIREMENTS
    assert output_authorization[0] == "runtime_risk_review"
    assert invocation == INVOCATION_REQUIREMENTS
    assert all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *packet.future_bind_authorization_requirements,
            *packet.future_bind_invocation_requirements,
        )
    )


def test_output_routes_only_to_runtime_risk_review_without_authority_or_effect(
    valid_packet,
):
    packet = valid_packet

    assert packet.ready_for_promotion_native_runtime_risk_review
    assert packet.fresh_verified_source_gate_still_required is False
    assert packet.bind_context_hash_derivation_still_required is False
    assert packet.bind_context_hash_derived is True
    assert packet.final_endpoint_identity_recheck_still_required is False
    assert packet.final_endpoint_identity_rechecked is True
    assert packet.final_credential_scope_recheck_still_required is False
    assert packet.final_credential_scope_rechecked is True
    assert packet.runtime_risk_review_still_required is True
    assert packet.bind_authorization_state == "NOT_AUTHORIZED"
    assert packet.authority_state == "NOT_AUTHORIZED"
    assert packet.human_approval_state == "NOT_APPROVED"
    assert not any(getattr(packet, field) for field in EFFECT_FIELDS)


def test_result_truthfully_limits_recheck_to_exact_local_metadata(valid_packet):
    result = valid_packet.final_credential_scope_recheck_result

    assert result.credential_reference_rechecked is True
    assert result.credential_scope_rechecked is True
    assert result.scope_match_mode == SCOPE_MATCH_MODE
    assert result.scope_containment_inferred is False
    assert result.trusted_clock_verified is False
    assert result.external_policy_freshness_verified is False
    assert result.credential_resolved is False
    assert result.credential_store_accessed is False
    assert result.credential_material_accessed is False
    assert result.revocation_verified is False


def test_recheck_binds_complete_reference_and_scope_to_exact_bind_context(
    source, valid_packet
):
    packet = valid_packet
    binding = packet.final_credential_scope_binding

    assert (
        packet.rechecked_credential_reference.model_dump(mode="json")
        == source.credential_reference
    )
    assert (
        packet.rechecked_credential_reference_digest
        == source.credential_reference_digest
        == source.exact_bind_context.credential_reference_digest
    )
    assert (
        binding["credential_scope_binding_digest"]
        == source.credential_scope_binding_digest
        == source.exact_bind_context.credential_scope_binding_digest
    )
    assert binding["bind_context_hash"] == source.bind_context_hash
    assert binding["required_credential_scope"] == "invoice:write"
    assert binding["bound_credential_scope"] == "invoice:write"
    assert binding["scope_match_mode"] == SCOPE_MATCH_MODE
    assert binding["scope_containment_inferred"] is False
    assert packet.final_credential_scope_binding_digest == scope_module._digest(
        DOMAINS["binding"], binding
    )


def test_recheck_packet_records_auditable_input_lineage_and_unsatisfied_work(
    source, valid_packet
):
    context = valid_packet.final_credential_scope_recheck_context

    assert context["source_final_endpoint_identity_recheck_hash"] == (
        source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash
    )
    assert context["source_bind_context_hash_derivation_hash"] == (
        source.source_bind_context_hash_derivation_hash
    )
    assert context["bind_context_hash"] == source.bind_context_hash
    assert context["credential_reference_digest"] == source.credential_reference_digest
    assert context["required_credential_scope"] == "invoice:write"
    assert valid_packet.trustlog_written is False
    assert valid_packet.future_bind_authorization_requirements[0].name == (
        "runtime_risk_review"
    )


def test_recheck_timestamp_changes_packet_not_frozen_bind_or_credential_identity(
    source, valid_packet
):
    first = valid_packet
    later = scope_module._assemble(
        source,
        scope_module._reference(_reference(source)),
        "invoice:write",
        scope_module._timestamp(RECHECKED_AT + timedelta(seconds=1)),
    )

    assert first.bind_context_hash == later["bind_context_hash"]
    assert (
        first.rechecked_credential_reference_digest
        == later["rechecked_credential_reference_digest"]
    )
    assert (
        first.final_credential_scope_binding_digest
        == later["final_credential_scope_binding_digest"]
    )
    assert (
        first.final_credential_scope_recheck_context_digest
        != later["final_credential_scope_recheck_context_digest"]
    )
    assert (
        first.promotion_live_adapter_dry_run_final_credential_scope_recheck_hash
        != later["promotion_live_adapter_dry_run_final_credential_scope_recheck_hash"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("credential_reference_id", "credential-ref:other:v1"),
        ("credential_kind", "OTHER_REFERENCE"),
        ("credential_provider_type", "OTHER_STORE_REFERENCE"),
        ("credential_scope", "invoice:read"),
        ("credential_environment", "production"),
        ("credential_purpose", "other-purpose"),
        ("adapter_contract_id", "adapter:other:v1"),
        ("endpoint_candidate_id", "endpoint:other:v1"),
        ("target_system", "other-system"),
        ("target_resource_scope", "other-resource"),
        ("declared_by", "operator:other"),
        ("declared_at", (RECHECKED_AT + timedelta(seconds=1)).isoformat()),
    ],
)
def test_any_complete_credential_metadata_change_fails_closed(source, field, value):
    reference = _reference(source, **{field: value})
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        _packet(source=source, reference=reference, required_scope="invoice:write")


@pytest.mark.parametrize(
    "required_scope",
    [
        "invoice:read",
        "invoice:*",
        "invoice:write ",
        "Invoice:write",
        "",
    ],
)
def test_scope_difference_or_inferred_containment_fails_closed(source, required_scope):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        _packet(source=source, required_scope=required_scope)


def test_sensitive_or_open_credential_input_fails_closed(source):
    reference = _reference(source)
    reference["token"] = "must-not-be-accepted"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        _packet(source=source, reference=reference)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("final_endpoint_identity_recheck_status",), "tampered"),
        (("ready_for_promotion_native_final_credential_scope_recheck",), False),
        (("bind_context_hash",), "0" * 64),
        (("credential_reference_digest",), "0" * 64),
        (("credential_scope_binding_digest",), "0" * 64),
        (
            ("final_endpoint_identity_recheck_result", "credential_scope_rechecked"),
            True,
        ),
    ],
)
def test_source_tamper_fails_closed(source, path, value):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        _packet(
            source=_tamper_source(source, path, value), reference=_reference(source)
        )


@pytest.mark.parametrize(
    "field",
    (
        "execution_authorized",
        "bind_authorization_issued",
        "credential_resolved",
        "credential_material_accessed",
        "credential_store_accessed",
        "network_used",
        "request_dispatched",
        "trustlog_written",
        "external_effect_used",
        "ready_for_real_bind",
    ),
)
def test_representative_source_effect_or_authority_claim_fails_closed(source, field):
    tampered = source.model_copy(update={field: True})
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        scope_module._validate_source(tampered)


def test_source_requirement_and_invocation_order_drift_fail_closed(source):
    for field in (
        "future_bind_authorization_requirements",
        "future_bind_invocation_requirements",
    ):
        requirements = list(getattr(source, field))
        requirements[0], requirements[1] = requirements[1], requirements[0]
        tampered = source.model_copy(update={field: tuple(requirements)})
        with pytest.raises(
            CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
        ):
            scope_module._validate_source(tampered)


def test_recheck_timestamp_before_source_fails_closed(source):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        _packet(source=source, rechecked_at=SOURCE_AT - timedelta(microseconds=1))


@pytest.mark.parametrize("value", [datetime(2030, 1, 1), "not-a-timestamp"])
def test_naive_or_invalid_timestamp_fails_closed(value):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        scope_module._timestamp(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("final_credential_scope_recheck_context_digest", "0" * 64),
        ("execution_authorized", True),
    ],
)
def test_packet_tamper_fails_reconstruction(valid_packet, field, value):
    raw = valid_packet.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            raw
        )


def test_nested_binding_reference_or_result_tamper_fails_reconstruction(
    valid_packet,
):
    raw = valid_packet.model_dump(mode="json")
    raw["final_credential_scope_binding"]["bind_context_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            raw
        )

    raw = valid_packet.model_dump(mode="json")
    raw["rechecked_credential_reference"]["declared_by"] = "operator:other"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            raw
        )

    raw = valid_packet.model_dump(mode="json")
    raw["final_credential_scope_recheck_result"]["scope_containment_inferred"] = True
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError
    ):
        verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            raw
        )


def test_builder_accepts_only_verified_source_reference_scope_and_timestamp():
    parameters = inspect.signature(
        build_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet
    ).parameters
    assert tuple(parameters) == (
        "source_final_endpoint_identity_recheck_packet",
        "credential_reference",
        "required_credential_scope",
        "credential_scope_rechecked_at",
    )


def test_production_imports_and_calls_have_no_effect_capabilities():
    tree = ast.parse(inspect.getsource(scope_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        (node.func.value.id, node.func.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }
    forbidden_imports = {"requests", "httpx", "urllib", "socket", "subprocess"}
    forbidden_direct_calls = {"open", "urlopen", "Popen"}
    effect_receivers = {
        "client",
        "connection",
        "httpx",
        "requests",
        "session",
        "socket",
        "subprocess",
        "urllib",
    }
    effect_methods = {
        "connect",
        "delete",
        "get",
        "patch",
        "post",
        "put",
        "request",
        "run",
        "send",
    }

    assert not any(name.startswith("veritas_os.tests") for name in imported)
    assert not any(name.split(".")[0] in forbidden_imports for name in imported)
    assert not called_names & forbidden_direct_calls
    assert not {
        (receiver, method)
        for receiver, method in called_attributes
        if receiver in effect_receivers and method in effect_methods
    }
    assert CHECK_MODE in inspect.getsource(scope_module)
