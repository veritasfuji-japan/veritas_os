#!/usr/bin/env python3
"""Generate a governance readiness report for VERITAS OS releases.

This script runs all governance-critical checks and produces a structured
JSON report plus a human-readable text summary. It is called by the
release-gate.yml workflow during the Tier 2 governance-report job.

Usage:
    python scripts/generate_release_readiness_report.py \
        --ref v2.0.1 \
        --sha abc1234 \
        --output release-artifacts/governance-readiness-report.json \
        --text-output release-artifacts/governance-readiness-report.txt

Exit code:
    0  — all blocking checks passed (release is governance-ready)
    1  — one or more blocking checks failed
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Check definitions ──────────────────────────────────────────────────────

# Each entry: (label, tier, command, blocking)
# blocking=True  → failure makes the release non-governance-ready
# blocking=False → advisory only (warning printed, exit code unaffected)
CHECKS: list[tuple[str, str, list[str], bool]] = [
    # Tier 1 — security invariants
    (
        "runtime-pickle-ban",
        "Tier 1",
        ["python", "scripts/security/check_runtime_pickle_artifacts.py"],
        True,
    ),
    (
        "bare-except-ban",
        "Tier 1",
        ["python", "scripts/security/check_bare_except_usage.py"],
        True,
    ),
    (
        "subprocess-shell-ban",
        "Tier 1",
        ["python", "scripts/security/check_subprocess_shell_usage.py"],
        True,
    ),
    (
        "unsafe-dynamic-execution",
        "Tier 1",
        ["python", "scripts/security/check_unsafe_dynamic_execution_usage.py"],
        True,
    ),
    (
        "httpx-raw-upload-ban",
        "Tier 1",
        ["python", "scripts/security/check_httpx_raw_upload_usage.py"],
        True,
    ),
    (
        "next-public-key-exposure",
        "Tier 1",
        ["python", "scripts/security/check_next_public_key_exposure.py"],
        True,
    ),
    # Tier 1 — architecture invariants
    (
        "responsibility-boundaries",
        "Tier 1",
        [
            "python",
            "scripts/architecture/check_responsibility_boundaries.py",
            "--report-format",
            "json",
        ],
        True,
    ),
    (
        "core-complexity-budget",
        "Tier 1",
        ["python", "scripts/architecture/check_core_complexity_budget.py"],
        True,
    ),
    # Tier 2 — quality gates
    (
        "replay-pipeline-version-rate",
        "Tier 2",
        [
            "python",
            "scripts/quality/check_replay_pipeline_version_unknown_rate.py",
            "--max-unknown-rate",
            "0.0",
        ],
        True,
    ),
    (
        "deployment-env-defaults",
        "Tier 2",
        ["python", "scripts/quality/check_deployment_env_defaults.py"],
        True,
    ),
    (
        "requirements-sync",
        "Tier 2",
        ["python", "scripts/quality/check_requirements_sync.py"],
        True,
    ),
    # Tier 2 — documentation consistency (advisory)
    (
        "operational-docs-consistency",
        "Tier 2",
        ["python", "scripts/quality/check_operational_docs_consistency.py"],
        False,
    ),
    (
        "frontend-docs-consistency",
        "Tier 2",
        ["python", "scripts/quality/check_frontend_docs_consistency.py"],
        False,
    ),
]


def run_check(
    label: str,
    command: list[str],
) -> tuple[bool, str]:
    """Run a single check command and return (passed, output_snippet)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        snippet = output[-500:] if len(output) > 500 else output
        return passed, snippet
    except subprocess.TimeoutExpired:
        return False, f"[TIMEOUT] check '{label}' exceeded 60s"
    except Exception as exc:  # noqa: BLE001
        return False, f"[ERROR] check '{label}' (cmd={command[0]}) failed: {exc}"


def build_report(
    ref: str,
    sha: str,
    results: list[dict],
) -> dict:
    """Build the structured governance readiness report."""
    blocking_failures = [r for r in results if not r["passed"] and r["blocking"]]
    advisory_failures = [r for r in results if not r["passed"] and not r["blocking"]]
    passed_count = sum(1 for r in results if r["passed"])

    return {
        "schema_version": "1.0",
        "report_type": "governance_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_ref": ref,
        "release_sha": sha,
        "summary": {
            "governance_ready": len(blocking_failures) == 0,
            "total_checks": len(results),
            "passed": passed_count,
            "blocking_failures": len(blocking_failures),
            "advisory_failures": len(advisory_failures),
        },
        "checks": results,
        "blocking_failures": [r["label"] for r in blocking_failures],
        "advisory_failures": [r["label"] for r in advisory_failures],
    }


