"""Closed Pydantic models for authenticated Real Bind Authorization v1."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    AUTHORIZATION_ARTIFACT_TYPE, AUTHORIZATION_ARTIFACT_VERSION,
    AUTHORIZER_ARTIFACT_TYPE, AUTHORIZER_ARTIFACT_VERSION, FORMAT_VERSION,
    HASH_PATTERN, ID_PATTERN, MECHANISM, STATUS, SignaturePurpose,
)

class SignatureSignerDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key_id: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    role: str = Field(min_length=1)


class BindAuthorizationDecision(BaseModel):
    """Exact signed GO decision for one reviewed future Bind context."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_gate_review_id: str = Field(min_length=1)
    source_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_id: str = Field(min_length=1)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(min_length=1)
    credential_reference_digest: str = Field(min_length=1)
    credential_scope_binding_digest: str = Field(min_length=1)
    policy_snapshot_id: str = Field(min_length=1)
    valid_from: str
    valid_until: str
    authorizer_id: str = Field(min_length=1)
    authorizer_role: str = Field(min_length=1)
    authorizer_attestation: str = Field(min_length=1)
    authorized_at: str
    authorization_reason: str = Field(min_length=1)
    explicit_go_no_go_confirmation: Literal["GO_AUTHORIZED"]
    acknowledged_exact_source_context_only: Literal[True]
    acknowledged_authorization_does_not_invoke_bind: Literal[True]
    acknowledged_authorization_does_not_dispatch_request: Literal[True]
    acknowledged_authorization_does_not_access_credentials: Literal[True]
    acknowledged_authorization_does_not_construct_authorization_header: Literal[True]
    acknowledged_authorization_does_not_create_bind_receipt: Literal[True]
    acknowledged_authorization_does_not_write_trustlog: Literal[True]
    acknowledged_semantic_match_is_not_authority: Literal[True]


class SignedBindAuthorizationDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_type: Literal[AUTHORIZER_ARTIFACT_TYPE]
    artifact_version: Literal[AUTHORIZER_ARTIFACT_VERSION]
    decision: BindAuthorizationDecision
    decision_hash: str = Field(pattern=HASH_PATTERN)
    signer: SignatureSignerDescriptor
    signed_at: str
    signature: str = Field(min_length=16)


class VerifiedSignatureBinding(BaseModel):
    """Verifier-derived signer identity stored as evidence, not caller authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    purpose: SignaturePurpose
    key_id: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    signer_identity: str = Field(min_length=1)
    signer_role: str = Field(min_length=1)
    signer_policy_id: str = Field(min_length=1)
    signer_policy_hash: str = Field(pattern=HASH_PATTERN)
    verifier_id: str = Field(min_length=1)
    verifier_trust_level: Literal["production"]
    verifier_key_id: str = Field(min_length=1)
    verifier_policy_id: str = Field(min_length=1)
    verifier_policy_hash: str = Field(pattern=HASH_PATTERN)
    verified_at: str


class AuthorizationRequirementProof(BaseModel):
    """Builder-derived proof of one exact #2130 authorization requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=11)
    requirement: str = Field(min_length=1)
    status: Literal["VERIFIED", "NOT_REQUIRED"]
    evidence_type: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=HASH_PATTERN)
    verified_at: str
    reason_code: str = Field(min_length=1)


class CredentialResolutionGrant(BaseModel):
    """Permission to resolve one exact credential reference only after consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    grant_version: Literal["credential-resolution-grant/v1"]
    allowed: Literal[True]
    credential_reference_digest: str = Field(min_length=1)
    credential_scope_binding_digest: str = Field(min_length=1)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(min_length=1)
    policy_snapshot_id: str = Field(min_length=1)
    source_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    consumption_required: Literal[True]


class AuthorizationHeaderConstructionGrant(BaseModel):
    """Permission to construct auth material later, after authorization consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    grant_version: Literal["authorization-header-construction-grant/v1"]
    allowed: Literal[True]
    credential_reference_digest: str = Field(min_length=1)
    credential_scope_binding_digest: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(min_length=1)
    policy_snapshot_id: str = Field(min_length=1)
    source_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    consumption_required: Literal[True]


