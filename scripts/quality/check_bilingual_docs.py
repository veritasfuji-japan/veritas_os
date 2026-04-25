"""Bilingual documentation drift checks for Japanese-first public surface."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
README_EN = REPO_ROOT / "README.md"
README_JA = REPO_ROOT / "README_JP.md"
DOCS_JA_README = REPO_ROOT / "docs/ja/README.md"
DOCS_INDEX = REPO_ROOT / "docs/INDEX.md"
DOCS_MAP = REPO_ROOT / "docs/DOCUMENTATION_MAP.md"
DOCS_BILINGUAL_RULES = REPO_ROOT / "docs/BILINGUAL_RULES.md"

ENDPOINTS = (
    "PUT /v1/governance/policy",
    "POST /v1/governance/policy-bundles/promote",
    "PUT /v1/compliance/config",
    "POST /v1/system/halt",
    "POST /v1/system/resume",
)

EN_JA_PAIRS = {
    "docs/en/guides/poc-pack-financial-quickstart.md": "docs/ja/guides/poc-pack-financial-quickstart.md",
    "docs/en/guides/financial-governance-templates.md": "docs/ja/guides/financial-governance-templates.md",
    "docs/en/validation/external-audit-readiness.md": "docs/ja/validation/external-audit-readiness.md",
    "docs/en/validation/technical-proof-pack.md": "docs/ja/validation/technical-proof-pack.md",
    "docs/en/validation/third-party-review-readiness.md": "docs/ja/validation/third-party-review-readiness.md",
    "docs/en/validation/backend-parity-coverage.md": "docs/ja/validation/backend-parity-coverage.md",
    "docs/en/validation/production-validation.md": "docs/ja/validation/production-validation.md",
    "docs/en/validation/postgresql-production-proof-map.md": "docs/ja/validation/postgresql-production-proof-map.md",
    "docs/en/operations/postgresql-production-guide.md": "docs/ja/operations/postgresql-production-guide.md",
    "docs/en/operations/postgresql-drill-runbook.md": "docs/ja/operations/postgresql-drill-runbook.md",
    "docs/en/operations/security-hardening.md": "docs/ja/operations/security-hardening.md",
    "docs/en/operations/database-migrations.md": "docs/ja/operations/database-migrations.md",
    "docs/en/operations/governance-artifact-signing.md": "docs/ja/operations/governance-artifact-signing.md",
    "docs/en/architecture/decision-semantics.md": "docs/ja/architecture/decision-semantics.md",
    "docs/en/architecture/bind-boundary-governance-artifacts.md": "docs/ja/architecture/bind-boundary-governance-artifacts.md",
    "docs/en/architecture/bind_time_admissibility_evaluator.md": "docs/ja/architecture/bind_time_admissibility_evaluator.md",
    "docs/en/governance/required-evidence-taxonomy.md": "docs/ja/governance/required-evidence-taxonomy.md",
    "docs/en/governance/governance-artifact-lifecycle.md": "docs/ja/governance/governance-artifact-lifecycle.md",
    "docs/en/guides/governance-policy-bundle-promotion.md": "docs/ja/guides/governance-policy-bundle-promotion.md",
    "docs/en/positioning/aml-kyc-beachhead-short-positioning.md": "docs/ja/positioning/aml-kyc-beachhead-short-positioning.md",
}

MARKDOWN_FORMAT_GUARD_TARGETS = (
    README_JA,
    DOCS_JA_README,
    DOCS_INDEX,
    DOCS_MAP,
    DOCS_BILINGUAL_RULES,
)
MARKDOWN_LINE_HARD_LIMIT = 1000
MARKDOWN_MIN_LINES = 5
MARKDOWN_MIN_CHARS_FOR_SHORT_FILE = 2000
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


def extract_bind_governed_block(markdown: str) -> str | None:
    """Extract a bounded README_JP block for bind-governed effect paths."""
    lines = markdown.splitlines()
    section_start: int | None = None
    heading_pattern = re.compile(r"^#{2,6}\s+")
    marker_pattern = re.compile(
        r"(bind-boundary adjudication|bind-governed|effect path|bind policy surface)",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        if marker_pattern.search(line):
            section_start = index
            break
    if section_start is None:
        return None

    section_end = len(lines)
    for index in range(section_start + 1, len(lines)):
        if heading_pattern.match(lines[index]):
            section_end = index
            break
    return "\n".join(lines[section_start:section_end])


def local_links(markdown: str) -> list[str]:
    """Extract markdown links that should resolve inside the repository."""
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown)
    results: list[str] = []
    for raw in links:
        candidate = raw.split("#", maxsplit=1)[0].strip()
        if not candidate or candidate.startswith(("http://", "https://", "mailto:", "#")):
            continue
        results.append(candidate)
    return results


def check_readme_bind_sync(errors: list[str]) -> None:
    """Check README_JP bind-governed section carries all required endpoints."""
    en_text = README_EN.read_text(encoding="utf-8")
    ja_text = README_JA.read_text(encoding="utf-8")
    bind_block = extract_bind_governed_block(ja_text)
    if bind_block is None:
        errors.append(
            "README_JP.md missing bind-governed effect path section "
            "(marker: bind-boundary adjudication / bind-governed / effect path)"
        )
        return

    for endpoint in ENDPOINTS:
        if endpoint not in en_text:
            errors.append(f"README.md missing required endpoint marker: {endpoint}")
        if endpoint not in bind_block:
            errors.append(
                "README_JP.md bind-governed section missing endpoint: "
                f"{endpoint} (must appear in bind policy surface block)"
            )


def check_readme_japanese_first(errors: list[str]) -> None:
    """Check README_JP avoids direct EN links when JA counterpart exists."""
    ja_text = README_JA.read_text(encoding="utf-8")
    for en_path, ja_path in EN_JA_PAIRS.items():
        ja_exists = (REPO_ROOT / ja_path).exists()
        if ja_exists and en_path in ja_text:
            errors.append(
                f"README_JP.md uses EN link despite JA page existing: {en_path} -> {ja_path}"
            )


def check_links_exist(markdown_path: Path, errors: list[str]) -> None:
    """Check all local links in a markdown file resolve."""
    text = markdown_path.read_text(encoding="utf-8")
    for link in local_links(text):
        resolved = (markdown_path.parent / link).resolve()
        if not resolved.exists():
            errors.append(
                f"{markdown_path.relative_to(REPO_ROOT)} broken link: {link} -> "
                f"{resolved.relative_to(REPO_ROOT) if resolved.is_relative_to(REPO_ROOT) else resolved}"
            )


def check_map_paths(errors: list[str]) -> None:
    """Check all repo-local code spans in DOCUMENTATION_MAP.md exist."""
    text = DOCS_MAP.read_text(encoding="utf-8")
    for raw in re.findall(r"`([^`]+)`", text):
        if raw in {"—", "-"} or raw.startswith("http"):
            continue
        if "/" not in raw:
            continue
        path = REPO_ROOT / raw
        if not path.exists():
            errors.append(f"docs/DOCUMENTATION_MAP.md stale path: {raw}")


def _is_fence_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and "|" in stripped[1:]


def _extract_urls(line: str) -> list[str]:
    """Extract HTTP(S) URLs from a markdown line."""
    return URL_PATTERN.findall(line)


def _is_shields_badge_url(url: str) -> bool:
    """Return True when the URL host is exactly img.shields.io."""
    parsed = urlparse(url)
    return parsed.hostname == "img.shields.io"


def _is_external_url_only_line(line: str) -> bool:
    """Return True when a markdown line is effectively just one URL."""
    stripped = line.strip().lstrip("-*").strip()
    if not stripped or " " in stripped:
        return False
    urls = _extract_urls(stripped)
    if len(urls) != 1:
        return False
    return stripped == urls[0]


def _is_long_url_or_generated_badge(line: str) -> bool:
    """Return True when a long line should be exempted from readability checks."""
    if _is_external_url_only_line(line):
        return True
    urls = _extract_urls(line)
    if any(_is_shields_badge_url(url) for url in urls):
        return True
    return False


def _check_markdown_line_lengths(markdown_path: Path, errors: list[str]) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < MARKDOWN_MIN_LINES and len(text) > MARKDOWN_MIN_CHARS_FOR_SHORT_FILE:
        errors.append(
            f"{markdown_path.relative_to(REPO_ROOT)} has {len(lines)} lines and "
            f"{len(text)} characters. Reformat Markdown into readable line breaks."
        )

    in_fenced_block = False
    for idx, raw_line in enumerate(lines, start=1):
        if _is_fence_line(raw_line):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue

        if _is_table_line(raw_line):
            continue
        if _is_long_url_or_generated_badge(raw_line):
            continue

        line_length = len(raw_line)
        if line_length > MARKDOWN_LINE_HARD_LIMIT:
            errors.append(
                f"{markdown_path.relative_to(REPO_ROOT)}: line {idx} is {line_length} "
                "characters. Reformat Markdown into readable line breaks."
            )


def check_markdown_readability(errors: list[str]) -> None:
    """Guard against markdown files compressed into unreadable long lines."""
    targets = {path.resolve() for path in MARKDOWN_FORMAT_GUARD_TARGETS}
    targets.update(path.resolve() for path in (REPO_ROOT / "docs/ja").rglob("*.md"))
    for markdown_path in sorted(targets):
        if markdown_path.exists():
            _check_markdown_line_lengths(markdown_path, errors)


def run() -> list[str]:
    """Run all checks and return actionable errors."""
    errors: list[str] = []
    check_readme_bind_sync(errors)
    check_readme_japanese_first(errors)
    check_links_exist(DOCS_JA_README, errors)
    check_links_exist(DOCS_INDEX, errors)
    check_map_paths(errors)
    check_markdown_readability(errors)
    return errors


def main() -> int:
    """CLI entrypoint."""
    errors = run()
    if errors:
        print("[check-bilingual-docs] failed")
        for error in errors:
            print(f" - {error}")
        return 1
    print("[check-bilingual-docs] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
