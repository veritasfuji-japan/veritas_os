"""Tests for static responsibility boundary checker script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.architecture.check_responsibility_boundaries import (
    REMEDIATION_LINK,
    BoundaryIssue,
    BoundaryRule,
    DocAlignmentIssue,
    ViolationDetail,
    build_machine_report,
    build_remediation_guide,
    check_boundaries,
    collect_boundary_issues,
    collect_doc_alignment_issues,
    extract_doc_extension_points,
    find_doc_alignment_issues,
)


def _write_module(path: Path, source: str) -> None:
    """Write UTF-8 source code to a module path."""
    path.write_text(source, encoding="utf-8")


def test_check_boundaries_reports_forbidden_import(tmp_path: Path) -> None:
    """Checker should report violations when forbidden imports exist."""
    _write_module(tmp_path / "planner.py", "import veritas_os.core.kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert len(issues) == 1
    assert "planner" in issues[0]
    assert "kernel" in issues[0]


def test_check_boundaries_accepts_valid_dependency_directions(tmp_path: Path) -> None:
    """Checker should pass when no forbidden cross-module imports are present."""
    _write_module(tmp_path / "planner.py", "from veritas_os.core.memory import summarize_for_planner\n")
    _write_module(tmp_path / "kernel.py", "from veritas_os.core.planner import plan_for_veritas_agi\n")
    _write_module(tmp_path / "fuji.py", "from veritas_os.core.fuji_codes import FujiAction\n")
    _write_module(tmp_path / "memory.py", "import json\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert issues == []


def test_check_boundaries_supports_custom_rules(tmp_path: Path) -> None:
    """Checker should evaluate custom rules provided by callers."""
    _write_module(tmp_path / "kernel.py", "from veritas_os.core.memory import add\n")
    _write_module(tmp_path / "planner.py", "# planner module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(
        core_dir=tmp_path,
        rules=(
            BoundaryRule(
                source_module="kernel",
                forbidden_imports=frozenset({"memory"}),
            ),
        ),
    )

    assert len(issues) == 1
    assert "kernel" in issues[0]
    assert "memory" in issues[0]


def test_check_boundaries_detects_from_core_import_pattern(tmp_path: Path) -> None:
    """Checker should catch `from veritas_os.core import <forbidden>` imports."""
    _write_module(tmp_path / "planner.py", "from veritas_os.core import kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert len(issues) == 1
    assert "planner" in issues[0]
    assert "kernel" in issues[0]


def test_build_remediation_guide_contains_required_columns(tmp_path: Path) -> None:
    """Remediation guide should include forbidden dependency, alternatives, and link."""
    violations = [
        ViolationDetail(
            source_module="planner",
            forbidden_module="kernel",
            path=tmp_path / "planner.py",
        ),
    ]

    guide = build_remediation_guide(violations)

    assert "禁止依存" in guide
    assert "代替実装先（許可依存）" in guide
    assert "正規拡張ポイント" in guide
    assert "planner -> kernel" in guide
    assert "veritas_os.core.memory" in guide
    assert "veritas_os.core.planner_normalization" in guide
    assert REMEDIATION_LINK in guide


def test_build_remediation_guide_returns_empty_for_no_violations() -> None:
    """No remediation guide should be emitted when violations are absent."""
    guide = build_remediation_guide([])

    assert guide == ""


def test_collect_boundary_issues_classifies_missing_module(tmp_path: Path) -> None:
    """Missing source modules should be classified as input_invalid."""
    _write_module(tmp_path / "planner.py", "# planner module\n")

    issues = collect_boundary_issues(core_dir=tmp_path)

    assert any(issue.code == "input_invalid" for issue in issues)


def test_collect_boundary_issues_classifies_boundary_violation(tmp_path: Path) -> None:
    """Forbidden import should be classified as boundary_violation."""
    _write_module(tmp_path / "planner.py", "import veritas_os.core.kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = collect_boundary_issues(core_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].code == "boundary_violation"
    assert issues[0].source_module == "planner"
    assert issues[0].forbidden_module == "kernel"


def test_collect_doc_alignment_issues_preserves_module_context(tmp_path: Path) -> None:
    """Structured doc drift issues should keep the affected module name."""
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
- veritas_os.core.planner_json

### Kernel (`veritas_os.core.kernel`)
**Preferred extension points**:
- veritas_os.core.kernel_stages

### FUJI (`veritas_os.core.fuji`)
**Preferred extension points**:
- veritas_os.core.fuji_policy

### MemoryOS (`veritas_os.core.memory`)
**Preferred extension points**:
- veritas_os.core.memory_store
""".strip(),
        encoding="utf-8",
    )

    issues = collect_doc_alignment_issues(doc_path)

    assert issues
    assert issues[0].source_module == "planner"
    assert "planner" in issues[0].message


