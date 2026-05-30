#!/usr/bin/env python3
"""Build a deterministic local/offline Reviewer Evidence Bundle v1."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.build_reviewer_evidence_artifact_manifest import (  # noqa: E402
    ARTIFACT_NAME,
    write_reviewer_evidence_artifact_manifest,
)
from scripts.demo.build_reviewer_evidence_step_summary import (  # noqa: E402
    write_reviewer_evidence_step_summary,
)
from scripts.demo.export_reviewer_evidence_packet import (  # noqa: E402
    build_reviewer_evidence_packet,
)
from scripts.demo.validate_reviewer_evidence_packet import (  # noqa: E402
    build_reviewer_evidence_packet_validation_report,
)
from scripts.demo.verify_reviewer_evidence_artifact_manifest import (  # noqa: E402
    verify_reviewer_evidence_artifact_manifest,
)

BUNDLE_ID = "reviewer-evidence-bundle-v1"
BUNDLE_VERSION = "v1"
DEFAULT_OUTPUT_DIR = Path("artifacts/reviewer-evidence-packet")
BOUNDARY_NOTE = (
    "local/offline reviewer evidence bundle only; no live SaaS/IAM/IdP/SSO/"
    "customer/bank/sanctions/production approval integration; not production "
    "audit certification"
)
REVIEWER_NOTES = [
    (
        "This bundle is generated locally/offline from VERITAS reviewer "
        "evidence scripts and checked-in artifacts."
    ),
    (
        "It mirrors the reviewer evidence artifacts produced by the "
        "GitHub Actions validation workflow."
    ),
    (
        "It includes the validation report, generated packet, golden fixture, "
        "schema, artifact manifest, manifest verification report, and step "
        "summary."
    ),
    (
        "It does not connect to live SaaS, IAM, IdP, SSO, customer "
        "directories, banks, sanctions systems, production approval workflows, "
        "or live audit stores."
    ),
    (
        "It is not legal advice, regulatory approval, third-party "
        "certification, production audit certification, or proof of live "
        "deployment."
    ),
]
SOURCE_FILES = {
    "reviewer-evidence-packet-golden-fixture.json": REPO_ROOT
    / "docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json",
    "reviewer-evidence-packet-schema.json": REPO_ROOT
    / "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json",
    "external-reviewer-quickstart.md": REPO_ROOT
    / "docs/en/demo/external-reviewer-quickstart.md",
    "external-reviewer-artifact-index.md": REPO_ROOT
    / "docs/en/demo/external-reviewer-artifact-index.md",
}
GENERATED_FILE_ROLES = {
    "reviewer-evidence-packet-validation-report.json": "validation_report",
    "reviewer-evidence-packet-generated.json": "generated_packet",
    "reviewer-evidence-packet-golden-fixture.json": "golden_fixture",
    "reviewer-evidence-packet-schema.json": "json_schema",
    "reviewer-evidence-artifact-manifest.json": "artifact_manifest",
    "reviewer-evidence-artifact-manifest-verification-report.json": (
        "artifact_manifest_verification_report"
    ),
    "reviewer-evidence-step-summary.md": "step_summary",
    "external-reviewer-quickstart.md": "quickstart_doc",
    "external-reviewer-artifact-index.md": "artifact_index_doc",
}
REQUIRED_FILENAMES = list(GENERATED_FILE_ROLES)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON to ``path``."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_required_sources(output_path: Path) -> list[str]:
    """Copy checked-in reviewer artifacts and return failure reason strings."""
    failures: list[str] = []
    for filename, source_path in SOURCE_FILES.items():
        if not source_path.is_file():
            failures.append(f"reviewer_evidence_bundle_source_missing:{filename}")
            continue
        shutil.copyfile(source_path, output_path / filename)
    return failures


def _file_summary(output_path: Path, filename: str) -> dict[str, Any]:
    """Return deterministic metadata for one bundle output file."""
    file_path = output_path / filename
    exists = file_path.is_file()
    return {
        "path": filename,
        "role": GENERATED_FILE_ROLES[filename],
        "required": True,
        "exists": exists,
        "size_bytes": file_path.stat().st_size if exists else 0,
    }


def _required_file_failure(filename: str) -> str | None:
    """Return a deterministic specific failure reason for a missing file."""
    return {
        "reviewer-evidence-packet-generated.json": (
            "reviewer_evidence_bundle_generated_packet_missing"
        ),
        "reviewer-evidence-packet-golden-fixture.json": (
            "reviewer_evidence_bundle_golden_fixture_missing"
        ),
        "reviewer-evidence-packet-schema.json": (
            "reviewer_evidence_bundle_schema_missing"
        ),
        "reviewer-evidence-artifact-manifest.json": (
            "reviewer_evidence_bundle_manifest_missing"
        ),
        "reviewer-evidence-step-summary.md": (
            "reviewer_evidence_bundle_step_summary_missing"
        ),
    }.get(filename)


def _append_unique(target: list[str], values: list[str]) -> None:
    """Append values to ``target`` while preserving deterministic first order."""
    for value in values:
        if value not in target:
            target.append(value)


def _aggregate_summary(
    *,
    generated_files: list[dict[str, Any]],
    validation_report: dict[str, Any],
    manifest_verification_report: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic aggregate bundle counts."""
    validation_summary = validation_report.get("aggregate_summary", {})
    verification_summary = manifest_verification_report.get("aggregate_summary", {})
    return {
        "total_files": len(generated_files),
        "required_files": sum(
            1 for file_entry in generated_files if file_entry["required"]
        ),
        "existing_files": sum(
            1 for file_entry in generated_files if file_entry["exists"]
        ),
        "missing_files": sum(
            1 for file_entry in generated_files if not file_entry["exists"]
        ),
        "total_size_bytes": sum(
            file_entry["size_bytes"] for file_entry in generated_files
        ),
        "validation_total_cases": validation_summary.get("total_cases", 0),
        "validation_passed_cases": validation_summary.get("passed_cases", 0),
        "manifest_verified_files": verification_summary.get("verified_files", 0),
        "local_offline_only": True,
    }


