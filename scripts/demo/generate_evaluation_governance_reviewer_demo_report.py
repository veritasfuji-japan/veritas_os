#!/usr/bin/env python3
"""Generate a Markdown report for Evaluation Governance reviewer demos.

This helper is intentionally local/offline, non-runtime, and non-enforcing. It
summarizes an already generated Evaluation Governance reviewer demo directory
without calling ``/v1/decide``, dereferencing artifact references, accessing the
network, requiring secrets, or modifying input artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.validate_evaluation_governance_reviewer_demo import (  # noqa: E402
    ReviewerDemoValidationError,
    ReviewerDemoValidationResult,
    validate_reviewer_demo,
)

DEMO_SUMMARY_FILE_NAME = "demo-summary.generated.example.json"
CHAIN_MANIFEST_FILE_NAME = "chain-manifest.generated.example.json"
REVIEWER_PACKET_FILE_NAME = "reviewer-evidence-packet.generated.example.json"
TRAJECTORY_MONITOR_FILE_NAME = (
    "trajectory-admissibility-monitor.generated.example.json"
)
LEGITIMACY_REVIEW_FILE_NAME = "legitimacy-impact-review.generated.example.json"


@dataclass(frozen=True)
class ChainManifestSummary:
    """Reviewer-relevant chain manifest fields for report rendering."""

    chain_id: str
    issued_at: str
    artifact_count: int
    artifact_types: list[str]
    artifacts: list[dict[str, str]]


@dataclass(frozen=True)
class ReviewerPacketSummary:
    """Reviewer Evidence Packet attachment fields for report rendering."""

    packet_schema_version: str
    has_evaluation_governance_artifacts: bool
    attachment_count: int
    attachment_types: list[str]
    attachments: list[dict[str, str]]


@dataclass(frozen=True)
class TrajectoryMonitorSummary:
    """Trajectory-level admissibility monitor fields for report rendering."""

    trajectory_status: str
    recommended_governance_action: str
    scope_expanded: bool
    expansion_type: str
    risk_signals: list[dict[str, str]]


@dataclass(frozen=True)
class LegitimacyReviewSummary:
    """Legitimacy impact review fields for report rendering."""

    legitimacy_impact_detected: bool
    impact_categories: list[str]
    review_status: str
    recommended_governance_action: str


@dataclass(frozen=True)
class ReportInputs:
    """Loaded and summarized reviewer demo inputs for Markdown rendering."""

    demo_summary: dict[str, Any]
    chain_manifest: ChainManifestSummary
    reviewer_packet: ReviewerPacketSummary
    trajectory_monitor: TrajectoryMonitorSummary
    legitimacy_review: LegitimacyReviewSummary
    validation_result: ReviewerDemoValidationResult | None
    local_hash_verification_enabled: bool = False


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object without dereferencing artifact references."""
    if not path.is_file():
        raise FileNotFoundError(f"missing JSON file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def _string(value: Any, default: str = "not provided") -> str:
    """Return ``value`` as a report-safe string for simple Markdown fields."""
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _bool(value: Any) -> bool:
    """Return a strict boolean only when the JSON value is a boolean."""
    return value if isinstance(value, bool) else False


def _table_cell(value: Any) -> str:
    """Render a compact Markdown table cell without changing references."""
    return _string(value).replace("|", "\\|").replace("\n", " ")


def _unique_preserving_order(values: list[str]) -> list[str]:
    """Return unique strings in their first-seen order."""
    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def _require_demo_boundaries(demo_summary: dict[str, Any]) -> None:
    """Require non-runtime and non-enforcing demo boundaries."""
    if demo_summary.get("non_runtime") is not True:
        raise ValueError("demo-summary non_runtime must be true")
    if demo_summary.get("non_enforcing") is not True:
        raise ValueError("demo-summary non_enforcing must be true")


def summarize_chain_manifest(
    chain_manifest: dict[str, Any],
) -> ChainManifestSummary:
    """Summarize chain manifest artifacts without dereferencing refs."""
    artifacts_payload = chain_manifest.get("artifacts", [])
    artifacts = []
    artifact_types = []
    if isinstance(artifacts_payload, list):
        for artifact in artifacts_payload:
            if not isinstance(artifact, dict):
                continue
            artifact_type = _string(artifact.get("artifact_type"))
            artifact_ref = _string(artifact.get("artifact_ref"))
            artifacts.append(
                {
                    "artifact_type": artifact_type,
                    "artifact_ref": artifact_ref,
                }
            )
            artifact_types.append(artifact_type)

    return ChainManifestSummary(
        chain_id=_string(chain_manifest.get("chain_id")),
        issued_at=_string(chain_manifest.get("issued_at")),
        artifact_count=len(artifacts),
        artifact_types=_unique_preserving_order(artifact_types),
        artifacts=artifacts,
    )


def summarize_reviewer_packet(
    reviewer_packet: dict[str, Any],
) -> ReviewerPacketSummary:
    """Summarize Reviewer Evidence Packet attachments for review."""
    attachments_payload = reviewer_packet.get("evaluation_governance_artifacts")
    has_attachments = isinstance(attachments_payload, list)
    attachments = []
    attachment_types = []
    if isinstance(attachments_payload, list):
        for attachment in attachments_payload:
            if not isinstance(attachment, dict):
                continue
            attachment_type = _string(attachment.get("artifact_type"))
            attachments.append(
                {
                    "artifact_type": attachment_type,
                    "required_for_review": _string(
                        attachment.get("required_for_review")
                    ),
                    "schema_ref": _string(attachment.get("schema_ref")),
                }
            )
            attachment_types.append(attachment_type)

    return ReviewerPacketSummary(
        packet_schema_version=_string(
            reviewer_packet.get("schema_version")
            or reviewer_packet.get("packet_version")
        ),
        has_evaluation_governance_artifacts=has_attachments,
        attachment_count=len(attachments),
        attachment_types=_unique_preserving_order(attachment_types),
        attachments=attachments,
    )


def summarize_trajectory_monitor(
    trajectory_monitor: dict[str, Any],
) -> TrajectoryMonitorSummary:
    """Summarize trajectory-level admissibility monitor signals."""
    scope_change = trajectory_monitor.get("admissibility_scope_change", {})
    if not isinstance(scope_change, dict):
        scope_change = {}

    risk_signals_payload = trajectory_monitor.get("trajectory_risk_signals", [])
    risk_signals = []
    if isinstance(risk_signals_payload, list):
        for signal in risk_signals_payload:
            if not isinstance(signal, dict):
                continue
            risk_signals.append(
                {
                    "signal_type": _string(signal.get("signal_type")),
                    "severity": _string(signal.get("severity")),
                    "explanation": _string(signal.get("explanation")),
                }
            )

    return TrajectoryMonitorSummary(
        trajectory_status=_string(trajectory_monitor.get("trajectory_status")),
        recommended_governance_action=_string(
            trajectory_monitor.get("recommended_governance_action")
        ),
        scope_expanded=_bool(scope_change.get("scope_expanded")),
        expansion_type=_string(scope_change.get("expansion_type")),
        risk_signals=risk_signals,
    )


def summarize_legitimacy_review(
    legitimacy_review: dict[str, Any],
) -> LegitimacyReviewSummary:
    """Summarize legitimacy-impacting signals without determining legitimacy."""
    categories_payload = legitimacy_review.get("impact_categories", [])
    impact_categories = []
    if isinstance(categories_payload, list):
        impact_categories = [
            category for category in categories_payload if isinstance(category, str)
        ]

    return LegitimacyReviewSummary(
        legitimacy_impact_detected=_bool(
            legitimacy_review.get("legitimacy_impact_detected")
        ),
        impact_categories=impact_categories,
        review_status=_string(legitimacy_review.get("review_status")),
        recommended_governance_action=_string(
            legitimacy_review.get("recommended_governance_action")
        ),
    )


def _render_list(items: list[str], indent: str = "") -> list[str]:
    """Render a Markdown bullet list, using an explicit empty marker."""
    if not items:
        return [f"{indent}- none"]
    return [f"{indent}- `{item}`" for item in items]


def render_markdown_report(report_inputs: ReportInputs) -> str:
    """Render the reviewer-facing Markdown report."""
    demo_summary = report_inputs.demo_summary
    chain = report_inputs.chain_manifest
    packet = report_inputs.reviewer_packet
    monitor = report_inputs.trajectory_monitor
    review = report_inputs.legitimacy_review

    lines = [
        "# Evaluation Governance Reviewer Demo Report",
        "",
        "## 1. Report purpose",
        "",
        (
            "This report summarizes a synthetic, offline Evaluation Governance "
            "reviewer demo output."
        ),
        "",
        "Boundary statements:",
        "",
        "- This report is non-runtime.",
        "- This report is non-enforcing in v1.",
        "- This report does not call /v1/decide.",
        "- This report does not establish legitimacy.",
        "- This report does not certify regulatory compliance.",
        "- This report does not dereference external artifact refs.",
        "- This report does not require network access.",
        "",
        "## 2. Demo boundary",
        "",
        f"- demo_id: `{_string(demo_summary.get('demo_id'))}`",
        f"- issued_at: `{_string(demo_summary.get('issued_at'))}`",
        f"- non_runtime: `{_string(demo_summary.get('non_runtime'))}`",
        f"- non_enforcing: `{_string(demo_summary.get('non_enforcing'))}`",
        "- non_goals:",
    ]
    lines.extend(_render_list(demo_summary.get("non_goals", []), "  "))
    lines.extend(
        [
            "",
            "## 3. Generated artifact chain",
            "",
            f"- chain_id: `{chain.chain_id}`",
            f"- issued_at: `{chain.issued_at}`",
            f"- artifact count: `{chain.artifact_count}`",
            "- artifact types:",
        ]
    )
    lines.extend(_render_list(chain.artifact_types, "  "))
    lines.extend(
        [
            "",
            "| Artifact type | Artifact ref |",
            "| --- | --- |",
        ]
    )
    for artifact in chain.artifacts:
        lines.append(
            "| "
            f"{_table_cell(artifact['artifact_type'])} | "
            f"{_table_cell(artifact['artifact_ref'])} |"
        )

    lines.extend(
        [
            "",
            "## 4. Reviewer Evidence Packet attachments",
            "",
            f"- packet schema version: `{packet.packet_schema_version}`",
            "- evaluation_governance_artifacts exists: "
            f"`{_string(packet.has_evaluation_governance_artifacts)}`",
            "- Evaluation Governance attachment count: "
            f"`{packet.attachment_count}`",
            "- attachment types:",
        ]
    )
    lines.extend(_render_list(packet.attachment_types, "  "))
    lines.extend(
        [
            "",
            "| Attachment type | Required for review | Schema ref |",
            "| --- | --- | --- |",
        ]
    )
    for attachment in packet.attachments:
        lines.append(
            "| "
            f"{_table_cell(attachment['artifact_type'])} | "
            f"{_table_cell(attachment['required_for_review'])} | "
            f"{_table_cell(attachment['schema_ref'])} |"
        )
    lines.extend(
        [
            "",
            (
                "These are optional reviewer evidence attachments in v1, not "
                "mandatory runtime outputs."
            ),
            "",
            "## 5. Trajectory-level admissibility signals",
            "",
            f"- trajectory_status: `{monitor.trajectory_status}`",
            "- recommended_governance_action: "
            f"`{monitor.recommended_governance_action}`",
            "- admissibility_scope_change.scope_expanded: "
            f"`{_string(monitor.scope_expanded)}`",
            f"- expansion_type: `{monitor.expansion_type}`",
            "- trajectory_risk_signals:",
        ]
    )
    if monitor.risk_signals:
        for signal in monitor.risk_signals:
            lines.append(
                "  - "
                f"`{signal['signal_type']}` "
                f"({signal['severity']}): {signal['explanation']}"
            )
        lines.extend(
            [
                "",
                (
                    "These signals are reviewer-facing indicators, not runtime "
                    "enforcement outcomes."
                ),
            ]
        )
    else:
        lines.append("  - none")

    lines.extend(
        [
            "",
            "## 6. Legitimacy impact review signals",
            "",
            "- legitimacy_impact_detected: "
            f"`{_string(review.legitimacy_impact_detected)}`",
            f"- review_status: `{review.review_status}`",
            "- recommended_governance_action: "
            f"`{review.recommended_governance_action}`",
            "- impact_categories:",
        ]
    )
    lines.extend(_render_list(review.impact_categories, "  "))
    lines.extend(
        [
            "",
            (
                "VERITAS does not automatically create or guarantee legitimacy. "
                "This artifact surfaces legitimacy-impacting signals for review."
            ),
            "",
            "## 7. Validation status",
            "",
        ]
    )
    if report_inputs.validation_result is None:
        lines.extend(
            [
                "Validation status: NOT RUN",
                "",
                "Validation was not run for this report generation request.",
            ]
        )
    else:
        lines.extend(
            [
                "Validation status: PASS",
                "",
                "The reviewer demo validator confirmed:",
                "",
                "- expected files present",
                "- schema shape validated where schemas exist",
                "- safety boundaries checked",
                "- reviewer packet attachments checked",
            ]
        )
        if report_inputs.local_hash_verification_enabled:
            lines.extend(
                [
                    "- Local hash consistency: PASS",
                    (
                        "- Local hash checks: "
                        f"{report_inputs.validation_result.local_hash_checks_passed} "
                        "passed, "
                        f"{report_inputs.validation_result.local_hash_checks_skipped} "
                        "skipped"
                    ),
                ]
            )

    lines.extend(
        [
            "",
            "## 8. Reviewer inspection order",
            "",
            "1. `demo-summary.generated.example.json`",
            "2. `chain-manifest.generated.example.json`",
            "3. `reviewer-evidence-packet.generated.example.json`",
            "4. `trajectory-admissibility-monitor.generated.example.json`",
            "5. `legitimacy-impact-review.generated.example.json`",
            "",
            "## 9. Non-goals",
            "",
            "- This report does not claim regulatory compliance.",
            "- This report does not claim automatic legitimacy determination.",
            "- This report does not change runtime behavior.",
            "- This report does not certify governance correctness.",
            (
                "- This report does not replace human, legal, compliance, or "
                "audit review."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def generate_reviewer_demo_report(
    demo_dir: Path | str,
    validate: bool = True,
    verify_local_hashes: bool = False,
    artifact_base_dir: Path | str | None = None,
) -> str:
    """Generate a Markdown report from a local reviewer demo output directory.

    Args:
        demo_dir: Directory containing generated reviewer demo artifacts.
        validate: Whether to run the local reviewer demo validator first.
        verify_local_hashes: When true and validation is enabled, compare
            artifact_hash values with local files that can be resolved without
            network access.
        artifact_base_dir: Optional local base directory for resolving artifact
            references during local hash verification.

    Returns:
        Human-readable Markdown report content.

    Raises:
        ReviewerDemoValidationError: If validation is enabled and fails.
        ValueError: If required non-runtime/non-enforcing boundaries are absent.
        FileNotFoundError: If required report input files are missing.
    """
    resolved_demo_dir = Path(demo_dir).resolve()
    resolved_artifact_base_dir = (
        Path(artifact_base_dir).resolve()
        if artifact_base_dir is not None
        else None
    )
    validation_result = (
        validate_reviewer_demo(
            resolved_demo_dir,
            verify_local_hashes=verify_local_hashes,
            artifact_base_dir=resolved_artifact_base_dir,
        )
        if validate
        else None
    )

    demo_summary = load_json(resolved_demo_dir / DEMO_SUMMARY_FILE_NAME)
    _require_demo_boundaries(demo_summary)
    chain_manifest = load_json(resolved_demo_dir / CHAIN_MANIFEST_FILE_NAME)
    reviewer_packet = load_json(resolved_demo_dir / REVIEWER_PACKET_FILE_NAME)
    trajectory_monitor = load_json(resolved_demo_dir / TRAJECTORY_MONITOR_FILE_NAME)
    legitimacy_review = load_json(resolved_demo_dir / LEGITIMACY_REVIEW_FILE_NAME)

    report_inputs = ReportInputs(
        demo_summary=demo_summary,
        chain_manifest=summarize_chain_manifest(chain_manifest),
        reviewer_packet=summarize_reviewer_packet(reviewer_packet),
        trajectory_monitor=summarize_trajectory_monitor(trajectory_monitor),
        legitimacy_review=summarize_legitimacy_review(legitimacy_review),
        validation_result=validation_result,
        local_hash_verification_enabled=verify_local_hashes,
    )
    return render_markdown_report(report_inputs)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for report generation."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a local, non-runtime Evaluation Governance reviewer "
            "demo Markdown report."
        )
    )
    parser.add_argument(
        "--demo-dir",
        required=True,
        type=Path,
        help="Directory containing generated reviewer demo artifacts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional Markdown output path. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate the demo directory before generating the report.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="Skip validation and render only from local JSON inputs.",
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


def _print_failure(error: Exception) -> None:
    """Print a concise report generation failure to stderr."""
    print("FAIL generated reviewer demo report", file=sys.stderr)
    if isinstance(error, ReviewerDemoValidationError):
        print(f"Check: {error.check}", file=sys.stderr)
        print(f"File: {error.path}", file=sys.stderr)
        print(f"Error: {error.message}", file=sys.stderr)
        return
    print(f"Error: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Run the reviewer demo report generator CLI."""
    args = _parse_args(argv)
    try:
        report = generate_reviewer_demo_report(
            args.demo_dir,
            args.validate,
            verify_local_hashes=args.verify_local_hashes,
            artifact_base_dir=args.artifact_base_dir,
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            print("PASS generated reviewer demo report")
            print(f"Output: {args.output}")
        else:
            print(report, end="")
    except Exception as exc:  # noqa: BLE001
        _print_failure(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
