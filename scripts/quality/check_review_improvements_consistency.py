#!/usr/bin/env python3
"""Validate the cross-domain review backlog stays consolidated and up-to-date.

This guard addresses the operational gap where improvement notes existed but lacked
an always-current, repository-local integrated view. The checker enforces a minimal
contract in `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` so API/frontend/security
workstreams remain visible in one place.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REVIEW_PATH = REPO_ROOT / "REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md"

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


def main() -> int:
    """Run the review backlog consolidation consistency check."""
    if not REVIEW_PATH.exists():
        print(f"[DOCS] Missing file: {REVIEW_PATH}")
        return 1

    content = REVIEW_PATH.read_text(encoding="utf-8")
    missing_tokens = collect_missing_tokens(content)

    if not missing_tokens:
        print("Review improvements consistency checks passed.")
        return 0

    print("[DOCS] Consolidated review backlog markers are incomplete:")
    for token in missing_tokens:
        print(f"- {REVIEW_PATH.relative_to(REPO_ROOT)}: missing token: {token}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