def test_build_machine_report_keeps_module_context_for_doc_alignment_error(
    tmp_path: Path,
) -> None:
    """Machine report should expose doc drift under the affected module."""
    issues = [
        BoundaryIssue(
            code="doc_alignment_error",
            message="Preferred extension points out of sync for 'memory'",
            path=tmp_path / "core_responsibility_boundaries.md",
            source_module="memory",
        ),
    ]

    report = json.loads(build_machine_report(issues))

    assert report["issues"][0]["source_module"] == "memory"
    assert report["issues"][0]["recommended_extension_points"] == [
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_search_helpers",
        "veritas_os.core.memory_summary_helpers",
        "veritas_os.core.memory_lifecycle",
        "veritas_os.core.memory_security",
    ]


def test_collect_boundary_issues_detects_doc_alignment_error(tmp_path: Path) -> None:
    """Doc/checker drift should surface as a machine-readable issue."""
    _write_module(tmp_path / "planner.py", "# planner module\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
- veritas_os.core.planner_json

### Kernel (`veritas_os.core.kernel`)
**Preferred extension points**:
- veritas_os.core.kernel_stages

### FUJI (`veritas_os.core.fuji`)
**Preferred extension points**:
- veritas_os.core.fuji_policy

### MemoryOS (`veritas_os.core.memory`)
**Preferred extension points**:
- veritas_os.core.memory_store
""".strip(),
        encoding="utf-8",
    )

    issues = collect_boundary_issues(core_dir=tmp_path, doc_path=doc_path)

    assert any(issue.code == "doc_alignment_error" for issue in issues)


def test_collect_doc_alignment_issues_classifies_missing_doc_file(
    tmp_path: Path,
) -> None:
    """Missing architecture docs should surface as structured doc errors."""
    doc_path = tmp_path / "missing_boundaries.md"

    issues = collect_doc_alignment_issues(doc_path)

    assert issues == [
        DocAlignmentIssue(
            message=(
                "Unable to read architecture boundary document: "
                f"file not found at {doc_path}"
            ),
            source_module="documentation",
        )
    ]


def test_build_machine_report_counts_by_code(tmp_path: Path) -> None:
    """Machine report should summarize issue counts for CI parsers."""
    issues = [
        BoundaryIssue(
            code="boundary_violation",
            message="violation",
            path=tmp_path / "planner.py",
            source_module="planner",
            forbidden_module="kernel",
        ),
        BoundaryIssue(
            code="permission_denied",
            message="permission denied",
            path=tmp_path / "fuji.py",
            source_module="fuji",
        ),
    ]

    report = json.loads(build_machine_report(issues))

    assert report["status"] == "failed"
    assert report["summary"]["boundary_violation"] == 1
    assert report["summary"]["permission_denied"] == 1
    assert report["summary"]["input_invalid"] == 0
    assert report["summary"]["doc_alignment_error"] == 0
    assert report["issues"][0]["allowed_dependencies"] == [
        "veritas_os.core.memory",
        "veritas_os.core.world",
        "veritas_os.core.strategy",
    ]
    assert report["issues"][0]["recommended_extension_points"] == [
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    ]
    assert report["issues"][0]["remediation_link"] == REMEDIATION_LINK


def test_build_machine_report_includes_doc_aligned_extension_points(tmp_path: Path) -> None:
    """Machine report should keep extension-point guidance aligned with docs."""
    issues = [
        BoundaryIssue(
            code="boundary_violation",
            message="violation",
            path=tmp_path / "memory.py",
            source_module="memory",
            forbidden_module="planner",
        ),
        BoundaryIssue(
            code="boundary_violation",
            message="violation",
            path=tmp_path / "fuji.py",
            source_module="fuji",
            forbidden_module="kernel",
        ),
    ]

    report = json.loads(build_machine_report(issues))

    assert report["issues"][0]["recommended_extension_points"] == [
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_search_helpers",
        "veritas_os.core.memory_summary_helpers",
        "veritas_os.core.memory_lifecycle",
        "veritas_os.core.memory_security",
    ]
    assert report["issues"][1]["recommended_extension_points"] == [
        "veritas_os.core.fuji_policy",
        "veritas_os.core.fuji_policy_rollout",
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji_safety_head",
    ]


def test_extract_doc_extension_points_reads_architecture_doc() -> None:
    """Architecture doc parser should extract module-specific extension points."""
    points = extract_doc_extension_points(
        Path("docs/architecture/core_responsibility_boundaries.md")
    )

    assert points["planner"] == (
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    )
    assert points["kernel"] == (
        "veritas_os.core.kernel_stages",
        "veritas_os.core.kernel_qa",
        "veritas_os.core.pipeline_contracts",
    )
    assert points["fuji"] == (
        "veritas_os.core.fuji_policy",
        "veritas_os.core.fuji_policy_rollout",
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji_safety_head",
    )
    assert points["memory"] == (
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_search_helpers",
        "veritas_os.core.memory_summary_helpers",
        "veritas_os.core.memory_lifecycle",
        "veritas_os.core.memory_security",
    )


def test_extract_doc_extension_points_tolerates_blank_line_after_marker(
    tmp_path: Path,
) -> None:
    """Doc parser should ignore cosmetic blank lines before bullet lists."""
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:

- `veritas_os.core.planner_normalization`
- `veritas_os.core.planner_json`
- `veritas_os.core.strategy`

### Kernel (`veritas_os.core.kernel`)
**Preferred extension points**:

- `veritas_os.core.kernel_stages`
- `veritas_os.core.kernel_qa`
- `veritas_os.core.pipeline_contracts`

### FUJI (`veritas_os.core.fuji`)
**Preferred extension points**:

- `veritas_os.core.fuji_policy`
- `veritas_os.core.fuji_policy_rollout`
- `veritas_os.core.fuji_helpers`
- `veritas_os.core.fuji_safety_head`

### MemoryOS (`veritas_os.core.memory`)
**Preferred extension points**:

- `veritas_os.core.memory_store`
- `veritas_os.core.memory_helpers`
- `veritas_os.core.memory_search_helpers`
- `veritas_os.core.memory_summary_helpers`
- `veritas_os.core.memory_lifecycle`
- `veritas_os.core.memory_security`
""".strip(),
        encoding="utf-8",
    )

    points = extract_doc_extension_points(doc_path)

    assert points["planner"] == (
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    )
    assert points["kernel"] == (
        "veritas_os.core.kernel_stages",
        "veritas_os.core.kernel_qa",
        "veritas_os.core.pipeline_contracts",
    )
    assert points["fuji"] == (
        "veritas_os.core.fuji_policy",
        "veritas_os.core.fuji_policy_rollout",
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji_safety_head",
    )
    assert points["memory"] == (
        "veritas_os.core.memory_store",
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory_search_helpers",
        "veritas_os.core.memory_summary_helpers",
        "veritas_os.core.memory_lifecycle",
        "veritas_os.core.memory_security",
    )


