#!/usr/bin/env python3
"""Export deterministic Human Approval alternatives reviewer evidence.

This local/offline supplement records observable review-session alternative
state. It distinguishes alternatives that were technically available from
alternatives actually presented to the reviewer.

It does not prove what the reviewer understood, believed, or mentally
considered, and it does not change runtime authorization or admissibility.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.saas_permission_change_governed_demo import (
    BOUNDARY_NOTE,
    _human_approval_receipt,
    run_saas_permission_change_governed_demo,
)
from veritas_os.governance.human_approval_receipt import (
    summarize_human_approval_alternatives_evidence,
    summarize_human_approval_engagement_timing,
    validate_human_approval_alternatives_evidence,
    with_receipt_hash,
)
from veritas_os.security.hash import sha256_of_canonical_json

PACKET_ID = "human-approval-alternatives-saas-permission-change-v1"
PACKET_VERSION = "v1"
CASE_ID = "valid_authority_and_approval"

APPROVAL_BASIS_OPENED_AT = {
    "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
    "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
}

REVIEW_ALTERNATIVES = [
    {
        "alternative_id": "approve_requested_scope",
        "alternative_type": "approve",
        "available": True,
        "presented": True,
        "presented_at": "2026-04-24T23:58:00+00:00",
        "unavailable_reason": None,
    },
    {
        "alternative_id": "approve_narrower_scope",
        "alternative_type": "approve_narrower",
        "available": True,
        "presented": True,
        "presented_at": "2026-04-24T23:58:00+00:00",
        "unavailable_reason": None,
    },
    {
        "alternative_id": "reject_request",
        "alternative_type": "reject",
        "available": True,
        "presented": True,
        "presented_at": "2026-04-24T23:58:00+00:00",
        "unavailable_reason": None,
    },
    {
        "alternative_id": "defer_review",
        "alternative_type": "defer",
        "available": True,
        "presented": False,
        "presented_at": None,
        "unavailable_reason": None,
    },
    {
        "alternative_id": "escalate_for_secondary_review",
        "alternative_type": "escalate",
        "available": False,
        "presented": True,
        "presented_at": "2026-04-24T23:58:00+00:00",
        "unavailable_reason": "secondary_reviewer_not_configured_in_fixture",
    },
]

SELECTED_AT = "2026-04-25T00:00:00+00:00"


def _base_evidence_receipt() -> Any:
    """Return the prior timing fixture extended with alternative-set evidence."""
    legacy_receipt = _human_approval_receipt(
        approved_scope=["saas:grant_admin"],
        expires_at="2026-04-30T00:00:00+00:00",
    )
    return replace(
        legacy_receipt,
        approval_basis_opened_at=dict(APPROVAL_BASIS_OPENED_AT),
        review_alternatives=[dict(item) for item in REVIEW_ALTERNATIVES],
        selected_alternative_id="approve_requested_scope",
        selected_at=SELECTED_AT,
    )


def build_human_approval_alternatives_evidence() -> dict[str, Any]:
    """Build the deterministic third human-oversight evidence data point."""
    demo = run_saas_permission_change_governed_demo()
    runtime_case = next(
        item for item in demo["cases"] if item["case_id"] == CASE_ID
    )

    approve_receipt = with_receipt_hash(_base_evidence_receipt())
    approve_validation = validate_human_approval_alternatives_evidence(
        approve_receipt
    )
    approve_summary = summarize_human_approval_alternatives_evidence(
        approve_receipt
    )

    reject_receipt = with_receipt_hash(
        replace(
            _base_evidence_receipt(),
            approval_result="denied",
            selected_alternative_id="reject_request",
            selected_at=SELECTED_AT,
        )
    )
    reject_validation = validate_human_approval_alternatives_evidence(
        reject_receipt
    )
    reject_summary = summarize_human_approval_alternatives_evidence(
        reject_receipt
    )

    packet: dict[str, Any] = {
        "packet_id": PACKET_ID,
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "boundary_note": BOUNDARY_NOTE,
        "runtime_case_outcome": runtime_case["actual_outcome"],
        "runtime_case_passed": runtime_case["passed"],
        "runtime_semantics_note": (
            "Alternative-set evidence is reviewer evidence only. The existing "
            "SaaS demo runtime outcome is reported for context; this evidence "
            "does not create execution permission or change authorization, "
            "admissibility, scope, bind, refusal, or outcome semantics."
        ),
        "evidentiary_limit": (
            "available != presented; presented != considered; selected != "
            "understood. The packet records observable review-session state, "
            "not reviewer cognition, belief, independence, or decision quality."
        ),
        "prior_timing_evidence": summarize_human_approval_engagement_timing(
            approve_receipt
        ),
        "approve_path": {
            "human_approval_receipt": approve_receipt.to_dict(),
            "alternatives_evidence": approve_summary,
            "alternatives_validation": {
                "is_valid": approve_validation.is_valid,
                "failure_reasons": approve_validation.failure_reasons,
            },
        },
        "reject_path_evidence_only": {
            "runtime_executed": False,
            "purpose": (
                "Demonstrates that the same recorded alternative set can "
                "represent reject as the selected live path. This synthetic "
                "evidence-only path is not a live runtime execution result."
            ),
            "human_approval_receipt": reject_receipt.to_dict(),
            "alternatives_evidence": reject_summary,
            "alternatives_validation": {
                "is_valid": reject_validation.is_valid,
                "failure_reasons": reject_validation.failure_reasons,
            },
        },
    }
    packet["packet_hash"] = sha256_of_canonical_json(packet)
    return packet


def main() -> int:
    """Print the deterministic local/offline alternatives evidence packet."""
    print(
        json.dumps(
            build_human_approval_alternatives_evidence(),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
