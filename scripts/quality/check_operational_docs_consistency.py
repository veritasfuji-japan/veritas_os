#!/usr/bin/env python3
"""Validate operational docs keep the P1 review clarifications intact.

The reassessment identified two high-priority operational risks:
1. secondary README files overstating production readiness; and
2. degraded health/status signals lacking fixed alert semantics.

This checker keeps the minimum doc contract in place so those regressions are
caught in CI before they become security or operations drift.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PRIMARY_README_PATH = REPO_ROOT / "README_JP.md"
README_PATH = REPO_ROOT / "veritas_os/README_JP.md"
RUNBOOK_PATH = REPO_ROOT / "docs/ja/operations/enterprise_slo_sli_runbook_ja.md"
LEGACY_RUNBOOK_PATH = REPO_ROOT / "docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md"
DOC_MAP_PATH = REPO_ROOT / "docs/notes/CODE_REVIEW_DOCUMENT_MAP.md"

PRIMARY_README_REQUIRED_TOKENS = (
    "**Release Status**: ベータ版",
    "**ベータ品質のガバナンス基盤**",
    "### 拡張時に重要な責務境界",
    "| **Planner** |",
    "| **Kernel** |",
    "| **FUJI** |",
    "| **MemoryOS** |",
)
README_REQUIRED_TOKENS = (
    "Beta%20Governance%20Platform",
    "**Document Scope**: バックエンド配下の補助リファレンス",
    "**正本 / 最新の運用判断**",
    "[`README_JP.md`](../README_JP.md)",
    "**セキュリティ注意**",
    "**記述スコープの注意**",
)
RUNBOOK_REQUIRED_TOKENS = (
    "### 4.3 degraded 判定のアラートポリシー（P1固定）",
    "runtime_features.sanitize=degraded",
    "runtime_features.atomic_io=degraded",
    "checks.auth_store=degraded",
    "checks.memory=degraded",
    "checks.trust_log=degraded",
    "status=degraded",
    "### 4.4 `/health` / `/status` の運用判定",
    "`ok=true` だけで正常判定してはいけない。",
)
DOC_MAP_REQUIRED_TOKENS = (
    "### README / Runbook の正本",
    "導入判断・責務境界・beta positioning の正本: `README_JP.md`",
    "degraded 状態の運用意味・アラート方針・復旧手順の正本",
    "`veritas_os/README_JP.md` は補助説明",
)


def collect_missing_tokens(content: str, required_tokens: tuple[str, ...]) -> list[str]:
    """Return required markers missing from a documentation file."""
    return [token for token in required_tokens if token not in content]


def collect_missing_any_tokens(content: str, token_groups: tuple[tuple[str, ...], ...]) -> list[str]:
    """Return missing markers where any token in each group is acceptable."""
    missing = []
    for group in token_groups:
        if not any(token in content for token in group):
            missing.append(" OR ".join(group))
    return missing


def _validate_file(path: pathlib.Path, required_tokens: tuple[str, ...]) -> list[str]:
    """Return missing-token errors for a required documentation file."""
    if not path.exists():
        return [f"Missing file: {path}"]
    content = path.read_text(encoding="utf-8")
    missing_tokens = collect_missing_tokens(content, required_tokens)
    return [
        f"{path.relative_to(REPO_ROOT)}: missing token: {token}"
        for token in missing_tokens
    ]


def main() -> int:
    """Validate the P1 operational documentation contract."""
    problems = []
    problems.extend(_validate_file(PRIMARY_README_PATH, PRIMARY_README_REQUIRED_TOKENS))
    problems.extend(_validate_file(README_PATH, README_REQUIRED_TOKENS))
    runbook_path = RUNBOOK_PATH if RUNBOOK_PATH.exists() else LEGACY_RUNBOOK_PATH
    problems.extend(_validate_file(runbook_path, RUNBOOK_REQUIRED_TOKENS))
    problems.extend(_validate_file(DOC_MAP_PATH, DOC_MAP_REQUIRED_TOKENS))

    primary_content = PRIMARY_README_PATH.read_text(encoding="utf-8") if PRIMARY_README_PATH.exists() else ""
    problems.extend(
        [
            f"{PRIMARY_README_PATH.relative_to(REPO_ROOT)}: missing token: {missing}"
            for missing in collect_missing_any_tokens(
                primary_content,
                (
                    (
                        "docs/ja/operations/enterprise_slo_sli_runbook_ja.md",
                        "docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md",
                    ),
                ),
            )
        ]
    )

    readme_content = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""
    problems.extend(
        [
            f"{README_PATH.relative_to(REPO_ROOT)}: missing token: {missing}"
            for missing in collect_missing_any_tokens(
                readme_content,
                (
                    (
                        "enterprise_slo_sli_runbook_ja.md",
                        "ENTERPRISE_SLO_SLI_RUNBOOK_JP.md",
                    ),
                ),
            )
        ]
    )

    if not problems:
        print("Operational documentation consistency checks passed.")
        return 0

    print("[DOCS] Operational documentation consistency is incomplete:")
    for problem in problems:
        print(f"- {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
