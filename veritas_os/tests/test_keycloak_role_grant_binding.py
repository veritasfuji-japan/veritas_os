"""Bind the approved Keycloak request separately from replay identity."""

from dataclasses import replace
import json
from uuid import UUID

import pytest

from veritas_os.policy.keycloak_role_grant_binding import (
    KeycloakRoleGrantBindingError,
    KeycloakRoleGrantTarget,
    build_keycloak_role_grant_binding,
    verify_keycloak_role_grant_binding,
)
from veritas_os.security.hash import sha256_hex, sha256_of_canonical_json

TARGET = KeycloakRoleGrantTarget(
    origin="https://keycloak.example.invalid",
    realm_name="veritas-test",
    realm_id=str(UUID(int=1)),
    user_id=str(UUID(int=2)),
    client_id=str(UUID(int=3)),
    role_id=str(UUID(int=4)),
    role_name="report-viewer",
)
INPUTS = {
    "target": TARGET,
    "event_id": "assignment-42",
    "attempt_id": str(UUID(int=5)),
    "deployment_policy_digest": "a" * 64,
}


def test_binding_maps_to_exact_role_request():
    result = build_keycloak_role_grant_binding(**INPUTS)
    assert result.endpoint_url == (
        f"{TARGET.origin}/admin/realms/veritas-test/users/{TARGET.user_id}"
        f"/role-mappings/clients/{TARGET.client_id}"
    )
    assert json.loads(result.body) == [{
        "id": TARGET.role_id,
        "name": "report-viewer",
        "description": f"veritas-keycloak-attempt:{INPUTS['attempt_id']}",
    }]
    assert result.body_digest == sha256_hex(result.body)
    assert result.business_event_key == sha256_of_canonical_json({
        "namespace": "veritas.keycloak-client-role-grant.business-event/v1",
        "event_id": "assignment-42",
        "origin": TARGET.origin,
        "realm_id": TARGET.realm_id,
        "user_id": TARGET.user_id,
        "client_id": TARGET.client_id,
        "role_id": TARGET.role_id,
    })
    assert verify_keycloak_role_grant_binding(
        **INPUTS, approved_reference=result.reference,
    ) == result


def test_replacement_attempt_cannot_change_business_event_key():
    first = build_keycloak_role_grant_binding(**INPUTS)
    replacement = INPUTS | {"attempt_id": str(UUID(int=6)), "deployment_policy_digest": "b" * 64}
    second = build_keycloak_role_grant_binding(**replacement)
    assert second.business_event_key == first.business_event_key
    assert second.body_digest != first.body_digest
    assert second.reference != first.reference


@pytest.mark.parametrize("updates", [
    {"event_id": "assignment-43"},
    {"attempt_id": str(UUID(int=6))},
    {"deployment_policy_digest": "b" * 64},
    {"target": replace(TARGET, realm_name="other-realm")},
    {"target": replace(TARGET, realm_id=str(UUID(int=7)))},
    {"target": replace(TARGET, user_id=str(UUID(int=7)))},
    {"target": replace(TARGET, client_id=str(UUID(int=7)))},
    {"target": replace(TARGET, role_id=str(UUID(int=7)))},
    {"target": replace(TARGET, role_name="other-role")},
    {"target": replace(TARGET, origin="https://other.example.invalid")},
])
def test_approved_reference_cannot_be_rebound(updates):
    original = build_keycloak_role_grant_binding(**INPUTS)
    with pytest.raises(KeycloakRoleGrantBindingError, match="KGR_REFERENCE_MISMATCH"):
        verify_keycloak_role_grant_binding(
            **(INPUTS | updates), approved_reference=original.reference,
        )


@pytest.mark.parametrize("target", [
    replace(TARGET, origin="http://keycloak.example.invalid"),
    replace(TARGET, origin="https://keycloak.example.invalid:443"),
    replace(TARGET, origin="https://keycloak.example.invalid/path"),
    replace(TARGET, origin="https://user@keycloak.example.invalid"),
    replace(TARGET, realm_name="realm/other"),
    replace(TARGET, realm_name="realm%2fother"),
    replace(TARGET, user_id=TARGET.user_id.replace("-", "")),
])
def test_rejects_ambiguous_targets(target):
    with pytest.raises(KeycloakRoleGrantBindingError, match="KGR_TARGET_INVALID"):
        build_keycloak_role_grant_binding(**(INPUTS | {"target": target}))


@pytest.mark.parametrize("updates", [
    {"event_id": ""},
    {"event_id": " foo"},
    {"attempt_id": "not-uuid"},
    {"deployment_policy_digest": "NOT_A_DIGEST"},
])
def test_rejects_invalid_intent_fields(updates):
    with pytest.raises(KeycloakRoleGrantBindingError, match="KGR_INTENT_INVALID"):
        build_keycloak_role_grant_binding(**(INPUTS | updates))
