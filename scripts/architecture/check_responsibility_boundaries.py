"""Static checker for Planner / Kernel / Fuji / MemoryOS import boundaries.

This script enforces directional dependency constraints between core modules.
It is intended for CI use and returns non-zero when violations are detected.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BoundaryRule:
    """A dependency rule for one source module against forbidden imports."""

    source_module: str
    forbidden_imports: frozenset[str]


@dataclass(frozen=True)
class ViolationDetail:
    """Structured details for a single responsibility-boundary violation."""

    source_module: str
    forbidden_module: str
    path: Path


@dataclass(frozen=True)
class BoundaryIssue:
    """Machine-readable issue produced by the boundary checker."""

    code: str
    message: str
    path: Path
    source_module: str
    forbidden_module: str | None = None


@dataclass(frozen=True)
class DocAlignmentIssue:
    """Structured mismatch between the checker config and architecture docs."""

    source_module: str
    message: str
    path: Path | None = None


@dataclass(frozen=True)
class DocExtractionError:
    """Structured error raised while reading extension points from docs."""

    message: str


DEFAULT_DOC_PATH = Path("docs/architecture/core_responsibility_boundaries.md")


DEFAULT_RULES: tuple[BoundaryRule, ...] = (
    BoundaryRule(
        source_module="planner",
        forbidden_imports=frozenset({"kernel", "fuji"}),
    ),
    BoundaryRule(
        source_module="fuji",
        forbidden_imports=frozenset({"kernel", "planner"}),
    ),
    BoundaryRule(
        source_module="memory",
        forbidden_imports=frozenset({"kernel", "planner", "fuji"}),
    ),
)


ALLOWED_DEPENDENCY_GUIDE: dict[str, tuple[str, ...]] = {
    "planner": (
        "veritas_os.core.memory",
        "veritas_os.core.world",
        "veritas_os.core.strategy",
    ),
    "kernel": (
        "veritas_os.core.planner",
        "veritas_os.core.fuji",
        "veritas_os.core.memory",
    ),
    "fuji": (
        "veritas_os.core.fuji_policy",
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji_safety_head",
    ),
    "memory": (
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_security",
    ),
}


RECOMMENDED_EXTENSION_POINTS: dict[str, tuple[str, ...]] = {
    "planner": (
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    ),
    "kernel": (
        "veritas_os.core.kernel_stages",
        "veritas_os.core.kernel_qa",
        "veritas_os.core.pipeline_contracts",
    ),
    "fuji": (
        "veritas_os.core.fuji_policy",
        "veritas_os.core.fuji_policy_rollout",
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji_safety_head",
    ),
    "memory": (
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_search_helpers",
        "veritas_os.core.memory_summary_helpers",
        "veritas_os.core.memory_lifecycle",
        "veritas_os.core.memory_security",
    ),
}


REMEDIATION_LINK = "docs/architecture/core_responsibility_boundaries.md"
DOC_SECTION_TO_MODULE: dict[str, str] = {
    "Planner": "planner",
    "Kernel": "kernel",
    "FUJI": "fuji",
    "MemoryOS": "memory",
}
MODULE_DOCSTRING_REQUIRED_MARKERS: tuple[str, ...] = (
    "Public contract:",
    "Preferred extension points:",
    "Compatibility guidance:",
)
DOCSTRING_GUARD_MODULES: tuple[str, ...] = (
    "pipeline",
    "kernel",
    "fuji",
    "memory",
)
MODULE_DOCSTRING_EXTENSION_POINTS: dict[str, tuple[str, ...]] = {
    "pipeline": (
        "veritas_os.core.pipeline_inputs",
        "veritas_os.core.pipeline_execute",
        "veritas_os.core.pipeline_policy",
        "veritas_os.core.pipeline_response",
        "veritas_os.core.pipeline_persist",
        "veritas_os.core.pipeline_replay",
    ),
    "kernel": RECOMMENDED_EXTENSION_POINTS["kernel"],
    "fuji": RECOMMENDED_EXTENSION_POINTS["fuji"],
    "memory": RECOMMENDED_EXTENSION_POINTS["memory"],
}


def _normalize_module_name(module_name: str) -> str:
    """Normalize import paths to the core module leaf name."""
    return module_name.rsplit(".", maxsplit=1)[-1]


def _collect_imported_names(tree: ast.Module) -> set[str]:
    """Collect imported module names from a module AST."""
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(_normalize_module_name(alias.name))
        elif isinstance(node, ast.ImportFrom):
            # Include imported symbols to detect patterns like:
            #   from veritas_os.core import kernel
            # This is a forbidden dependency equivalent to
            #   import veritas_os.core.kernel
            for alias in node.names:
                imported.add(_normalize_module_name(alias.name))
            if node.module:
                imported.add(_normalize_module_name(node.module))
            else:
                for alias in node.names:
                    imported.add(_normalize_module_name(alias.name))
    return imported


def _check_rule(core_dir: Path, rule: BoundaryRule) -> list[str]:
    """Check one rule and return violation messages, one per forbidden import found."""
    path = _resolve_module_source_path(core_dir, rule.source_module)
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"Boundary check error: '{rule.source_module}' not found at {path}"]
    tree = ast.parse(source, filename=str(path))
    imported = _collect_imported_names(tree)
    violations = sorted(imported & rule.forbidden_imports)

    return [
        f"Boundary violation: '{rule.source_module}' imports forbidden module '{v}' ({path})"
        for v in violations
    ]


def _parse_imported_names(path: Path) -> set[str]:
    """Parse a module and return imported names from its AST."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return _collect_imported_names(tree)


