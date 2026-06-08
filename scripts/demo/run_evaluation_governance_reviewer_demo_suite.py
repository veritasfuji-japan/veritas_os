#!/usr/bin/env python3
"""Run the full synthetic Evaluation Governance reviewer demo suite.

This thin orchestration helper composes existing local/offline demo helpers:

1. Generate reviewer demo outputs.
2. Validate the generated outputs.
3. Generate the Markdown reviewer report.

It is intentionally non-runtime and non-enforcing. It does not call
``/v1/decide``, mutate production governance configuration, dereference
external artifact references, access the network, establish legitimacy, or
certify regulatory compliance.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.generate_evaluation_governance_reviewer_demo_report import (  # noqa: E501
    generate_reviewer_demo_report,
)
from scripts.demo.run_evaluation_governance_reviewer_demo import (
    DEFAULT_INPUT_DIR,
    EXAMPLE_OUTPUT_DIR,
    run_reviewer_demo,
)
from scripts.demo.validate_evaluation_governance_reviewer_demo import (
    ReviewerDemoValidationError,
    ReviewerDemoValidationResult,
    validate_reviewer_demo,
)

REPORT_FILE_NAME = "reviewer-demo-report.md"
EXAMPLE_REPORT_FILE_NAME = "reviewer-demo-report.generated.example.md"


@dataclass(frozen=True)
class ReviewerDemoSuiteResult:
    """Result metadata returned by ``run_reviewer_demo_suite``."""

    output_dir: Path
    report_path: Path
    validation_result: ReviewerDemoValidationResult


def resolve_output_dir(
    output_dir: Path | None = None,
    write_example_output: bool = False,
) -> Path:
    """Resolve the suite output directory while avoiding unsafe repo writes.

    Args:
        output_dir: Safe caller-provided output directory for generated files.
        write_example_output: Whether to intentionally update checked-in
            generated example outputs.

    Returns:
        The directory the suite should write.

    Raises:
        ValueError: If neither output mode is selected.
    """
    if output_dir is not None and write_example_output:
        raise ValueError(
            "--output-dir and --write-example-output are mutually exclusive"
        )
    if output_dir is not None:
        return output_dir
    if write_example_output:
        return EXAMPLE_OUTPUT_DIR
    raise ValueError(
        "--output-dir or --write-example-output is required; pass "
        "--output-dir for safe temporary output, or --write-example-output "
        "to intentionally update checked-in generated examples"
    )


def select_report_output_path(
    output_dir: Path,
    write_example_output: bool = False,
) -> Path:
    """Return the report path for temporary or checked-in example output."""
    file_name = EXAMPLE_REPORT_FILE_NAME if write_example_output else REPORT_FILE_NAME
    return output_dir / file_name


def run_reviewer_demo_suite(
    input_dir: Path,
    output_dir: Path | None = None,
    write_example_output: bool = False,
    verify_local_hashes: bool = False,
    artifact_base_dir: Path | None = None,
) -> ReviewerDemoSuiteResult:
    """Run generation, validation, and report creation for the reviewer demo.

    Args:
        input_dir: Directory containing synthetic offline-chain input files.
        output_dir: Optional safe output directory. Required unless
            ``write_example_output`` is true.
        write_example_output: Intentionally write the checked-in generated
            example output directory and generated example report.
        verify_local_hashes: When true, validate local artifact hash
            consistency for resolvable files before report generation.
        artifact_base_dir: Optional local base directory for resolving
            artifact references during local hash verification.

    Returns:
        Paths and validation metadata for the completed suite run.

    Raises:
        ValueError: If no output mode is selected.
        FileNotFoundError: If required local inputs are missing.
        ReviewerDemoValidationError: If generated outputs fail validation.
    """
    resolved_output_dir = resolve_output_dir(output_dir, write_example_output)
    run_result = run_reviewer_demo(input_dir, resolved_output_dir)
    validation_result = validate_reviewer_demo(
        run_result.output_dir,
        verify_local_hashes=verify_local_hashes,
        artifact_base_dir=artifact_base_dir,
    )
    report = generate_reviewer_demo_report(
        run_result.output_dir,
        validate=True,
        verify_local_hashes=verify_local_hashes,
        artifact_base_dir=artifact_base_dir,
    )
    report_path = select_report_output_path(
        run_result.output_dir,
        write_example_output,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return ReviewerDemoSuiteResult(
        output_dir=run_result.output_dir,
        report_path=report_path,
        validation_result=validation_result,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the reviewer demo suite."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the non-runtime Evaluation Governance reviewer demo suite: "
            "generate outputs, validate them, and write a Markdown report."
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
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help="Safe output directory for generated reviewer demo artifacts.",
    )
    output_group.add_argument(
        "--write-example-output",
        action="store_true",
        help=(
            "Intentionally overwrite checked-in reviewer demo generated "
            "examples and the generated example report."
        ),
    )
    parser.add_argument(
        "--artifact-base-dir",
        type=Path,
        help=(
            "Optional local base directory used only for resolving artifact "
            "references during --verify-local-hashes."
        ),
    )
    parser.add_argument(
        "--verify-local-hashes",
        action="store_true",
        help=(
            "Optionally verify artifact_hash values for local files that can "
            "be resolved without dereferencing external refs."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the Evaluation Governance reviewer demo suite CLI."""
    args = _parse_args(argv)
    try:
        result = run_reviewer_demo_suite(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            write_example_output=args.write_example_output,
            verify_local_hashes=args.verify_local_hashes,
            artifact_base_dir=args.artifact_base_dir,
        )
    except ReviewerDemoValidationError as exc:
        print("Evaluation Governance Reviewer Demo Suite", file=sys.stderr)
        print(f"FAIL {exc.check}", file=sys.stderr)
        print(f"File: {exc.path}", file=sys.stderr)
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI presents concise errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Evaluation Governance Reviewer Demo Suite")
    print("")
    print("PASS generated reviewer demo outputs")
    print("PASS validated reviewer demo outputs")
    if args.verify_local_hashes:
        print("PASS local hash consistency")
    print("PASS generated reviewer demo report")
    print("")
    print(f"Output directory: {result.output_dir}")
    print(f"Report: {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
