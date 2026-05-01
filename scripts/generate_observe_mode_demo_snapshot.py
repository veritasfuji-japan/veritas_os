#!/usr/bin/env python3
"""Generate a dev-only Observe Mode governance snapshot for walkthroughs.

This tooling script is intended for development/test/documentation workflows.
It does not enable Observe Mode runtime behavior and does not modify
production fail-closed enforcement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from veritas_os.governance.observation_evaluator import evaluate_governance_observation
from veritas_os.governance.observe_mode_wrapper import (
    ObserveModeDecisionInput,
    build_governance_observation_for_dry_run,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a dev-only Mission Control-style snapshot containing "
            "wrapper-generated governance_observation."
        )
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write output JSON to a file path instead of stdout.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON (default emits pretty JSON).",
    )
    return parser


def _build_snapshot() -> dict:
    observation = build_governance_observation_for_dry_run(
        ObserveModeDecisionInput(
            policy_mode="observe",
            environment="development",
            would_be_outcome="block",
            reason="policy_violation:missing_authority_evidence",
        )
    )
    evaluation = evaluate_governance_observation(observation)
    if not evaluation.valid:
        issues = ", ".join(
            f"{issue.code}: {issue.message}" for issue in evaluation.issues
        )
        raise ValueError(
            "generated governance_observation failed semantic validation: "
            f"{issues}"
        )

    return {
        "sample_kind": "dev_only_observe_mode_demo",
        "governance_layer_snapshot": {
            "participation_state": "decision_shaping",
            "pre_bind_source": "trustlog_matching_decision",
            "bind_reason_code": "AUTHORITY_MISSING",
            "bind_failure_reason": "Authority evidence missing",
            "failure_category": "policy_violation",
            "target_path": "/governance/policies/authority",
            "target_type": "policy",
            "target_label": "Authority policy",
            "operator_surface": "governance",
            "relevant_ui_href": "/governance",
            "decision_id": "dec_observe_generated_001",
            "bind_receipt_id": "br_observe_generated_001",
            "execution_intent_id": "ei_observe_generated_001",
            "governance_observation": observation.model_dump(mode="json"),
        },
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        snapshot = _build_snapshot()
    except ValueError as exc:
        print("observe mode demo snapshot generation: invalid", file=sys.stderr)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    indent = None if args.compact else 2
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=indent) + "\n"

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"observe mode demo snapshot generation: wrote {args.out}")
        return 0

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