def _resolve_module_source_path(core_dir: Path, module_name: str) -> Path:
    """Resolve module source path, supporting both module.py and package __init__.py."""
    module_file = core_dir / f"{module_name}.py"
    if module_file.exists():
        return module_file

    package_init = core_dir / module_name / "__init__.py"
    if package_init.exists():
        return package_init

    return module_file


def _load_module_docstring(path: Path) -> str:
    """Return the module docstring for a Python source file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return ast.get_docstring(tree, clean=False) or ""


def collect_module_docstring_issues(
    core_dir: Path,
    modules: Iterable[str] = DOCSTRING_GUARD_MODULES,
) -> list[DocAlignmentIssue]:
    """Validate core module docstrings keep boundary guidance visible."""
    issues: list[DocAlignmentIssue] = []
    for module_name in modules:
        path = _resolve_module_source_path(core_dir, module_name)
        try:
            docstring = _load_module_docstring(path)
        except FileNotFoundError:
            continue

        missing_markers = [
            marker for marker in MODULE_DOCSTRING_REQUIRED_MARKERS
            if marker not in docstring
        ]
        if missing_markers:
            issues.append(
                DocAlignmentIssue(
                    source_module=module_name,
                    message=(
                        f"Module docstring guidance missing for '{module_name}': "
                        f"{missing_markers}"
                    ),
                    path=path,
                )
            )

        recommended_points = MODULE_DOCSTRING_EXTENSION_POINTS.get(module_name, ())
        missing_points = [
            point for point in recommended_points
            if f"``{point.rsplit('.', maxsplit=1)[-1]}.py``" not in docstring
            and f"``{point.rsplit('.', maxsplit=1)[-1]}``" not in docstring
            and point not in docstring
        ]
        if missing_points:
            issues.append(
                DocAlignmentIssue(
                    source_module=module_name,
                    message=(
                        "Module docstring extension points out of sync for "
                        f"'{module_name}': missing={missing_points}"
                    ),
                    path=path,
                )
            )

    return issues


def collect_boundary_issues(
    core_dir: Path,
    rules: Iterable[BoundaryRule] = DEFAULT_RULES,
    doc_path: Path = DEFAULT_DOC_PATH,
) -> list[BoundaryIssue]:
    """Collect machine-classifiable boundary checker issues."""
    issues: list[BoundaryIssue] = []
    for issue in collect_doc_alignment_issues(doc_path):
        issues.append(
            BoundaryIssue(
                code="doc_alignment_error",
                message=issue.message,
                path=issue.path or doc_path,
                source_module=issue.source_module,
            )
        )
    for issue in collect_module_docstring_issues(core_dir):
        issues.append(
            BoundaryIssue(
                code="doc_alignment_error",
                message=issue.message,
                path=issue.path or _resolve_module_source_path(core_dir, issue.source_module),
                source_module=issue.source_module,
            )
        )
    for rule in rules:
        path = _resolve_module_source_path(core_dir, rule.source_module)
        try:
            imported = _parse_imported_names(path)
        except FileNotFoundError:
            issues.append(
                BoundaryIssue(
                    code="input_invalid",
                    message=f"Boundary check error: '{rule.source_module}' not found at {path}",
                    path=path,
                    source_module=rule.source_module,
                )
            )
            continue
        except PermissionError:
            issues.append(
                BoundaryIssue(
                    code="permission_denied",
                    message=f"Boundary check error: permission denied for {path}",
                    path=path,
                    source_module=rule.source_module,
                )
            )
            continue
        except SyntaxError as exc:
            issues.append(
                BoundaryIssue(
                    code="input_invalid",
                    message=(
                        "Boundary check error: invalid Python syntax in "
                        f"{path} at line {exc.lineno}"
                    ),
                    path=path,
                    source_module=rule.source_module,
                )
            )
            continue

        violations = sorted(imported & rule.forbidden_imports)
        for forbidden_module in violations:
            issues.append(
                BoundaryIssue(
                    code="boundary_violation",
                    message=(
                        "Boundary violation: "
                        f"'{rule.source_module}' imports forbidden module "
                        f"'{forbidden_module}' ({path})"
                    ),
                    path=path,
                    source_module=rule.source_module,
                    forbidden_module=forbidden_module,
                )
            )
    return issues


def _collect_violations(
    core_dir: Path,
    rules: Iterable[BoundaryRule] = DEFAULT_RULES,
) -> list[ViolationDetail]:
    """Collect structured violation details for remediation guidance output."""
    violation_details: list[ViolationDetail] = []
    for rule in rules:
        path = _resolve_module_source_path(core_dir, rule.source_module)
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        tree = ast.parse(source, filename=str(path))
        imported = _collect_imported_names(tree)
        violations = sorted(imported & rule.forbidden_imports)
        for forbidden_module in violations:
            violation_details.append(
                ViolationDetail(
                    source_module=rule.source_module,
                    forbidden_module=forbidden_module,
                    path=path,
                )
            )
    return violation_details


def build_remediation_guide(
    violations: Iterable[ViolationDetail],
    remediation_link: str = REMEDIATION_LINK,
) -> str:
    """Build a CI-friendly remediation guide for boundary violations."""
    rows: list[str] = []
    for violation in violations:
        alternatives = ", ".join(
            ALLOWED_DEPENDENCY_GUIDE.get(violation.source_module, ("N/A",))
        )
        extension_points = ", ".join(
            RECOMMENDED_EXTENSION_POINTS.get(violation.source_module, ("N/A",))
        )
        rows.append(
            " | ".join(
                (
                    f"{violation.source_module} -> {violation.forbidden_module}",
                    alternatives,
                    extension_points,
                    remediation_link,
                )
            )
        )

    if not rows:
        return ""

    header = (
        "\n=== Responsibility Boundary Remediation Guide ===\n"
        "禁止依存 | 代替実装先（許可依存） | 正規拡張ポイント | 修正例リンク\n"
    )
    return header + "\n".join(rows)


def check_boundaries(
    core_dir: Path,
    rules: Iterable[BoundaryRule] = DEFAULT_RULES,
    doc_path: Path = DEFAULT_DOC_PATH,
) -> list[str]:
    """Run all boundary rules and return all violation messages."""
    return [
        issue.message
        for issue in collect_boundary_issues(
            core_dir=core_dir,
            rules=rules,
            doc_path=doc_path,
        )
    ]


def build_machine_report(issues: Iterable[BoundaryIssue]) -> str:
    """Build JSON report for CI log parsing and alert classification."""
    issue_list = list(issues)
    counts: dict[str, int] = {
        "boundary_violation": 0,
        "input_invalid": 0,
        "permission_denied": 0,
        "doc_alignment_error": 0,
    }
    for issue in issue_list:
        if issue.code in counts:
            counts[issue.code] += 1
        else:
            counts[issue.code] = counts.get(issue.code, 0) + 1

    payload = {
        "status": "failed" if issue_list else "passed",
        "summary": counts,
        "issues": [
            {
                "code": issue.code,
                "source_module": issue.source_module,
                "forbidden_module": issue.forbidden_module,
                "path": str(issue.path),
                "message": issue.message,
                "allowed_dependencies": list(
                    ALLOWED_DEPENDENCY_GUIDE.get(issue.source_module, ())
                ),
                "recommended_extension_points": list(
                    RECOMMENDED_EXTENSION_POINTS.get(issue.source_module, ())
                ),
                "remediation_link": REMEDIATION_LINK,
            }
            for issue in issue_list
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_doc_extension_points(doc_path: Path) -> dict[str, tuple[str, ...]]:
    """Extract preferred extension points from the architecture document."""
    document = doc_path.read_text(encoding="utf-8")
    extracted, _ = _extract_doc_extension_points_from_text(document)
    return extracted


def _extract_doc_extension_points_from_text(
    document: str,
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Extract doc extension points and duplicate module sections from text."""
    section_pattern = re.compile(
        r"### (?P<section>[^\r\n]+?) \(`veritas_os\.core\.[^`]+`\)\r?\n"
        r"(?P<body>.*?)(?=\r?\n### |\Z)",
        re.DOTALL,
    )
    marker = "**Preferred extension points**:"
    extracted: dict[str, tuple[str, ...]] = {}
    duplicate_sections: list[str] = []

    for match in section_pattern.finditer(document):
        section_name = match.group("section").strip()
        module_name = DOC_SECTION_TO_MODULE.get(section_name)
        if module_name is None:
            continue

        body = match.group("body")
        _, marker_found, remainder = body.partition(marker)
        if not marker_found:
            continue

        bullet_lines: list[str] = []
        bullet_collection_started = False
        bullet_pattern = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)(?P<item>.+)$")
        for line in remainder.splitlines():
            stripped_line = line.strip()
            if not stripped_line:
                if bullet_collection_started:
                    break
                continue
            bullet_match = bullet_pattern.match(stripped_line)
            if bullet_match is not None:
                bullet_collection_started = True
                bullet_lines.append(bullet_match.group("item").strip().strip("`"))
                continue
            if bullet_collection_started:
                break
        if module_name in extracted:
            duplicate_sections.append(module_name)
            continue
        extracted[module_name] = tuple(bullet_lines)

    return extracted, tuple(duplicate_sections)


