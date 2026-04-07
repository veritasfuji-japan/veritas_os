#!/usr/bin/env python3
"""Validate the cross-domain review backlog stays consolidated and up-to-date.

This guard addresses the operational gap where improvement notes existed but lacked
an always-current, repository-local integrated view. The checker enforces a minimal
contract in the canonical review backlog document so API/frontend/security
workstreams remain visible in one place.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CANONICAL_REVIEW_PATH = (
    REPO_ROOT / "docs" / "ja" / "reviews" / "review_current_improvements_2026_03_30_ja.md"
)
LEGACY_REVIEW_PATH = REPO_ROOT / "REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md"

REQUIRED_TOKENS = (
    "対象: API / Frontend / 運用設定 / セキュリティ境界。",
    "## 優先度付きテーマ（次アクション）",
    "## セキュリティ警告（必読）",
    "### 2026-03-30 追加追記（改善バックログの統合ビュー運用を追加）",
    "- **統合ビュー更新手順（単一正本）**",
    "- **進捗ステータス（2026-03-30 時点）**",
    "- **週次更新ルール（運用固定）**",
)


def collect_missing_tokens(content: str) -> list[str]:
    """Return required markers missing from the review document."""
    return [token for token in REQUIRED_TOKENS if token not in content]


def resolve_review_path() -> pathlib.Path:
    """Return canonical review path, with legacy fallback for compatibility."""
    if CANONICAL_REVIEW_PATH.exists():
        return CANONICAL_REVIEW_PATH
    return LEGACY_REVIEW_PATH


def main() -> int:
    """Run the review backlog consolidation consistency check."""
    review_path = resolve_review_path()
    if not review_path.exists():
        print(f"[DOCS] Missing file: {CANONICAL_REVIEW_PATH}")
        print(f"[DOCS] Legacy fallback not found either: {LEGACY_REVIEW_PATH}")
        return 1

    content = review_path.read_text(encoding="utf-8")
    missing_tokens = collect_missing_tokens(content)

    if not missing_tokens:
        print("Review improvements consistency checks passed.")
        return 0

    print("[DOCS] Consolidated review backlog markers are incomplete:")
    for token in missing_tokens:
        print(f"- {review_path.relative_to(REPO_ROOT)}: missing token: {token}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
