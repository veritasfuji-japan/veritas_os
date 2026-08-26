"""Real governance re-verification for Bind Authorization v1."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import (
    validate_verified_authority_evidence, verify_authority_evidence_artifact_to_proof,
)
from veritas_os.governance.human_approval_receipt import (
    VerifiedHumanApprovalReceipt, validate_human_approval_context_binding,
    verify_human_approval_receipt_artifact_to_proof,
)
from veritas_os.governance.runtime_authority import (
    RuntimeAuthorityValidationResult, RuntimeAuthorityValidator,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    DOMAINS, RealBindAuthorizationGovernanceInputs, _GovernanceOutcome,
    LiveAdapterBindAuthorizationError,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _digest
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    AUTHORIZATION_REQUIREMENTS, CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    LiveAdapterDryRunBindAuthorizationGateReviewError,
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.policy.real_bind_context import (
    derive_verified_real_bind_context_hash,
)


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    try:
        return verify_live_adapter_dry_run_bind_authorization_gate_review_packet(value)
    except (
        LiveAdapterDryRunBindAuthorizationGateReviewError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_INVALID") from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> None:
    accepted = (
        source.bind_authorization_gate_review_result
        .accepted_for_future_real_bind_authorization_artifact
    )
    invalid = (
        source.gate_review_state
        != "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
        or source.fail_closed
        or not accepted
        or source.request_dispatch_state != "NOT_DISPATCHED"
        or source.request_dispatched
        or source.bind_state != "NOT_BOUND"
        or source.bind_invoked
        or source.bind_authorization_state != "NOT_AUTHORIZED"
        or source.bind_authorization_created
        or source.execution_authority_created
        or source.bind_receipt_created
        or source.trustlog_written
        or source.network_used
        or source.webhook_called
        or source.live_adapter_instantiated
    )
    if invalid:
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_NOT_AUTHORIZABLE")
    requirements = source.future_real_bind_authorization_artifact_requirements
    if tuple(item.name for item in requirements) != AUTHORIZATION_REQUIREMENTS:
        raise LiveAdapterBindAuthorizationError("LABA_REQUIREMENTS_MISMATCH")


def _source_context(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> tuple[str, str, str, tuple[str, ...], str]:
    intent = source.execution_intent
    actor = str(intent.get("actor_identity") or "").strip()
    policy_snapshot_id = str(intent.get("policy_snapshot_id") or "").strip()
    request_ref = str(intent.get("request_id") or "").strip()
    intended_action = str(intent.get("intended_action") or "").strip()
    scope_raw = source.authority_evidence_reference_bundle.get("bundle_scope")
    if (
        not actor
        or not policy_snapshot_id
        or not request_ref
        or not intended_action
        or not isinstance(scope_raw, list)
    ):
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_CONTEXT_INVALID")
    requested_scope = tuple(
        str(item).strip() for item in scope_raw if str(item).strip()
    )
    if not requested_scope or len(set(requested_scope)) != len(requested_scope):
        raise LiveAdapterBindAuthorizationError("LABA_SOURCE_SCOPE_INVALID")
    return actor, policy_snapshot_id, request_ref, requested_scope, intended_action


def _requires_human_approval(contract: ActionClassContract) -> bool:
    rules = contract.human_approval_rules
    minimum_approvals = int(rules.get("minimum_approvals", 0) or 0)
    if bool(rules.get("required", False)):
        return True
    return (
        contract.irreversibility.get("level") == "high"
        and minimum_approvals > 0
    )


def _runtime_result_payload(
    result: RuntimeAuthorityValidationResult,
) -> dict[str, Any]:
    payload = asdict(result)
    predicate_times = {
        item.evaluated_at
        for predicates in (
            result.passed_predicates,
            result.failed_predicates,
            result.stale_predicates,
            result.missing_predicates,
            result.indeterminate_predicates,
        )
        for item in predicates
        if item.evaluated_at
    }
    # RuntimeAuthorityValidator currently creates the aggregate result timestamp
    # separately from the predicate evaluation timestamp.  Bind Authorization
    # evidence must be reproducible when the same explicit verification instant
    # is replayed, so canonicalize the redundant aggregate field to the single
    # verifier-derived predicate instant while still hashing every predicate and
    # its timestamp.  Ambiguous/mixed predicate times remain unmodified.
    if len(predicate_times) == 1:
        payload["evaluated_at"] = next(iter(predicate_times))
    return payload


def _runtime_result_digest(result: RuntimeAuthorityValidationResult) -> str:
    return _digest(DOMAINS["runtime"], _runtime_result_payload(result))


def _authority_reference(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> dict[str, Any]:
    references = source.authority_evidence_reference_bundle.get(
        "authority_evidence_references"
    )
    if not isinstance(references, list) or len(references) != 1:
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_CARDINALITY_UNSUPPORTED"
        )
    reference = references[0]
    if not isinstance(reference, dict):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORITY_REFERENCE_INVALID")
    return reference


def _human_reference(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> dict[str, Any]:
    references = source.human_approval_reference_bundle.get(
        "human_approval_references"
    )
    if not isinstance(references, list) or len(references) != 1:
        raise LiveAdapterBindAuthorizationError(
            "LABA_HUMAN_APPROVAL_REFERENCE_CARDINALITY_UNSUPPORTED"
        )
    reference = references[0]
    if not isinstance(reference, dict):
        raise LiveAdapterBindAuthorizationError(
            "LABA_HUMAN_APPROVAL_REFERENCE_INVALID"
        )
    return reference


def _validate_real_governance_inputs(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    inputs: RealBindAuthorizationGovernanceInputs,
) -> _GovernanceOutcome:
    if not isinstance(inputs, RealBindAuthorizationGovernanceInputs):
        raise LiveAdapterBindAuthorizationError("LABA_GOVERNANCE_INPUTS_REQUIRED")
    now = inputs.verification_now
    if now.tzinfo is None or now.utcoffset() is None:
        raise LiveAdapterBindAuthorizationError("LABA_VERIFICATION_NOW_NAIVE")

    actor, policy_snapshot_id, request_ref, requested_scope, intended_action = (
        _source_context(source)
    )
    contract = inputs.action_contract
    if contract.id != intended_action:
        raise LiveAdapterBindAuthorizationError(
            "LABA_ACTION_CONTRACT_SOURCE_MISMATCH"
        )
    if any(scope not in contract.allowed_scope for scope in requested_scope):
        raise LiveAdapterBindAuthorizationError(
            "LABA_ACTION_CONTRACT_SCOPE_MISMATCH"
        )
    if contract.required_evidence:
        raise LiveAdapterBindAuthorizationError(
            "LABA_REQUIRED_EVIDENCE_PROOF_UNAVAILABLE"
        )

    try:
        authority_proof = verify_authority_evidence_artifact_to_proof(
            inputs.signed_authority_evidence_artifact,
            action_contract=contract,
            actor_identity=actor,
            requested_scope=list(requested_scope),
            policy_snapshot_id=policy_snapshot_id,
            signature_verifier=inputs.authority_signature_verifier,
            signer_policy=inputs.authority_signer_policy,
            verifier_policy=inputs.authority_verifier_policy,
            revocation_checker=inputs.authority_revocation_checker,
            revocation_policy=inputs.authority_revocation_policy,
            now=now,
        )
        authority_validation = validate_verified_authority_evidence(
            authority_proof,
            action_contract=contract,
            actor_identity=actor,
            requested_scope=list(requested_scope),
            policy_snapshot_id=policy_snapshot_id,
            verifier_policy=inputs.authority_verifier_policy,
            revocation_policy=inputs.authority_revocation_policy,
            now=now,
            require_production_verifier=True,
        )
    except (TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError(
            f"LABA_AUTHORITY_VERIFICATION_FAILED:{exc}"
        ) from exc
    if not authority_validation.is_valid:
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_VERIFICATION_FAILED:"
            + authority_validation.failure_reasons[0]
        )

    authority_ref = _authority_reference(source)
    evidence = authority_proof.authority_evidence
    if evidence.authority_evidence_id != str(
        authority_ref.get("authority_evidence_reference_id") or ""
    ):
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_ID_MISMATCH"
        )
    if evidence.actor_identity != str(authority_ref.get("authority_subject") or ""):
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_SUBJECT_MISMATCH"
        )
    if authority_proof.issuer_identity != str(
        authority_ref.get("authority_issuer") or ""
    ):
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_ISSUER_MISMATCH"
        )
    if str(authority_ref.get("authority_scope") or "") not in requested_scope:
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_SCOPE_MISMATCH"
        )
    declared_source_ids = {
        str(authority_ref.get("authority_source_id") or ""),
        str(authority_ref.get("authority_policy_id") or ""),
    }
    if not declared_source_ids.intersection(set(evidence.authority_source_refs)):
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORITY_REFERENCE_SOURCE_MISMATCH"
        )

    bind_context_hash = derive_verified_real_bind_context_hash(source)
    human_proof: VerifiedHumanApprovalReceipt | None = None
    human_status: Literal["VERIFIED", "NOT_REQUIRED"] = "NOT_REQUIRED"
    needs_human = _requires_human_approval(contract)
    if needs_human:
        if (
            inputs.signed_human_approval_artifact is None
            or inputs.human_approval_signature_verifier is None
            or inputs.human_approval_signer_policy is None
            or inputs.human_approval_verifier_policy is None
        ):
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_REQUIRED"
            )
        try:
            human_proof = verify_human_approval_receipt_artifact_to_proof(
                inputs.signed_human_approval_artifact,
                inputs.human_approval_signature_verifier.verify,
                requested_scope=list(requested_scope),
                action_class=contract.action_class,
                policy_snapshot_id=policy_snapshot_id,
                now=now,
                signer_policy=inputs.human_approval_signer_policy,
                verifier_policy=inputs.human_approval_verifier_policy,
                require_structured_signature_result=True,
                require_production_verifier=True,
            )
        except (TypeError, ValueError) as exc:
            raise LiveAdapterBindAuthorizationError(
                f"LABA_HUMAN_APPROVAL_VERIFICATION_FAILED:{exc}"
            ) from exc

        context_validation = validate_human_approval_context_binding(
            human_proof.receipt,
            request_ref=request_ref,
            ai_output_ref=None,
            execution_intent_id=source.execution_intent_id,
            decision_id=str(source.execution_intent.get("decision_id") or ""),
            action_class=contract.action_class,
            policy_snapshot_id=policy_snapshot_id,
            authority_evidence_id=evidence.authority_evidence_id,
            bind_context_hash=bind_context_hash,
        )
        if not context_validation.is_valid:
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_CONTEXT_MISMATCH:"
                + context_validation.failure_reasons[0]
            )
        human_ref = _human_reference(source)
        if human_proof.receipt.approval_receipt_id != str(
            human_ref.get("human_approval_reference_id") or ""
        ):
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_REFERENCE_ID_MISMATCH"
            )
        if human_proof.receipt.approver_identity != str(
            human_ref.get("approver_id") or ""
        ):
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_REFERENCE_IDENTITY_MISMATCH"
            )
        if human_proof.receipt.approver_role != str(
            human_ref.get("approver_role") or ""
        ):
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_REFERENCE_ROLE_MISMATCH"
            )
        if str(human_ref.get("approval_scope") or "") not in requested_scope:
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_REFERENCE_SCOPE_MISMATCH"
            )
        human_status = "VERIFIED"
    elif inputs.signed_human_approval_artifact is not None:
        raise LiveAdapterBindAuthorizationError(
            "LABA_HUMAN_APPROVAL_UNEXPECTED_FOR_CONTRACT"
        )

    runtime_result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=None,
        verified_authority_evidence=authority_proof,
        authority_verifier_policy=inputs.authority_verifier_policy,
        authority_revocation_policy=inputs.authority_revocation_policy,
        requested_scope=list(requested_scope),
        required_evidence_metadata={},
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor,
        verified_human_approval=human_proof,
        human_approval_verifier_policy=inputs.human_approval_verifier_policy,
        request_ref=request_ref,
        ai_output_ref=None,
        execution_intent_id=source.execution_intent_id,
        bind_context_hash=bind_context_hash,
        bind_context_metadata={
            "source_gate_review_hash": (
                source.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
            "execution_intent_hash": source.execution_intent_hash,
            "adapter_contract_hash": source.adapter_contract_hash,
            "endpoint_identity_binding_digest": (
                source.endpoint_identity_binding_digest
            ),
            "credential_scope_binding_digest": (
                source.credential_scope_binding_digest
            ),
        },
        now=now,
    )
    if (
        runtime_result.status != "pass"
        or runtime_result.recommended_outcome != "commit"
    ):
        raise LiveAdapterBindAuthorizationError(
            "LABA_RUNTIME_AUTHORITY_NOT_COMMIT:"
            + runtime_result.status
            + ":"
            + runtime_result.recommended_outcome
        )

    return _GovernanceOutcome(
        authority_proof=authority_proof,
        human_approval_proof=human_proof,
        human_approval_status=human_status,
        runtime_result=runtime_result,
        runtime_result_digest=_runtime_result_digest(runtime_result),
        action_contract_id=contract.id,
        action_contract_digest=contract.deterministic_digest(),
        requested_scope=requested_scope,
        actor_identity=actor,
        policy_snapshot_id=policy_snapshot_id,
        request_ref=request_ref,
        bind_context_hash=bind_context_hash,
    )