def _normalize_extension_points_for_alignment(
    extension_points: tuple[str, ...],
) -> tuple[str, ...]:
    """Normalize extension-point lists for order-insensitive doc alignment."""
    return tuple(sorted(extension_points))


def collect_doc_alignment_issues(doc_path: Path) -> list[DocAlignmentIssue]:
    """Return structured mismatches between docs and checker guidance."""
    try:
        document = doc_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        extraction_error = DocExtractionError(
            message=(
                "Unable to read architecture boundary document: "
                f"file not found at {doc_path}"
            )
        )
        documented_points = {}
        duplicate_sections: tuple[str, ...] = ()
    except PermissionError:
        extraction_error = DocExtractionError(
            message=(
                "Unable to read architecture boundary document: "
                f"permission denied for {doc_path}"
            )
        )
        documented_points = {}
        duplicate_sections = ()
    except UnicodeDecodeError:
        extraction_error = DocExtractionError(
            message=(
                "Unable to read architecture boundary document: "
                f"invalid UTF-8 at {doc_path}"
            )
        )
        documented_points = {}
        duplicate_sections = ()
    except OSError as exc:
        extraction_error = DocExtractionError(
            message=(
                "Unable to read architecture boundary document: "
                f"os error for {doc_path}: {exc.strerror or str(exc)}"
            )
        )
        documented_points = {}
        duplicate_sections = ()
    else:
        documented_points, duplicate_sections = _extract_doc_extension_points_from_text(
            document
        )
        extraction_error = None

    mismatches: list[DocAlignmentIssue] = []
    if extraction_error is not None:
        mismatches.append(
            DocAlignmentIssue(
                source_module="documentation",
                message=extraction_error.message,
            )
        )
        return mismatches

    for module_name in duplicate_sections:
        mismatches.append(
            DocAlignmentIssue(
                source_module=module_name,
                message=(
                    "Duplicate preferred extension point section found for "
                    f"'{module_name}' in {doc_path}"
                ),
            )
        )

    for module_name, configured_points in RECOMMENDED_EXTENSION_POINTS.items():
        expected_points = documented_points.get(module_name)
        if expected_points is None:
            mismatches.append(
                DocAlignmentIssue(
                    source_module=module_name,
                    message=(
                        "Missing preferred extension point section for "
                        f"'{module_name}' in {doc_path}"
                    ),
                )
            )
            continue
        if _normalize_extension_points_for_alignment(
            expected_points
        ) != _normalize_extension_points_for_alignment(configured_points):
            mismatches.append(
                DocAlignmentIssue(
                    source_module=module_name,
                    message=(
                        "Preferred extension points out of sync for "
                        f"'{module_name}': doc={list(expected_points)} "
                        f"checker={list(configured_points)}"
                    ),
                )
            )

    return mismatches


