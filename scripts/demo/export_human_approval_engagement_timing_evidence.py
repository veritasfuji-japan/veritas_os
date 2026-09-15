#!/usr/bin/env python3
"""Export deterministic Human Approval engagement-timing reviewer evidence.

This is a local/offline evidence supplement for the SaaS permission-change demo.
It does not change runtime admissibility or claim that a reviewer read,
understood, or independently evaluated the referenced material.
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
    summarize_human_approval_engagement_timing,
    validate_human_approval_engagement_timing,
    with_receipt_hash,
)
from veritas_os.security.hash import sha256_of_canonical_json

PACKET_ID = "human-approval-engagement-timing-saas-permission-change-v1"
PACKET_VERSION = "v1"
CASE_ID = "valid_authority_and_approval"
APPROVAL_BASIS_OPENED_AT = {
    "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
    "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00",
}


def build_human_approval_engagement_timing_evidence() -> dict[str, Any]:
    """Build a deterministic reviewer-facing timing evidence supplement."""
    demo = run_saas_permission_change_governed_demo()
    case = next(item for item in demo["cases"] if item["case_id"] == CASE_ID)

    legacy_receipt = _human_approval_receipt(
        approved_scope=["saas:grant_admin"],
        expires_at="2026-04-30T00:00:00+00:00",
    )
    timed_receipt = replace(
        legacy_receipt,
        approval_basis_opened_at=dict(APPROVAL_BASIS_OPENED_AT),
    )
    finalized = with_receipt_hash(timed_receipt)
    timing_validation = validate_human_approval_engagement_timing(finalized)
    timing_summary = summarize_human_approval_engagement_timing(finalized)

    packet: dict[str, Any] = {
        "packet_id": PACKET_ID,
        "packet_version": PACKET_VERSION,
        "case_id": CASE_ID,
        "boundary_note": BOUNDARY_NOTE,
        "runtime_case_outcome": case["actual_outcome"],
        "runtime_case_passed": case["passed"],
        "runtime_semantics_note": (
            "Engagement timing is reviewer evidence only. The existing SaaS demo "
            "runtime outcome is reported for context; timing is not an "
            "authorization, admissibility, scope, bind, or refusal predicate."
        ),
        "evidentiary_limit": (
            "The signal records when referenced approval-basis material was "
            "opened or presented. It does not prove that the reviewer read, "
            "understood, independently evaluated, or agreed with the material."
        ),
        "human_approval_receipt": finalized.to_dict(),
        "engagement_timing": timing_summary,
        "engagement_timing_validation": {
            "is_valid": timing_validation.is_valid,
            "failure_reasons": timing_validation.failure_reasons,
        },
    }
    packet["packet_hash"] = sha256_of_canonical_json(packet)
    return packet


def main() -> int:
    """Print the deterministic local/offline timing evidence packet."""
    print(
        json.dumps(
            build_human_approval_engagement_timing_evidence(),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
