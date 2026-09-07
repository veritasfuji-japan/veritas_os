"""Bind one synthetic sandbox request to an independently verified native grant.

The pre-issuance reference must enter the decision candidate's evidence_refs.
This module neither modifies/creates authorization nor consumes, resolves secrets,
claims an execution attempt or dispatches. Deployment inputs are trusted caller
configuration, not fields extracted from an authorization packet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any
from uuid import UUID

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    verify_native_bind_authorization,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

ACTION = "sandbox.event.register.v1"
REFERENCE_PREFIX = "sandbox-action:v1:sha256:"


class SandboxActionBindingError(ValueError):
    """Sanitized failure of local action binding, never an execution decision."""


@dataclass(frozen=True)
class SandboxDeployment:
    """Reviewed deployment pins; no defaults, secret material or packet fallback.

    credential_version pins the provider version to be checked by a future
    resolver; this metadata-only verifier cannot authenticate the provider.
    """

    endpoint_url: str
    target_system: str
    action_contract_digest: str
    credential_reference_id: str
    credential_version: str
    credential_provider_type: str
    credential_scope: str
    credential_environment: str


@dataclass(frozen=True)
class SandboxActionBinding:
    """Immutable local request description; not an authorization/capability."""

    reference: str
    payload_json: str
    payload_digest: str


@dataclass(frozen=True)
class VerifiedSandboxActionBinding:
    """Audit association only; consumption and pre-effect checks remain required."""

    binding: SandboxActionBinding
    authorization_id: str
    authorization_hash: str
    idempotency_key: str


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SandboxActionBindingError("SAB_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def build_sandbox_action_binding(
    payload_json: str,
    *,
    deployment: SandboxDeployment,
    expected_contract: ActionClassContract,
) -> SandboxActionBinding:
    """Build a reference before issuance, over exact payload and deployment pins.

    Only the existing two-string event protocol is accepted. No URL normalization,
    network lookup, runtime configuration mutation or new policy is performed.
    """
    if type(deployment) is not SandboxDeployment or any(
        type(value) is not str or not value or value != value.strip()
        for value in asdict(deployment).values()
    ):
        raise SandboxActionBindingError("SAB_DEPLOYMENT_REQUIRED")
    # Deliberately narrow: lower-case ASCII DNS, default TLS port, exact path.
    if not re.fullmatch(
        r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?/v1/events",
        deployment.endpoint_url,
    ):
        raise SandboxActionBindingError("SAB_ENDPOINT_INVALID")
    if (
        type(expected_contract) is not ActionClassContract
        or expected_contract.id != ACTION
        or expected_contract.action_class != ACTION
        or deployment.action_contract_digest != expected_contract.deterministic_digest()
    ):
        raise SandboxActionBindingError("SAB_CONTRACT_MISMATCH")
    try:
        if type(payload_json) is not str or len(payload_json.encode("utf-8")) > 4096:
            raise SandboxActionBindingError("SAB_PAYLOAD_INVALID")
        payload = json.loads(payload_json, object_pairs_hook=_unique_object)
        if (
            type(payload) is not dict
            or set(payload) != {"event_id", "message"}
            or type(payload["event_id"]) is not str
            or str(UUID(payload["event_id"])) != payload["event_id"]
            or type(payload["message"]) is not str
            or not 1 <= len(payload["message"].encode("utf-8")) <= 256
        ):
            raise SandboxActionBindingError("SAB_PAYLOAD_INVALID")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SandboxActionBindingError("SAB_PAYLOAD_INVALID") from None
    digest = sha256_of_canonical_json(payload)
    reference = REFERENCE_PREFIX + sha256_of_canonical_json({
        "domain": "veritas.sandbox-action-binding/v1",
        "action": ACTION,
        "method": "POST",
        "payload_digest": digest,
        "deployment": asdict(deployment),
    })
    return SandboxActionBinding(reference, canonical_json_dumps(payload), digest)


def verify_sandbox_action_binding(
    authorization: Any,
    payload_json: str,
    *,
    deployment: SandboxDeployment,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> VerifiedSandboxActionBinding:
    """Verify native signatures/lineage, then reconstruct the pre-issuance binding.

    Returned canonical bytes are for later checked use, not permission to send.
    Provider authenticity, credential expiry and TLS-peer identity are not claimed.
    No consumed flag or caller-asserted 'verified' result is accepted as a shortcut.
    """
    verified = verify_native_bind_authorization(
        authorization, source_inputs=source_inputs,
        governance_inputs=governance_inputs, trust_inputs=trust_inputs,
    )
    binding = build_sandbox_action_binding(
        payload_json, deployment=deployment,
        expected_contract=governance_inputs.action_contract,
    )
    intent = verified.execution_intent
    refs = intent.get("evidence_refs", [])
    if (
        intent.get("intended_action") != ACTION
        or intent.get("target_system") != deployment.target_system
        or intent.get("target_resource") != deployment.endpoint_url
        or verified.action_contract_digest != deployment.action_contract_digest
        or [ref for ref in refs if isinstance(ref, str) and ref.startswith(REFERENCE_PREFIX)]
        != [binding.reference]
    ):
        raise SandboxActionBindingError("SAB_AUTHORIZATION_BINDING_MISMATCH")
    endpoint = source_inputs.current_endpoint
    credential = source_inputs.current_credential_reference
    if not isinstance(endpoint, dict) or not isinstance(credential, dict):
        raise SandboxActionBindingError("SAB_CURRENT_METADATA_REQUIRED")
    host = deployment.endpoint_url[len("https://"):-len("/v1/events")]
    if any(endpoint.get(k) != v for k, v in {
        "endpoint_scheme": "https", "endpoint_host": host,
        "endpoint_port": 443, "endpoint_path_prefix": "/v1/events",
    }.items()) or any(credential.get(k) != getattr(deployment, k) for k in (
        "credential_reference_id", "credential_provider_type",
        "credential_scope", "credential_environment",
    )) or source_inputs.required_credential_scope != deployment.credential_scope:
        raise SandboxActionBindingError("SAB_CURRENT_METADATA_MISMATCH")
    return VerifiedSandboxActionBinding(
        binding, verified.authorization_id, verified.authorization_hash,
        verified.idempotency_key,
    )
