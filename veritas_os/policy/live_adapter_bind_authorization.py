"""Authenticated Real Bind Authorization v1 public API.

The public boundary ends at a signed, verified, unconsumed authorization.
Credential access, request dispatch, Bind invocation, receipts and TrustLog
writes remain forbidden here.
"""

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    ACKNOWLEDGEMENTS,
    AUTHORIZATION_ARTIFACT_TYPE,
    AUTHORIZATION_ARTIFACT_VERSION,
    AUTHORIZER_ARTIFACT_TYPE,
    AUTHORIZER_ARTIFACT_VERSION,
    EFFECT_FIELDS,
    ApprovedBindAuthorizationVerifier,
    BindAuthorizationSignatureVerificationResult,
    BindAuthorizationSignatureVerifier,
    BindAuthorizationSigner,
    BindAuthorizationSignerPolicy,
    BindAuthorizationTrustInputs,
    BindAuthorizationVerifierPolicy,
    LiveAdapterBindAuthorizationError,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    AuthorizationHeaderConstructionGrant,
    AuthorizationRequirementProof,
    BindAuthorizationDecision,
    CanonicalLiveAdapterBindAuthorizationArtifact,
    CredentialResolutionGrant,
    SignatureSignerDescriptor,
    SignedBindAuthorizationDecisionArtifact,
    VerifiedSignatureBinding,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _artifact_hash,
    _digest,
    _json,
    _timestamp,
    bind_authorization_artifact_signature_payload,
    bind_authorizer_decision_signature_payload,
)
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _bind_context_hash,
    _source,
    _validate_real_governance_inputs,
    _validate_source,
)
from veritas_os.policy.live_adapter_bind_authorization_checks import _decision_hash
from veritas_os.policy.live_adapter_bind_authorization_issuance import (
    build_live_adapter_bind_authorization_artifact,
)
from veritas_os.policy.live_adapter_bind_authorization_verification import (
    validate_live_adapter_bind_authorization_temporal_validity,
    verify_live_adapter_bind_authorization_artifact,
)

__all__ = [
    "ACKNOWLEDGEMENTS",
    "AUTHORIZATION_ARTIFACT_TYPE",
    "AUTHORIZATION_ARTIFACT_VERSION",
    "AUTHORIZER_ARTIFACT_TYPE",
    "AUTHORIZER_ARTIFACT_VERSION",
    "EFFECT_FIELDS",
    "ApprovedBindAuthorizationVerifier",
    "AuthorizationHeaderConstructionGrant",
    "AuthorizationRequirementProof",
    "BindAuthorizationDecision",
    "BindAuthorizationSignatureVerificationResult",
    "BindAuthorizationSignatureVerifier",
    "BindAuthorizationSigner",
    "BindAuthorizationSignerPolicy",
    "BindAuthorizationTrustInputs",
    "BindAuthorizationVerifierPolicy",
    "CanonicalLiveAdapterBindAuthorizationArtifact",
    "CredentialResolutionGrant",
    "LiveAdapterBindAuthorizationError",
    "RealBindAuthorizationGovernanceInputs",
    "SignatureSignerDescriptor",
    "SignedBindAuthorizationDecisionArtifact",
    "VerifiedSignatureBinding",
    "build_live_adapter_bind_authorization_artifact",
    "verify_live_adapter_bind_authorization_artifact",
    "validate_live_adapter_bind_authorization_temporal_validity",
    "bind_authorizer_decision_signature_payload",
    "bind_authorization_artifact_signature_payload",
    "_artifact_hash",
    "_bind_context_hash",
    "_decision_hash",
    "_digest",
    "_json",
    "_source",
    "_timestamp",
    "_validate_real_governance_inputs",
    "_validate_source",
]
