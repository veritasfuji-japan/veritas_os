"""Native v2 authorization issuance, never consumption or execution.

Reconstruct the requirement-aware chain using deployment-owned anchors, then
reuse the existing authority, human receipt, authorizer and grant primitives.
No native artifact is relabelled as a legacy handoff. The private context is
only a non-serializable projection for existing cryptographic checks.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationSigner,
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
    LiveAdapterBindAuthorizationError,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    SignedBindAuthorizationDecisionArtifact,
    VerifiedSignatureBinding,
    SignatureSignerDescriptor,
    CredentialResolutionGrant,
    AuthorizationHeaderConstructionGrant,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _json,
    _digest,
    _timestamp,
    native_bind_authorization_signature_payload,
)
from veritas_os.policy.live_adapter_bind_authorization_checks import (
    _verify_signed_decision,
    _window,
    _grants,
    _idempotency_key,
    _decision_hash,
    _signature_binding,
)
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _validate_governance_for_verified_context,
)
from veritas_os.policy.live_adapter_bind_authorization_requirements import (
    _approved_issuer_binding,
)
from veritas_os.policy.promotion_requirement_runtime_risk import (
    _require_runtime_risk_pass_and_source,
)

DOMAIN = "veritas.native-live-adapter-bind-authorization/v2"


def _supported_approval_rules(rules: dict[str, Any]) -> None:
    """Never claim one receipt satisfies quorum or unimplemented policy rules."""
    minimum = rules.get("minimum_approvals", 0)
    if (
        set(rules) - {"required", "minimum_approvals"}
        or type(rules.get("required", False)) is not bool
        or type(minimum) is not int
        or minimum not in (0, 1)
    ):
        raise LiveAdapterBindAuthorizationError("NABA_UNSUPPORTED_HUMAN_RULES")


@dataclass(frozen=True)
class NativeAuthorizationSourceInputs:
    """Independent deployment inputs, never populated from candidate snapshots.

    Source and contract live in governance_inputs; verification_now is its
    trusted current clock. No candidate-supplied defaults are permitted.
    """

    final_recheck: Any
    expected_risk_decision: Any
    expected_recorded_at: datetime
    expected_verified_at: datetime
    expected_rechecked_at: datetime
    current_endpoint: Any
    current_credential_reference: Any
    required_credential_scope: str


@dataclass(frozen=True)
class _VerifiedContext:
    """Internal projection; attribute aliases reuse v1 checks, not its schema."""

    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_id: str
    adapter_contract_hash: str
    endpoint_identity_binding_digest: str
    credential_reference_digest: str
    credential_scope_binding_digest: str
    authority_evidence_reference_bundle: dict[str, Any]
    human_approval_reference_bundle: dict[str, Any]
    live_adapter_dry_run_bind_authorization_gate_review_id: str
    live_adapter_dry_run_bind_authorization_gate_review_hash: str
    bind_authorization_gate_review_decision: Any


class NativeBindAuthorizationArtifact(BaseModel):
    """Signed, unconsumed native permission; rejected by the v1 consumer."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["native-live-adapter-bind-authorization/v2"]
    artifact_type: Literal["live_adapter_bind_authorization"]
    artifact_version: Literal["v2"]
    authorization_id: str = Field(pattern=r"^laba:v2:sha256:[0-9a-f]{64}$")
    authorization_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_runtime_risk_packet: dict[str, Any]
    source_final_recheck_hash: str
    source_gate_hash: str
    bind_context_hash: str
    action_contract_digest: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    signed_authority_evidence_artifact: dict[str, Any]
    authority_verification_proof_digest: str
    signed_human_approval_artifact: dict[str, Any] | None
    human_approval_verification_proof_digest: str | None
    human_approval_requirement_status: Literal["VERIFIED", "NOT_REQUIRED"]
    runtime_authority_result_digest: str
    authorization_decision_artifact: SignedBindAuthorizationDecisionArtifact
    authorizer_verification: VerifiedSignatureBinding
    credential_resolution_grant: CredentialResolutionGrant
    authorization_header_construction_grant: AuthorizationHeaderConstructionGrant
    authorized_at: str
    valid_from: str
    valid_until: str
    idempotency_key: str = Field(pattern=r"^laba-idem:v2:sha256:[0-9a-f]{64}$")
    single_use: Literal[True]
    authorization_consumption_required: Literal[True]
    duplicate_dispatch_prohibited: Literal[True]
    duplicate_absence_verified: Literal[False]
    bind_time_runtime_risk_recheck_required: Literal[True]
    bind_authorization_created: Literal[True]
    authorization_consumption_state: Literal["NOT_CONSUMED"]
    execution_authority_created: Literal[False]
    human_approval_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    authorization_issuer_signer: SignatureSignerDescriptor
    authorization_issuer_verification: VerifiedSignatureBinding
    authorization_signed_at: str
    authorization_signature: str = Field(min_length=16)


