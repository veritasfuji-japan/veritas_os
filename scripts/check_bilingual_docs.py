"""Bilingual documentation consistency checks for public entrypoints.

This script validates Japanese-first navigation and EN/JA synchronization claims
for core repository documentation.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_EN = REPO_ROOT / "README.md"
README_JA = REPO_ROOT / "README_JP.md"
DOCS_JA_README = REPO_ROOT / "docs/ja/README.md"
DOCS_INDEX = REPO_ROOT / "docs/INDEX.md"
DOCS_MAP = REPO_ROOT / "docs/DOCUMENTATION_MAP.md"

HIGH_PRIORITY_EN_DOCS = (
    "docs/en/architecture/decision-semantics.md",
    "docs/en/architecture/bind-boundary-governance-artifacts.md",
    "docs/en/architecture/bind_time_admissibility_evaluator.md",
    "docs/en/validation/external-audit-readiness.md",
    "docs/en/validation/technical-proof-pack.md",
    "docs/en/validation/third-party-review-readiness.md",
    "docs/en/validation/backend-parity-coverage.md",
    "docs/en/validation/production-validation.md",
    "docs/en/operations/postgresql-production-guide.md",
    "docs/en/operations/postgresql-drill-runbook.md",
    "docs/en/operations/security-hardening.md",
    "docs/en/operations/database-migrations.md",
    "docs/en/operations/governance-artifact-signing.md",
    "docs/en/guides/financial-governance-templates.md",
    "docs/en/guides/governance-policy-bundle-promotion.md",
    "docs/en/positioning/aml-kyc-beachhead-short-positioning.md",
)

MUTATION_ENDPOINTS = (
    "PUT /v1/governance/policy",
    "POST /v1/governance/policy-bundles/promote",
    "PUT /v1/compliance/config",
    "POST /v1/system/halt",
    "POST /v1/system/resume",
)


def extract_local_links(markdown_text: str) -> list[str]:
    """Return local markdown links excluding anchors, URLs, and mailto targets."""
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown_text)
    results: list[str] = []
    for raw in links:
        target = raw.split("#", maxsplit=1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        results.append(target)
    return results


def assert_links_exist(doc_path: Path, errors: list[str]) -> None:
    """Append errors for local markdown links that do not resolve on disk."""
    text = doc_path.read_text(encoding="utf-8")
    for link in extract_local_links(text):
        resolved = (doc_path.parent / link).resolve()
        if not resolved.exists():
            rel = resolved.relative_to(REPO_ROOT) if resolved.is_relative_to(REPO_ROOT) else resolved
            errors.append(f"{doc_path.relative_to(REPO_ROOT)} has broken link: {link} -> {rel}")


def assert_readme_sync(errors: list[str]) -> None:
    """Ensure README.md and README_JP.md agree on version/status/endpoints."""
    en_text = README_EN.read_text(encoding="utf-8")
    ja_text = README_JA.read_text(encoding="utf-8")

    en_version = re.search(r"\*\*Version:\*\*\s*([^\n]+)", en_text)
    ja_version = re.search(r"\*\*Version\*\*:\s*([^\n]+)", ja_text)
    if not en_version or not ja_version or en_version.group(1).strip() != ja_version.group(1).strip():
        errors.append("README version mismatch between README.md and README_JP.md")

    if "**Release Status:** Beta" not in en_text:
        errors.append("README.md release status no longer matches expected Beta marker")
    if "**Release Status**: ベータ版" not in ja_text:
        errors.append("README_JP.md release status no longer matches expected ベータ版 marker")

    for endpoint in MUTATION_ENDPOINTS:
        if endpoint not in en_text:
            errors.append(f"README.md missing bind-governed endpoint: {endpoint}")
        if endpoint not in ja_text:
            errors.append(f"README_JP.md missing bind-governed endpoint: {endpoint}")


def assert_japanese_first_links(errors: list[str]) -> None:
    """Disallow direct README_JP links to high-priority EN docs when JA docs exist."""
    text = README_JA.read_text(encoding="utf-8")
    for en_path in HIGH_PRIORITY_EN_DOCS:
        ja_candidate = Path(str(en_path).replace("docs/en/", "docs/ja/").replace("bind_time_", "bind-time-"))
        if en_path in text and (REPO_ROOT / ja_candidate).exists():
            errors.append(
                "README_JP.md links to high-priority EN doc despite JA counterpart: "
                f"{en_path} -> {ja_candidate}"
            )


def assert_documentation_map_paths(errors: list[str]) -> None:
    """Validate that markdown code path references in DOCUMENTATION_MAP exist."""
    text = DOCS_MAP.read_text(encoding="utf-8")
    for raw in re.findall(r"`([^`]+)`", text):
        if raw in {"—", "(same file, bilingual)"} or "/" not in raw or raw.endswith("/"):
            continue
        path = REPO_ROOT / raw
        if not path.exists():
            errors.append(f"DOCUMENTATION_MAP missing path on disk: {raw}")


def run_checks() -> list[str]:
    """Run all bilingual checks and return validation error messages."""
    errors: list[str] = []
    assert_japanese_first_links(errors)
    assert_links_exist(DOCS_JA_README, errors)
    assert_links_exist(DOCS_INDEX, errors)
    assert_documentation_map_paths(errors)
    assert_readme_sync(errors)
    return errors


def main() -> int:
    """CLI entrypoint."""
    errors = run_checks()
    if errors:
        print("[bilingual-docs] check failed:")
        for item in errors:
            print(f" - {item}")
        return 1
    print("[bilingual-docs] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