class CanonicalLiveAdapterBindAuthorizationArtifact(BaseModel):
    """Signed permission for one exact future Bind attempt; no execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    artifact_type: Literal[AUTHORIZATION_ARTIFACT_TYPE]
    artifact_version: Literal[AUTHORIZATION_ARTIFACT_VERSION]
    live_adapter_bind_authorization_id: str = Field(pattern=ID_PATTERN)
    live_adapter_bind_authorization_hash: str = Field(pattern=HASH_PATTERN)
    authorization_mechanism: Literal[MECHANISM]
    source_gate_review_id: str
    source_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    source_gate_review_packet: dict[str, Any]
    source_final_bind_authorization_readiness_hash: str
    source_human_approval_linkage_review_hash: str
    source_authority_evidence_linkage_review_hash: str
    source_bind_pre_dispatch_review_hash: str
    source_operator_dispatch_review_hash: str
    source_credential_authorization_hash: str
    source_endpoint_allowlist_evaluation_hash: str
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_hash: str
    request_descriptor: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_version: str
    endpoint_candidate: dict[str, Any]
    endpoint_candidate_digest: str
    endpoint_identity_binding: dict[str, Any]
    endpoint_identity_binding_digest: str
    credential_reference: dict[str, Any]
    credential_reference_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_linkage_result: dict[str, Any]
    authority_evidence_linkage_result_digest: str
    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str
    human_approval_linkage_result: dict[str, Any]
    human_approval_linkage_result_digest: str
    final_bind_authorization_readiness_result: dict[str, Any]
    final_bind_authorization_readiness_result_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    signed_authority_evidence_artifact: dict[str, Any]
    signed_authority_evidence_artifact_digest: str = Field(pattern=HASH_PATTERN)
    authority_verification_proof_digest: str = Field(pattern=HASH_PATTERN)
    human_approval_requirement_status: Literal["VERIFIED", "NOT_REQUIRED"]
    signed_human_approval_artifact: dict[str, Any] | None
    signed_human_approval_artifact_digest: str | None
    human_approval_verification_proof_digest: str | None
    runtime_authority_status: Literal["pass"]
    runtime_authority_recommended_outcome: Literal["commit"]
    runtime_authority_result_digest: str = Field(pattern=HASH_PATTERN)
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    authorization_decision_artifact: SignedBindAuthorizationDecisionArtifact
    authorization_decision: BindAuthorizationDecision
    authorization_decision_digest: str = Field(pattern=HASH_PATTERN)
    authorizer_verification: VerifiedSignatureBinding
    credential_resolution_grant: CredentialResolutionGrant
    credential_resolution_grant_digest: str = Field(pattern=HASH_PATTERN)
    authorization_header_construction_grant: AuthorizationHeaderConstructionGrant
    authorization_header_construction_grant_digest: str = Field(pattern=HASH_PATTERN)
    authorization_requirement_proofs: tuple[AuthorizationRequirementProof, ...]
    authorization_requirement_proofs_digest: str = Field(pattern=HASH_PATTERN)
    authorized_at: str
    valid_from: str
    valid_until: str
    idempotency_key: str = Field(pattern=r"^laba-idem:v1:sha256:[0-9a-f]{64}$")
    single_use: Literal[True]
    authorization_consumption_required: Literal[True]
    replay_protection_required: Literal[True]
    duplicate_dispatch_prohibited: Literal[True]
    bind_authorization_status: Literal[STATUS]
    bind_authorization_state: Literal["AUTHORIZED"]
    bind_authorization_created: Literal[True]
    execution_authority_created: Literal[False]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    bind_invocation_state: Literal["NOT_INVOKED"]
    authorization_consumption_state: Literal["NOT_CONSUMED"]
    execution_state: Literal["NOT_EXECUTED"]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    request_dispatched: Literal[False]
    endpoint_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    network_used: Literal[False]
    dns_used: Literal[False]
    webhook_called: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_called: Literal[False]
    external_effect_used: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_used: Literal[False]
    subprocess_used: Literal[False]
    operation_committed: Literal[False]
    authorization_issuer_signer: SignatureSignerDescriptor
    authorization_issuer_verification: VerifiedSignatureBinding
    authorization_signed_at: str
    authorization_signature: str = Field(min_length=16)
