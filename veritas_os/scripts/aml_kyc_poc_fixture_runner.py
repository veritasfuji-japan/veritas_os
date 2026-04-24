#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic AML/KYC PoC fixture runner.

This runner provides one lightweight, repo-native executable scenario for the
AML/KYC beachhead. It evaluates a single synthetic fixture and emits a
bind-boundary governance result suitable for operator/audit walkthroughs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SCENARIO_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_poc_pack/"
    "scenario_high_risk_manual_review.json"
)


def load_scenario(path: Path) -> dict[str, Any]:
    """Load and parse one AML/KYC PoC scenario fixture."""
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_list(value: Any) -> list[str]:
    """Normalize a JSON value into a sorted string list without duplicates."""
    if not isinstance(value, list):
        return []
    normalized = {str(item).strip() for item in value if str(item).strip()}
    return sorted(normalized)


def evaluate_fixture(scenario: dict[str, Any]) -> dict[str, Any]:
    """Evaluate fixture inputs and build deterministic governance output."""
    required_evidence = _normalized_list(scenario.get("required_evidence"))
    provided_evidence = _normalized_list(scenario.get("provided_evidence"))

    missing_evidence = sorted(set(required_evidence) - set(provided_evidence))
    risk_flags = scenario.get("risk_flags") or {}

    risk_triggered = bool(
        risk_flags.get("pep_association")
        or risk_flags.get("sanctions_partial_match")
        or risk_flags.get("high_risk_country_corridor")
    )

    if missing_evidence:
        gate_decision = "hold"
        business_decision = "EVIDENCE_REQUIRED"
        next_action = "COLLECT_REQUIRED_EVIDENCE"
        bind_admissible = False
    elif risk_triggered:
        gate_decision = "human_review_required"
        business_decision = "REVIEW_REQUIRED"
        next_action = "PREPARE_HUMAN_REVIEW_PACKET"
        bind_admissible = False
    else:
        gate_decision = "proceed"
        business_decision = "APPROVE"
        next_action = "EXECUTE_WITH_STANDARD_MONITORING"
        bind_admissible = True

    scenario_id = str(scenario.get("scenario_id", "")).strip()
    bind_receipt_id = f"bind_receipt::{scenario_id}"

    return {
        "scenario_id": scenario_id,
        "domain": str(scenario.get("domain", "")).strip(),
        "governance_outcome": {
            "gate_decision": gate_decision,
            "business_decision": business_decision,
            "next_action": next_action,
            "human_review_required": gate_decision == "human_review_required",
        },
        "evidence_summary": {
            "required_count": len(required_evidence),
            "provided_count": len(provided_evidence),
            "missing_count": len(missing_evidence),
            "missing_evidence": missing_evidence,
            "evidence_coverage_ratio": (
                round(len(provided_evidence) / len(required_evidence), 4)
                if required_evidence
                else 1.0
            ),
        },
        "bind_result": {
            "execution_intent": str(scenario.get("execution_intent", "")).strip(),
            "admissible": bind_admissible,
            "bind_receipt_id": bind_receipt_id,
            "reason": (
                "risk-triggered-manual-review" if risk_triggered and not missing_evidence
                else "missing-required-evidence" if missing_evidence
                else "controls-and-evidence-sufficient"
            ),
        },
        "compliance_view": {
            "control_plane": "bind-boundary",
            "policy_pack": str((scenario.get("governance_identity") or {}).get("policy_pack", "")).strip(),
            "policy_hash": str((scenario.get("governance_identity") or {}).get("policy_hash", "")).strip(),
            "status": "conformant" if not missing_evidence else "evidence-gap",
            "scope": "synthetic_poc",
        },
    }


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for AML/KYC PoC fixture runner."""
    parser = argparse.ArgumentParser(
        description="Run deterministic AML/KYC PoC fixture and emit governance outputs."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_SCENARIO_PATH),
        help="Path to AML/KYC scenario fixture JSON.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path for output JSON.",
    )
    parser.add_argument(
        "--verify-expected",
        default="",
        help="Optional expected-output JSON path for deterministic verification.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for deterministic AML/KYC PoC fixture execution."""
    args = _parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        raise SystemExit(f"[aml-kyc-poc] input file not found: {input_path}")

    scenario = load_scenario(input_path)
    output = evaluate_fixture(scenario)

    if args.verify_expected:
        expected_path = Path(args.verify_expected)
        if not expected_path.exists():
            raise SystemExit(f"[aml-kyc-poc] expected file not found: {expected_path}")
        expected_payload = json.loads(expected_path.read_text(encoding="utf-8"))
        if expected_payload != output:
            raise SystemExit("[aml-kyc-poc] expected output mismatch")
        print("[aml-kyc-poc] expected output verification: pass")

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[aml-kyc-poc] report saved: {output_path}")


if __name__ == "__main__":
    main()
