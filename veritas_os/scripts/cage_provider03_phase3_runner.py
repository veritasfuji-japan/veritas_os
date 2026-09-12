"""CLI for the synthetic VERITAS / CAGE Provider03 Phase 3 proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas_os.governance.cage_provider03_phase3 import (
    build_negative_test_report,
    build_phase3_proof_bundle,
    build_replay_report,
    write_phase3_artifacts,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the synthetic deterministic VERITAS / CAGE Provider03 Phase 3 "
            "AML/KYC fixture proof."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional directory for reviewer-facing proof artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    first = build_phase3_proof_bundle()
    second = build_phase3_proof_bundle()
    replay = build_replay_report(first, second)
    negative = build_negative_test_report(first)

    if args.output_dir:
        summary = write_phase3_artifacts(
            Path(args.output_dir),
            first_bundle=first,
            second_bundle=second,
        )
    else:
        summary = {
            "proof_id": first["manifest"]["proof_id"],
            "scenario_count": first["manifest"]["scenario_count"],
            "observed_primary_results": first["manifest"]["observed_primary_results"],
            "overall_replay_match": replay["overall_replay_match"],
            "negative_tests_passed": negative["passed"],
            "live_external_effects": False,
            "production_claim": False,
            "live_cage_runtime_claim": False,
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