def _verified_source(
    risk: Any,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
) -> tuple[Any, Any, _VerifiedContext]:
    """Rebuild every source before projecting fields for shared checks."""
    if not isinstance(source_inputs, NativeAuthorizationSourceInputs) or not isinstance(
        governance_inputs, RealBindAuthorizationGovernanceInputs
    ):
        raise LiveAdapterBindAuthorizationError("NABA_INDEPENDENT_INPUTS_REQUIRED")
    anchors = dict(
        expected_source=governance_inputs.expected_source,
        expected_contract=governance_inputs.action_contract,
        expected_verified_at=source_inputs.expected_verified_at,
        expected_rechecked_at=source_inputs.expected_rechecked_at,
        current_endpoint=source_inputs.current_endpoint,
        current_credential_reference=source_inputs.current_credential_reference,
        required_credential_scope=source_inputs.required_credential_scope,
    )
    verified_risk, final = _require_runtime_risk_pass_and_source(
        risk,
        source_inputs.final_recheck,
        expected_risk_decision=source_inputs.expected_risk_decision,
        expected_recorded_at=source_inputs.expected_recorded_at,
        verification_now=governance_inputs.verification_now,
        **anchors,
    )
    # Traverse only the freshly reconstructed chain, not the input objects.
    gate = final.source_packet["source_packet"]
    satisfaction = gate["source_packet"]["source_packet"]
    authority = satisfaction["source_authority_evidence_linkage_review_packet"]
    linkage = satisfaction["required_human_approval_linkage_packet"]
    from veritas_os.policy.promotion_requirement_bind_readiness import (
        RequirementBindReviewDecision,
    )

    context = final.exact_bind_context
    projected = _VerifiedContext(
        execution_intent=final.execution_intent,
        execution_intent_id=context.execution_intent_id,
        execution_intent_hash=context.execution_intent_hash,
        adapter_contract_id=context.adapter_contract_id,
        adapter_contract_hash=context.adapter_contract_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        authority_evidence_reference_bundle=authority[
            "authority_evidence_reference_bundle"
        ],
        human_approval_reference_bundle=(
            linkage["human_approval_reference_bundle"] if linkage is not None else {}
        ),
        live_adapter_dry_run_bind_authorization_gate_review_id=gate["packet_id"],
        live_adapter_dry_run_bind_authorization_gate_review_hash=gate["packet_hash"],
        bind_authorization_gate_review_decision=RequirementBindReviewDecision.model_validate(
            gate["review_decision"]
        ),
    )
    return verified_risk, final, projected


def _unsigned(
    risk: Any,
    signed_decision: Any,
    valid_from: Any,
    valid_until: Any,
    *,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    issuer_signer: SignatureSignerDescriptor,
    issuer_binding: VerifiedSignatureBinding,
) -> dict[str, Any]:
    risk, final, source = _verified_source(risk, source_inputs, governance_inputs)
    _supported_approval_rules(governance_inputs.action_contract.human_approval_rules)
    governance = _validate_governance_for_verified_context(
        source,
        governance_inputs,
        bind_context_hash=final.bind_context_hash,
    )
    if (governance.human_approval_status == "VERIFIED") != risk.required_human_approval:
        raise LiveAdapterBindAuthorizationError("NABA_APPROVAL_REQUIREMENT_MISMATCH")
    start, end = _timestamp(valid_from), _timestamp(valid_until)
    decision, authorizer = _verify_signed_decision(
        signed_decision,
        source=source,
        trust=trust_inputs,
        now=governance_inputs.verification_now,
        expected_valid_from=start,
        expected_valid_until=end,
    )
    authorized_at, start, end = _window(
        source, governance, decision.decision, start, end
    )
    now = _timestamp(governance_inputs.verification_now)
    dt = datetime.fromisoformat
    if not (
        dt(risk.recorded_at)
        <= dt(start)
        <= dt(now)
        < dt(end)
        <= dt(risk.risk_decision.valid_until)
    ):
        raise LiveAdapterBindAuthorizationError("NABA_VALIDITY_OUTSIDE_CURRENT_RISK")
    if risk.risk_decision.reviewer_id.strip() == authorizer.signer_identity.strip():
        raise LiveAdapterBindAuthorizationError("NABA_RISK_REVIEWER_AUTHORIZER_OVERLAP")
    credential, header = _grants(
        source, governance.policy_snapshot_id, final.bind_context_hash
    )
    base_key = _idempotency_key(
        source,
        _decision_hash(decision.decision),
        start,
        end,
        governance.policy_snapshot_id,
        final.bind_context_hash,
    )
    raw = dict(
        format_version="native-live-adapter-bind-authorization/v2",
        artifact_type="live_adapter_bind_authorization",
        artifact_version="v2",
        source_runtime_risk_packet=_json(risk),
        source_final_recheck_hash=final.packet_hash,
        source_gate_hash=final.exact_bind_context.gate_packet_hash,
        bind_context_hash=final.bind_context_hash,
        action_contract_digest=governance.action_contract_digest,
        execution_intent=source.execution_intent,
        execution_intent_id=source.execution_intent_id,
        execution_intent_hash=source.execution_intent_hash,
        signed_authority_evidence_artifact=_json(
            governance_inputs.signed_authority_evidence_artifact
        ),
        authority_verification_proof_digest=governance.authority_proof.verification_proof_hash,
        signed_human_approval_artifact=_json(
            governance_inputs.signed_human_approval_artifact
        ),
        human_approval_verification_proof_digest=(
            governance.human_approval_proof.verification_proof_hash
            if governance.human_approval_proof
            else None
        ),
        human_approval_requirement_status=governance.human_approval_status,
        runtime_authority_result_digest=governance.runtime_result_digest,
        authorization_decision_artifact=_json(decision),
        authorizer_verification=_json(authorizer),
        credential_resolution_grant=_json(credential),
        authorization_header_construction_grant=_json(header),
        authorized_at=authorized_at,
        valid_from=start,
        valid_until=end,
        idempotency_key="laba-idem:v2:sha256:"
        + _digest(
            DOMAIN + ".idempotency",
            {
                "base_key": base_key,
                "risk_hash": risk.packet_hash,
                "action_contract_digest": governance.action_contract_digest,
            },
        ),
        single_use=True,
        authorization_consumption_required=True,
        duplicate_dispatch_prohibited=True,
        duplicate_absence_verified=False,
        bind_time_runtime_risk_recheck_required=True,
        bind_authorization_created=True,
        authorization_consumption_state="NOT_CONSUMED",
        **{
            name: False
            for name in (
                "execution_authority_created",
                "human_approval_created",
                "bind_invoked",
                "bind_receipt_created",
                "credential_material_accessed",
                "authorization_header_constructed",
                "network_used",
                "external_effect_occurred",
            )
        },
        authorization_issuer_signer=_json(issuer_signer),
        authorization_issuer_verification=_json(issuer_binding),
        authorization_signed_at=now,
    )
    digest = _digest(DOMAIN, raw)
    return {
        **raw,
        "authorization_hash": digest,
        "authorization_id": "laba:v2:sha256:" + digest,
    }


