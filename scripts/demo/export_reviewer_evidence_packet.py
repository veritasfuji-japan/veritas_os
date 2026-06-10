#!/usr/bin/env python3
"""Export a deterministic local/offline reviewer evidence packet for the SaaS demo."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.reviewer_key_provenance_metadata import key_provenance_metadata
from scripts.demo.saas_permission_change_governed_demo import (
    BOUNDARY_NOTE,
    run_saas_permission_change_governed_demo,
)
from veritas_os.security.hash import sha256_of_canonical_json

PACKET_ID = "reviewer-evidence-packet-saas-permission-change-v1"
PACKET_VERSION = "v1"
PACKET_TITLE = "SaaS Permission-Change Governed Execution Reviewer Evidence Packet"


REVIEWER_NOTES = [
    "This packet is generated from a local/offline fixture demo.",
    (
        "It does not connect to live SaaS, IAM, IdP, SSO, customer "
        "directory, bank, sanctions, or production approval systems."
    ),
    (
        "It demonstrates bind-time governance and evidence-chain "
        "verification using deterministic artifacts."
    ),
    (
        "It is not legal advice, regulatory approval, third-party "
        "certification, production audit certification, or proof of live "
        "deployment."
    ),
]


def _human_approval_summary(human_approval_state: dict[str, Any]) -> dict[str, Any]:
    """Return a compact deterministic summary of human approval state."""
    receipt_hash = human_approval_state.get("receipt_hash")
    return {
        "approved": bool(human_approval_state.get("approved", False)),
        "approval_receipt_id": human_approval_state.get("approval_receipt_id"),
        "approver_identity": human_approval_state.get("approver_identity"),
        "approver_role": human_approval_state.get("approver_role"),
        "approved_scope": list(human_approval_state.get("approved_scope", [])),
        "receipt_hash_present": bool(receipt_hash),
        "failure_reasons": list(human_approval_state.get("failure_reasons", [])),
    }


def _reviewer_interpretation(case: dict[str, Any]) -> str:
    """Create a deterministic reviewer-facing interpretation for one demo case."""
    actual_outcome = case["actual_outcome"]
    case_id = case["case_id"]
    if actual_outcome in {"commit", "commit_eligible"}:
        return (
            "AuthorityEvidence and HumanApprovalReceipt were sufficient for the "
            "local/offline fixture to reach a commit outcome."
        )
    if case_id == "missing_authority":
        return "The local/offline fixture blocked because AuthorityEvidence was missing."
    if case_id == "missing_human_approval":
        return "The local/offline fixture blocked because HumanApprovalReceipt was missing."
    if case_id == "expired_human_approval":
        return "The local/offline fixture blocked because HumanApprovalReceipt was expired."
    if case_id == "scope_mismatch":
        return (
            "The local/offline fixture blocked because approved authority "
            "or approval scope was insufficient."
        )
    return (
        "The local/offline fixture blocked or deferred according to existing "
        "demo governance artifacts."
    )


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    """Return a compact reviewer-facing case summary with nested evidence details."""
    return {
        "case_id": case["case_id"],
        "expected_outcome": case["expected_outcome"],
        "actual_outcome": case["actual_outcome"],
        "passed": case["passed"],
        "requested_scope": list(case["requested_scope"]),
        "target_system": case["target_system"],
        "target_resource": case["target_resource"],
        "authority_validation_status": case["authority_validation_status"],
        "runtime_recommended_outcome": case["runtime_recommended_outcome"],
        "human_approval_summary": _human_approval_summary(case["human_approval_state"]),
        "refusal_basis": case["refusal_basis"],
        "failure_reasons": list(case["failure_reasons"]),
        "outcome_receipt_summary": copy.deepcopy(case["outcome_receipt_summary"]),
        "evidence_chain_manifest_summary": copy.deepcopy(
            case["evidence_chain_manifest_summary"]
        ),
        "evidence_chain_verification_summary": copy.deepcopy(
            case["evidence_chain_verification_summary"]
        ),
        "reviewer_interpretation": _reviewer_interpretation(case),
        "boundary_note": case.get("boundary_note", BOUNDARY_NOTE),
    }


def _aggregate_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic aggregate counts derived from packet cases."""
    verification_statuses = [
        case["evidence_chain_verification_summary"]["verification_status"]
        for case in cases
    ]
    return {
        "total_cases": len(cases),
        "passed_cases": sum(1 for case in cases if case["passed"]),
        "blocked_cases": sum(
            1 for case in cases if case["outcome_receipt_summary"].get("blocked") is True
        ),
        "committed_cases": sum(
            1 for case in cases if case["outcome_receipt_summary"].get("committed") is True
        ),
        "verified_chains": verification_statuses.count("verified"),
        "failed_chains": verification_statuses.count("failed"),
        "incomplete_chains": verification_statuses.count("incomplete"),
        "indeterminate_chains": verification_statuses.count("indeterminate"),
        "local_offline_only": True,
    }


def compute_reviewer_packet_hash(packet: dict[str, Any]) -> str:
    """Compute a stable SHA-256 hash for a reviewer packet.

    The packet_hash field is excluded so finalizing a packet cannot recursively
    change the digest it is meant to report.
    """
    payload = copy.deepcopy(packet)
    payload.pop("packet_hash", None)
    return sha256_of_canonical_json(payload)


def with_packet_hash(packet: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``packet`` with deterministic packet_hash populated."""
    finalized = copy.deepcopy(packet)
    finalized["packet_hash"] = compute_reviewer_packet_hash(finalized)
    return finalized


def build_reviewer_evidence_packet() -> dict[str, Any]:
    """Build the local/offline reviewer evidence packet from the existing demo."""
    demo_output = run_saas_permission_change_governed_demo()
    cases = [_case_summary(case) for case in demo_output["cases"]]
    packet = {
        "packet_id": PACKET_ID,
        "packet_version": PACKET_VERSION,
        "demo_id": demo_output["demo_id"],
        "generated_at": demo_output["generated_at"],
        "title": PACKET_TITLE,
        "summary": (
            "Deterministic local/offline reviewer packet for the SaaS "
            "permission-change governed execution demo."
        ),
        "boundary_note": demo_output.get("boundary_note", BOUNDARY_NOTE),
        "local_offline_only": True,
        "cases": cases,
        "aggregate_summary": _aggregate_summary(cases),
        "key_provenance": key_provenance_metadata(),
        "reviewer_notes": list(REVIEWER_NOTES),
        "packet_hash": "",
    }
    return with_packet_hash(packet)


def main() -> int:
    """Print deterministic reviewer evidence packet JSON to stdout."""
    print(json.dumps(build_reviewer_evidence_packet(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
