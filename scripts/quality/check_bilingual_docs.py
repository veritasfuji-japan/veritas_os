"""Bilingual documentation quality checks for Japanese-first governance docs."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README_JA = REPO_ROOT / "README_JP.md"
DOCS_JA_README = REPO_ROOT / "docs/ja/README.md"
DOCS_INDEX = REPO_ROOT / "docs/INDEX.md"
DOCS_MAP = REPO_ROOT / "docs/DOCUMENTATION_MAP.md"
DOCS_BILINGUAL_RULES = REPO_ROOT / "docs/BILINGUAL_RULES.md"

REQUIRED_BIND_ENDPOINTS = (
    "PUT /v1/governance/policy",
    "POST /v1/governance/policy-bundles/promote",
    "PUT /v1/compliance/config",
    "POST /v1/system/halt",
    "POST /v1/system/resume",
)

BIND_SECTION_ANCHORS = (
    "bind-boundary adjudication",
    "bind-governed",
    "effect path",
    "bind policy surface",
    "運用者管理 effect path",
)

EN_CANONICAL_LABELS = (
    "英語正本",
    "English canonical",
    "EN canonical",
)

EN_TO_JA_PRIORITY_MAP = {
    "docs/en/architecture/decision-semantics.md": (
        "docs/ja/architecture/decision-semantics.md"
    ),
    "docs/en/architecture/bind-boundary-governance-artifacts.md": (
        "docs/ja/architecture/bind-boundary-governance-artifacts.md"
    ),
    "docs/en/architecture/bind_time_admissibility_evaluator.md": (
        "docs/ja/architecture/bind_time_admissibility_evaluator.md"
    ),
    "docs/en/validation/external-audit-readiness.md": (
        "docs/ja/validation/external-audit-readiness.md"
    ),
    "docs/en/validation/technical-proof-pack.md": (
        "docs/ja/validation/technical-proof-pack.md"
    ),
    "docs/en/validation/backend-parity-coverage.md": (
        "docs/ja/validation/backend-parity-coverage.md"
    ),
    "docs/en/validation/production-validation.md": (
        "docs/ja/validation/production-validation.md"
    ),
    "docs/en/validation/third-party-review-readiness.md": (
        "docs/ja/validation/third-party-review-readiness.md"
    ),
    "docs/en/operations/postgresql-production-guide.md": (
        "docs/ja/operations/postgresql-production-guide.md"
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
    "docs/en/operations/postgresql-drill-runbook.md": (
        "docs/ja/operations/postgresql-drill-runbook.md"
    ),
    "docs/en/governance/required-evidence-taxonomy.md": (
        "docs/ja/governance/required-evidence-taxonomy.md"
    ),
    "docs/en/governance/governance-artifact-lifecycle.md": (
        "docs/ja/governance/governance-artifact-lifecycle.md"
    ),
    "docs/en/guides/poc-pack-financial-quickstart.md": (
        "docs/ja/guides/poc-pack-financial-quickstart.md"
    ),
    "docs/en/guides/financial-governance-templates.md": (
        "docs/ja/guides/financial-governance-templates.md"
    ),
    "docs/en/guides/governance-policy-bundle-promotion.md": (
        "docs/ja/guides/governance-policy-bundle-promotion.md"
    ),
    "docs/en/positioning/aml-kyc-beachhead-short-positioning.md": (
        "docs/ja/positioning/aml-kyc-beachhead-short-positioning.md"
    ),
}

LOCAL_LINK_CHECK_TARGETS = (
    DOCS_JA_README,
    DOCS_INDEX,
    DOCS_MAP,
)

COMPRESSION_GUARD_TARGETS = (
    README_JA,
    DOCS_JA_README,
    DOCS_INDEX,
    DOCS_MAP,
    DOCS_BILINGUAL_RULES,
)

MARKDOWN_LINE_HARD_LIMIT = 10_000
MARKDOWN_SHORT_FILE_MAX_LINES = 2
MARKDOWN_SHORT_FILE_MIN_CHARS = 10_001

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

REQUIRED_REGULATED_ACTION_TERMS_EN = (
    "Regulated Action Governance Kernel",
    "Action Class Contract",
    "Authority Evidence",
    "Runtime Authority Validation",
    "Admissibility Predicate",
    "Irreversible Commit Boundary",
)

REQUIRED_REGULATED_ACTION_TERMS_JA = (
    "Regulated Action Governance Kernel",
    "Action Class Contract",
    "Authority Evidence",
    "Runtime Authority Validation",
    "Admissibility Predicate",
    "Irreversible Commit Boundary",
    "commit / block / escalate / refuse",
    "AML/KYC customer risk escalation fixture",
)

REQUIRED_DISCLAIMER_TERMS_EN = (
    "not legal advice",
    "not regulatory approval",
    "not third-party certification",
)

REQUIRED_DISCLAIMER_TERMS_JA = (
    "法的助言ではありません",
    "規制当局の承認",
    "第三者認証",
)

REQUIRED_REGULATED_ACTION_LINKS = (
    "docs/en/architecture/regulated-action-governance-kernel.md",
    "docs/en/architecture/authority-evidence-vs-audit-log.md",
    "docs/en/use-cases/aml-kyc-regulated-action-path.md",
    "docs/en/validation/regulated-action-governance-proof-pack.md",
    "docs/en/validation/regulated-action-governance-quality-gate.md",
)

REQUIRED_EXTERNAL_REVIEW_HANDOFF_DOCS = (
    "docs/en/validation/external-review-handoff-regulated-action-governance.md",
    "docs/ja/validation/external-review-handoff-regulated-action-governance-summary.md",
)

FORBIDDEN_OVERCLAIM_PATTERNS = (
    "implements OTANIS",
    "implements ISDAIRE",
    "implements ARETABA",
    "regulatory approval",
    "third-party certification",
    "legal compliance guaranteed",
)
CODE_PATH_PATTERN = re.compile(
    r"(?<![\w.-])(?:README(?:_JP)?\.md|docs/(?:en|ja)/[^\s`\)\]\(]+\.md)"
)


def _extract_bind_section(markdown: str) -> str | None:
    """Return a bounded section around bind-governed/effect-path markers."""
    lines = markdown.splitlines()
    heading_pattern = re.compile(r"^#{1,6}\s+")
    anchor_pattern = re.compile(
        "|".join(re.escape(anchor) for anchor in BIND_SECTION_ANCHORS),
        re.IGNORECASE,
    )

    section_start: int | None = None
    section_end: int | None = None

    for index, line in enumerate(lines):
        if anchor_pattern.search(line):
            section_start = index
            for back in range(index, -1, -1):
                if heading_pattern.match(lines[back]):
                    section_start = back
                    break
            break

    if section_start is None:
        return None

    for index in range(section_start + 1, len(lines)):
        if heading_pattern.match(lines[index]):
            section_end = index
            break

    if section_end is None:
        section_end = len(lines)

    return "\n".join(lines[section_start:section_end])


def _iter_markdown_links(markdown: str) -> list[tuple[str, str]]:
    """Return a list of (label, target) markdown links."""
    return [
        (label.strip(), target.strip())
        for label, target in LINK_PATTERN.findall(markdown)
    ]


def _is_allowed_english_canonical_link(label: str) -> bool:
    return any(marker in label for marker in EN_CANONICAL_LABELS)


def _normalize_local_target(raw_target: str) -> str:
    return raw_target.split("#", maxsplit=1)[0].strip()


def _is_ignored_link(target: str) -> bool:
    lowered = target.lower()
    return (
        not target
        or lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or target.startswith("#")
    )


def _resolve_local_link(source_file: Path, target: str) -> Path:
    if target.startswith("docs/"):
        return (REPO_ROOT / target).resolve()
    return (source_file.parent / target).resolve()


def _is_fence_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def check_readme_bind_governed_section(errors: list[str]) -> None:
    """Validate required endpoints inside README_JP bind-governed section."""
    markdown = README_JA.read_text(encoding="utf-8")
    section = _extract_bind_section(markdown)

    if section is None:
        errors.append(
            "README_JP.md: bind-governed/effect-path section was not found. "
            "Add one of these anchors: bind-boundary adjudication, "
            "bind-governed, effect path, bind policy surface, "
            "運用者管理 effect path."
        )
        return

    for endpoint in REQUIRED_BIND_ENDPOINTS:
        if endpoint not in section:
            errors.append(
                f"README_JP.md: bind-governed section is missing {endpoint}."
            )


def check_readme_japanese_first_links(errors: list[str]) -> None:
    """Validate README_JP uses Japanese-first links for high-priority docs."""
    markdown = README_JA.read_text(encoding="utf-8")
    links = _iter_markdown_links(markdown)

    for label, raw_target in links:
        target = _normalize_local_target(raw_target)
        if target not in EN_TO_JA_PRIORITY_MAP:
            continue

        ja_target = EN_TO_JA_PRIORITY_MAP[target]
        if not (REPO_ROOT / ja_target).exists():
            continue

        if _is_allowed_english_canonical_link(label):
            continue

        errors.append(
            "README_JP.md: links to "
            f"{target} even though {ja_target} exists. "
            "Use Japanese-first link or label the English link as 英語正本."
        )




def _missing_terms(markdown: str, terms: tuple[str, ...]) -> list[str]:
    lowered = markdown.lower()
    return [term for term in terms if term.lower() not in lowered]


def check_readme_regulated_action_and_disclaimer(errors: list[str]) -> None:
    """Validate core regulated-action framing and disclaimer presence in README pair."""
    readme_en = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_ja = README_JA.read_text(encoding="utf-8")

    missing_en = _missing_terms(readme_en, REQUIRED_REGULATED_ACTION_TERMS_EN)
    if missing_en:
        errors.append(
            "README.md: missing regulated-action terms: " + ", ".join(missing_en)
        )

    missing_ja = _missing_terms(readme_ja, REQUIRED_REGULATED_ACTION_TERMS_JA)
    if missing_ja:
        errors.append(
            "README_JP.md: missing regulated-action terms: " + ", ".join(missing_ja)
        )

    if "Audit Log" not in readme_ja or "Authority Evidence" not in readme_ja:
        errors.append(
            "README_JP.md: Authority Evidence vs Audit Log distinction is missing."
        )

    missing_disclaimer_en = _missing_terms(readme_en, REQUIRED_DISCLAIMER_TERMS_EN)
    if missing_disclaimer_en:
        errors.append(
            "README.md: missing disclaimer terms: "
            + ", ".join(missing_disclaimer_en)
        )

    missing_disclaimer_ja = _missing_terms(readme_ja, REQUIRED_DISCLAIMER_TERMS_JA)
    if missing_disclaimer_ja:
        errors.append(
            "README_JP.md: missing disclaimer terms: "
            + ", ".join(missing_disclaimer_ja)
        )

    for path in REQUIRED_REGULATED_ACTION_LINKS:
        if path not in readme_en:
            errors.append(f"README.md: missing link {path}.")
        if path not in readme_ja:
            errors.append(f"README_JP.md: missing link {path}.")


def check_external_review_handoff_docs_exist(errors: list[str]) -> None:
    """Ensure regulated-action external review handoff docs are present."""
    for raw_path in REQUIRED_EXTERNAL_REVIEW_HANDOFF_DOCS:
        path = REPO_ROOT / raw_path
        if not path.exists():
            errors.append(
                f"missing required external review handoff doc: {raw_path}"
            )


def check_forbidden_framework_overclaims(errors: list[str]) -> None:
    """Reject external-framework implementation/certification overclaims in READMEs."""
    readme_en = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_ja = README_JA.read_text(encoding="utf-8")

    for marker in FORBIDDEN_OVERCLAIM_PATTERNS:
        lower = marker.lower()
        if lower in readme_en.lower() and "not " + lower not in readme_en.lower():
            errors.append(f"README.md: potential overclaim phrase detected: {marker}")

    forbidden_ja_terms = ("OTANIS", "ISDAIRE", "ARETABA", "法令適合を保証")
    for marker in forbidden_ja_terms:
        if marker.lower() in readme_ja.lower() and "ではありません" not in readme_ja:
            errors.append(
                f"README_JP.md: potential overclaim phrase detected: {marker}"
            )


def check_local_markdown_links(errors: list[str]) -> None:
    """Validate local markdown links in designated documentation files."""
    for source_file in LOCAL_LINK_CHECK_TARGETS:
        markdown = source_file.read_text(encoding="utf-8")
        for _, raw_target in _iter_markdown_links(markdown):
            target = _normalize_local_target(raw_target)
            if _is_ignored_link(target):
                continue

            resolved = _resolve_local_link(source_file, target)
            if resolved.exists():
                continue

            source_rel = source_file.relative_to(REPO_ROOT)
            try:
                resolved_rel = resolved.relative_to(REPO_ROOT)
            except ValueError:
                resolved_rel = resolved

            errors.append(
                f"{source_rel}: local link target '{target}' is missing "
                f"(resolved path: {resolved_rel})."
            )


def check_documentation_map_paths(errors: list[str]) -> None:
    """Validate repo-local file paths referenced in docs/DOCUMENTATION_MAP.md."""
    markdown = DOCS_MAP.read_text(encoding="utf-8")
    for raw_path in sorted(set(CODE_PATH_PATTERN.findall(markdown))):
        resolved = REPO_ROOT / raw_path

        if not resolved.exists():
            errors.append(
                "docs/DOCUMENTATION_MAP.md: referenced path "
                f"'{raw_path}' does not exist at '{resolved}'."
            )


def _check_markdown_compression_guard(markdown_path: Path, errors: list[str]) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if (
        len(lines) <= MARKDOWN_SHORT_FILE_MAX_LINES
        and len(text) >= MARKDOWN_SHORT_FILE_MIN_CHARS
    ):
        errors.append(
            f"{markdown_path.relative_to(REPO_ROOT)}: file has {len(lines)} lines "
            f"with {len(text)} characters; likely compressed into one-line Markdown."
        )

    in_fenced_block = False
    for line_number, line in enumerate(lines, start=1):
        if _is_fence_line(line):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue

        if len(line) > MARKDOWN_LINE_HARD_LIMIT:
            errors.append(
                f"{markdown_path.relative_to(REPO_ROOT)}: line {line_number} exceeds "
                f"{MARKDOWN_LINE_HARD_LIMIT} characters outside a code block."
            )


def check_extreme_markdown_compression(errors: list[str]) -> None:
    """Guard against extremely compressed markdown files."""
    targets = {path.resolve() for path in COMPRESSION_GUARD_TARGETS}
    targets.update(path.resolve() for path in (REPO_ROOT / "docs/ja").rglob("*.md"))

    for markdown_path in sorted(targets):
        if markdown_path.exists():
            _check_markdown_compression_guard(markdown_path, errors)


def run() -> list[str]:
    """Run all bilingual documentation quality checks."""
    errors: list[str] = []
    check_readme_bind_governed_section(errors)
    check_readme_japanese_first_links(errors)
    check_local_markdown_links(errors)
    check_documentation_map_paths(errors)
    check_readme_regulated_action_and_disclaimer(errors)
    check_external_review_handoff_docs_exist(errors)
    check_forbidden_framework_overclaims(errors)
    check_extreme_markdown_compression(errors)
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
