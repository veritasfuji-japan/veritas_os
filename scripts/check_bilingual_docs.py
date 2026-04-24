#!/usr/bin/env python3
"""Lightweight bilingual documentation drift checks for VERITAS OS."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HIGH_PRIORITY_EN_TO_JA = {
    "docs/en/guides/poc-pack-financial-quickstart.md": (
        "docs/ja/guides/aml-kyc-poc-quickstart.md"
    ),
    "docs/en/guides/financial-governance-templates.md": (
        "docs/ja/guides/financial-governance-templates.md"
    ),
    "docs/en/validation/external-audit-readiness.md": (
        "docs/ja/validation/external-audit-readiness.md"
    ),
    "docs/en/validation/technical-proof-pack.md": (
        "docs/ja/validation/technical-proof-pack.md"
    ),
    "docs/en/validation/third-party-review-readiness.md": (
        "docs/ja/validation/third-party-review-readiness.md"
    ),
    "docs/en/validation/backend-parity-coverage.md": (
        "docs/ja/validation/backend-parity-coverage.md"
    ),
    "docs/en/validation/production-validation.md": (
        "docs/ja/validation/production-validation.md"
    ),
    "docs/en/operations/postgresql-production-guide.md": (
        "docs/ja/operations/postgresql-production-guide.md"
    ),
    "docs/en/operations/postgresql-drill-runbook.md": (
        "docs/ja/operations/postgresql-drill-runbook.md"
    ),
    "docs/en/operations/security-hardening.md": (
        "docs/ja/operations/security-hardening.md"
    ),
    "docs/en/operations/database-migrations.md": (
        "docs/ja/operations/database-migrations.md"
    ),
    "docs/en/operations/governance-artifact-signing.md": (
        "docs/ja/operations/governance-artifact-signing.md"
    ),
    "docs/en/architecture/decision-semantics.md": (
        "docs/ja/architecture/decision-semantics.md"
    ),
    "docs/en/architecture/bind-boundary-governance-artifacts.md": (
        "docs/ja/architecture/bind-boundary-governance-artifacts.md"
    ),
    "docs/en/architecture/bind_time_admissibility_evaluator.md": (
        "docs/ja/architecture/bind_time_admissibility_evaluator.md"
    ),
    "docs/en/positioning/aml-kyc-beachhead-short-positioning.md": (
        "docs/ja/positioning/aml-kyc-beachhead-short-positioning.md"
    ),
}

BIND_ENDPOINT_PATTERN = re.compile(
    r"`(PUT /v1/governance/policy|"
    r"POST /v1/governance/policy-bundles/promote|"
    r"PUT /v1/compliance/config|"
    r"POST /v1/system/halt|"
    r"POST /v1/system/resume)`"
)
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CODE_LINK_PATTERN = re.compile(r"`([^`]*\.[^`\s]+)`")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def path_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def extract_links(markdown: str) -> list[str]:
    return [match.group(1) for match in LINK_PATTERN.finditer(markdown)]


def check_readme_jp_links(issues: list[str]) -> None:
    readme_jp = read("README_JP.md")
    for en_path, ja_path in HIGH_PRIORITY_EN_TO_JA.items():
        if not path_exists(ja_path):
            issues.append(f"Missing mapped JA page: {ja_path}")
            continue
        if en_path in readme_jp:
            issues.append(
                "README_JP.md links to EN high-priority page "
                f"despite JA counterpart existing: {en_path} -> {ja_path}"
            )


def extract_bind_endpoints(markdown: str) -> list[str]:
    seen = []
    for match in BIND_ENDPOINT_PATTERN.finditer(markdown):
        endpoint = match.group(1)
        if endpoint not in seen:
            seen.append(endpoint)
    return seen


def check_bind_endpoint_sync(issues: list[str]) -> None:
    readme_en = read("README.md")
    readme_ja = read("README_JP.md")
    en_endpoints = extract_bind_endpoints(readme_en)
    ja_endpoints = extract_bind_endpoints(readme_ja)

    if en_endpoints != ja_endpoints:
        issues.append(
            "README.md and README_JP.md bind-governed endpoint lists differ: "
            f"EN={en_endpoints}, JA={ja_endpoints}"
        )


def check_markdown_links(file_path: str, issues: list[str]) -> None:
    content = read(file_path)
    links = extract_links(content)
    for raw_link in links:
        if raw_link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = raw_link.split("#", maxsplit=1)[0]
        if not target:
            continue
        resolved = (ROOT / Path(file_path).parent / target).resolve()
        if not resolved.exists():
            issues.append(f"Broken link in {file_path}: {raw_link}")


def check_documentation_map_paths(issues: list[str]) -> None:
    content = read("docs/DOCUMENTATION_MAP.md")
    code_paths = CODE_LINK_PATTERN.findall(content)
    for code_path in code_paths:
        if not code_path.startswith(("README", "docs/")):
            continue
        if code_path == "—":
            continue
        if not path_exists(code_path):
            issues.append(f"Missing path referenced by docs/DOCUMENTATION_MAP.md: {code_path}")


def main() -> int:
    issues: list[str] = []
    check_readme_jp_links(issues)
    check_bind_endpoint_sync(issues)
    check_markdown_links("docs/ja/README.md", issues)
    check_markdown_links("docs/INDEX.md", issues)
    check_documentation_map_paths(issues)

    if issues:
        print("[check-bilingual-docs] FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("[check-bilingual-docs] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
