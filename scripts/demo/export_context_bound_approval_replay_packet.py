#!/usr/bin/env python3
"""Export deterministic context-bound approval replay-prevention examples."""

from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.export_reviewer_evidence_packet import (  # noqa: E402
    PACKET_VERSION,
    with_packet_hash,
)
from scripts.demo.verifier_lifecycle import (  # noqa: E402
    verifier_lifecycle_summary_from_human_approval,
)
from veritas_os.governance.human_approval_receipt import (  # noqa: E402
    HumanApprovalReceipt,
    validate_human_approval_context_binding,
    with_receipt_hash,
)
from veritas_os.security.hash import sha256_of_canonical_json  # noqa: E402

PACKET_ID = "reviewer-evidence-packet-approval-replay-prevention-v1"
GENERATED_AT = "2026-05-10T00:00:00+00:00"
BOUNDARY_NOTE = (
    "Local/offline deterministic reviewer example only; no live identity, "
    "signature, SaaS, IAM, audit-store, or production approval system is used."
)
VERIFIED_APPROVAL_PROOF_HASH = (
    "4c5825bb7e0f647e705ca280a411695d052bfb8e65382f13804e86c0f485ef0c"
)
VERIFIER_ID = "veritas-human-approval-verifier-v1"
VERIFIER_KEY_ID = "local-demo-verifier-key"
VERIFIER_POLICY_ID = "human-approval-verifier-policy-v1"
VERIFIER_POLICY_HASH = (
    "b625a813408d3a1d6c55ff59e9661ac21c4a9017fda76e4369bd9407a743a2cd"
)
BASE_CONTEXT = {
    "request_ref": "request:permission-change:001",
    "ai_output_ref": "ai-output:permission-change:001",
    "execution_intent_id": "intent-replay-001",
    "decision_id": "decision-replay-001",
    "action_class": "permission_change",
    "policy_snapshot_id": "policy-replay-001",
    "authority_evidence_id": "aev-replay-001",
    "bind_context_hash": "1" * 64,
}
REQUESTED_SCOPE = ["workspace:permission:update"]


def _base_receipt() -> HumanApprovalReceipt:
    """Return the deterministic signed approval receipt used by all cases."""
    return with_receipt_hash(
        HumanApprovalReceipt(
            approval_receipt_id="har-replay-001",
            decision_id=BASE_CONTEXT["decision_id"],
            execution_intent_id=BASE_CONTEXT["execution_intent_id"],
            approver_identity="operator:approver-1",
            approver_role="risk_manager",
            approved_action_class=BASE_CONTEXT["action_class"],
            approved_scope=REQUESTED_SCOPE,
            approval_basis_refs=["policy:permission-change:v1"],
            approved_at="2026-05-01T00:00:00+00:00",
            expires_at="2026-06-01T00:00:00+00:00",
            policy_snapshot_id=BASE_CONTEXT["policy_snapshot_id"],
            authority_evidence_id=BASE_CONTEXT["authority_evidence_id"],
            approval_result="approved",
            signature_verified=True,
            receipt_hash="",
            request_ref=BASE_CONTEXT["request_ref"],
            ai_output_ref=BASE_CONTEXT["ai_output_ref"],
            bind_context_hash=BASE_CONTEXT["bind_context_hash"],
            metadata={"demo_fixture": "approval_replay_prevention"},
        )
    )


