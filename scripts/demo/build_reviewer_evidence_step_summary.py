#!/usr/bin/env python3
"""Build a deterministic local/offline reviewer evidence step summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.build_reviewer_evidence_artifact_manifest import (  # noqa: E402
    ARTIFACT_NAME,
)

SUMMARY_TITLE = "Reviewer Evidence Packet Validation Summary"
BOUNDARY_NOTE = (
    "local/offline reviewer evidence summary only; no live SaaS/IAM/IdP/SSO/"
    "customer/bank/sanctions/production approval integration; not production "
    "audit certification"
)


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object from ``path`` or return an empty object."""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_icon(status: str | None) -> str:
    """Return a deterministic Markdown status icon."""
    return "✅" if status == "pass" else "❌"


def build_reviewer_evidence_step_summary(
    *,
    artifact_dir: Path | str,
    validation_report: dict[str, Any] | None = None,
    artifact_manifest: dict[str, Any] | None = None,
    manifest_verification_report: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic GitHub Step Summary-compatible Markdown string.

    Args:
        artifact_dir: Local directory containing reviewer evidence artifacts.
        validation_report: Optional prebuilt validation report.
        artifact_manifest: Optional prebuilt artifact manifest.
        manifest_verification_report: Optional prebuilt manifest verification report.

    Returns:
        Markdown summary for reviewer-facing local/offline evidence artifacts.
    """
    artifact_path = Path(artifact_dir)
    validation = validation_report or _read_json_object(
        artifact_path / "reviewer-evidence-packet-validation-report.json"
    )
    manifest = artifact_manifest or _read_json_object(
        artifact_path / "reviewer-evidence-artifact-manifest.json"
    )
    verification = manifest_verification_report or _read_json_object(
        artifact_path
        / "reviewer-evidence-artifact-manifest-verification-report.json"
    )

    validation_status = validation.get("status")
    verification_status = verification.get("status")
    packet_summary = validation.get("aggregate_summary", {})
    manifest_summary = manifest.get("aggregate_summary", {})
    verification_summary = verification.get("aggregate_summary", {})
    files = manifest.get("files", []) if isinstance(manifest.get("files"), list) else []

    lines = [
        f"# {SUMMARY_TITLE}",
        "",
        (
            "This deterministic summary describes local/offline reviewer "
            "evidence artifacts."
        ),
        "",
        "## Status",
        "",
        "| Check | Status |",
        "| --- | --- |",
        (
            "| Reviewer Evidence Packet validation | "
            f"{_status_icon(validation_status)} "
            f"{validation_status or 'unknown'} |"
        ),
        (
            "| Artifact manifest verification | "
            f"{_status_icon(verification_status)} "
            f"{verification_status or 'unknown'} |"
        ),
        "",
        "## Artifact bundle",
        "",
        f"- Artifact name: `{ARTIFACT_NAME}`",
        (
            "- Local/offline only: "
            f"`{str(validation.get('local_offline_only') is True).lower()}`"
        ),
        f"- Total cases: `{packet_summary.get('total_cases', 0)}`",
        f"- Passed cases: `{packet_summary.get('passed_cases', 0)}`",
        f"- Blocked cases: `{packet_summary.get('blocked_cases', 0)}`",
        f"- Committed cases: `{packet_summary.get('committed_cases', 0)}`",
        f"- Manifest files: `{manifest_summary.get('total_files', len(files))}`",
        f"- Verified files: `{verification_summary.get('verified_files', 0)}`",
        "",
        "## Files",
        "",
        "| Path | Role | Required | Size bytes |",
        "| --- | --- | --- | ---: |",
    ]

    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        lines.append(
            "| `{path}` | `{role}` | `{required}` | `{size}` |".format(
                path=file_entry.get("path", ""),
                role=file_entry.get("role", ""),
                required=str(file_entry.get("required") is True).lower(),
                size=file_entry.get("size_bytes", 0),
            )
        )

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            BOUNDARY_NOTE,
            "",
        ]
    )
    return "\n".join(lines)


def write_reviewer_evidence_step_summary(
    *,
    artifact_dir: Path | str,
    output_path: Path | str | None = None,
    validation_report: dict[str, Any] | None = None,
    artifact_manifest: dict[str, Any] | None = None,
    manifest_verification_report: dict[str, Any] | None = None,
) -> str:
    """Build and write the deterministic reviewer evidence step summary."""
    artifact_path = Path(artifact_dir)
    destination = (
        Path(output_path)
        if output_path is not None
        else artifact_path / "reviewer-evidence-step-summary.md"
    )
    summary = build_reviewer_evidence_step_summary(
        artifact_dir=artifact_path,
        validation_report=validation_report,
        artifact_manifest=artifact_manifest,
        manifest_verification_report=manifest_verification_report,
    )
    destination.write_text(summary, encoding="utf-8")
    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build the Reviewer Evidence Packet step summary."
    )
    parser.add_argument("artifact_dir", help="Reviewer evidence artifact directory")
    parser.add_argument(
        "--output-path",
        help="Optional output path for reviewer-evidence-step-summary.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Write the step summary and print it to stdout."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    summary = write_reviewer_evidence_step_summary(
        artifact_dir=args.artifact_dir,
        output_path=args.output_path,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