def render_text_report(report: dict) -> str:
    """Render a human-readable text version of the governance readiness report."""
    lines = []
    summary = report["summary"]
    ready = summary["governance_ready"]

    sha_display = report["release_sha"][:12] + "..." if len(report["release_sha"]) > 12 else report["release_sha"]
    lines.append("=" * 62)
    lines.append("  VERITAS OS — Governance Readiness Report")
    lines.append(f"  Release:  {report['release_ref']}")
    lines.append(f"  SHA:      {sha_display}")
    lines.append(f"  Date:     {report['generated_at']}")
    lines.append("=" * 62)
    lines.append("")

    if ready:
        lines.append("  🟢  RELEASE IS GOVERNANCE-READY")
    else:
        lines.append("  🔴  RELEASE IS NOT GOVERNANCE-READY")
        lines.append(f"  {summary['blocking_failures']} blocking check(s) failed.")
    lines.append("")

    lines.append("  Check Summary")
    lines.append("  " + "-" * 58)
    for check in report["checks"]:
        icon = "✅" if check["passed"] else ("❌" if check["blocking"] else "⚠️ ")
        tag = "[BLOCKING]" if check["blocking"] else "[advisory]"
        lines.append(f"  {icon} {check['tier']:7s}  {tag:11s}  {check['label']}")
        if not check["passed"] and check.get("output"):
            for detail_line in textwrap.wrap(check["output"][:200], width=55):
                lines.append(f"           ↳ {detail_line}")
    lines.append("")

    lines.append("  Totals")
    lines.append("  " + "-" * 58)
    lines.append(f"  Total checks:       {summary['total_checks']}")
    lines.append(f"  Passed:             {summary['passed']}")
    lines.append(f"  Blocking failures:  {summary['blocking_failures']}")
    lines.append(f"  Advisory failures:  {summary['advisory_failures']}")
    lines.append("")

    lines.append("  How to tell if a release is governance-ready")
    lines.append("  " + "-" * 58)
    lines.append(
        textwrap.fill(
            "A VERITAS OS release is governance-ready when ALL of the following hold:",
            width=62,
            initial_indent="  ",
        )
    )
    lines.append("")
    lines.append(
        "  1. governance_ready = true  (no blocking check failures)"
    )
    lines.append(
        "  2. The release-gate workflow completed with status=success"
    )
    lines.append(
        "  3. Tier 2 production-tests job passed (pytest -m 'production or smoke')"
    )
    lines.append(
        "  4. Tier 2 docker-smoke job passed (full-stack health check)"
    )
    lines.append(
        "  5. The governance-readiness-report.json artifact is attached to the run"
    )
    lines.append("")
    lines.append(
        "  To verify: download the 'release-governance-readiness-report' artifact"
    )
    lines.append(
        "  from the release-gate.yml workflow run for the target tag."
    )
    lines.append("=" * 62)

    return "\n".join(lines)


def main() -> int:
    """Run all governance checks and emit a readiness report.

    Returns:
        0 if all blocking checks passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="unknown", help="Release ref (tag or branch)")
    parser.add_argument("--sha", default="unknown", help="Commit SHA")
    parser.add_argument(
        "--output",
        default="governance-readiness-report.json",
        help="Path for JSON report output",
    )
    parser.add_argument(
        "--text-output",
        default="governance-readiness-report.txt",
        help="Path for human-readable text report",
    )
    args = parser.parse_args()

    results = []
    logger.info("Running %d governance checks...", len(CHECKS))

    for label, tier, command, blocking in CHECKS:
        logger.info("  [%s] %s", tier, label)
        passed, output = run_check(label, command)
        status = "PASSED" if passed else ("FAILED" if blocking else "WARNING")
        logger.info("    → %s", status)
        results.append(
            {
                "label": label,
                "tier": tier,
                "blocking": blocking,
                "passed": passed,
                "output": output,
            }
        )

    report = build_report(ref=args.ref, sha=args.sha, results=results)
    text_report = render_text_report(report)

    # Write JSON report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("JSON report written: %s", output_path)

    # Write text report
    text_path = Path(args.text_output)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text_report, encoding="utf-8")
    logger.info("Text report written: %s", text_path)

    # Print text report to stdout
    print(text_report)

    # Exit with code 1 if any blocking check failed
    if not report["summary"]["governance_ready"]:
        logger.error(
            "%d blocking check(s) failed — release is NOT governance-ready.",
            report["summary"]["blocking_failures"],
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