def test_extract_doc_extension_points_tolerates_explanatory_text_before_bullets(
    tmp_path: Path,
) -> None:
    """Doc parser should ignore short prose before the preferred bullet list."""
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
These modules should absorb new planner shaping logic before planner.py.
- `veritas_os.core.planner_normalization`
- `veritas_os.core.planner_json`
- `veritas_os.core.strategy`
""".strip(),
        encoding="utf-8",
    )

    points = extract_doc_extension_points(doc_path)

    assert points["planner"] == (
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    )


def test_extract_doc_extension_points_accepts_asterisk_bullets(
    tmp_path: Path,
) -> None:
    """Doc parser should accept standard Markdown `*` bullets too."""
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
* `veritas_os.core.planner_normalization`
* `veritas_os.core.planner_json`
* `veritas_os.core.strategy`
""".strip(),
        encoding="utf-8",
    )

    points = extract_doc_extension_points(doc_path)

    assert points["planner"] == (
        "veritas_os.core.planner_normalization",
        "veritas_os.core.planner_json",
        "veritas_os.core.strategy",
    )


def test_find_doc_alignment_issues_returns_empty_for_current_doc() -> None:
    """Checker guidance should stay aligned with the architecture source of truth."""
    issues = find_doc_alignment_issues(
        Path("docs/architecture/core_responsibility_boundaries.md")
    )

    assert issues == []


def test_find_doc_alignment_issues_ignores_bullet_order_only(tmp_path: Path) -> None:
    """Pure bullet reordering should not count as doc/checker drift."""
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
- `veritas_os.core.strategy`
- `veritas_os.core.planner_json`
- `veritas_os.core.planner_normalization`

### Kernel (`veritas_os.core.kernel`)
**Preferred extension points**:
- `veritas_os.core.pipeline_contracts`
- `veritas_os.core.kernel_qa`
- `veritas_os.core.kernel_stages`

### FUJI (`veritas_os.core.fuji`)
**Preferred extension points**:
- `veritas_os.core.fuji_safety_head`
- `veritas_os.core.fuji_helpers`
- `veritas_os.core.fuji_policy_rollout`
- `veritas_os.core.fuji_policy`

### MemoryOS (`veritas_os.core.memory`)
**Preferred extension points**:
- `veritas_os.core.memory_security`
- `veritas_os.core.memory_lifecycle`
- `veritas_os.core.memory_summary_helpers`
- `veritas_os.core.memory_search_helpers`
- `veritas_os.core.memory_helpers`
- `veritas_os.core.memory_store`
""".strip(),
        encoding="utf-8",
    )

    issues = find_doc_alignment_issues(doc_path)

    assert issues == []


def test_check_boundaries_includes_doc_alignment_issues(tmp_path: Path) -> None:
    """Text-mode checker should fail when the architecture doc drifts."""
    _write_module(tmp_path / "planner.py", "# planner module\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")
    doc_path = tmp_path / "core_responsibility_boundaries.md"
    doc_path.write_text(
        """
# Core Responsibility Boundaries

### Planner (`veritas_os.core.planner`)
**Preferred extension points**:
- veritas_os.core.planner_json
""".strip(),
        encoding="utf-8",
    )

    issues = check_boundaries(core_dir=tmp_path, doc_path=doc_path)

    assert any("Preferred extension points out of sync" in issue for issue in issues)