def issue_native_bind_authorization(
    runtime_risk_packet: Any,
    signed_authorization_decision_artifact: Any,
    valid_from: datetime | str,
    valid_until: datetime | str,
    *,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    authorization_issuer_signer: BindAuthorizationSigner,
) -> NativeBindAuthorizationArtifact:
    """Issue and independently verify one native authorization, without effects.

    Requires original signed authority and, where required, human approval.
    Raises ValueError on any failed source, governance, time or signature check.
    Injected signer/verifiers must be deployment-controlled non-effecting backends.
    """
    signer = authorization_issuer_signer
    binding = _approved_issuer_binding(
        signer, trust_inputs, governance_inputs.verification_now
    )
    descriptor = SignatureSignerDescriptor(
        key_id=signer.key_id,
        algorithm=signer.algorithm,
        identity=signer.identity,
        role=signer.role,
    )
    raw = _unsigned(
        runtime_risk_packet,
        signed_authorization_decision_artifact,
        valid_from,
        valid_until,
        source_inputs=source_inputs,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
        issuer_signer=descriptor,
        issuer_binding=binding,
    )
    raw["authorization_signature"] = base64.urlsafe_b64encode(
        signer.sign(native_bind_authorization_signature_payload(raw).encode("utf-8"))
    ).decode("ascii")
    return verify_native_bind_authorization(
        raw,
        source_inputs=source_inputs,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )


def verify_native_bind_authorization(
    artifact: Any,
    *,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> NativeBindAuthorizationArtifact:
    """Reconstruct the entire signed artifact using external anchors and clock.

    This verifies issuance evidence at governance_inputs.verification_now, not
    permission to consume. The v2 consume-only API must independently recheck all
    governance and current runtime conditions before atomic consumption.
    """
    candidate = NativeBindAuthorizationArtifact.model_validate(_json(artifact))
    raw = candidate.model_dump(mode="json")
    result = trust_inputs.authorization_issuer_signature_verifier.verify(raw)
    binding = _signature_binding(
        purpose="authorization_issuer",
        result=result,
        signer_policy=trust_inputs.authorization_issuer_signer_policy,
        verifier_policy=trust_inputs.authorization_issuer_verifier_policy,
        verified_at=governance_inputs.verification_now,
    )
    descriptor = SignatureSignerDescriptor(
        key_id=binding.key_id,
        algorithm=binding.algorithm,
        identity=binding.signer_identity,
        role=binding.signer_role,
    )
    expected = _unsigned(
        candidate.source_runtime_risk_packet,
        candidate.authorization_decision_artifact,
        candidate.valid_from,
        candidate.valid_until,
        source_inputs=source_inputs,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
        issuer_signer=descriptor,
        issuer_binding=binding,
    )
    if {k: v for k, v in raw.items() if k != "authorization_signature"} != expected:
        raise LiveAdapterBindAuthorizationError("NABA_RECONSTRUCTION_MISMATCH")
    return NativeBindAuthorizationArtifact.model_validate(
        {
            **expected,
            "authorization_signature": candidate.authorization_signature,
        }
    )
