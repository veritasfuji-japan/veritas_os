#!/usr/bin/env python3
"""Deterministic local/offline SaaS permission-change governed execution demo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from veritas_os.governance import (
    ActionClassContract,
    CommitBoundaryEvaluator,
    HumanApprovalReceipt,
    RuntimeAuthorityValidator,
    build_outcome_receipt,
    build_human_approval_state,
)
from veritas_os.governance.authority_evidence_ingestion import (
    ingest_authority_evidence_payload,
)

FIXED_NOW = datetime.fromisoformat("2026-04-26T00:00:00").replace(tzinfo=UTC)
REQUESTED_SCOPE = ["saas:grant_admin"]
TARGET_SYSTEM = "mock_saas_directory"
TARGET_RESOURCE = "contractor:external.user@example.test"
BOUNDARY_NOTE = "local/offline fixture only; no live SaaS/IAM/IdP integration"


def _action_contract() -> ActionClassContract:
    """Return a deterministic action-class contract for SaaS permission changes."""
    return ActionClassContract(
        id="saas_permission_change",
        version="1.0.0",
        domain="saas",
        action_class="permission_change",
        description="Govern SaaS permission changes before execution.",
        declared_intent="Validate authority and human approval for admin grants.",
        allowed_scope=["saas:permission_change", "saas:grant_admin"],
        prohibited_scope=["saas:delete_workspace", "saas:billing_owner_transfer"],
        authority_sources=["policy.saas_access"],
        required_evidence=["access_request_ticket", "manager_approval"],
        evidence_freshness={
            "access_request_ticket": "P7D",
            "manager_approval": "P7D",
        },
        irreversibility={"boundary": "saas_permission_commit", "level": "high"},
        human_approval_rules={"minimum_approvals": 1},
        refusal_conditions=["authority_indeterminate"],
        escalation_conditions=["evidence_stale"],
        default_failure_mode="fail_closed",
        metadata={"regulated": True, "demo_fixture": True},
    )


def _authority_payload(*, scope_grants: list[str] | None = None) -> dict[str, Any]:
    """Build a deterministic authority evidence payload for ingestion."""
    return {
        "authority_evidence_id": "aev-saas-001",
        "action_contract_id": "saas_permission_change",
        "action_contract_version": "1.0.0",
        "actor_identity": "agent:ops-assistant",
        "actor_role": "automation_operator",
        "authority_source_refs": ["policy.saas_access"],
        "role_or_policy_basis": ["role:automation_operator"],
        "scope_grants": scope_grants or ["saas:grant_admin"],
        "scope_limitations": ["saas:billing_owner_transfer"],
        "issued_at": "2026-04-25T00:00:00+00:00",
        "valid_from": "2026-04-25T00:00:00+00:00",
        "valid_until": "2026-04-30T00:00:00+00:00",
        "policy_snapshot_id": "policy-snapshot-saas-001",
        "verification_result": "valid",
        "metadata": {"source_type": "mock_policy_registry", "issuer": "governance"},
    }


def _human_approval_receipt(*, approved_scope: list[str], expires_at: str) -> HumanApprovalReceipt:
    """Return a deterministic local/offline HumanApprovalReceipt."""
    return HumanApprovalReceipt(
        approval_receipt_id="har-saas-001",
        decision_id="decision-saas-001",
        execution_intent_id="intent-saas-001",
        approver_identity="human:manager.alex",
        approver_role="engineering_manager",
        approved_action_class="permission_change",
        approved_scope=approved_scope,
        approval_basis_refs=["ticket:AR-1001", "manager_approval:MA-2002"],
        approved_at="2026-04-25T00:00:00+00:00",
        expires_at=expires_at,
        policy_snapshot_id="policy-snapshot-saas-001",
        authority_evidence_id="aev-saas-001",
        approval_result="approved",
        signature_verified=True,
        receipt_hash="",
        metadata={"fixture": True},
    )


def _evaluate_case(
    *,
    case_id: str,
    expected_outcome: str,
    authority_scope_grants: list[str] | None,
    include_receipt: bool,
    receipt_scope: list[str] | None,
    receipt_expires_at: str,
) -> dict[str, Any]:
    """Evaluate one deterministic scenario and return JSON-friendly results."""
    contract = _action_contract()
    authority_evidence = None
    if authority_scope_grants is not None:
        authority_evidence = ingest_authority_evidence_payload(
            _authority_payload(scope_grants=authority_scope_grants)
        )

    receipt = None
    if include_receipt and receipt_scope is not None:
        receipt = _human_approval_receipt(
            approved_scope=receipt_scope,
            expires_at=receipt_expires_at,
        )

    human_approval_state = build_human_approval_state(
        receipt,
        requested_scope=REQUESTED_SCOPE,
        action_class=contract.action_class,
        policy_snapshot_id="policy-snapshot-saas-001",
        now=FIXED_NOW,
    )

    required_evidence_metadata = {
        "access_request_ticket": {"present": True},
        "manager_approval": {"present": True},
    }
    evidence_freshness_metadata = {
        "access_request_ticket": {"fresh": True},
        "manager_approval": {"fresh": True},
    }

    runtime_result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=authority_evidence,
        requested_scope=REQUESTED_SCOPE,
        required_evidence_metadata={
            key: {**required_evidence_metadata[key], **evidence_freshness_metadata[key]}
            for key in required_evidence_metadata
        },
        policy_snapshot_id="policy-snapshot-saas-001",
        actor_identity="agent:ops-assistant",
        human_approval_state=human_approval_state,
        bind_context_metadata={"session_id": "bind-saas-001", "fixture": True},
        now=FIXED_NOW,
    )
    boundary_result = CommitBoundaryEvaluator().evaluate(
        execution_intent={"action_class": "permission_change", "admissible": True},
        action_contract=contract,
        authority_evidence=authority_evidence,
        requested_scope=REQUESTED_SCOPE,
        required_evidence_metadata=required_evidence_metadata,
        evidence_freshness_metadata=evidence_freshness_metadata,
        policy_snapshot_id="policy-snapshot-saas-001",
        actor_identity="agent:ops-assistant",
        human_approval_state=human_approval_state,
        bind_context_metadata={"session_id": "bind-saas-001", "fixture": True},
        now=FIXED_NOW,
    )

    actual_outcome = boundary_result.commit_boundary_result
    observed_effects: list[dict[str, Any]] = []
    postcondition_status = "skipped"
    if case_id == "valid_authority_and_approval":
        observed_effects = [
            {
                "effect_type": "permission_grant",
                "permission": "saas:grant_admin",
                "target_resource": TARGET_RESOURCE,
                "fixture_only": True,
            }
        ]
        postcondition_status = "passed"

    outcome_receipt = build_outcome_receipt(
        decision_id="decision-saas-001",
        execution_intent_id="intent-saas-001",
        bind_receipt_id=None,
        operation_id=f"saas-permission-change-{case_id}",
        action_class=contract.action_class,
        target_system=TARGET_SYSTEM,
        target_resource=TARGET_RESOURCE,
        intended_action="grant_admin_permission",
        requested_scope=list(REQUESTED_SCOPE),
        final_outcome=actual_outcome,
        postcondition_status=postcondition_status,
        observed_effects=observed_effects,
        failure_reasons=sorted(
            {
                item.reason
                for item in boundary_result.failed_predicates
                + boundary_result.missing_predicates
            }
        ),
        rollback_status=None,
        evaluated_at=FIXED_NOW.isoformat(),
        metadata={"fixture_only": True, "boundary_note": BOUNDARY_NOTE},
    )
    return {
        "case_id": case_id,
        "expected_outcome": expected_outcome,
        "actual_outcome": actual_outcome,
        "passed": expected_outcome == actual_outcome,
        "authority_validation_status": runtime_result.status,
        "runtime_recommended_outcome": runtime_result.recommended_outcome,
        "human_approval_state": human_approval_state,
        "refusal_basis": boundary_result.refusal_basis,
        "failure_reasons": sorted(
            {item.reason for item in boundary_result.failed_predicates + boundary_result.missing_predicates}
        ),
        "requested_scope": list(REQUESTED_SCOPE),
        "target_system": TARGET_SYSTEM,
        "target_resource": TARGET_RESOURCE,
        "boundary_note": BOUNDARY_NOTE,
        "outcome_receipt_summary": outcome_receipt.to_dict(),
    }


def run_saas_permission_change_governed_demo() -> dict[str, Any]:
    """Run deterministic local/offline governed execution cases for reviewers."""
    scenarios = [
        {
            "case_id": "missing_authority",
            "expected_outcome": "block",
            "authority_scope_grants": None,
            "include_receipt": True,
            "receipt_scope": ["saas:grant_admin"],
            "receipt_expires_at": "2026-04-30T00:00:00+00:00",
        },
        {
            "case_id": "missing_human_approval",
            "expected_outcome": "block",
            "authority_scope_grants": ["saas:grant_admin"],
            "include_receipt": False,
            "receipt_scope": None,
            "receipt_expires_at": "2026-04-30T00:00:00+00:00",
        },
        {
            "case_id": "expired_human_approval",
            "expected_outcome": "block",
            "authority_scope_grants": ["saas:grant_admin"],
            "include_receipt": True,
            "receipt_scope": ["saas:grant_admin"],
            "receipt_expires_at": "2026-04-20T00:00:00+00:00",
        },
        {
            "case_id": "scope_mismatch",
            "expected_outcome": "block",
            "authority_scope_grants": ["saas:permission_change"],
            "include_receipt": True,
            "receipt_scope": ["saas:permission_change"],
            "receipt_expires_at": "2026-04-30T00:00:00+00:00",
        },
        {
            "case_id": "valid_authority_and_approval",
            "expected_outcome": "commit",
            "authority_scope_grants": ["saas:permission_change", "saas:grant_admin"],
            "include_receipt": True,
            "receipt_scope": ["saas:grant_admin"],
            "receipt_expires_at": "2026-04-30T00:00:00+00:00",
        },
    ]

    case_results = [_evaluate_case(**scenario) for scenario in scenarios]
    return {
        "demo_id": "saas_permission_change_governed_execution_v1",
        "generated_at": FIXED_NOW.isoformat(),
        "boundary_note": BOUNDARY_NOTE,
        "cases": case_results,
    }


def main() -> int:
    """Run demo from CLI and print deterministic JSON output."""
    print(json.dumps(run_saas_permission_change_governed_demo(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
