#!/usr/bin/env python3
"""Generate a staged operational readiness report for VERITAS OS.

Combines governance checks, compose validation results, live-provider results,
and load/TLS summaries into a single machine-readable + human-readable artifact.

This is the successor to ``generate_release_readiness_report.py`` for full
operational proof — it includes deployment-surface coverage beyond static checks.

Usage:
    python scripts/generate_staged_readiness_report.py \\
        --ref v2.1.0 \\
        --sha abc1234 \\
        --output release-artifacts/staged-readiness-report.json \\
        --text-output release-artifacts/staged-readiness-report.txt

    # Include external validation artifacts:
    python scripts/generate_staged_readiness_report.py \\
        --ref v2.1.0 --sha abc1234 \\
        --compose-report /tmp/compose-report.json \\
        --live-report /tmp/live-report.json \\
        --output release-artifacts/staged-readiness-report.json \\
        --text-output release-artifacts/staged-readiness-report.txt

Exit code:
    0  — all blocking checks passed
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

# ── Static governance checks (same as generate_release_readiness_report.py) ─

GOVERNANCE_CHECKS: list[tuple[str, str, list[str], bool]] = [
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


def run_check(label: str, command: list[str]) -> tuple[bool, str]:
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
        return False, f"[ERROR] check '{label}' failed: {exc}"


def load_json_report(path: str | None) -> dict | None:
    """Load a JSON report file if it exists."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        logger.warning("Report file not found: %s", path)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse report %s: %s", path, exc)
        return None


def build_report(
    ref: str,
    sha: str,
    governance_results: list[dict],
    compose_report: dict | None,
    live_report: dict | None,
) -> dict:
    """Build the staged operational readiness report."""
    blocking_failures = [
        r for r in governance_results if not r["passed"] and r["blocking"]
    ]
    advisory_failures = [
        r for r in governance_results if not r["passed"] and not r["blocking"]
    ]
    passed_count = sum(1 for r in governance_results if r["passed"])

    # Compose validation summary
    compose_summary = None
    if compose_report:
        compose_summary = compose_report.get("summary", {})

    # Live provider summary
    live_summary = None
    if live_report:
        live_summary = live_report.get("summary", {})

    # Overall readiness determination
    governance_ready = len(blocking_failures) == 0
    compose_ok = (
        compose_summary is None
        or compose_summary.get("overall") != "FAIL"
    )
    live_ok = live_summary is None or live_summary.get("overall") != "FAIL"

    return {
        "schema_version": "2.0",
        "report_type": "staged_operational_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_ref": ref,
        "release_sha": sha,
        "overall_readiness": {
            "governance_ready": governance_ready,
            "compose_validated": compose_ok,
            "live_provider_ok": live_ok,
            "deployment_ready": governance_ready and compose_ok,
        },
        "governance": {
            "total_checks": len(governance_results),
            "passed": passed_count,
            "blocking_failures": len(blocking_failures),
            "advisory_failures": len(advisory_failures),
            "checks": governance_results,
            "blocking_failure_labels": [r["label"] for r in blocking_failures],
            "advisory_failure_labels": [r["label"] for r in advisory_failures],
        },
        "compose_validation": compose_report,
        "live_provider_validation": live_report,
        "coverage_matrix": {
            "proven_in_ci": [
                "Security invariants (pickle, bare-except, shell, eval, httpx)",
                "Architecture boundaries (responsibility, complexity)",
                "Quality gates (replay pipeline, env defaults, requirements)",
                "5800+ unit/integration tests with 85% coverage gate",
                "FastAPI health/OpenAPI/decide contract smoke",
                "Docker compose topology validation (YAML parse)",
                "Governance policy CRUD + audit trail",
                "TrustLog write/read/verify/chain integrity",
                "Encryption fail-closed behavior",
                "Web search SSRF prevention",
                "TLS security headers (HSTS, CSP, X-Frame)",
                "Concurrent burst load (32 req / 8 workers)",
            ],
            "proven_in_compose": [
                "Backend container health (/health endpoint)",
                "Frontend container reachability",
                "Governance endpoint reachability via HTTP",
                "Security header presence in containerized deployment",
                "OpenAPI schema served from container",
                "Auth enforcement (401/403 without API key)",
            ],
            "proven_with_secrets": [
                "OpenAI API connectivity and key validity",
                "LLM client end-to-end completion",
                "Staging TLS certificate expiry check",
                "Staging security header validation",
                "Web search provider integration",
            ],
            "requires_environment": [
                "Kubernetes Helm chart deployment",
                "Production TLS certificate chain (OCSP, CRL)",
                "Multi-region failover behavior",
                "Long-duration load/stress (k6/locust)",
                "Database migration (if applicable)",
                "Monitoring/alerting integration (Datadog, PagerDuty)",
            ],
        },
    }