def find_doc_alignment_issues(doc_path: Path) -> list[str]:
    """Return human-readable mismatches between docs and checker guidance."""
    return [issue.message for issue in collect_doc_alignment_issues(doc_path)]


def _build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--core-dir",
        type=Path,
        default=Path("veritas_os/core"),
        help="Path to the core module directory (default: veritas_os/core).",
    )
    parser.add_argument(
        "--doc-path",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help=(
            "Path to the architecture document used for extension-point "
            "alignment checks "
            "(default: docs/architecture/core_responsibility_boundaries.md)."
        ),
    )
    parser.add_argument(
        "--report-format",
        choices=("text", "json"),
        default="text",
        help="Output format for CI logs (default: text).",
    )
    return parser


def main() -> int:
    """CLI entrypoint for CI execution."""
    parser = _build_parser()
    args = parser.parse_args()
    structured_issues = collect_boundary_issues(
        core_dir=args.core_dir,
        doc_path=args.doc_path,
    )
    issues = [issue.message for issue in structured_issues]

    if issues:
        violations = _collect_violations(core_dir=args.core_dir)
        if args.report_format == "json":
            print(build_machine_report(structured_issues))
        else:
            for issue in issues:
                print(issue)
            remediation_guide = build_remediation_guide(violations)
            if remediation_guide:
                print(remediation_guide)
        return 1

    if args.report_format == "json":
        print(build_machine_report(structured_issues))
    else:
        print("Responsibility boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
