"""Trust contracts and runtime inputs for authenticated Real Bind Authorization v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import (
    AuthorityEvidenceSignatureVerifier, AuthorityEvidenceSignerPolicy,
    AuthorityEvidenceVerifierPolicy, AuthorityRevocationChecker,
    AuthorityRevocationPolicy, VerifiedAuthorityEvidence,
)
from veritas_os.governance.human_approval_receipt import (
    HumanApprovalSignatureVerifier, HumanApprovalSignerPolicy,
    HumanApprovalVerifierPolicy, VerifiedHumanApprovalReceipt,
)
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidationResult
from veritas_os.security.hash import sha256_of_canonical_json

FORMAT_VERSION = "canonical-live-adapter-bind-authorization/v1"
STATUS = "LIVE_ADAPTER_BIND_AUTHORIZATION_GRANTED_NOT_INVOKED"
MECHANISM = "authorize_exact_future_live_adapter_bind_without_invocation/v1"
HASH_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^laba:v1:sha256:[0-9a-f]{64}$"
AUTHORIZER_ARTIFACT_TYPE = "bind_authorizer_decision"
AUTHORIZER_ARTIFACT_VERSION = "v1"
AUTHORIZATION_ARTIFACT_TYPE = "live_adapter_bind_authorization"
AUTHORIZATION_ARTIFACT_VERSION = "v1"
AUTHORIZER_SIGNATURE_DOMAIN = "VERITAS:bind-authorizer-decision:v1:"
AUTHORIZATION_SIGNATURE_DOMAIN = "VERITAS:live-adapter-bind-authorization:v1:"
SignaturePurpose = Literal["authorizer_decision", "authorization_issuer"]

ACKNOWLEDGEMENTS = (
    "acknowledged_exact_source_context_only",
    "acknowledged_authorization_does_not_invoke_bind",
    "acknowledged_authorization_does_not_dispatch_request",
    "acknowledged_authorization_does_not_access_credentials",
    "acknowledged_authorization_does_not_construct_authorization_header",
    "acknowledged_authorization_does_not_create_bind_receipt",
    "acknowledged_authorization_does_not_write_trustlog",
    "acknowledged_semantic_match_is_not_authority",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor",
    "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
    "endpoint_candidate", "endpoint_candidate_digest",
    "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_reference", "credential_reference_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "authority_evidence_reference_bundle",
    "authority_evidence_reference_bundle_digest",
    "authority_evidence_linkage_result",
    "authority_evidence_linkage_result_digest",
    "human_approval_reference_bundle", "human_approval_reference_bundle_digest",
    "human_approval_linkage_result", "human_approval_linkage_result_digest",
    "final_bind_authorization_readiness_result",
    "final_bind_authorization_readiness_result_digest",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)
UPSTREAM_HASH_FIELDS = (
    "source_live_adapter_dry_run_request_hash", "source_dispatch_readiness_hash",
    "source_endpoint_allowlist_evaluation_hash",
    "source_credential_authorization_hash",
    "source_operator_dispatch_review_hash", "source_bind_pre_dispatch_review_hash",
    "source_authority_evidence_linkage_review_hash",
    "source_human_approval_linkage_review_hash",
    "source_final_bind_authorization_readiness_hash",
)
EFFECT_FIELDS = (
    "bind_invoked", "bind_receipt_created", "trustlog_written",
    "request_dispatched", "endpoint_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "network_used", "dns_used",
    "webhook_called", "live_adapter_instantiated", "live_adapter_method_called",
    "external_effect_used", "filesystem_used", "database_used", "provider_used",
    "subprocess_used", "operation_committed",
)
DOMAINS = {
    "decision": "veritas.live-adapter-bind-authorization.decision/v1",
    "requirements": "veritas.live-adapter-bind-authorization.requirements/v1",
    "idempotency": "veritas.live-adapter-bind-authorization.idempotency/v1",
    "bind_context": "veritas.live-adapter-bind-authorization.bind-context/v1",
    "credential_grant": "veritas.live-adapter-bind-authorization.credential-grant/v1",
    "header_grant": "veritas.live-adapter-bind-authorization.header-grant/v1",
    "runtime": "veritas.live-adapter-bind-authorization.runtime-authority/v1",
    "artifact": "veritas.live-adapter-bind-authorization.artifact/v1",
}


class LiveAdapterBindAuthorizationError(ValueError):
    """Stable fail-closed error raised for invalid authorization evidence."""


@dataclass(frozen=True)
class BindAuthorizationSignatureVerificationResult:
    """Verifier-derived signature identity for authorizer or authorization issuer."""

    verified: bool
    key_id: str | None = None
    algorithm: str | None = None
    signer_identity: str | None = None
    signer_role: str | None = None
    reason: str | None = None
    verifier_trust_level: str | None = None
    verifier_id: str | None = None
    verifier_key_id: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = None


class BindAuthorizationSignatureVerifier(Protocol):
    """Deployment-controlled signature verifier; artifact keys are never trust roots."""

    def verify(
        self, artifact: dict[str, Any]
    ) -> BindAuthorizationSignatureVerificationResult:
        ...


class BindAuthorizationSigner(Protocol):
    """Injected signer used only to sign the final non-effecting authorization."""

    key_id: str
    algorithm: str
    identity: str
    role: str

    def sign(self, payload: bytes) -> bytes:
        ...


@dataclass(frozen=True)
class BindAuthorizationSignerPolicy:
    """Allowlist for an authorizer or final authorization issuer."""

    policy_id: str
    purpose: SignaturePurpose
    allowed_key_ids: list[str]
    allowed_algorithms: list[str]
    allowed_identities: list[str]
    allowed_roles: list[str]

    def deterministic_hash(self) -> str:
        return sha256_of_canonical_json(
            {
                "policy_id": self.policy_id,
                "purpose": self.purpose,
                "allowed_key_ids": sorted(self.allowed_key_ids),
                "allowed_algorithms": sorted(self.allowed_algorithms),
                "allowed_identities": sorted(self.allowed_identities),
                "allowed_roles": sorted(self.allowed_roles),
            }
        )


@dataclass(frozen=True)
class ApprovedBindAuthorizationVerifier:
    """Deployment-owned verifier policy entry."""

    verifier_id: str
    trust_level: str
    purpose: SignaturePurpose
    verifier_key_id: str
    verifier_policy_id: str
    verifier_policy_hash: str
    signer_policy_id: str
    signer_policy_hash: str


@dataclass(frozen=True)
class BindAuthorizationVerifierPolicy:
    """Deployment-controlled accepted verifier provenance."""

    approved_verifiers: list[ApprovedBindAuthorizationVerifier]

    def approved_by_id(
        self, verifier_id: str
    ) -> ApprovedBindAuthorizationVerifier | None:
        return next(
            (item for item in self.approved_verifiers if item.verifier_id == verifier_id),
            None,
        )


@dataclass(frozen=True)
class RealBindAuthorizationGovernanceInputs:
    """Original artifacts and independent deployment trust inputs.

    For v0.3, expected_source must be acquired independently of the candidate
    gate, and action_contract must come from trusted policy configuration.
    These anchors are not reconstructed from embedded artifact snapshots.
    """

    action_contract: ActionClassContract
    signed_authority_evidence_artifact: dict[str, Any]
    authority_signature_verifier: AuthorityEvidenceSignatureVerifier
    authority_signer_policy: AuthorityEvidenceSignerPolicy
    authority_verifier_policy: AuthorityEvidenceVerifierPolicy
    authority_revocation_checker: AuthorityRevocationChecker
    authority_revocation_policy: AuthorityRevocationPolicy
    verification_now: datetime
    signed_human_approval_artifact: dict[str, Any] | None = None
    human_approval_signature_verifier: HumanApprovalSignatureVerifier | None = None
    human_approval_signer_policy: HumanApprovalSignerPolicy | None = None
    human_approval_verifier_policy: HumanApprovalVerifierPolicy | None = None
    # Independent source anchor for v0.3; never extract from the candidate gate.
    # action_contract above is the corresponding trusted policy anchor.
    expected_source: Any = None


@dataclass(frozen=True)
class BindAuthorizationTrustInputs:
    """Trust roots for the authorizer decision and final authorization signature."""

    authorizer_signature_verifier: BindAuthorizationSignatureVerifier
    authorizer_signer_policy: BindAuthorizationSignerPolicy
    authorizer_verifier_policy: BindAuthorizationVerifierPolicy
    authorization_issuer_signature_verifier: BindAuthorizationSignatureVerifier
    authorization_issuer_signer_policy: BindAuthorizationSignerPolicy
    authorization_issuer_verifier_policy: BindAuthorizationVerifierPolicy


@dataclass(frozen=True)
class _GovernanceOutcome:
    authority_proof: VerifiedAuthorityEvidence
    human_approval_proof: VerifiedHumanApprovalReceipt | None
    human_approval_status: Literal["VERIFIED", "NOT_REQUIRED"]
    runtime_result: RuntimeAuthorityValidationResult
    runtime_result_digest: str
    action_contract_id: str
    action_contract_digest: str
    requested_scope: tuple[str, ...]
    actor_identity: str
    policy_snapshot_id: str
    request_ref: str
    bind_context_hash: str
