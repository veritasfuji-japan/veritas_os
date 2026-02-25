#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate PR impact summaries from changed files.

This helper produces a markdown table designed for pull request descriptions.
For each changed file it estimates:
- responsibility area
- expected risk
- required tests

The script is intentionally conservative: unknown paths are marked as "medium"
risk and ask for focused regression checks.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ImpactRow:
    """One line of PR impact summary."""

    file_path: str
    responsibility: str
    risk: str
    required_tests: str


def _run_git_diff_name_only(base_ref: str, head_ref: str) -> list[str]:
    """Return changed file paths from git diff.

    Args:
        base_ref: Git revision used as the left side of diff.
        head_ref: Git revision used as the right side of diff.

    Returns:
        A list of changed file paths.

    Raises:
        RuntimeError: If git command execution fails.
    """
    cmd = ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(f"git diff failed: {stderr}")

    files = [line.strip() for line in completed.stdout.splitlines()]
    return [file_path for file_path in files if file_path]


def _contains_security_sensitive_parts(parts: Iterable[str]) -> bool:
    """Return True when path indicates security-sensitive changes."""
    sensitive_tokens = {
        "security",
        "auth",
        "oauth",
        "token",
        "secrets",
        "sanitize",
        "llm_safety",
    }
    lowered = {part.lower() for part in parts}
    return any(token in lowered for token in sensitive_tokens)


def infer_impact(file_path: str) -> ImpactRow:
    """Infer responsibility, risk, and required tests from file path."""
    p = Path(file_path)
    parts = p.parts

    if file_path.startswith("veritas_os/core/planner"):
        return ImpactRow(
            file_path=file_path,
            responsibility="Planner: planning strategy and task generation",
            risk=(
                "high (plan quality or execution priority can regress; "
                "verify Planner boundary only)"
            ),
            required_tests="pytest veritas_os/tests/test_planner.py",
        )

    if file_path.startswith("veritas_os/core/kernel"):
        return ImpactRow(
            file_path=file_path,
            responsibility="Kernel: orchestration and execution flow",
            risk="high (runtime flow and integration stability)",
            required_tests="pytest veritas_os/tests/test_kernel_core.py",
        )

    if file_path.startswith("veritas_os/core/fuji"):
        return ImpactRow(
            file_path=file_path,
            responsibility="Fuji: policy and risk judgement",
            risk="high (safety policy or risk judgement drift)",
            required_tests="pytest veritas_os/tests/test_fuji_policy_guardrails.py",
        )

    if file_path.startswith("veritas_os/core/memory"):
        return ImpactRow(
            file_path=file_path,
            responsibility="MemoryOS: memory persistence/search behavior",
            risk="high (recall quality, storage compatibility)",
            required_tests="pytest veritas_os/tests/test_memory_coverage.py",
        )

    if file_path.startswith("frontend/"):
        return ImpactRow(
            file_path=file_path,
            responsibility="Frontend: UI and client-side behavior",
            risk="medium (UX regression, component integration)",
            required_tests="pnpm --filter frontend test",
        )

    if file_path.startswith("veritas_os/api/"):
        risk = "high (API contract changes impact external consumers)"
        if _contains_security_sensitive_parts(parts):
            risk = (
                "high (security-sensitive API change; validate auth/input "
                "sanitization)"
            )
        return ImpactRow(
            file_path=file_path,
            responsibility="API: contract, validation, and integration endpoints",
            risk=risk,
            required_tests=(
                "pytest veritas_os/tests/test_telos.py "
                "veritas_os/tests/test_chainlit_app_formatters.py"
            ),
        )

    if file_path.startswith("veritas_os/scripts/"):
        return ImpactRow(
            file_path=file_path,
            responsibility="Operations scripts: automation and maintenance tooling",
            risk="medium (operator workflow and CI helper behavior)",
            required_tests="pytest veritas_os/tests -k script",
        )

    if _contains_security_sensitive_parts(parts):
        return ImpactRow(
            file_path=file_path,
            responsibility="Security-related configuration or implementation",
            risk="high (security risk; manual review mandatory)",
            required_tests="Targeted tests + security-focused review",
        )

    return ImpactRow(
        file_path=file_path,
        responsibility="General repository change",
        risk="medium (scope unclear; run targeted regression)",
        required_tests="Run nearest module tests and smoke checks",
    )


def _render_markdown(rows: list[ImpactRow]) -> str:
    """Render impact rows as markdown text."""
    lines = [
        "## 変更影響範囲（自動要約）",
        "",
        "| 変更ファイル | 責務 | 想定リスク | 必要テスト |",
        "|---|---|---|---|",
    ]

    for row in rows:
        lines.append(
            f"| `{row.file_path}` | {row.responsibility} | "
            f"{row.risk} | `{row.required_tests}` |"
        )

    if not rows:
        lines.append("| _変更なし_ | - | - | - |")

    security_rows = [r for r in rows if "security" in r.risk.lower()]
    if security_rows:
        lines.extend(
            [
                "",
                "### セキュリティ警告",
                "- セキュリティ関連の変更が含まれています。",
                "- 認証・入力検証・機密情報の取り扱いを重点的にレビューしてください。",
            ]
        )

    return "\n".join(lines)


def generate_summary(base_ref: str, head_ref: str) -> str:
    """Generate markdown summary for changed files between refs."""
    changed_files = _run_git_diff_name_only(base_ref=base_ref, head_ref=head_ref)
    rows = [infer_impact(file_path) for file_path in changed_files]
    return _render_markdown(rows)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PR作成時の変更影響範囲を自動要約します。"
            "（変更ファイル→責務→想定リスク→必要テスト）"
        )
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="diff base ref (default: origin/main)",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="diff head ref (default: HEAD)",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    print(generate_summary(base_ref=args.base_ref, head_ref=args.head_ref))


if __name__ == "__main__":
    main()
