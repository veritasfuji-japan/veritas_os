#!/usr/bin/env python3
"""Generate deterministic reviewer failure reason catalog artifacts.

This local/offline helper derives JSON and Markdown reviewer documentation from
``scripts.demo.reviewer_failure_reasons``. It does not change emitted failure
reason strings, reviewer packet schemas, runtime admissibility, or governance
behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.reviewer_failure_reasons import (  # noqa: E402
    REVIEWER_FAILURE_REASON_CATEGORIES,
    REVIEWER_FAILURE_REASON_METADATA,
    REVIEWER_FAILURE_REASON_SEVERITIES,
    REVIEWER_FAILURE_REASONS,
)

CATALOG_VERSION = "reviewer-failure-reason-catalog-v1"
GENERATED_AT = "2026-01-01T00:00:00Z"
CATALOG_DIR = (
    REPO_ROOT
    / "docs/en/demo/examples/reviewer-failure-reason-catalog-v1"
)
JSON_OUTPUT_PATH = (
    CATALOG_DIR / "reviewer-failure-reason-catalog.generated.example.json"
)
MARKDOWN_OUTPUT_PATH = (
    CATALOG_DIR / "reviewer-failure-reason-catalog.generated.example.md"
)


def build_catalog() -> dict[str, Any]:
    """Build the deterministic catalog payload from metadata source data."""
    reasons = [
        asdict(REVIEWER_FAILURE_REASON_METADATA[reason])
        for reason in sorted(REVIEWER_FAILURE_REASONS)
    ]
    return {
        "catalog_version": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "total_reasons": len(REVIEWER_FAILURE_REASONS),
        "categories": sorted(REVIEWER_FAILURE_REASON_CATEGORIES),
        "severities": sorted(REVIEWER_FAILURE_REASON_SEVERITIES),
        "reasons": reasons,
    }


def render_json(catalog: dict[str, Any]) -> str:
    """Render catalog JSON with stable key ordering and trailing newline."""
    return json.dumps(
        catalog,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _markdown_escape(value: str) -> str:
    """Escape Markdown table separators in generated cell content."""
    return value.replace("|", "\\|")


def render_markdown(catalog: dict[str, Any]) -> str:
    """Render compact reviewer-facing Markdown from a catalog payload."""
    lines = [
        "# Reviewer Failure Reason Catalog v1",
        "",
        "Generated deterministic local/offline reviewer documentation.",
        "",
        f"- catalog_version: `{catalog['catalog_version']}`",
        f"- generated_at: `{catalog['generated_at']}`",
        f"- total_reasons: `{catalog['total_reasons']}`",
        "",
        "| reason | category | severity | reviewer label | affected artifacts |",
        "|---|---|---|---|---|",
    ]
    for entry in catalog["reasons"]:
        artifacts = ", ".join(entry["affected_artifacts"])
        lines.append(
            "| "
            + " | ".join(
                _markdown_escape(str(value))
                for value in (
                    entry["reason"],
                    entry["category"],
                    entry["severity"],
                    entry["reviewer_label"],
                    artifacts,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Explanations and remediation hints are available in the generated JSON catalog.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_catalog() -> None:
    """Write generated catalog artifacts to the repository docs tree."""
    catalog = build_catalog()
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(render_json(catalog), encoding="utf-8")
    MARKDOWN_OUTPUT_PATH.write_text(render_markdown(catalog), encoding="utf-8")


def check_catalog() -> int:
    """Return zero when checked-in generated artifacts are current."""
    catalog = build_catalog()
    expected = {
        JSON_OUTPUT_PATH: render_json(catalog),
        MARKDOWN_OUTPUT_PATH: render_markdown(catalog),
    }
    stale = [
        path
        for path, content in expected.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != content
    ]
    if stale:
        for path in stale:
            print(f"stale generated artifact: {path.relative_to(REPO_ROOT)}")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate reviewer failure reason catalog artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated artifacts are current without writing files",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    if args.check:
        return check_catalog()
    write_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
