"""Contract tests for promotion-native Real Bind Authorization composition."""

from __future__ import annotations

import ast
import importlib.util
import inspect

import pytest
from pydantic import ValidationError

import veritas_os.policy.canonical_promotion_real_bind_authorization_contract as contract_module
from veritas_os.policy.bind_core.core import execute_bind_adjudication
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    INVOCATION_REQUIREMENTS,
)
from veritas_os.policy.canonical_promotion_real_bind_authorization_contract import (
    BIND_TIME_RISK_OWNER,
    CONTRACT_VERSION,
    NEXT_AUTHORIZATION_REQUIREMENT,
    RUNTIME_RISK_ARTIFACT_OWNER,
    CanonicalPromotionRealBindAuthorizationContractError,
    VerifiedPromotionAuthorizationSource,
    project_verified_promotion_authorization_source,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    _packet as credential_scope_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    _packet as endpoint_identity_packet,
    source_packet as bind_context_packet,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def source_packet():
    """Build the recursively verified #2176 source once for this contract."""

    endpoint = endpoint_identity_packet(source=bind_context_packet())
    return credential_scope_packet(source=endpoint)


@pytest.fixture(scope="module")
def projection(source_packet):
    """Build one non-authorizing verified projection."""

    return project_verified_promotion_authorization_source(source_packet)


def test_projection_preserves_exact_security_bindings_without_nested_source(
    source_packet,
    projection,
):
    assert projection.contract_version == CONTRACT_VERSION
    assert projection.source_final_credential_scope_recheck_id == (
        source_packet.promotion_live_adapter_dry_run_final_credential_scope_recheck_id
    )
    assert projection.source_final_credential_scope_recheck_hash == (
        source_packet.promotion_live_adapter_dry_run_final_credential_scope_recheck_hash
    )
    assert projection.execution_intent == source_packet.execution_intent
    assert projection.execution_intent_id == source_packet.execution_intent_id
    assert projection.execution_intent_hash == source_packet.execution_intent_hash
    assert projection.adapter_contract_id == source_packet.adapter_contract_id
    assert projection.adapter_contract_hash == source_packet.adapter_contract_hash
    assert projection.bind_context_hash == source_packet.bind_context_hash
    assert projection.endpoint_identity_binding_digest == (
        source_packet.endpoint_identity_binding_digest
    )
    assert projection.final_endpoint_identity_binding_digest == (
        source_packet.final_endpoint_identity_binding_digest
    )
    assert projection.credential_reference_digest == (
        source_packet.credential_reference_digest
    )
    assert projection.credential_scope_binding_digest == (
        source_packet.credential_scope_binding_digest
    )
    assert projection.final_credential_scope_binding_digest == (
        source_packet.final_credential_scope_binding_digest
    )
    assert "source_packet" not in VerifiedPromotionAuthorizationSource.model_fields


def test_contract_routes_every_remaining_requirement_once(projection):
    authorization = tuple(
        route.requirement for route in projection.authorization_routes
    )
    invocation = tuple(route.requirement for route in projection.invocation_routes)

    assert authorization == AUTHORIZATION_REQUIREMENTS
    assert invocation == INVOCATION_REQUIREMENTS
    assert len(set(authorization)) == len(authorization)
    assert len(set(invocation)) == len(invocation)
    assert all(
        route.ordinal == ordinal
        and route.phase == "authorization"
        and route.separate_evidence_boundary_required
        and not route.satisfied_by_contract
        for ordinal, route in enumerate(projection.authorization_routes, 1)
    )
    assert all(
        route.ordinal == ordinal
        and route.phase == "invocation"
        and route.separate_evidence_boundary_required
        and not route.satisfied_by_contract
        for ordinal, route in enumerate(projection.invocation_routes, 1)
    )


def test_only_runtime_risk_requires_new_pre_authorization_implementation(
    projection,
):
    runtime_route = projection.authorization_routes[0]

    assert runtime_route.requirement == NEXT_AUTHORIZATION_REQUIREMENT
    assert runtime_route.implementation_owner == RUNTIME_RISK_ARTIFACT_OWNER
    assert runtime_route.reuse_existing_implementation is False
    assert runtime_route.bind_time_recheck_required is True
    assert all(
        route.reuse_existing_implementation
        for route in (
            *projection.authorization_routes[1:],
            *projection.invocation_routes,
        )
    )


def test_all_declared_reuse_owners_are_existing_importable_modules(projection):
    owners = {
        route.implementation_owner
        for route in (
            *projection.authorization_routes,
            *projection.invocation_routes,
        )
        if route.reuse_existing_implementation
    }

    assert owners
    assert all(importlib.util.find_spec(owner) is not None for owner in owners)
    assert importlib.util.find_spec(RUNTIME_RISK_ARTIFACT_OWNER) is None


def test_runtime_risk_contract_preserves_just_in_time_bind_recheck(projection):
    assert projection.next_authorization_requirement == (NEXT_AUTHORIZATION_REQUIREMENT)
    assert projection.preauthorization_runtime_risk_artifact_required is True
    assert projection.bind_time_runtime_risk_recheck_required is True
    assert projection.bind_time_runtime_risk_owner == BIND_TIME_RISK_OWNER
    assert "adapter.assess_runtime_risk" in inspect.getsource(execute_bind_adjudication)


def test_projection_never_promotes_source_into_authority_or_effect(projection):
    assert projection.execution_authorized is False
    assert projection.bind_authorization_issued is False
    assert projection.request_dispatched is False
    assert projection.bind_invoked is False
    assert projection.external_effect_used is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("bind_context_hash", "0" * 64),
        ("credential_scope_binding_digest", "0" * 64),
        ("execution_authorized", True),
        ("runtime_risk_review_still_required", False),
    ],
)
def test_any_source_identity_state_or_effect_tamper_fails_closed(
    source_packet,
    field,
    value,
):
    raw = source_packet.model_dump(mode="json")
    raw[field] = value

    with pytest.raises(CanonicalPromotionRealBindAuthorizationContractError):
        project_verified_promotion_authorization_source(raw)