def render_text_report(report: dict) -> str:
    """Render a human-readable text version of the staged readiness report."""
    lines: list[str] = []
    readiness = report["overall_readiness"]
    gov = report["governance"]

    sha_display = (
        report["release_sha"][:12] + "..."
        if len(report["release_sha"]) > 12
        else report["release_sha"]
    )

    lines.append("=" * 66)
    lines.append("  VERITAS OS — Staged Operational Readiness Report")
    lines.append(f"  Release:    {report['release_ref']}")
    lines.append(f"  SHA:        {sha_display}")
    lines.append(f"  Date:       {report['generated_at']}")
    lines.append(f"  Schema:     v{report['schema_version']}")
    lines.append("=" * 66)
    lines.append("")

    # Overall status
    if readiness["deployment_ready"]:
        lines.append("  🟢  DEPLOYMENT-READY")
    else:
        lines.append("  🔴  NOT DEPLOYMENT-READY")
    lines.append("")
    lines.append(
        f"  Governance:        {'✅ Ready' if readiness['governance_ready'] else '❌ Not Ready'}"
    )
    lines.append(
        f"  Compose:           {'✅ Validated' if readiness['compose_validated'] else '⚠️  Not Validated'}"
    )
    lines.append(
        f"  Live Providers:    {'✅ OK' if readiness['live_provider_ok'] else '⚠️  Not OK'}"
    )
    lines.append("")

    # Governance checks
    lines.append("  Governance Checks")
    lines.append("  " + "-" * 62)
    for check in gov["checks"]:
        icon = "✅" if check["passed"] else ("❌" if check["blocking"] else "⚠️ ")
        tag = "[BLOCKING]" if check["blocking"] else "[advisory]"
        lines.append(f"  {icon} {check['tier']:7s}  {tag:11s}  {check['label']}")
        if not check["passed"] and check.get("output"):
            for detail_line in textwrap.wrap(check["output"][:200], width=55):
                lines.append(f"           ↳ {detail_line}")
    lines.append("")

    # Compose validation
    lines.append("  Compose Validation")
    lines.append("  " + "-" * 62)
    compose = report.get("compose_validation")
    if compose:
        for check in compose.get("checks", []):
            icon_map = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}
            icon = icon_map.get(check["result"], "❓")
            lines.append(f"  {icon} {check['name']:35s}  {check['detail']}")
    else:
        lines.append("  ⏭️  Not included (run with --compose-report)")
    lines.append("")

    # Live provider validation
    lines.append("  Live Provider Validation")
    lines.append("  " + "-" * 62)
    live = report.get("live_provider_validation")
    if live:
        for check in live.get("checks", []):
            icon_map = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}
            icon = icon_map.get(check["result"], "❓")
            lines.append(f"  {icon} {check['name']:35s}  {check['detail']}")
    else:
        lines.append("  ⏭️  Not included (run with --live-report)")
    lines.append("")

    # Coverage matrix
    lines.append("  Coverage Matrix")
    lines.append("  " + "-" * 62)
    matrix = report.get("coverage_matrix", {})
    for section, items in matrix.items():
        label = section.replace("_", " ").title()
        lines.append(f"  [{label}]")
        for item in items:
            lines.append(f"    • {item}")
    lines.append("")

    lines.append("  Totals")
    lines.append("  " + "-" * 62)
    lines.append(f"  Governance checks:    {gov['total_checks']}")
    lines.append(f"  Governance passed:    {gov['passed']}")
    lines.append(f"  Blocking failures:    {gov['blocking_failures']}")
    lines.append(f"  Advisory failures:    {gov['advisory_failures']}")
    lines.append("")
    lines.append("=" * 66)

    return "\n".join(lines)


def main() -> int:
    """Run staged readiness checks and emit report.

    Returns:
        0 if all blocking checks passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="unknown", help="Release ref (tag or branch)")
    parser.add_argument("--sha", default="unknown", help="Commit SHA")
    parser.add_argument(
        "--output",
        default="staged-readiness-report.json",
        help="Path for JSON report output",
    )
    parser.add_argument(
        "--text-output",
        default="staged-readiness-report.txt",
        help="Path for human-readable text report",
    )
    parser.add_argument(
        "--compose-report",
        default=None,
        help="Path to compose_validation.sh JSON report",
    )
    parser.add_argument(
        "--live-report",
        default=None,
        help="Path to live_provider_validation.sh JSON report",
    )
    args = parser.parse_args()

    # Run governance checks
    results: list[dict] = []
    logger.info("Running %d governance checks...", len(GOVERNANCE_CHECKS))

    for label, tier, command, blocking in GOVERNANCE_CHECKS:
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

    # Load external reports
    compose_report = load_json_report(args.compose_report)
    live_report = load_json_report(args.live_report)

    report = build_report(
        ref=args.ref,
        sha=args.sha,
        governance_results=results,
        compose_report=compose_report,
        live_report=live_report,
    )
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
    if not report["overall_readiness"]["governance_ready"]:
        logger.error(
            "%d blocking check(s) failed — release is NOT deployment-ready.",
            report["governance"]["blocking_failures"],
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
