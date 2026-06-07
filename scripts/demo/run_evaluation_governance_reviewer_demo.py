#!/usr/bin/env python3
"""Run the synthetic Evaluation Governance reviewer demo end to end.

This helper composes the offline Evaluation Governance chain runner with the
Reviewer Evidence Packet generator. It is intentionally local/offline,
non-runtime, and non-enforcing: it does not call ``/v1/decide``, does not alter
runtime admissibility, does not dereference external artifact references, and
does not establish legitimacy or certify compliance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.generate_reviewer_evidence_packet_from_evaluation_governance_chain import (  # noqa: E501
    generate_reviewer_evidence_packet_from_chain,
)
from scripts.demo.run_evaluation_governance_offline_chain import (
    DEFAULT_GENERATED_DIR_NAME,
    GENERATED_FILE_NAMES,
    run_offline_chain,
)

ISSUED_AT = "2026-01-01T00:00:00Z"
DEMO_ID = "evaluation-governance-reviewer-demo-example-001"
DEMO_SUMMARY_SCHEMA_VERSION = "evaluation-governance-reviewer-demo-summary-v1"
DEMO_SUMMARY_FILE_NAME = "demo-summary.generated.example.json"
REVIEWER_PACKET_FILE_NAME = "reviewer-evidence-packet.generated.example.json"
DEFAULT_INPUT_DIR = (
    REPO_ROOT / "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
EXAMPLE_OUTPUT_DIR = (
    REPO_ROOT
    / "docs/en/demo/examples/evaluation-governance-reviewer-demo-v1"
    / DEFAULT_GENERATED_DIR_NAME
)
SUMMARY_ARTIFACT_TYPES = {
    "attribution_1": "outcome_delta_attribution",
    "attribution_2": "outcome_delta_attribution",
    "drift_1": "evaluation_drift_detection",
    "drift_2": "evaluation_drift_detection",
    "monitor": "trajectory_admissibility_monitor",
    "review": "legitimacy_impact_review",
    "manifest": "chain_manifest",
}
NON_GOALS = [
    "does_not_change_runtime_behavior",
    "does_not_call_v1_decide",
    "does_not_establish_legitimacy",
    "does_not_certify_compliance",
    "does_not_dereference_external_artifact_refs",
    "does_not_require_network_access",
]


@dataclass(frozen=True)
class ReviewerDemoRunResult:
    """Result metadata returned by ``run_reviewer_demo`` for tests and CLIs."""

    output_dir: Path
    chain_manifest: dict[str, Any]
    reviewer_packet: dict[str, Any]
    demo_summary: dict[str, Any]
    artifact_paths: dict[str, Path]


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object from ``path`` with clear demo-runner errors."""
    if not path.is_file():
        raise FileNotFoundError(f"missing JSON file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as stable, reviewer-readable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def canonical_json_hash(payload: Any) -> str:
    """Return the SHA-256 digest of canonical JSON for local artifacts."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _artifact_entry(
    artifact_type: str,
    artifact_ref: str,
    artifact_payload: dict[str, Any],
) -> dict[str, str]:
    """Build a demo summary artifact entry with a canonical JSON hash."""
    return {
        "artifact_type": artifact_type,
        "artifact_ref": artifact_ref,
        "artifact_hash": canonical_json_hash(artifact_payload),
    }


def build_demo_summary(
    input_dir: Path,
    chain_artifacts: dict[str, dict[str, Any]],
    reviewer_packet: dict[str, Any],
) -> dict[str, Any]:
    """Build the reviewer-facing summary for the synthetic end-to-end demo."""
    generated_artifacts = []
    for key, file_name in GENERATED_FILE_NAMES.items():
        generated_artifacts.append(
            _artifact_entry(
                SUMMARY_ARTIFACT_TYPES[key],
                file_name,
                chain_artifacts[key],
            )
        )
    generated_artifacts.append(
        _artifact_entry(
            "reviewer_evidence_packet",
            REVIEWER_PACKET_FILE_NAME,
            reviewer_packet,
        )
    )

    return {
        "schema_version": DEMO_SUMMARY_SCHEMA_VERSION,
        "demo_id": DEMO_ID,
        "issued_at": ISSUED_AT,
        "non_runtime": True,
        "non_enforcing": True,
        "input_dir": input_dir.as_posix(),
        "generated_artifacts": generated_artifacts,
        "demo_summary": (
            "Synthetic offline Evaluation Governance reviewer demo generated "
            "for architecture review."
        ),
        "non_goals": NON_GOALS,
    }


def run_reviewer_demo(input_dir: Path, output_dir: Path) -> ReviewerDemoRunResult:
    """Generate the complete synthetic reviewer demo output directory.

    Args:
        input_dir: Directory containing local synthetic Evaluation Governance
            example inputs for the offline chain runner.
        output_dir: Directory where reviewer-facing generated artifacts are
            written.

    Returns:
        Metadata for generated chain artifacts, the reviewer packet, and the
        demo summary.

    Raises:
        FileNotFoundError: If required local input files are missing.
        ValueError: If JSON is invalid or helper validation fails.
    """
    summary_input_dir = input_dir
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    chain_result = run_offline_chain(input_dir, output_dir)
    reviewer_packet = generate_reviewer_evidence_packet_from_chain(
        chain_result.manifest,
        output_dir,
    )
    reviewer_packet_path = output_dir / REVIEWER_PACKET_FILE_NAME
    write_json(reviewer_packet_path, reviewer_packet)

    demo_summary = build_demo_summary(
        summary_input_dir,
        chain_result.artifacts,
        reviewer_packet,
    )
    demo_summary_path = output_dir / DEMO_SUMMARY_FILE_NAME
    write_json(demo_summary_path, demo_summary)

    artifact_paths = dict(chain_result.artifact_paths)
    artifact_paths["reviewer_packet"] = reviewer_packet_path
    artifact_paths["demo_summary"] = demo_summary_path

    return ReviewerDemoRunResult(
        output_dir=output_dir,
        chain_manifest=chain_result.manifest,
        reviewer_packet=reviewer_packet,
        demo_summary=demo_summary,
        artifact_paths=artifact_paths,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the reviewer demo runner."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a non-runtime, non-enforcing end-to-end Evaluation "
            "Governance reviewer demo from local synthetic inputs."
        )
    )
    parser.add_argument(
        "--input-dir",
        default=DEFAULT_INPUT_DIR,
        type=Path,
        help=(
            "Directory containing synthetic offline-chain input JSON files "
            f"(default: {DEFAULT_INPUT_DIR.relative_to(REPO_ROOT)})"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Safe output directory for generated reviewer-facing artifacts.",
    )
    parser.add_argument(
        "--write-example-output",
        action="store_true",
        help=(
            "Intentionally overwrite checked-in reviewer demo example outputs. "
            "Required when --output-dir is omitted."
        ),
    )
    return parser.parse_args(argv)


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    """Resolve output directory while preventing accidental repo mutations."""
    if args.output_dir is not None:
        return args.output_dir
    if args.write_example_output:
        return EXAMPLE_OUTPUT_DIR
    raise ValueError(
        "refusing to write checked-in generated examples without "
        "--write-example-output; pass --output-dir for safe temporary output"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the Evaluation Governance reviewer demo CLI."""
    args = _parse_args(argv)
    try:
        output_dir = _resolve_output_dir(args)
        result = run_reviewer_demo(args.input_dir, output_dir)
    except Exception as exc:  # noqa: BLE001 - CLI presents concise errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Evaluation Governance Reviewer Demo")
    print("")
    print("PASS generated offline chain artifacts")
    print("PASS generated reviewer evidence packet")
    print("PASS generated demo summary")
    print("")
    print(f"Output directory: {result.output_dir}")
    print("")
    print(f"Generated {len(result.artifact_paths)} reviewer-facing artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