def test_requirement_order_drift_fails_closed(source_packet):
    raw = source_packet.model_dump(mode="json")
    requirements = raw["future_bind_authorization_requirements"]
    requirements[0], requirements[1] = requirements[1], requirements[0]

    with pytest.raises(CanonicalPromotionRealBindAuthorizationContractError):
        project_verified_promotion_authorization_source(raw)


def test_projection_schema_is_closed_and_frozen(projection):
    raw = projection.model_dump(mode="json")
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        VerifiedPromotionAuthorizationSource.model_validate(raw)
    with pytest.raises(ValidationError):
        projection.execution_authorized = True


def test_requirement_owner_drift_fails_closed(monkeypatch):
    owners = dict(contract_module._AUTHORIZATION_OWNERS)
    owners.pop(NEXT_AUTHORIZATION_REQUIREMENT)
    monkeypatch.setattr(contract_module, "_AUTHORIZATION_OWNERS", owners)

    with pytest.raises(
        CanonicalPromotionRealBindAuthorizationContractError,
        match="CPRBAC_REQUIREMENT_OWNER_MISMATCH",
    ):
        contract_module._routes(
            AUTHORIZATION_REQUIREMENTS,
            contract_module._AUTHORIZATION_OWNERS,
            phase="authorization",
        )


def test_contract_module_has_no_effect_capabilities():
    tree = ast.parse(inspect.getsource(contract_module))
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

    assert not any(name.startswith("veritas_os.tests") for name in imported)
    assert not any(
        name.split(".")[0] in {"httpx", "requests", "socket", "subprocess", "urllib"}
        for name in imported
    )
    assert not called_names & {"open", "urlopen", "Popen"}
