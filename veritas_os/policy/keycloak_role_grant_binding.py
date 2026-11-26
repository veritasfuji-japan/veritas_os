"""Construct the exact request and reservation identity for one Keycloak grant.

Deployment supplies the fixed target. The resulting reference is an input to
authorization and can be recomputed on recovery. This module has no dispatch
or credential access.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from uuid import UUID

from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json

ACTION = "keycloak.client-role.grant.v1"
BUSINESS_EVENT_NAMESPACE = "veritas.keycloak-client-role-grant.business-event/v1"
REFERENCE_PREFIX = "keycloak-client-role-grant:v1:sha256:"

_ORIGIN = re.compile(
    r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_PATH_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class KeycloakRoleGrantBindingError(ValueError):
    """The proposed or reconstructed request failed a binding check."""


@dataclass(frozen=True)
class KeycloakRoleGrantTarget:
    """One trusted target pinned by the PoC deployment."""

    origin: str
    realm_name: str
    realm_id: str
    user_id: str
    client_id: str
    role_id: str
    role_name: str


@dataclass(frozen=True)
class KeycloakLabDeployment:
    """Reviewed configuration for a disposable loopback TLS Keycloak lab."""

    target: KeycloakRoleGrantTarget
    tls_port: int
    ca_pem: str
    writer_user: str
    writer_client: str
    audit_reader_client: str
    mapping_reader_client: str
    writer_reference_id: str
    writer_scope: str

    def __post_init__(self) -> None:
        if (
            type(self.target) is not KeycloakRoleGrantTarget
            or type(self.target.realm_name) is not str
            or not self.target.realm_name.startswith("veritas-rehearsal-")
            or type(self.target.origin) is not str
            or not self.target.origin.endswith(".invalid")
            or type(self.tls_port) is not int
            or not 1024 <= self.tls_port <= 65535
            or type(self.ca_pem) is not str
            or not self.ca_pem
            or not all(
                type(value) is str and _PATH_NAME.fullmatch(value)
                for value in (
                    self.writer_client,
                    self.audit_reader_client,
                    self.mapping_reader_client,
                )
            )
            or len(
                {
                    self.writer_client,
                    self.audit_reader_client,
                    self.mapping_reader_client,
                }
            )
            != 3
            or not _canonical_uuid(self.writer_user)
            or not all(
                type(value) is str and 0 < len(value) <= 256
                for value in (self.writer_reference_id, self.writer_scope)
            )
        ):
            raise KeycloakRoleGrantBindingError("KGR_LAB_DEPLOYMENT_INVALID")

    def digest(self) -> str:
        """Bind the local TLS peer, target and distinct credential identities."""
        policy = asdict(self)
        policy["ca_pem"] = sha256_hex(self.ca_pem.encode("ascii"))
        return sha256_of_canonical_json(
            {"profile": "keycloak-loopback-lab/v1", **policy}
        )


@dataclass(frozen=True)
class KeycloakRoleGrantBinding:
    """Deterministic request bytes and identities for later verified use."""

    endpoint_url: str
    body: bytes
    body_digest: str
    business_event_key: str
    reference: str


def _canonical_uuid(value: str) -> bool:
    try:
        return type(value) is str and str(UUID(value)) == value
    except ValueError:
        return False


def build_keycloak_role_grant_binding(
    *,
    target: KeycloakRoleGrantTarget,
    event_id: str,
    attempt_id: str,
    deployment_policy_digest: str,
) -> KeycloakRoleGrantBinding:
    """Bind a fixed POST to an upstream event and a preassigned attempt UUID."""
    if (
        type(target) is not KeycloakRoleGrantTarget
        or type(target.origin) is not str
        or len(target.origin) > 261
        or not _ORIGIN.fullmatch(target.origin)
        or any(
            type(name) is not str or not _PATH_NAME.fullmatch(name)
            for name in (target.realm_name, target.role_name)
        )
        or not all(
            _canonical_uuid(value)
            for value in (target.realm_id, target.user_id, target.client_id, target.role_id)
        )
    ):
        raise KeycloakRoleGrantBindingError("KGR_TARGET_INVALID")
    if (
        type(event_id) is not str
        or not _EVENT_ID.fullmatch(event_id)
        or not _canonical_uuid(attempt_id)
        or type(deployment_policy_digest) is not str
        or not _DIGEST.fullmatch(deployment_policy_digest)
    ):
        raise KeycloakRoleGrantBindingError("KGR_INTENT_INVALID")

    business_event_key = sha256_of_canonical_json({
        "namespace": BUSINESS_EVENT_NAMESPACE,
        "event_id": event_id,
        "origin": target.origin,
        "realm_id": target.realm_id,
        "user_id": target.user_id,
        "client_id": target.client_id,
        "role_id": target.role_id,
    })
    endpoint_url = (
        f"{target.origin}/admin/realms/{target.realm_name}/users/{target.user_id}"
        f"/role-mappings/clients/{target.client_id}"
    )
    body = canonical_json_dumps([{
        "id": target.role_id,
        "name": target.role_name,
        "description": f"veritas-keycloak-attempt:{attempt_id}",
    }]).encode("utf-8")
    body_digest = sha256_hex(body)
    reference = REFERENCE_PREFIX + sha256_of_canonical_json({
        "action": ACTION,
        "method": "POST",
        "endpoint_url": endpoint_url,
        "body_digest": body_digest,
        "business_event_key": business_event_key,
        "deployment_policy_digest": deployment_policy_digest,
    })
    return KeycloakRoleGrantBinding(endpoint_url, body, body_digest, business_event_key, reference)


def verify_keycloak_role_grant_binding(
    *,
    target: KeycloakRoleGrantTarget,
    event_id: str,
    attempt_id: str,
    deployment_policy_digest: str,
    approved_reference: str,
) -> KeycloakRoleGrantBinding:
    """Rebuild the request and compare the reference from a verified intent.

    The caller verifies the intent and its authorization before using the
    reference. A match establishes the request identity only.
    """
    binding = build_keycloak_role_grant_binding(
        target=target,
        event_id=event_id,
        attempt_id=attempt_id,
        deployment_policy_digest=deployment_policy_digest,
    )
    if type(approved_reference) is not str or approved_reference != binding.reference:
        raise KeycloakRoleGrantBindingError("KGR_REFERENCE_MISMATCH")
    return binding