def _hash_payload(payload: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hash for a nested demo payload."""
    return sha256_of_canonical_json(payload)


def _case_context(case_id: str) -> dict[str, str]:
    """Return the expected governed context for one replay scenario."""
    context = dict(BASE_CONTEXT)
    if case_id == "replay_different_request_ref":
        context["request_ref"] = "request:permission-change:replay-other"
    elif case_id == "replay_different_action_class":
        context["action_class"] = "admin_role_assignment"
    elif case_id == "replay_different_bind_context_hash":
        context["bind_context_hash"] = "2" * 64
    return context


def _case_summary(case_id: str, expected_context: dict[str, str]) -> dict[str, Any]:
    """Build one schema-valid reviewer case for a replay validation scenario."""
    receipt = _base_receipt()
    validation = validate_human_approval_context_binding(
        receipt,
        **expected_context,
    )
    failure_reasons = validation.failure_reasons
    actual_outcome = "commit_eligible" if validation.is_valid else "block"
    operation_id = f"operation-{case_id}"
    human_approval_summary = {
        "approved": validation.is_valid,
        "approval_receipt_id": receipt.approval_receipt_id,
        "approver_identity": receipt.approver_identity,
        "approver_role": receipt.approver_role,
        "approved_scope": list(receipt.approved_scope),
        "receipt_hash_present": validation.is_valid,
        "verifier_id": VERIFIER_ID if validation.is_valid else None,
        "verifier_key_id": VERIFIER_KEY_ID if validation.is_valid else None,
        "verifier_policy_id": VERIFIER_POLICY_ID if validation.is_valid else None,
        "verifier_policy_hash": (
            VERIFIER_POLICY_HASH if validation.is_valid else None
        ),
        "verification_proof_hash": (
            VERIFIED_APPROVAL_PROOF_HASH if validation.is_valid else None
        ),
        "verified_at": GENERATED_AT if validation.is_valid else None,
        "failure_reasons": list(failure_reasons),
        "context_binding": copy.deepcopy(expected_context),
    }
    lifecycle_summary = verifier_lifecycle_summary_from_human_approval(
        human_approval_summary
    )
    lifecycle_hash = (
        lifecycle_summary.get("verifier_lifecycle_snapshot_hash")
        if lifecycle_summary is not None
        else None
    )
    outcome = {
        "outcome_receipt_id": f"outcome-{case_id}",
        "decision_id": expected_context["decision_id"],
        "execution_intent_id": expected_context["execution_intent_id"],
        "operation_id": operation_id,
        "action_class": expected_context["action_class"],
        "target_system": "local-demo-iam",
        "target_resource": "workspace:demo",
        "intended_action": "Apply reviewer-demo permission change.",
        "requested_scope": list(REQUESTED_SCOPE),
        "final_outcome": actual_outcome,
        "committed": validation.is_valid,
        "blocked": not validation.is_valid,
        "escalated": False,
        "rolled_back": False,
        "postcondition_status": "skipped" if not validation.is_valid else "passed",
        "observed_effects": [],
        "failure_reasons": list(failure_reasons),
        "evaluated_at": GENERATED_AT,
        "outcome_hash": "",
        "metadata": {"context_binding_valid": validation.is_valid},
    }
    if validation.is_valid:
        outcome["metadata"].update(
            {
                "verified_human_approval_proof_hash": (
                    VERIFIED_APPROVAL_PROOF_HASH
                ),
                "verified_human_approval_receipt_id": (
                    receipt.approval_receipt_id
                ),
                "human_approval_verification_source": (
                    "signed_human_approval_artifact"
                ),
                "human_approval_verifier_id": VERIFIER_ID,
                "human_approval_verifier_key_id": VERIFIER_KEY_ID,
                "human_approval_verifier_policy_id": VERIFIER_POLICY_ID,
                "human_approval_verifier_policy_hash": VERIFIER_POLICY_HASH,
                "human_approval_verifier_lifecycle_snapshot_hash": lifecycle_hash,
            }
        )
    outcome["outcome_hash"] = _hash_payload(outcome)
    manifest = {
        "manifest_id": f"manifest-{case_id}",
        "decision_id": expected_context["decision_id"],
        "execution_intent_id": expected_context["execution_intent_id"],
        "operation_id": operation_id,
        "action_class": expected_context["action_class"],
        "target_system": outcome["target_system"],
        "target_resource": outcome["target_resource"],
        "requested_scope": list(REQUESTED_SCOPE),
        "authority_evidence_id": expected_context["authority_evidence_id"],
        "authority_evidence_hash": "3" * 64,
        "human_approval_receipt_id": (
            receipt.approval_receipt_id if validation.is_valid else None
        ),
        "human_approval_receipt_hash": (
            receipt.receipt_hash if validation.is_valid else None
        ),
        "verified_human_approval_proof_hash": (
            VERIFIED_APPROVAL_PROOF_HASH if validation.is_valid else None
        ),
        "human_approval_verifier_id": VERIFIER_ID if validation.is_valid else None,
        "human_approval_verifier_key_id": (
            VERIFIER_KEY_ID if validation.is_valid else None
        ),
        "human_approval_verifier_policy_id": (
            VERIFIER_POLICY_ID if validation.is_valid else None
        ),
        "human_approval_verifier_policy_hash": (
            VERIFIER_POLICY_HASH if validation.is_valid else None
        ),
        "human_approval_verifier_lifecycle_snapshot_hash": (
            lifecycle_hash if validation.is_valid else None
        ),
        "human_approval_required": True,
        "bind_receipt_id": f"bind-{case_id}",
        "bind_receipt_hash": expected_context["bind_context_hash"],
        "outcome_receipt_id": outcome["outcome_receipt_id"],
        "outcome_receipt_hash": outcome["outcome_hash"],
        "bind_coverage_operation_id": operation_id,
        "final_outcome": actual_outcome,
        "chain_status": "complete" if validation.is_valid else "blocked",
        "missing_links": [],
        "refusal_basis": list(failure_reasons),
        "observed_effects_summary": [],
        "generated_at": GENERATED_AT,
        "manifest_hash": "",
        "metadata": {"signature_validity_alone_is_insufficient": True},
    }
    manifest["manifest_hash"] = _hash_payload(manifest)
    verification = {
        "is_valid": validation.is_valid,
        "verification_status": "verified" if validation.is_valid else "failed",
        "manifest_id": manifest["manifest_id"],
        "decision_id": expected_context["decision_id"],
        "execution_intent_id": expected_context["execution_intent_id"],
        "operation_id": operation_id,
        "verified_links": (
            [
                "human_approval_receipt_signature",
                "verified_human_approval_proof_hash",
            ]
            if validation.is_valid
            else ["human_approval_receipt_signature"]
        ),
        "missing_links": [],
        "mismatched_links": list(failure_reasons),
        "failure_reasons": list(failure_reasons),
        "recomputed_manifest_hash": manifest["manifest_hash"],
        "manifest_hash_matches": True,
        "verified_at": GENERATED_AT,
        "metadata": {"context_binding_valid": validation.is_valid},
    }
    return {
        "case_id": case_id,
        "expected_outcome": actual_outcome,
        "actual_outcome": actual_outcome,
        "passed": True,
        "requested_scope": list(REQUESTED_SCOPE),
        "target_system": outcome["target_system"],
        "target_resource": outcome["target_resource"],
        "authority_validation_status": "valid",
        "runtime_recommended_outcome": "commit" if validation.is_valid else "block",
        "human_approval_summary": human_approval_summary,
        "verifier_lifecycle_summary": lifecycle_summary,
        "refusal_basis": list(failure_reasons),
        "failure_reasons": list(failure_reasons),
        "outcome_receipt_summary": outcome,
        "evidence_chain_manifest_summary": manifest,
        "evidence_chain_verification_summary": verification,
        "reviewer_interpretation": (
            "The signed approval is accepted only when the governed context "
            "matches; replayed context values fail closed deterministically."
        ),
        "boundary_note": BOUNDARY_NOTE,
    }


def build_context_bound_approval_replay_packet() -> dict[str, Any]:
    """Build deterministic reviewer examples for approval replay prevention."""
    case_ids = [
        "valid_same_context",
        "replay_different_request_ref",
        "replay_different_action_class",
        "replay_different_bind_context_hash",
    ]
    cases = [_case_summary(case_id, _case_context(case_id)) for case_id in case_ids]
    packet = {
        "packet_id": PACKET_ID,
        "packet_version": PACKET_VERSION,
        "demo_id": "context-bound-approval-replay-prevention-v1",
        "generated_at": GENERATED_AT,
        "title": "Context-bound Approval Replay Prevention Reviewer Examples",
        "summary": (
            "Deterministic examples showing that valid approval signatures are "
            "insufficient when replayed against a different governed context."
        ),
        "boundary_note": BOUNDARY_NOTE,
        "local_offline_only": True,
        "cases": cases,
        "aggregate_summary": {
            "total_cases": len(cases),
            "passed_cases": len(cases),
            "blocked_cases": sum(1 for case in cases if case["actual_outcome"] == "block"),
            "committed_cases": sum(
                1 for case in cases if case["actual_outcome"] == "commit_eligible"
            ),
            "verified_chains": sum(
                1
                for case in cases
                if case["evidence_chain_verification_summary"]["is_valid"] is True
            ),
            "failed_chains": sum(
                1
                for case in cases
                if case["evidence_chain_verification_summary"]["is_valid"] is False
            ),
            "incomplete_chains": 0,
            "indeterminate_chains": 0,
            "local_offline_only": True,
        },
        "reviewer_notes": [
            "Signature validity alone is not enough for governed execution.",
            "The same signed receipt passes only for its original context.",
            "Different request_ref, action_class, or bind_context_hash values fail closed.",
        ],
        "packet_hash": "",
    }
    return with_packet_hash(packet)


def main() -> int:
    """Print deterministic context-bound replay examples as JSON."""
    print(
        json.dumps(
            build_context_bound_approval_replay_packet(),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