def _failure_summary(
    *,
    output_path: Path,
    validation_report: dict[str, Any],
    manifest_verification_report: dict[str, Any],
    generation_failures: list[str],
) -> list[str]:
    """Return deterministic bundle failure reason strings."""
    failures = list(generation_failures)
    if validation_report.get("status") != "pass":
        failures.append("reviewer_evidence_bundle_validation_report_failed")
    if manifest_verification_report.get("status") != "pass":
        failures.append("reviewer_evidence_bundle_manifest_verification_failed")

    missing_required = False
    for filename in REQUIRED_FILENAMES:
        if (output_path / filename).is_file():
            continue
        missing_required = True
        specific_failure = _required_file_failure(filename)
        if specific_failure is not None:
            failures.append(specific_failure)
    if missing_required:
        failures.append("reviewer_evidence_bundle_required_file_missing")
    return list(dict.fromkeys(failures))


def _base_summary(
    *,
    output_path: Path,
    generated_files: list[dict[str, Any]] | None = None,
    validation_report: dict[str, Any] | None = None,
    manifest_verification_report: dict[str, Any] | None = None,
    failure_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Build the deterministic JSON-friendly bundle summary."""
    files = generated_files or [
        _file_summary(output_path, filename) for filename in REQUIRED_FILENAMES
    ]
    validation = validation_report or {}
    verification = manifest_verification_report or {}
    failures = failure_reasons or []
    return {
        "bundle_id": BUNDLE_ID,
        "bundle_version": BUNDLE_VERSION,
        "status": "pass" if not failures else "fail",
        "output_dir": str(output_path),
        "local_offline_only": True,
        "artifact_name": ARTIFACT_NAME,
        "generated_files": files,
        "validation_status": validation.get("status"),
        "artifact_manifest_status": "pass"
        if (output_path / "reviewer-evidence-artifact-manifest.json").is_file()
        else "fail",
        "artifact_manifest_verification_status": verification.get("status"),
        "step_summary_written": (
            output_path / "reviewer-evidence-step-summary.md"
        ).is_file(),
        "aggregate_summary": _aggregate_summary(
            generated_files=files,
            validation_report=validation,
            manifest_verification_report=verification,
        ),
        "failure_reasons": failures,
        "reviewer_notes": list(REVIEWER_NOTES),
        "boundary_note": BOUNDARY_NOTE,
    }


def build_reviewer_evidence_bundle(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Build the complete local/offline Reviewer Evidence Bundle v1.

    Args:
        output_dir: Directory where bundle artifacts should be written.

    Returns:
        Deterministic JSON-friendly summary with pass/fail status, generated file
        metadata, aggregate counts, reviewer notes, and local/offline boundary.
    """
    output_path = Path(output_dir)
    generation_failures: list[str] = []
    validation_report: dict[str, Any] = {}
    manifest_verification_report: dict[str, Any] = {}

    if output_path.exists() and not output_path.is_dir():
        return _base_summary(
            output_path=output_path,
            failure_reasons=["reviewer_evidence_bundle_output_dir_invalid"],
        )

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        validation_report = build_reviewer_evidence_packet_validation_report()
        _write_json(
            output_path / "reviewer-evidence-packet-validation-report.json",
            validation_report,
        )
        _write_json(
            output_path / "reviewer-evidence-packet-generated.json",
            build_reviewer_evidence_packet(),
        )
        _append_unique(generation_failures, _copy_required_sources(output_path))
        artifact_manifest = write_reviewer_evidence_artifact_manifest(
            artifact_dir=output_path,
        )
        manifest_verification_report = verify_reviewer_evidence_artifact_manifest(
            artifact_dir=output_path,
        )
        _write_json(
            output_path
            / "reviewer-evidence-artifact-manifest-verification-report.json",
            manifest_verification_report,
        )
        write_reviewer_evidence_step_summary(
            artifact_dir=output_path,
            validation_report=validation_report,
            artifact_manifest=artifact_manifest,
            manifest_verification_report=manifest_verification_report,
        )
    except (OSError, ValueError, TypeError) as exc:
        generation_failures.append(
            f"reviewer_evidence_bundle_generation_failed:{exc.__class__.__name__}"
        )

    generated_files = [
        _file_summary(output_path, filename) for filename in REQUIRED_FILENAMES
    ]
    failure_reasons = _failure_summary(
        output_path=output_path,
        validation_report=validation_report,
        manifest_verification_report=manifest_verification_report,
        generation_failures=generation_failures,
    )
    return _base_summary(
        output_path=output_path,
        generated_files=generated_files,
        validation_report=validation_report,
        manifest_verification_report=manifest_verification_report,
        failure_reasons=failure_reasons,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build the local/offline Reviewer Evidence Bundle v1."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for Reviewer Evidence Bundle artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Build the bundle, print deterministic JSON, and return status code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    summary = build_reviewer_evidence_bundle(output_dir=args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
